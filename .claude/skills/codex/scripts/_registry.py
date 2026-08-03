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

import contextlib
import fcntl
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from _util import git_toplevel, nfc, now_iso, pid_alive

TERMINAL_STATES = ("completed", "failed", "interrupted", "orphaned", "timed_out")


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
    """Sortable, human-readable, and collision-resistant under parallel starts.

    Resistant, not free: the stamp has one-second resolution and the suffix is
    16 bits, so two runs started in the same second under the same label collide
    about once in 65,536. `batch start` makes same-second same-label starts the
    normal case rather than a freak one, so callers go through `claim_run_dir`,
    which retries.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")[:32] if label else ""
    return f"{stamp}-{slug or 'run'}-{uuid.uuid4().hex[:4]}"


def claim_run_dir(runs_dir: Path, label=None, attempts: int = 5):
    """Generate a run id and take exclusive ownership of its directory.

    `mkdir` without `exist_ok` is the claim: it either creates the directory or
    raises, atomically, so two processes racing on the same id cannot both
    believe they own it. Returns (run_id, run_dir).
    """
    for _ in range(attempts):
        run_id = new_run_id(label)
        run_dir = runs_dir / run_id
        try:
            run_dir.mkdir(parents=True)
        except FileExistsError:
            continue
        return run_id, run_dir
    raise FileExistsError(
        f"could not claim a free run id under {runs_dir} in {attempts} attempts")


# -- meta.json --------------------------------------------------------------

def read_meta(run_dir: Path):
    try:
        return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return None


@contextlib.contextmanager
def _meta_lock(run_dir: Path):
    """Serialise read-modify-write on one run's meta.json.

    `os.replace` makes the *swap* atomic, which is enough for a reader — but not
    for two writers merging fields, because each reads a base the other is about
    to invalidate and the loser's field vanishes. The lock file is separate from
    meta.json on purpose: locking the file being replaced would leave each writer
    holding a lock on an inode that is no longer the current one.
    """
    lock = run_dir / ".meta.lock"
    fh = None
    try:
        fh = lock.open("a+")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    except OSError:
        # A registry we cannot lock (read-only mount, exotic filesystem) must
        # still be usable: fall back to unserialised access rather than failing
        # the run outright. Unique tmp names below keep this from corrupting
        # anything; the only loss is the merge guarantee.
        yield
    finally:
        if fh is not None:
            with contextlib.suppress(Exception):
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            with contextlib.suppress(Exception):
                fh.close()


def write_meta(run_dir: Path, meta: dict):
    """Atomic: a concurrent reader sees the old file or the new one, never a
    half-written one.

    The tmp name carries pid and a random suffix because the *rename* being
    atomic does not make a *shared staging path* safe — a second writer opening
    the same tmp path truncates the first writer's inode, and the first writer's
    rename then fails on a source that no longer exists. Measured: 152 uncaught
    FileNotFoundError in 240 concurrent writes before this changed.
    """
    tmp = run_dir / f".meta.json.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(run_dir / "meta.json")
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def update_meta(run_dir: Path, **fields):
    """Merge `fields` into meta.json under the run's lock."""
    with _meta_lock(run_dir):
        meta = read_meta(run_dir) or {}
        meta.update(fields)
        write_meta(run_dir, meta)
        return meta


def update_meta_if(run_dir: Path, expected_states, **fields):
    """Compare-and-set on `state`: merge `fields` only if the state on disk is
    still one of `expected_states`, and return whatever is actually on disk.

    A caller that decided from a snapshot cannot commit through `update_meta`,
    because between snapshot and commit the run may have finished and written
    its real outcome — and overwriting that outcome is not self-healing. Reading
    and writing inside one lock is what makes the check meaningful.
    """
    with _meta_lock(run_dir):
        meta = read_meta(run_dir) or {}
        if meta.get("state") not in expected_states:
            return meta
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


def unreadable_runs(runs_dir: Path):
    """Run directories `iter_runs` had to skip because their meta.json would not
    parse, newest-looking first by name.

    `read_meta` swallowing a parse error is right — one corrupt run must not
    take down every view of every other one. Dropping it *silently* is not: the
    caller then gets a complete-looking answer with the broken run missing from
    it, which is the failure D27 refuses. Counting them costs one extra stat per
    skipped directory and turns a disappearance into a fact.
    """
    if not runs_dir.is_dir():
        return []
    bad = []
    for d in runs_dir.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        if (d / "meta.json").is_file() and read_meta(d) is None:
            bad.append(d.name)
    return sorted(bad)


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
    # Everything above judged from the caller's snapshot, and `pid_alive` is a
    # slow enough check that the supervisor can finish and write `completed`
    # while we are still deciding. Commit conditionally so that a real outcome
    # always beats our stale one — `orphaned, exit_code: 0` is a lie that never
    # self-heals once written.
    return update_meta_if(run_dir, ("running", "starting"),
                          state="orphaned", ended_at=now_iso())
