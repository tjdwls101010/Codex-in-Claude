"""The loop every `--follow` runs, and the closing line a group's follow ends on.

A follower holds no state `status --group` could not re-derive, so one that dies loses nothing, and every follow ends on a terminal line — including on `--follow-timeout` — so silence never stands in for an outcome.
"""

from __future__ import annotations

import time

from codex.codex_cli.events import FOLLOW_INTERVAL
from codex.registry.groups import unstarted_members, vanished_members
from codex.registry.runs import unreadable_runs


def follow(step, *, timeout, heartbeat):
    """Run `step()` every FOLLOW_INTERVAL, yielding each line it produces, until it is done or `timeout` passes.

    `step()` returns `(lines, pending)`: this tick's lines, and `pending` — None once `lines` ends on the terminal line, else `(live count, lines to print if the deadline has passed)`. With `heartbeat`, a `still-running` line is printed on the first tick at or after each interval.
    """
    started = beat_at = time.time()
    while True:
        lines, pending = step()
        for line in lines:
            yield line + "\n"
        if pending is None:
            return
        running, deadline_lines = pending
        now = time.time()
        if timeout and now - started >= timeout:
            for line in deadline_lines:
                yield line + "\n"
            return
        if heartbeat and now - beat_at >= heartbeat:
            yield f"still-running elapsed={int(now - started)} running={running}\n"
            beat_at = now
        time.sleep(FOLLOW_INTERVAL)


def group_tail(runs_dir, name):
    """The counts a group's closing line appends when non-zero."""
    never = unstarted_members(runs_dir, name) + vanished_members(runs_dir, name)
    bad = len(unreadable_runs(runs_dir))
    return never, (f" unstarted={len(never)}" if never else "") + (f" unreadable={bad}" if bad else "")
