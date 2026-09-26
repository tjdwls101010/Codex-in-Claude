"""The run registry: `<project>/.codex-runs/<run_id>/`.

    .codex-runs/
    ├── .gitignore            # `*`, so the registry never lands in the user's history
    ├── .groups/<name>.json   # batch manifests
    ├── .locks/               # per-thread turn locks
    └── <run_id>/
        ├── meta.json         # the run's settings and lifecycle
        ├── events.jsonl      # `codex exec --json` stdout
        ├── stderr.log
        └── last-message.txt  # from -o

`codex exec resume` inherits no per-invocation setting from the thread it continues, so this registry is the only place a run's intended sandbox, model and effort exist at all.
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

from codex.util import nfc, now_iso, pid_alive

TERMINAL_STATES = ("completed", "failed", "interrupted", "orphaned", "timed_out")

# Everything that is not terminal, named once. `waiting` is no longer created but a registry left by an older release can hold one, and it has to stay stoppable, reapable and protective of its thread and worktree. `stalled` is derived for display and never stored.
ACTIVE_STATES = ("starting", "waiting", "running", "stalled")


def still_writing(meta: dict) -> bool:
    """Whether this run's Codex process is still going, whatever its state says.

    `orphaned` means "nothing is left to record this run's outcome", not "nothing is running": a supervisor lost to SIGKILL leaves its `codex exec` child alive and appending to the rollout.
    """
    return pid_alive(meta.get("codex_pid"))


def is_live(meta: dict) -> bool:
    """The one liveness question every view and guard asks: not terminal, or terminal while its Codex still writes. Callers reap first."""
    return meta.get("state") not in TERMINAL_STATES or still_writing(meta)


# -- locating things --------------------------------------------------------

def resolve_runs_dir(project: Path, explicit=None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return project / ".codex-runs"


def ensure_runs_dir(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    gi = d / ".gitignore"
    if not gi.exists():
        gi.write_text("*\n", encoding="utf-8")
    return d


def new_run_id(label=None) -> str:
    """Sortable and human-readable. Same-second, same-label ids collide about once in 65,536, which `claim_run_dir` retries."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")[:32] if label else ""
    return f"{stamp}-{slug or 'run'}-{uuid.uuid4().hex[:4]}"


def claim_run_dir(runs_dir: Path, label=None, attempts: int = 5):
    """Take exclusive ownership of a fresh run directory: `mkdir` without `exist_ok` is the atomic claim. Returns (run_id, run_dir)."""
    for _ in range(attempts):
        run_id = new_run_id(label)
        run_dir = runs_dir / run_id
        try:
            run_dir.mkdir(parents=True)
        except FileExistsError:
            continue
        return run_id, run_dir
    raise FileExistsError(f"could not claim a free run id under {runs_dir} in {attempts} attempts")


# -- locks and atomic writes --------------------------------------------------

@contextlib.contextmanager
def _flock_path(lock: Path):
    """Hold an exclusive lock on `lock` for the body.

    Failing to take the lock degrades to unlocked access, so a registry on a filesystem that cannot lock still works; an error raised by the body is the body's and propagates.
    """
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        fh = lock.open("a+")
    except OSError:
        yield
        return
    try:
        with contextlib.suppress(OSError):
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        with contextlib.suppress(Exception):
            fh.close()


def thread_turn_lock(runs_dir: Path, thread_ref):
    """Serialise "is this thread free?" with publishing the run that answers it, across processes.

    Without it two resumes a fraction of a second apart both see an idle thread and start two turns on one rollout file. Held only across check-and-publish, never across the turn.
    """
    if not thread_ref:
        return contextlib.nullcontext()
    return _flock_path(runs_dir / ".locks" / (nfc(str(thread_ref)).replace("/", "_") + ".lock"))


def _meta_lock(run_dir: Path):
    """Serialise read-modify-write on one meta.json. The lock file is separate because locking the file being replaced would lock an inode that is no longer current."""
    return _flock_path(run_dir / ".meta.lock")


def write_json_atomic(path: Path, obj):
    """A reader sees the old file or the new one, never half of one. The staging name is unique per writer: a shared one lets two writers truncate each other."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


# -- meta.json ----------------------------------------------------------------

def read_meta(run_dir: Path):
    try:
        return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def meta_unreadable(run_dir: Path) -> bool:
    """Present but will not parse, as distinct from absent: `read_meta` answers None for both."""
    return (run_dir / "meta.json").is_file() and read_meta(run_dir) is None


def write_meta(run_dir: Path, meta: dict):
    write_json_atomic(run_dir / "meta.json", meta)


def update_meta(run_dir: Path, **fields):
    """Merge `fields` into meta.json under the run's lock."""
    with _meta_lock(run_dir):
        meta = read_meta(run_dir) or {}
        meta.update(fields)
        write_meta(run_dir, meta)
        return meta


def update_meta_if(run_dir: Path, expected_states, **fields):
    """Compare-and-set on `state`: merge only if the state on disk is still one of `expected_states`, and return what is on disk. A caller deciding from a snapshot commits this way so an outcome written in between wins."""
    with _meta_lock(run_dir):
        meta = read_meta(run_dir) or {}
        if meta.get("state") not in expected_states:
            return meta
        meta.update(fields)
        write_meta(run_dir, meta)
        return meta


# -- finding runs -------------------------------------------------------------

def run_sort_key(item):
    """Oldest to newest by `started_at` (millisecond resolution), the run id only breaking ties."""
    run_dir, meta = item
    return (meta.get("started_at") or "", run_dir.name)


def iter_runs(runs_dir: Path):
    """Yield (run_dir, meta) oldest first, skipping runs whose meta.json will not parse (`unreadable_runs` names those)."""
    if not runs_dir.is_dir():
        return
    found = []
    for d in runs_dir.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        m = read_meta(d)
        if m:
            found.append((d, m))
    yield from sorted(found, key=run_sort_key)


def unreadable_runs(runs_dir: Path):
    """Run directories `iter_runs` had to skip, so a listing missing them can say so."""
    if not runs_dir.is_dir():
        return []
    return sorted(d.name for d in runs_dir.iterdir()
                  if d.is_dir() and not d.name.startswith(".") and meta_unreadable(d))


def find_run(runs_dir: Path, ref: str):
    """Resolve a run id, a thread id, or a run-id prefix; newest wins. Returns (run_dir, meta), with meta None for a run whose meta.json will not parse."""
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
    """Record `orphaned` for an active run whose supervisor is gone, so a dead process is never reported live.

    A run still being built has no supervisor yet; its creator's pid is asked instead of a clock, because `git worktree add` can take longer than any grace period. The commit is compare-and-set, so a real outcome written meanwhile wins.
    """
    if meta.get("state") not in ACTIVE_STATES:
        return meta
    sup = meta.get("supervisor_pid")
    if sup and pid_alive(sup):
        return meta
    if meta.get("state") == "starting" and not sup:
        creator = meta.get("creator_pid")
        if creator and pid_alive(creator):
            return meta
        try:
            if time.time() - os.path.getmtime(run_dir / "meta.json") < 30:
                return meta
        except OSError:
            pass
    return update_meta_if(run_dir, ACTIVE_STATES, state="orphaned", ended_at=now_iso())
