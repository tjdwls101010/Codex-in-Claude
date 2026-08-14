"""Three reporting defects the second adversarial round found.

All three are the same shape as the round's headline work: a number or a
sentence that is not false exactly, but says something other than what a reader
will take from it.
"""

from __future__ import annotations

import json
import time
import unittest

from helpers import BridgeCase
from test_as_ready import AsReadyBase


class ElapsedMustNotCountTheWait(AsReadyBase):
    """`elapsed_seconds` is measured from `started_at`, which is when the run
    object was created — for a chained member, before its predecessor finished.

    This round added `codex_started_at` precisely because `started_at` stopped
    being a reliable clock the moment `--as-ready` shipped, and then left the
    one field callers actually read to judge "is this taking too long" measuring
    from the old one. A member queued for an hour and running for a minute
    reports sixty-one minutes of work.
    """

    def test_a_waiting_member_reports_no_turn_time_yet(self):
        self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")
        row = self.bridge("status", "--run", rid)["runs"][0]
        self.assertIsNotNone(row["elapsed_seconds"],
                             "how long it has existed is still a real question")
        self.assertIsNone(row.get("codex_elapsed_seconds"),
                          "no turn has started, so it has taken no time")

    def test_turn_time_excludes_the_wait(self):
        _, members = self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")
        time.sleep(3)
        self.bridge("stop", "--run", members[0])
        self.wait_terminal(members[0])
        self.wait_terminal(rid, timeout=40)
        row = self.bridge("status", "--run", rid)["runs"][0]
        self.assertLess(
            row["codex_elapsed_seconds"], row["elapsed_seconds"],
            "the turn cannot have taken as long as the run has existed — the "
            "difference is the wait")

    def test_an_ordinary_run_reports_both(self):
        out = self.bridge("start", "--sandbox", "read-only", "go")
        self.wait_terminal(out["run_id"])
        row = self.bridge("status", "--run", out["run_id"])["runs"][0]
        self.assertIsNotNone(row["codex_elapsed_seconds"])
        self.assertLessEqual(row["codex_elapsed_seconds"], row["elapsed_seconds"])


class ATruncatedTailIsNotSilence(BridgeCase):
    """`read_events` drops a trailing line with no newline, on the reasoning
    that the next poll will see it once it completes. For a run that has already
    reached a terminal state there is no next poll — Codex was killed mid-write,
    or crashed — and the dropped bytes are then reported as nothing at all.

    Same silent drop the round fixed for unparseable lines, arriving from the
    other side: this one is not unparseable, it is simply never read.
    """

    def test_a_stream_cut_mid_write_says_so(self):
        out = self.bridge("start", "--sandbox", "read-only", "go")
        run_id = out["run_id"]
        self.wait_terminal(run_id)
        events = self.project / ".codex-runs" / run_id / "events.jsonl"
        with events.open("a", encoding="utf-8") as fh:
            fh.write('{"type":"item.completed","item":{"id":"item_9"')
        row = self.bridge("status", "--run", run_id)["runs"][0]
        self.assertEqual(row.get("unparsed_events"), 1,
                         "a terminal run's half-written last line is never "
                         "coming back, so nothing is waiting for it")

    def test_a_complete_stream_still_reports_nothing(self):
        out = self.bridge("start", "--sandbox", "read-only", "go")
        self.wait_terminal(out["run_id"])
        row = self.bridge("status", "--run", out["run_id"])["runs"][0]
        self.assertNotIn("unparsed_events", row)


class TheCleanTreeSentence(BridgeCase):
    """`uncommitted_clause` special-cased "unknown" and left zero reading as a
    double negative around a number: "it does not contain the 0 uncommitted
    file(s) that exist in theirs". True, and a strange way to say the caller's
    tree has nothing this one is missing."""

    def preamble(self):
        argv = self.invocations()[0]["argv"]
        return "\n".join(a for a in argv if "Working tree:" in a)

    def start_batch(self):
        tasks = self.tasks_file("one", "two")
        return self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks)

    def test_a_clean_tree_is_not_described_as_zero_files_that_exist(self):
        self.start_batch()
        text = self.preamble()
        self.assertTrue(text, "no worktree preamble reached codex")
        self.assertNotIn("the 0 uncommitted file(s) that exist", text)

    def test_a_dirty_tree_still_says_how_many(self):
        (self.project / "dirty.txt").write_text("x\n")
        self.start_batch()
        self.assertIn("1 uncommitted file(s)", self.preamble())


if __name__ == "__main__":
    unittest.main()
