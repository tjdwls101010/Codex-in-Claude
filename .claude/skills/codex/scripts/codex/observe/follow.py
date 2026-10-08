"""The silent wait `result --wait` makes, and a group as that wait sees it look by look. It prints nothing at all, so the result printed after it is the whole output, and it holds no state `status --group` could not re-derive, so one that dies loses nothing."""

from __future__ import annotations

import time

from codex.errors import Refusal
from codex.observe.rows import run_row
from codex.registry import group_view, read_meta

# How often a wait asks whether the run or group has ended.
FOLLOW_INTERVAL = 1.0


def wait_until(ended, timeout):
    """Ask `ended()` every FOLLOW_INTERVAL until it holds or `timeout` seconds have passed (None: no limit)."""
    started = time.time()
    while not ended():
        if timeout and time.time() - started >= timeout:
            return
        time.sleep(FOLLOW_INTERVAL)


class GroupWatch:
    """A group as a wait sees it, look by look: its members' rows and the slots no row stands for, both from one read of the manifest, so a member counts once and one a still-starting batch adds is seen. Once `clean` has released the name, another batch has claimed it again, or the manifest stops parsing, what was last read stands, its members re-read: a slot that never started is not forgotten, and nothing of a group that only shares the name is taken in."""

    def __init__(self, runs_dir, name, project):
        self.runs_dir, self.name, self.project = runs_dir, name, project
        # Refuses an unknown or unreadable group before anything is waited for.
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
