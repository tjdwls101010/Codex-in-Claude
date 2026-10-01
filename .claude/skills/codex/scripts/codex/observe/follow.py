"""The loop every `--follow` runs, the closing line a group's follow ends on, and the silent wait `result --wait` makes.

A follower holds no state `status --group` could not re-derive, so one that dies loses nothing, and every follow ends on a terminal line — including on `--follow-timeout` — so silence never stands in for an outcome. A wait is the opposite contract: it prints nothing at all, so the result printed after it is the whole output.
"""

from __future__ import annotations

import time

from codex.observe.rows import group_snapshot
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


def wait_until(ended, timeout):
    """Ask `ended()` every FOLLOW_INTERVAL until it holds or `timeout` seconds have passed (None: no limit)."""
    started = time.time()
    while not ended():
        if timeout and time.time() - started >= timeout:
            return
        time.sleep(FOLLOW_INTERVAL)


def closing_line(runs_dir, name, rows):
    """The line a group's follow ends on, from its rows and its gaps as they stand now: a member that stopped parsing while it was followed counts against `completed` as one that never parsed does."""
    never, tail = group_tail(runs_dir, name)
    _running, done, failed, gstate = group_snapshot(rows, len(never))
    return f"group.{gstate} group={name} done={len(done)} failed={len(failed)}" + tail + "\n"


def group_tail(runs_dir, name):
    """The counts a group's closing line appends when non-zero."""
    never = group_gaps(runs_dir, name)
    bad = len(unreadable_runs(runs_dir))
    return never, (f" unstarted={len(never)}" if never else "") + (f" unreadable={bad}" if bad else "")
