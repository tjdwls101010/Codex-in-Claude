"""The loop every `--follow` runs, the closing line a group's follow ends on, and the silent wait `result --wait` makes.

A follower holds no state `status --group` could not re-derive, so one that dies loses nothing, and every follow ends on a terminal line — including on `--follow-timeout` — so silence never stands in for an outcome. A wait is the opposite contract: it prints nothing at all, so the result printed after it is the whole output.
"""

from __future__ import annotations

import time

from codex.errors import Refusal
from codex.observe.rows import group_snapshot, run_row
from codex.registry import group_view, read_meta, unreadable_runs

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


class GroupWatch:
    """A group as a follower or a wait sees it, tick by tick: its members' rows and the slots no row stands for, both from one read of the manifest, so a member counts once and one a still-starting batch adds is seen. Once `clean` has released the name, another batch has claimed it again, or the manifest stops parsing, what was last read stands, its members re-read: a slot that never started is not forgotten, and nothing of a group that only shares the name is taken in."""

    def __init__(self, runs_dir, name, project):
        self.runs_dir, self.name, self.project = runs_dir, name, project
        # Refuses an unknown or unreadable group before anything is followed.
        self.members, self.gaps, self.epoch = group_view(runs_dir, name)

    def view(self):
        """`(members, gaps)` as they stand: members as `(run_dir, meta)`, in start order."""
        try:
            members, gaps, epoch = group_view(self.runs_dir, self.name)
            if epoch != self.epoch:
                raise Refusal(f"group {self.name!r} was claimed again")
            self.members, self.gaps = members, gaps
        except Refusal:
            members, gaps = [], list(self.gaps)
            for rd, m in self.members:
                fresh = read_meta(rd)
                if fresh:
                    members.append((rd, fresh))
                else:
                    gaps.append({"run_id": m.get("run_id"), "label": m.get("label"), "error": "its meta.json will not parse"})
        return members, gaps

    def now(self):
        """`(rows, gaps)` as they stand, each row reaped."""
        members, gaps = self.view()
        return [run_row(rd, m, self.project) for rd, m in members], gaps


def tail(runs_dir, gaps):
    """The counts a group's closing line appends when non-zero."""
    bad = len(unreadable_runs(runs_dir))
    return (f" unstarted={len(gaps)}" if gaps else "") + (f" unreadable={bad}" if bad else "")


def closing_line(runs_dir, name, rows, gaps):
    """The line a group's follow ends on."""
    _running, done, failed, gstate = group_snapshot(rows, len(gaps))
    return f"group.{gstate} group={name} done={len(done)} failed={len(failed)}" + tail(runs_dir, gaps) + "\n"
