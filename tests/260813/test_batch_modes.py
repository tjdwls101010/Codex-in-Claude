"""D1 — `batch start --foreground` runs the batch one member at a time.

`task_args` copies the caller's whole namespace onto every member, `_batch.py`
never mentions `foreground`, and `create_run` calls `supervise()` synchronously
whenever `meta["foreground"]` is set. So the spawn loop waits out each member's
entire Codex turn before starting the next: three members that hang two seconds
each take seven, and their run ids come out two seconds apart.

Nothing about that is announced. `batch` exists to run tasks concurrently, and
the flag that turns it into a serial loop reports the same shape either way, so
the only symptom is that it took N times longer than the caller expected.

There is a working way to block until a batch is done — start it, then
`status --group --follow` — so the fix is to refuse the flag and say so, not to
build a second supervision model for it.
"""

from __future__ import annotations

import unittest

from helpers import BridgeCase


class ForegroundIsNotABatchMode(BridgeCase):

    def test_batch_start_refuses_foreground(self):
        tasks = self.tasks_file("a", "b")
        out = self.bridge("batch", "start", "--group", "g",
                          "--tasks-file", tasks, "--foreground", expect_rc=1)
        self.assertIn("--foreground", out["error"])

    def test_the_refusal_names_a_way_to_wait_for_the_batch(self):
        """A refusal that removes the only obvious way to block is a dead end
        unless it says where the working one is."""
        tasks = self.tasks_file("a", "b")
        out = self.bridge("batch", "start", "--group", "g",
                          "--tasks-file", tasks, "--foreground", expect_rc=1)
        self.assertIn("--follow", out["error"])

    def test_the_group_name_survives_the_refusal(self):
        """Refused above `claim_group`, for the reason the `--worktree` /
        `--no-worktree` contradiction is: group names are single-use, so
        refusing after the claim burns the name on a typo."""
        tasks = self.tasks_file("a")
        self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks,
                    "--foreground", expect_rc=1)
        out = self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks)
        self.assertEqual(out["spawned"], 1)

    def test_a_single_run_still_accepts_foreground(self):
        """The flag means something on `start`; only `batch start` is refused."""
        out = self.bridge("start", "--sandbox", "read-only", "--foreground", "go")
        self.assertEqual(out["state"], "completed")


if __name__ == "__main__":
    unittest.main()
