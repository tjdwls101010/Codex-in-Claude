#!/usr/bin/env python3
"""SessionEnd — stop background Codex runs this session started.

Why kill them at all. A background `codex exec` outlives the Claude session that
launched it: nobody is reading its log any more, but it keeps writing to the
repository and burning tokens, and the person who started it has no handle on it
left. That is the worse failure. A killed run is not lost — SIGINT leaves the
thread resumable from its rollout (measured: Codex exits ~0.3 s later and the
resumed turn still knows what the interrupted turn had finished) — so the cost
of killing is a resume, while the cost of not killing is unbounded.

`--detach` exempts a run, deliberately, for the case where outliving the session
is the point.

SessionEnd also fires on `/clear` and `/resume`, not only on real termination.
That is intended: after a `/clear` nobody is watching either.

**This file is standalone on purpose.** It imports only what the standard
library gives it for free and never imports the bridge — SessionEnd's default
timeout is 1.5 seconds, the shortest of any hook event by nearly two orders of
magnitude, and the bridge pulls in argparse, subprocess and sqlite3 for no
benefit here. The duplicated ~20 lines of meta reading are cheaper than the
coupling.
"""

import json
import os
import signal
import sys
import time
from pathlib import Path

# Total wall-clock this hook will spend signalling, against a 1.5 s budget. The
# rest is left as headroom for interpreter startup and stdin.
SIGNAL_BUDGET = 0.9

# How long to let SIGINT work before escalating. Measured: Codex exits ~0.3 s
# after SIGINT, having flushed its rollout. Sending SIGTERM immediately after
# SIGINT — as "SIGINT, then SIGTERM" reads — would defeat the flush that makes
# the thread resumable, which is the whole reason SIGINT goes first.
SIGINT_GRACE = 0.5

MAX_WALK_UP = 24


def find_runs_dir(start: Path):
    """Walk up for `.codex-runs`.

    The registry lives at the git top level but the session's cwd may be any
    subdirectory of it. Walking up is a handful of stat() calls; asking git
    would mean spawning a process, which is exactly the kind of cost this hook
    cannot afford.
    """
    cur = start
    for _ in range(MAX_WALK_UP):
        candidate = cur / ".codex-runs"
        if candidate.is_dir():
            return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()
    runs_dir = find_runs_dir(Path(cwd))
    if runs_dir is None:
        # The common case for every project that never uses Codex. It must cost
        # effectively nothing, which is why this check comes before anything
        # else and why nothing above it touches the filesystem more than once.
        return 0

    # Match on either source. The hook input carries `session_id` and the
    # environment carries CLAUDE_CODE_SESSION_ID; both were confirmed present,
    # but relying on one alone is a single point of failure whose failure mode
    # is silent. Accepting either makes a disagreement fail toward killing
    # nothing (benign) rather than killing another session's runs (not).
    session_ids = {s for s in (payload.get("session_id"),
                               os.environ.get("CLAUDE_CODE_SESSION_ID")) if s}

    targets = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir() or run_dir.name.startswith("."):
            continue
        try:
            meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("state") not in ("running", "starting"):
            continue
        if meta.get("detached"):
            continue
        if meta.get("claude_session_id") not in session_ids:
            continue
        pgid = meta.get("pgid")
        if pgid:
            targets.append((run_dir, meta, int(pgid)))

    if not targets:
        return 0

    deadline = time.time() + SIGNAL_BUDGET
    stopped = []

    for run_dir, meta, pgid in targets:
        try:
            os.killpg(pgid, signal.SIGINT)
            stopped.append((run_dir, meta, pgid, "SIGINT"))
        except (ProcessLookupError, PermissionError, OSError):
            stopped.append((run_dir, meta, pgid, "already-gone"))

    def alive(meta):
        for pid in (meta.get("supervisor_pid"), meta.get("codex_pid")):
            if not pid:
                continue
            try:
                os.kill(int(pid), 0)
                return True
            except OSError as e:
                import errno
                if e.errno == errno.EPERM:
                    return True
        return False

    grace_until = min(time.time() + SIGINT_GRACE, deadline)
    while time.time() < grace_until:
        if not any(alive(m) for _, m, _, _ in stopped):
            break
        time.sleep(0.05)

    for i, (run_dir, meta, pgid, how) in enumerate(stopped):
        if how == "already-gone" or not alive(meta):
            continue
        if time.time() >= deadline:
            break
        try:
            os.killpg(pgid, signal.SIGTERM)
            stopped[i] = (run_dir, meta, pgid, "SIGINT+SIGTERM")
        except OSError:
            pass

    # Record the outcome so `status` does not show these as still running, and
    # so the reason is discoverable later. Writing is last: if the budget ran
    # out, the processes are already signalled, which is the part that matters.
    reason = payload.get("reason") or "session-end"
    for run_dir, meta, _pgid, how in stopped:
        meta["state"] = "interrupted"
        meta["ended_at"] = meta.get("ended_at") or time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        meta["stopped_by"] = f"SessionEnd({reason})"
        meta["stop_signals"] = how
        try:
            tmp = run_dir / ".meta.json.tmp"
            tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(run_dir / "meta.json")
        except Exception:
            pass

    # SessionEnd has no decision channel — it cannot block termination — so
    # stdout is only for a human reading the transcript.
    names = ", ".join(m.get("run_id", "?") for _, m, _, _ in stopped)
    sys.stdout.write(f"codex: stopped {len(stopped)} background run(s) on "
                     f"session end ({reason}): {names}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
