"""The loop every `--follow` runs, and the closing line a group's follow ends on.

A follower holds no state `status --group` could not re-derive, so one that dies loses nothing, and every follow ends on a terminal line — including on `--follow-timeout` — so silence never stands in for an outcome.
"""

from __future__ import annotations

import time

from codex.registry import group_gaps, unreadable_runs

# How often a follower asks whether anything changed. A tick reads forward from a byte offset, so it is cheap.
FOLLOW_INTERVAL = 1.0


def follow(step, *, timeout):
    """Run `step()` every FOLLOW_INTERVAL until it is done or `timeout` passes, passing each line on as soon as it is produced.

    `step()` is a generator that yields this tick's lines, newline included, as it produces them — so a failure later in the tick does not take earlier lines with it — and returns None once it has yielded the terminal line, else the lines to print if the deadline has passed.
    """
    started = time.time()
    while True:
        deadline_lines = yield from step()
        if deadline_lines is None:
            return
        if timeout and time.time() - started >= timeout:
            for line in deadline_lines:
                yield line + "\n"
            return
        time.sleep(FOLLOW_INTERVAL)


def group_tail(runs_dir, name):
    """The counts a group's closing line appends when non-zero."""
    never = group_gaps(runs_dir, name)
    bad = len(unreadable_runs(runs_dir))
    return never, (f" unstarted={len(never)}" if never else "") + (f" unreadable={bad}" if bad else "")
