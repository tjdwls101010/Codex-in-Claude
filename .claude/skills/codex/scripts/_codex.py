"""Spawning a run under its detached supervisor, and the supervisor itself (moves to core/supervisor)."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from codex.events import first_thread_id
from _registry import read_meta, update_meta
from util import now_iso

# How long to wait for `thread.started` before returning `thread_id: null`. It
# is the first line Codex emits and arrives in well under a second; the window
# is generous only so a cold start cannot lose the id, and missing it is not an
# error because `status` backfills it from events.jsonl.
THREAD_ID_WAIT = 15.0

# Seconds a timed-out run gets after SIGINT to flush its rollout before SIGTERM, the same first rung `stop --grace` defaults to.
DEADLINE_GRACE = 5.0


# -- spawning ---------------------------------------------------------------

def spawn_supervised(run_dir: Path) -> int:
    """Start the run under a supervisor process, in its own session.

    A background `codex exec` needs someone to reap it, or nothing ever records
    the exit code and a finished run is indistinguishable from a crashed one.
    Spawning the supervisor into a new session puts supervisor and Codex in one
    process group, which is what lets `stop` signal exactly one run's tree —
    and why it never has to match processes by name, the thing that would make
    concurrent runs kill each other.
    """
    log = (run_dir / "supervisor.log").open("ab")
    try:
        p = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent / "cli_codex.py"),
             "__supervise", "--run-dir", str(run_dir)],
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True, cwd=str(run_dir),
        )
    finally:
        log.close()
    return p.pid


def supervise(run_dir: Path) -> int:
    """Spawn Codex, record what happened, exit. Runs as its own process."""
    meta = read_meta(run_dir)
    if not meta:
        return 1
    # The supervisor is a re-exec of `__supervise --run-dir`, so meta.json is the only channel the deadline survives.
    timeout = meta.get("timeout_seconds")
    interrupted = {"flag": False}

    def on_signal(signum, _frame):
        # Deliberately does not exit. Codex flushes its rollout on SIGINT and
        # stays resumable; if the supervisor died first, nothing would record
        # the outcome and the run would read as `running` forever.
        interrupted["flag"] = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, on_signal)
        except ValueError:
            pass

    events_path = run_dir / "events.jsonl"
    out = events_path.open("ab")
    err = (run_dir / "stderr.log").open("ab")
    if not Path(meta["cwd"]).is_dir():
        # `Popen` raises the same FileNotFoundError for a missing cwd as for a
        # missing executable, so the two have to be told apart here.
        update_meta(run_dir, state="failed", exit_code=1, ended_at=now_iso(),
                    error=f"the working directory recorded for this run is gone: "
                          f"{meta['cwd']}")
        out.close()
        err.close()
        return 1
    try:
        proc = subprocess.Popen(
            meta["argv"], cwd=meta["cwd"], stdout=out, stderr=err,
            stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        update_meta(run_dir, state="failed", exit_code=127, ended_at=now_iso(),
                    error="codex not found on PATH")
        return 127
    finally:
        out.close()
        err.close()

    # Codex stays in this supervisor's process group (the supervisor is a session leader), which is what lets `stop`'s killpg reach the supervisor, whose handler records `interrupted`.
    # The deadline counts from launch: the thread-id wait below is part of the time the run was given.
    ends_at = time.time() + timeout if timeout is not None else None
    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = None
    update_meta(run_dir, state="running", codex_pid=proc.pid,
                supervisor_pid=os.getpid(), pgid=pgid,
                codex_started_at=now_iso())

    deadline = time.time() + THREAD_ID_WAIT
    if ends_at is not None:
        deadline = min(deadline, ends_at)
    tid = None
    while time.time() < deadline:
        tid = first_thread_id(events_path)
        if tid:
            update_meta(run_dir, thread_id=tid)
            break
        if proc.poll() is not None:
            break
        time.sleep(0.05)

    try:
        rc = proc.wait(timeout=None if ends_at is None else max(0.0, ends_at - time.time()))
    except subprocess.TimeoutExpired:
        # A distinct terminal state, not `interrupted`: the caller needs to tell
        # "I stopped it" from "Codex failed" from "it ran out of the time I gave
        # it", and only the third is answered by raising --timeout. The thread
        # stays resumable across the SIGINT, with the pre-timeout turn's context
        # intact.
        fields = {"state": "timed_out", "ended_at": now_iso(), "error": f"timed out after {timeout}s"}
        rc, group = None, pgid or proc.pid
        # SIGINT lets Codex flush its rollout. Every rung is sent even after Codex exits, because a descendant of it can outlive it in the same group.
        for sig, wait in ((signal.SIGINT, DEADLINE_GRACE), (signal.SIGTERM, 3.0)):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(group, sig)
            try:
                rc = proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                pass
        # This supervisor is in the group it is about to SIGKILL, so the outcome is written first.
        update_meta(run_dir, exit_code=rc if rc is not None else -signal.SIGKILL, **fields)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(group, signal.SIGKILL)
        return rc

    if not tid:
        tid = first_thread_id(events_path)
    state = "completed" if rc == 0 else ("interrupted" if interrupted["flag"] else "failed")
    fields = {"state": state, "exit_code": rc, "ended_at": now_iso()}
    if tid:
        fields["thread_id"] = tid
    update_meta(run_dir, **fields)
    return rc
