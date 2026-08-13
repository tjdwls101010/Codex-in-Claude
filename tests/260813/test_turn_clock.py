"""Why the one-turn-per-thread check reads `codex_started_at`, not `started_at`.

`started_at` is stamped when the run object is built. Under `--as-ready` that is
deliberately while the predecessor's turn is still running, so the two fields
stop being interchangeable: a correct chained member has

    started_at  <  predecessor.ended_at  <  codex_started_at

Any overlap test fed the first of those reports a violation on a run where the
two turns never coexisted. The natural reaction to that — loosening the overlap
test — would remove the one check standing between this design and the rollout
corruption F4 reproduced, so the reason it must be the second field is worth a
test of its own rather than a comment.
"""

from __future__ import annotations

import unittest

from test_as_ready import AsReadyBase


class TwoClocks(AsReadyBase):

    def chained_pair(self):
        """A phase-2 member built while its predecessor is still running."""
        _, members = self.phase_one(hang=10, n=2)
        self.bridge("stop", "--run", members[0])
        self.wait_terminal(members[0])
        out = self.phase_two()
        second = out["runs"][1]["run_id"]
        self.wait_for_state(second, "waiting")
        self.bridge("stop", "--run", members[1])
        self.wait_terminal(members[1])
        self.wait_for_state(second, "running", timeout=30)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        return self.meta(members[1]), self.meta(second)

    def test_the_two_clocks_disagree_by_construction(self):
        pred, member = self.chained_pair()
        self.assertLess(member["started_at"], pred["ended_at"],
                        "the member was built before its predecessor ended — "
                        "that is what --as-ready does")
        self.assertGreater(member["codex_started_at"], pred["ended_at"],
                           "but its turn began after")

    def test_the_creation_clock_would_report_a_false_overlap(self):
        """Documenting the trap, so nobody re-points the check back."""
        pred, member = self.chained_pair()
        self.assertEqual(member["thread_id"], pred["thread_id"])
        overlaps = (member["started_at"] < pred["ended_at"]
                    and pred["started_at"] < (member["ended_at"] or "9"))
        self.assertTrue(overlaps,
                        "if this ever stops being true, the note on soak "
                        "oracle 5 is stale")

    def test_the_turn_clock_reports_no_overlap(self):
        pred, member = self.chained_pair()
        self.assertFalse(
            member["codex_started_at"] < pred["ended_at"],
            "the turns really did overlap, which is a defect and not a "
            "measurement artefact")

    def test_an_ordinary_run_records_both(self):
        """The new field is not `--as-ready`-only; every run has a turn."""
        out = self.bridge("start", "--sandbox", "read-only", "go")
        m = self.wait_terminal(out["run_id"])
        self.assertIsNotNone(m["codex_started_at"])
        self.assertGreaterEqual(m["codex_started_at"], m["started_at"])


if __name__ == "__main__":
    unittest.main()
