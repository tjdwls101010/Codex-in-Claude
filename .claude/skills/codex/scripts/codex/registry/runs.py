"""Run records: one directory per run, its `meta.json` the run's settings and lifecycle, and the one liveness question every view and guard asks."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

from codex.registry.locks import meta_lock, write_json_atomic
from codex.errors import Refusal
from codex.util import now_iso, pid_alive

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
    with meta_lock(run_dir):
        meta = read_meta(run_dir) or {}
        meta.update(fields)
        write_meta(run_dir, meta)
        return meta


def update_meta_if(run_dir: Path, expected_states, **fields):
    """Compare-and-set on `state`: merge only if the state on disk is still one of `expected_states`, and return what is on disk. A caller deciding from a snapshot commits this way so an outcome written in between wins."""
    with meta_lock(run_dir):
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


def resolve_implicit_run(candidates):
    """Pick a run nobody named, from `candidates` in `iter_runs` order: the one live run, else the newest with a note saying so. Two or more live runs are refused with the candidates listed, because guessing would hand the caller another run's label and sandbox."""
    reaped = [(rd, reap(rd, m)) for rd, m in candidates]
    live = [(rd, m) for rd, m in reaped if is_live(m)]
    if len(live) == 1:
        rd, m = live[0]
        return rd, m, "the only non-terminal run"
    if len(live) >= 2:
        raise Refusal("two or more runs are live, so the target is ambiguous; name a run id, thread id or thread name",
                      candidates=[{"run_id": m.get("run_id"), "label": m.get("label"),
                                   "state": m.get("state"), "sandbox": m.get("sandbox"),
                                   "thread_id": m.get("thread_id")} for rd, m in live])
    if not reaped:
        return None, None, None
    rd, m = reaped[-1]
    return rd, m, "the newest run (no non-terminal runs)"


def refuse_unresolved_run(ref, run_dir, meta, runs_dir):
    """"Cannot read that run" and "no such run" are different answers: the first still has an event stream on disk."""
    if meta:
        return
    if run_dir is not None and meta_unreadable(run_dir):
        raise Refusal(f"run {ref} has a meta.json that will not parse, so its state is unknown; its event stream may still be readable",
                      run_id=run_dir.name, run_dir=str(run_dir), events=str(run_dir / "events.jsonl"))
    raise Refusal(f"no such run: {ref}", runs_dir=str(runs_dir))
