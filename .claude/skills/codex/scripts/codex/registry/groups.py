"""Groups: `<runs_dir>/.groups/<name>.json`, the set of runs one `batch` created, addressed afterwards as one thing.

The manifest is a file rather than a query over the registry: claiming it is the atomic claim on the name, it records start order (which run ids cannot recover — same-second, same-label starts are the normal case), and reading a group does not walk the whole registry on every look a wait takes.
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
    """The group's manifest — `group`, `created_at`, `epoch`, `requested` and `members` in start order (one written before 0.11 also holds a `derived_from` nothing reads) — or None when it is absent or will not parse."""
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


def claim_group(runs_dir: Path, name: str, requested=0) -> dict:
    """Take the name before anything spawns, refused while it is reserved. Returns the manifest.

    `os.link` publishes a manifest that is already complete, so no reader sees the name without its content. `requested` is written now because a batch killed partway would otherwise be indistinguishable from one that asked for fewer tasks. `epoch` identifies this claim, so a writer notices if the name was released and claimed again underneath it.
    """
    try:
        return _claim(runs_dir, name, requested)
    except FileExistsError:
        existing = group_manifest(runs_dir, name) or {}
        raise Refusal(f"group {name!r} already exists; `clean --group {name}` releases the name once nothing is left",
                      created_at=existing.get("created_at"), members=len(existing.get("members") or [])) from None


def _claim(runs_dir: Path, name: str, requested) -> dict:
    d = groups_dir(runs_dir)
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"group": name, "created_at": now_iso(), "epoch": uuid.uuid4().hex, "requested": requested, "members": []}
    path = group_path(runs_dir, name)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return manifest


def release_group(runs_dir: Path, name: str):
    """Give the name back; the runs themselves stay in the registry."""
    group_path(runs_dir, name).unlink(missing_ok=True)


def record_members(runs_dir: Path, name: str, members: list, epoch=None) -> dict:
    """Record the member list so far, after every member: a spawned member must be reachable through its group from the instant it exists."""
    manifest = group_manifest(runs_dir, name) or {"group": name, "created_at": now_iso()}
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


def group_view(runs_dir: Path, name: str):
    """`(members, gaps, epoch)` from one read of the manifest, so no slot is in both and neither lags the other. `members` are `(run_dir, meta)` in start order; `gaps` are every slot no view can show as a run — slots that never started, tasks a killed `batch` never reached included, then members whose run is gone or will not parse, which still holds its work; `epoch` identifies this claim of the name, so a reader that looks again can tell the same group from a new one that took the name. Refuses an unknown or unreadable group."""
    g = group_manifest(runs_dir, name)
    if g is None:
        if group_unreadable(runs_dir, name):
            raise Refusal(f"group {name!r} has a manifest that will not parse; `members_recorded_by_runs` lists its runs, which `status --run` reads one by one",
                          manifest=str(group_path(runs_dir, name)),
                          members_recorded_by_runs=owned_run_ids(runs_dir, name))
        raise Refusal(f"no such group: {name}", runs_dir=str(runs_dir), known_groups=list_groups(runs_dir))
    slots = g.get("members", [])
    members, never, gone = [], [], []
    for m in slots:
        rid = m.get("run_id")
        if not rid:
            never.append({"index": m.get("index"), "label": m.get("label"), "kind": m.get("kind"), "error": m.get("error")})
            continue
        rd, meta = find_run(runs_dir, rid)
        if meta:
            members.append((rd, meta))
            continue
        present = rd is not None and meta_unreadable(rd)
        gone.append({"index": m.get("index"), "label": m.get("label"), "run_id": rid,
                     "error": ("its meta.json will not parse; the run directory "
                               "is still there and may still hold results"
                               if present else "its run directory is no longer in the registry")})
    for i in range(len(slots), g.get("requested") or 0):
        never.append({"index": i, "label": None, "kind": None, "error": "batch recorded no run for this task"})
    return members, never + gone, g.get("epoch")


def group_runs(runs_dir: Path, name: str):
    """The members of `group_view`: `(run_dir, meta)` in start order; refuses an unknown or unreadable group."""
    return group_view(runs_dir, name)[0]


def group_gaps(runs_dir: Path, name: str):
    """The gaps of `group_view`, so no group view answers as if fewer were asked for; `[]` for a group that is not there or will not parse."""
    try:
        return group_view(runs_dir, name)[1]
    except Refusal:
        return []
