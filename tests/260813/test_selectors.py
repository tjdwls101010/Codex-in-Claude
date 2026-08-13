"""D3 — a second selector flag must be refused, not silently dropped.

`refuse_run_and_group` already exists and already says why (R28): two selectors
name different questions, and answering one of them while reporting success is
how a caller ends up believing a group was stopped when one run was. The rule
was fixed for `--run` + `--group` and never generalized to the selector sitting
next to them, so `stop --run X --all` still answers only the first branch that
matches.

The last test here is the boundary. `status --all` is not a selector — it is a
display modifier that suppresses a row-count cap — so refusing it would be the
opposite error, breaking a combination that means something.
"""

from __future__ import annotations

import unittest

from helpers import BridgeCase


class CompetingSelectors(BridgeCase):

    def start_one(self):
        return self.bridge("start", "--sandbox", "read-only", "go")["run_id"]

    def test_stop_refuses_a_run_and_all_together(self):
        run_id = self.start_one()
        out = self.bridge("stop", "--run", run_id, "--all", expect_rc=1)
        self.assertIn("--all", out["error"])
        self.assertIn("--run", out["error"])

    def test_stop_refuses_a_group_and_all_together(self):
        tasks = self.tasks_file("a")
        self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks)
        out = self.bridge("stop", "--group", "g", "--all", expect_rc=1)
        self.assertIn("--all", out["error"])
        self.assertIn("--group", out["error"])

    def test_stop_still_refuses_a_run_and_a_group_together(self):
        """R28's original case, kept so generalizing does not lose it."""
        run_id = self.start_one()
        out = self.bridge("stop", "--run", run_id, "--group", "g", expect_rc=1)
        self.assertIn("--run", out["error"])
        self.assertIn("--group", out["error"])

    def test_stop_alone_is_not_refused(self):
        """The refusal must fire on a second selector, not on any --all."""
        self.start_one()
        out = self.bridge("stop", "--all")
        self.assertIn("stopped", out)

    def test_status_accepts_a_run_and_all_together(self):
        """`--all` on `status` lifts a row-count cap; it selects nothing.

        Refusing this would be the same defect with the sign flipped — a
        combination that means something, turned into an error.
        """
        run_id = self.start_one()
        out = self.bridge("status", "--run", run_id, "--all")
        self.assertEqual([r["run_id"] for r in out["runs"]], [run_id])


if __name__ == "__main__":
    unittest.main()
