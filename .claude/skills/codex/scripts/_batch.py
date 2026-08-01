"""Groups: `<project>/.codex-runs/.groups/<name>.json`.

A group is a set of runs started by one `batch start` and thereafter addressed
as one thing — `status --group`, `result --group`, `stop --group`. The manifest
is a small file rather than a derived query, and each of the three reasons is
load-bearing:

  * **Uniqueness is free.** Creating the file with `O_EXCL` is the atomic claim
    on the name, so a second `batch start --group p1` fails on the filesystem
    rather than on a check that could race.
  * **Membership order is recorded, not re-derived.** `--resume-from` pairs the
    previous group's members with this group's tasks positionally, and a run id
    carries only a one-second stamp — batch start makes same-second, same-label
    starts the normal case (audit F15), so ordering by id or timestamp would be
    a coin flip exactly when it matters most.
  * **Reading a group does not walk the whole registry.** `status --group
    --follow` polls once a second; resolving membership through `iter_runs`
    would re-read every meta.json in the project on every tick.

`iter_runs` skips dot-directories, so `.groups/` is invisible to it and cannot
be mistaken for a run.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from _util import now_iso

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def groups_dir(runs_dir: Path) -> Path:
    return runs_dir / ".groups"


def group_path(runs_dir: Path, name: str) -> Path:
    return groups_dir(runs_dir) / f"{name}.json"


def valid_name(name: str) -> bool:
    """A group name becomes a filename, so it may not contain a separator or
    start with a dot. Rejecting up front beats discovering it as a traversal."""
    return bool(NAME_RE.match(name or ""))


def read_group(runs_dir: Path, name: str):
    try:
        return json.loads(group_path(runs_dir, name).read_text(encoding="utf-8"))
    except Exception:
        return None


def list_groups(runs_dir: Path):
    d = groups_dir(runs_dir)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _tmp_path(path: Path) -> Path:
    """A tmp name no other writer can be using. Same discipline as `write_meta`
    (F1): a fixed name lets two writers truncate each other's file and lets a
    reader see the result."""
    return path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")


def _write_atomic(path: Path, manifest: dict):
    tmp = _tmp_path(path)
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def claim_group(runs_dir: Path, name: str, derived_from=None) -> dict:
    """Take the name, atomically, before any run is spawned.

    Raises FileExistsError if the name is taken. Claiming first means a
    duplicate name costs nothing — no Codex process has started yet.

    The claim is `os.link`, not `O_CREAT|O_EXCL` on the destination, and the
    difference is not cosmetic. `O_EXCL` creates the file empty and fills it
    afterwards, so a crash — or merely a concurrent reader arriving in that
    window — sees a name that exists with no parsable content behind it, which
    `read_group` cannot distinguish from a corrupt manifest. `link` publishes a
    file that is already complete, and fails if the name is taken, so the name
    and its content appear in the same instant.
    """
    d = groups_dir(runs_dir)
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"group": name, "created_at": now_iso(),
                "derived_from": derived_from, "members": []}
    path = group_path(runs_dir, name)
    tmp = _tmp_path(path)
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.link(tmp, path)   # raises FileExistsError if the name is taken
    finally:
        tmp.unlink(missing_ok=True)
    return manifest


def write_members(runs_dir: Path, name: str, members: list) -> dict:
    """Record the member list so far, in start order.

    Called after **every** member rather than once at the end. Writing once was
    the natural shape — `batch start` is the only writer and knows the full list
    by the time it finishes — but it left a window with teeth: a batch killed
    partway through had already spawned live Codex processes whose manifest
    still said `members: []`, so `status/stop/result --group` could not see them
    and nothing could stop them through the group. Rewriting a file of a few
    hundred bytes N times is not a cost worth trading that for.
    """
    path = group_path(runs_dir, name)
    manifest = read_group(runs_dir, name) or {"group": name, "created_at": now_iso(),
                                              "derived_from": None}
    manifest["members"] = members
    _write_atomic(path, manifest)
    return manifest


def member_run_ids(runs_dir: Path, name: str):
    """Run ids in start order, skipping members that never spawned."""
    g = read_group(runs_dir, name)
    if not g:
        return None
    return [m["run_id"] for m in g.get("members", []) if m.get("run_id")]


def derived_groups(runs_dir: Path, name: str):
    """Groups whose `--resume-from` was this one. `batch clean` needs them:
    a phase-2 member resumes into its phase-1 predecessor's worktree, so
    removing phase 1's worktrees pulls the ground out from under phase 2."""
    return [g for g in list_groups(runs_dir)
            if (read_group(runs_dir, g) or {}).get("derived_from") == name]
