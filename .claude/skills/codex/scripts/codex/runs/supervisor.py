"""The detached supervisor that runs Codex and records its outcome, and the signal ladder that ends a run for `stop` and for a deadline alike.

A run is its own process group: the supervisor is a session leader and Codex its child in that group. Signals go to the recorded group, never to a process name, so one run's stop cannot reach another run's Codex.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from codex.codex_cli.events import first_thread_id
from codex.registry.runs import ACTIVE_STATES, read_meta, update_meta, update_meta_if
from codex.util import ENTRY, now_iso, pid_alive

# How long a new run waits for `thread.started` before handing back `thread_id: null`; `status` backfills it later.
THREAD_ID_WAIT = 15.0

# Seconds a run gets after SIGINT to flush its rollout, which is what keeps an ended run resumable, before SIGTERM.
DEFAULT_GRACE = 5.0

def spawn_supervised(run_dir: Path) -> int:
    """Start the run's supervisor in a new session, re-executing the entrypoint. Without a supervisor nothing would record the exit code."""
    log = (run_dir / "supervisor.log").open("ab")
    try:
        p = subprocess.Popen([sys.executable, str(ENTRY), "__supervise", "--run-dir", str(run_dir)],
                             stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                             start_new_session=True, cwd=str(run_dir))
    finally:
        log.close()
    return p.pid


def end_group(pgid, *, grace, done, before_kill=None, every_rung=False, sent=None):
    """SIGINT, then SIGTERM, then SIGKILL to a process group, then a SIGKILL sweep, because a descendant can outlive Codex.

    Each rung waits up to its time for `done()`. By default the ladder stops at the first rung after which `done()` holds (a stop ends once the run's own processes are gone); with `every_rung` SIGTERM is sent even so, so leftovers get the chance to exit cleanly before SIGKILL. `before_kill` runs before any SIGKILL — a supervisor ending its own group records its outcome there. Signals actually sent are appended to `sent` (returned), which survives a PermissionError the caller catches.
    """
    sent = [] if sent is None else sent
    for sig, wait in ((signal.SIGINT, grace), (signal.SIGTERM, 3.0), (signal.SIGKILL, 1.0)):
        if sig == signal.SIGKILL and before_kill:
            before_kill()
        try:
            os.killpg(int(pgid), sig)
        except ProcessLookupError:
            return sent
        sent.append(sig.name)
        deadline = time.time() + wait
        while time.time() < deadline and not done():
            time.sleep(0.1)
        if done() and (not every_rung or sig == signal.SIGTERM):
            break
    if sent[-1] != "SIGKILL":
        if before_kill:
            before_kill()
        with contextlib.suppress(ProcessLookupError):
            os.killpg(int(pgid), signal.SIGKILL)
            sent.append("SIGKILL")
    return sent


def stop_run(run_dir: Path, meta: dict, grace: float = DEFAULT_GRACE):
    """End one run through its process group and record `interrupted` — compare-and-set, since the supervisor may have written the true outcome meanwhile."""
    pgid = meta.get("pgid")
    result = {"run_id": meta.get("run_id"), "pgid": pgid}
    if not pgid:
        return {**result, "signalled": False, "reason": "no process group recorded", "state": meta.get("state")}
    sent = []
    try:
        end_group(pgid, grace=grace, sent=sent,
                  done=lambda: not pid_alive(meta.get("supervisor_pid"), pgid) and not pid_alive(meta.get("codex_pid"), pgid))
    except PermissionError:
        result["error"] = f"not permitted to signal process group {pgid}"
    result["signals_sent"] = sent
    result["signalled"] = bool(sent)
    m = update_meta_if(run_dir, ACTIVE_STATES, state="interrupted", ended_at=now_iso())
    result["state"] = m.get("state")
    result["thread_id"] = m.get("thread_id")
    return result


def supervise(run_dir: Path) -> int:
    """Spawn Codex, record what happened, exit. Runs as its own process."""
    meta = read_meta(run_dir)
    if not meta:
        return 1
    # The supervisor is a re-exec of `__supervise --run-dir`, so meta.json is the only channel the deadline survives.
    timeout = meta.get("timeout_seconds")
    interrupted = {"flag": False}

    def on_signal(signum, _frame):
        # Does not exit: Codex flushes its rollout on SIGINT, and a supervisor that died first would leave nothing to record the outcome.
        interrupted["flag"] = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(ValueError):
            signal.signal(sig, on_signal)

    events_path = run_dir / "events.jsonl"
    if not Path(meta["cwd"]).is_dir():
        # Popen raises the same FileNotFoundError for a missing cwd as for a missing executable.
        update_meta(run_dir, state="failed", exit_code=1, ended_at=now_iso(),
                    error=f"the working directory recorded for this run is gone: {meta['cwd']}")
        return 1
    out = events_path.open("ab")
    err = (run_dir / "stderr.log").open("ab")
    try:
        proc = subprocess.Popen(meta["argv"], cwd=meta["cwd"], stdout=out, stderr=err, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        update_meta(run_dir, state="failed", exit_code=127, ended_at=now_iso(), error="codex not found on PATH")
        return 127
    finally:
        out.close()
        err.close()

    # The deadline counts from launch: the thread-id wait below is part of the time the run was given.
    ends_at = time.time() + timeout if timeout is not None else None
    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = None
    update_meta(run_dir, state="running", codex_pid=proc.pid, supervisor_pid=os.getpid(), pgid=pgid,
                codex_started_at=now_iso())

    tid = None
    tid_deadline = min(time.time() + THREAD_ID_WAIT, ends_at or float("inf"))
    while time.time() < tid_deadline:
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
        # Its own terminal state: "it ran out of the time I gave it" is answered by raising --timeout, unlike a stop or a failure. The thread stays resumable.
        fields = {"state": "timed_out", "ended_at": now_iso(), "error": f"timed out after {timeout}s"}

        def record():
            # This supervisor is in the group about to be SIGKILLed, so the outcome is written first.
            code = proc.poll()
            update_meta(run_dir, exit_code=code if code is not None else -signal.SIGKILL, **fields)

        end_group(pgid or proc.pid, grace=DEFAULT_GRACE, done=lambda: proc.poll() is not None, before_kill=record,
                  every_rung=True)
        rc = proc.wait()
        update_meta(run_dir, exit_code=rc, **fields)
        return rc

    if not tid:
        tid = first_thread_id(events_path)
    state = "completed" if rc == 0 else ("interrupted" if interrupted["flag"] else "failed")
    fields = {"state": state, "exit_code": rc, "ended_at": now_iso()}
    if tid:
        fields["thread_id"] = tid
    update_meta(run_dir, **fields)
    return rc
