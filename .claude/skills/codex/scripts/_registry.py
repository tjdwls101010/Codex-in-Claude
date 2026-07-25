"""The run registry: `<project>/.codex-runs/<run_id>/`.

    .codex-runs/
    ├── .gitignore            # contains exactly:  *
    └── <run_id>/
        ├── meta.json         # the run's settings and lifecycle
        ├── events.jsonl      # raw `codex --json` stdout, the durable source of truth
        ├── stderr.log
        └── last-message.txt  # from -o

The registry is mandatory rather than a convenience. `codex exec resume`
inherits no per-invocation setting from the thread it resumes — it re-derives
every one from whatever config layer is in effect — so the only place a run's
intended sandbox, model and effort exist at all is here. Everything else the
registry buys (parallel-safe stop, stall detection, session-scoped cleanup) sits
on top of that one non-negotiable.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from _util import git_toplevel, nfc, now_iso, pid_alive

TERMINAL_STATES = ("completed", "failed", "interrupted", "orphaned")


# -- locating things --------------------------------------------------------

def resolve_project(explicit=None) -> Path:
    base = Path(explicit).expanduser().resolve() if explicit else Path.cwd().resolve()
    return git_toplevel(base) or base


def resolve_runs_dir(project: Path, explicit=None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return project / ".codex-runs"


def ensure_runs_dir(d: Path) -> Path:
    """The registry ignores itself, so it can never land in the user's history
    and we never have to edit the user's own .gitignore."""
    d.mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")
    return d


def new_run_id(label=None) -> str:
    """Sortable, human-readable, and collision-free under parallel starts."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")[:32] if label else ""
    return f"{stamp}-{slug or 'run'}-{uuid.uuid4().hex[:4]}"


# -- meta.json --------------------------------------------------------------

def read_meta(run_dir: Path):
    try:
        return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def write_meta(run_dir: Path, meta: dict):
    """Atomic: a concurrent reader sees the old file or the new one, never a
    half-written one."""
    tmp = run_dir / ".meta.json.tmp"
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(run_dir / "meta.json")


def update_meta(run_dir: Path, **fields):
    meta = read_meta(run_dir) or {}
    meta.update(fields)
    write_meta(run_dir, meta)
    return meta


# -- finding runs -----------------------------------------------------------

def run_sort_key(item):
    """Order runs oldest-to-newest.

    A run id only carries a one-second stamp, so several runs started in the
    same second sort by their random suffix — which would make "newest wins"
    pick arbitrarily. `started_at` has millisecond resolution and is the real
    ordering; the id is only the tie-break.
    """
    run_dir, meta = item
    return (meta.get("started_at") or "", run_dir.name)


def iter_runs(runs_dir: Path):
    """Yield (run_dir, meta) oldest first. Every caller that means "the latest
    run" relies on this order, so it is established in exactly one place."""
    if not runs_dir.is_dir():
        return
    found = []
    for d in runs_dir.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        m = read_meta(d)
        if m:
            found.append((d, m))
    for pair in sorted(found, key=run_sort_key):
        yield pair


def find_run(runs_dir: Path, ref: str):
    """Resolve a run id, a thread id, or a run-id prefix; newest wins."""
    d = runs_dir / ref
    if d.is_dir() and (d / "meta.json").exists():
        return d, read_meta(d)
    by_thread, by_prefix = [], []
    for rd, m in iter_runs(runs_dir):
        if m.get("thread_id") == ref:
            by_thread.append((rd, m))
        if rd.name.startswith(ref):
            by_prefix.append((rd, m))
    for group in (by_thread, by_prefix):
        if group:
            return sorted(group, key=run_sort_key)[-1]
    return None, None


def reap(run_dir: Path, meta: dict) -> dict:
    """A run whose supervisor is gone but whose meta still says `running` was
    killed without getting to write its outcome. Say so, rather than reporting a
    dead process as live — a stale `running` row is how a caller ends up waiting
    forever on something that died minutes ago."""
    if meta.get("state") not in ("running", "starting"):
        return meta
    sup = meta.get("supervisor_pid")
    if sup and pid_alive(sup):
        return meta
    if meta.get("state") == "starting" and not sup:
        # The supervisor writes its pid as its first act; give it a moment
        # before calling a just-spawned run dead.
        try:
            if time.time() - os.path.getmtime(run_dir / "meta.json") < 30:
                return meta
        except OSError:
            pass
    return update_meta(run_dir, state="orphaned",
                       ended_at=meta.get("ended_at") or now_iso())
