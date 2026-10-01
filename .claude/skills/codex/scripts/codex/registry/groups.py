"""Groups: `<runs_dir>/.groups/<name>.json`, the set of runs one `batch start` created, addressed afterwards as one thing.

The manifest is a file rather than a query over the registry: claiming it is the atomic claim on the name, it records start order (which `--resume-from` pairs against and which run ids cannot recover — same-second, same-label starts are the normal case), and reading a group does not walk the whole registry on every follower tick.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from codex.registry.locks import write_json_atomic
from codex.registry.runs import find_run, iter_runs, meta_unreadable
from codex.errors import Refusal
from codex.util import now_iso


NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def groups_dir(runs_dir: Path) -> Path:
    return runs_dir / ".groups"


def group_path(runs_dir: Path, name: str) -> Path:
    return groups_dir(runs_dir) / f"{name}.json"


def valid_group_name(name: str) -> bool:
    """A group name becomes a filename, so no separator and no leading dot."""
    return bool(NAME_RE.match(name or ""))


def group_manifest(runs_dir: Path, name: str):
    """The group's manifest — `group`, `created_at`, `epoch`, `derived_from`, `requested` and `members` in start order — or None when it is absent or will not parse."""
    try:
        return json.loads(group_path(runs_dir, name).read_text(encoding="utf-8"))
    except Exception:
        return None


def group_unreadable(runs_dir: Path, name: str) -> bool:
    """Present but will not parse, as distinct from absent. Membership survives it (each run records its group); start order does not."""
    return group_path(runs_dir, name).is_file() and group_manifest(runs_dir, name) is None


def list_groups(runs_dir: Path):
    d = groups_dir(runs_dir)
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def claim_group(runs_dir: Path, name: str, derived_from=None, requested=0) -> dict:
    """Take the name before anything spawns, refused while it is reserved. Returns the manifest.

    `os.link` publishes a manifest that is already complete, so no reader sees the name without its content. `requested` is written now because a batch killed partway would otherwise be indistinguishable from one that asked for fewer tasks. `epoch` identifies this claim, so a writer notices if the name was released and claimed again underneath it.
    """
    d = groups_dir(runs_dir)
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"group": name, "created_at": now_iso(), "epoch": uuid.uuid4().hex,
                "derived_from": derived_from, "requested": requested, "members": []}
    path = group_path(runs_dir, name)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.link(tmp, path)
    except FileExistsError:
        existing = group_manifest(runs_dir, name) or {}
        raise Refusal(f"group {name!r} already exists; `batch clean --group {name}` releases the name once nothing is left",
                      created_at=existing.get("created_at"), members=len(existing.get("members") or [])) from None
    finally:
        tmp.unlink(missing_ok=True)
    return manifest


def release_group(runs_dir: Path, name: str):
    """Give the name back; the runs themselves stay in the registry."""
    group_path(runs_dir, name).unlink(missing_ok=True)


def record_members(runs_dir: Path, name: str, members: list, epoch=None) -> dict:
    """Record the member list so far, after every member: a spawned member must be reachable through its group from the instant it exists."""
    manifest = group_manifest(runs_dir, name) or {"group": name, "created_at": now_iso(), "derived_from": None}
    if epoch is not None and manifest.get("epoch") != epoch:
        raise Refusal(f"group {name!r} was released and claimed again while this batch was starting; the members listed in `spawned` are still recorded as members of it",
                      spawned=[m.get("run_id") for m in members if m.get("run_id")])
    manifest["members"] = members
    write_json_atomic(group_path(runs_dir, name), manifest)
    return manifest


def member_run_ids(runs_dir: Path, name: str):
    """Run ids in start order, skipping slots that never spawned; `[]` for an unreadable manifest, None for an absent one."""
    g = group_manifest(runs_dir, name)
    if not g:
        return [] if group_unreadable(runs_dir, name) else None
    return [m["run_id"] for m in g.get("members", []) if m.get("run_id")]


def owned_run_ids(runs_dir: Path, name: str):
    """Every run that says it belongs to this group, manifest order first, then runs only the registry knows — the manifest lags a member that was killed between claiming its directory and being recorded."""
    ids = member_run_ids(runs_dir, name)
    if ids is None:
        return None
    seen = set(ids)
    return ids + [m["run_id"] for _rd, m in iter_runs(runs_dir)
                  if m.get("group") == name and m.get("run_id") and m["run_id"] not in seen]


def derived_groups(runs_dir: Path, name: str):
    """Groups whose `--resume-from` was this one; their members work in this group's worktrees."""
    return [g for g in list_groups(runs_dir) if (group_manifest(runs_dir, g) or {}).get("derived_from") == name]


def group_runs(runs_dir: Path, name: str):
    """Members as (run_dir, meta) in start order; refuses an unknown or unreadable group. Members that never became a readable run are `group_gaps`."""
    if group_unreadable(runs_dir, name):
        raise Refusal(f"group {name!r} has a manifest that will not parse; `members_recorded_by_runs` lists its runs, which `status --run` reads one by one",
                      manifest=str(group_path(runs_dir, name)),
                      members_recorded_by_runs=owned_run_ids(runs_dir, name))
    ids = member_run_ids(runs_dir, name)
    if ids is None:
        raise Refusal(f"no such group: {name}", runs_dir=str(runs_dir), known_groups=list_groups(runs_dir))
    out = []
    for rid in ids:
        rd, m = find_run(runs_dir, rid)
        if m:
            out.append((rd, m))
    return out


def group_gaps(runs_dir: Path, name: str):
    """Every member no group view can show as a run, so none answers as if fewer were asked for: slots that never started, then members whose run is gone or will not parse."""
    return _unstarted_members(runs_dir, name) + _vanished_members(runs_dir, name)


def _unstarted_members(runs_dir: Path, name: str):
    """Slots that never became runs, including tasks a killed `batch start` never reached, so no group view answers as if fewer were asked for."""
    g = group_manifest(runs_dir, name) or {}
    members = g.get("members", [])
    never = [{"index": m.get("index"), "label": m.get("label"), "kind": m.get("kind"), "error": m.get("error")}
             for m in members if not m.get("run_id")]
    for i in range(len(members), g.get("requested") or 0):
        never.append({"index": i, "label": None, "kind": None,
                      "error": "batch start recorded no run for this task"})
    return never


def _vanished_members(runs_dir: Path, name: str):
    """Members the manifest names that no longer resolve — a directory removed by hand, or one whose meta.json will not parse, which still holds its work."""
    gone = []
    for m in (group_manifest(runs_dir, name) or {}).get("members", []):
        rid = m.get("run_id")
        if not rid:
            continue
        rd, meta = find_run(runs_dir, rid)
        if meta:
            continue
        present = rd is not None and meta_unreadable(rd)
        gone.append({"index": m.get("index"), "label": m.get("label"), "run_id": rid,
                     "error": ("its meta.json will not parse; the run directory "
                               "is still there and may still hold results"
                               if present else "its run directory is no longer in the registry")})
    return gone
