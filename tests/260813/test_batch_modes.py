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
`status --group --follow` — so the fix is to refuse the flag, not to build a
second supervision model for it.

The 260823 round moved that refusal one layer out. The flag was accepted by the
parser and rejected by the command, which meant `batch start --help` had to
carry the sentence "Refused on `batch start`" — an option surface documenting a
hole in itself. `batch start` no longer offers the argument at all, so argparse
refuses it and the help is honest by having nothing to say. What this file pins
is unchanged: the flag cannot get through, and the caller is told where the
working way to wait is. That second half now lives in `batch start --help`'s
epilog rather than in an error string, which is where a caller reads it before
guessing at a flag rather than after.
"""

from __future__ import annotations

import unittest

from helpers import BridgeCase


class ForegroundIsNotABatchMode(BridgeCase):

    def test_batch_start_refuses_foreground(self):
        tasks = self.tasks_file("a", "b")
        p = self.bridge_raw("batch", "start", "--group", "g",
                            "--tasks-file", tasks, "--foreground")
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("--foreground", p.stderr)

    def test_the_option_surface_does_not_offer_it(self):
        """A refusal a caller meets after typing the flag is worse than a
        listing that never offered it."""
        p = self.bridge_raw("batch", "start", "--help")
        self.assertNotIn("--foreground", p.stdout)

    def test_the_help_names_a_way_to_wait_for_the_batch(self):
        """Removing the only obvious way to block is a dead end unless the
        working one is somewhere the caller is already looking."""
        p = self.bridge_raw("batch", "start", "--help")
        self.assertIn("--follow", p.stdout)

    def test_the_group_name_survives_the_refusal(self):
        """Refused above `claim_group`, for the reason the `--worktree` /
        `--no-worktree` contradiction is: group names are single-use, so
        refusing after the claim burns the name on a typo."""
        tasks = self.tasks_file("a")
        p = self.bridge_raw("batch", "start", "--group", "g",
                            "--tasks-file", tasks, "--foreground")
        self.assertEqual(p.returncode, 2, p.stdout)
        out = self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks)
        self.assertEqual(out["spawned"], 1)

    def test_a_single_run_still_accepts_foreground(self):
        """The flag means something on `start`; only `batch start` is refused."""
        out = self.bridge("start", "--sandbox", "read-only", "--foreground", "go")
        self.assertEqual(out["state"], "completed")


if __name__ == "__main__":
    unittest.main()
