"""What the adversarial round found in `--as-ready` after it passed its own tests.

Every one of these was reachable by running documented commands, and none was
caught by the twenty tests written alongside the feature — which is the whole
argument for running the round rather than trusting a green suite.

Two of them were found twice, independently: the chain refusal by a static lens
reading `refuse_concurrent_turn` and by an agent driving the real CLI who simply
chained a third phase and got refused, and the seventh state tuple by two lenses
that came at `status` from different directions.
"""

from __future__ import annotations

import json
import unittest

from test_as_ready import AsReadyBase


class AChainLongerThanOneHop(AsReadyBase):
    """`refuse_concurrent_turn` exempted exactly one run id — the direct
    predecessor — so registering phase 3 while phase 1 was still running was
    refused, naming the grandparent as a live turn.

    Phase 3 could never have raced it: phase 3 waits for phase 2, which waits
    for phase 1. The whole chain is ordered by construction. Refusing it forces
    the caller to poll each stage until it visibly starts before the next can be
    registered, which is the waiting `--as-ready` exists to remove.
    """

    def build_chain(self):
        _, p1 = self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        p2 = self.bridge("batch", "start", "--group", "p2",
                         "--resume-from", "p1", "--as-ready",
                         "--tasks-file", self.tasks_file("second"))
        second = p2["runs"][0]["run_id"]
        self.wait_for_state(second, "waiting")
        return p1[0], second

    def test_phase_three_can_be_registered_while_phase_one_still_runs(self):
        first, second = self.build_chain()
        self.assertEqual(self.meta(first)["state"], "running",
                         "the premise: the grandparent is still mid-turn")
        third = self.bridge("batch", "start", "--group", "p3",
                            "--resume-from", "p2", "--as-ready",
                            "--tasks-file", self.tasks_file("third"))
        self.assertEqual(third["spawned"], 1)

    def test_the_third_member_waits_for_the_second_not_the_first(self):
        _first, second = self.build_chain()
        third = self.bridge("batch", "start", "--group", "p3",
                            "--resume-from", "p2", "--as-ready",
                            "--tasks-file", self.tasks_file("third"))
        rid = third["runs"][0]["run_id"]
        self.assertEqual(self.meta(rid)["waits_for"], second)

    def test_an_unrelated_live_turn_on_the_thread_is_still_refused(self):
        """The exemption follows the caller's own wait chain. A run on the same
        thread that is not in it must still refuse — otherwise the guard is
        gone rather than narrowed."""
        first, _second = self.build_chain()
        thread = self.meta(first)["thread_id"]
        refused = self.bridge("resume", thread, "an unrelated turn", expect_rc=1)
        self.assertIn("live turn", refused["error"])

    def test_a_plain_resume_is_still_refused_once_the_waiter_is_running(self):
        """A waiter is not a free pass for someone else. Phase 2 is given its
        own hang so its turn is still in flight when the resume lands —
        otherwise the fake finishes in under a second and the run is refused
        for having ended, which proves nothing about the guard."""
        _, p1 = self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        p2 = self.bridge("batch", "start", "--group", "p2",
                         "--resume-from", "p1", "--as-ready",
                         "--tasks-file", self.tasks_file("second"),
                         env_extra={"FAKE_CODEX_HANG": 10})
        second = p2["runs"][0]["run_id"]
        self.wait_for_state(second, "waiting")
        self.bridge("stop", "--run", p1[0])
        self.wait_terminal(p1[0])
        self.wait_for_state(second, "running", timeout=30)
        thread = self.meta(second)["thread_id"]
        refused = self.bridge("resume", thread, "squeeze in", expect_rc=1)
        self.assertIn("live turn", refused["error"])


class TheSeventhStateTuple(AsReadyBase):
    """`ACTIVE_STATES` replaced six hand-written tuples and missed a seventh:
    `cmd_status`'s top-level summary, which reads `("running", "stalled")`.

    A waiting member appears in `runs[]` with `state: "waiting"` and in none of
    `running`, `done` or `failed`. The same run through `status --group` is
    counted as running, so one field name means two different things depending
    on which view you asked. The tuple was also already missing `starting`
    before this round, which is the same hole at a shorter timescale.
    """

    def waiting_member(self):
        self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")
        return rid

    def test_the_plain_view_counts_a_waiting_member_as_running(self):
        rid = self.waiting_member()
        out = self.bridge("status")
        self.assertIn(rid, out["running"],
                      "the row says `waiting` but the summary counts it nowhere")

    def test_the_two_views_agree_about_the_same_run(self):
        rid = self.waiting_member()
        plain = self.bridge("status")
        grouped = self.bridge("status", "--group", "p2")
        self.assertEqual(rid in plain["running"], rid in grouped["running"],
                         "`running` means two different things depending on "
                         "which view answered")

    def test_every_row_lands_in_exactly_one_bucket(self):
        self.waiting_member()
        out = self.bridge("status", "--all")
        buckets = set(out["running"]) | set(out["done"]) | set(out["failed"])
        missing = [r["run_id"] for r in out["runs"]
                   if r["run_id"] not in buckets]
        self.assertEqual(missing, [],
                         "runs present in `runs` and counted in no summary")


class OneCorruptRunMustNotKillTheFeature(AsReadyBase):
    """The unreadable-run guard appended every unparseable run in the project,
    with no thread filter — and `--as-ready` cannot pass `--force`, which was
    the only way past it. One corrupt run anywhere made the feature permanently
    unusable, and no command removes a single run.

    An unreadable run's thread id is recoverable: `events.jsonl` is a separate
    file, and the thread is announced in it. Recovering it turns "block
    everything" into "block the thread that might actually be at risk".
    """

    def corrupt_unrelated_run(self):
        out = self.bridge("start", "--sandbox", "read-only", "unrelated")
        self.wait_terminal(out["run_id"])
        (self.project / ".codex-runs" / out["run_id"] / "meta.json").write_text("{")
        return out["run_id"]

    def test_a_corrupt_run_on_another_thread_does_not_block_as_ready(self):
        self.corrupt_unrelated_run()
        self.phase_one(hang=8, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1)
        self.assertEqual(out["spawned"], 1)

    def test_a_corrupt_run_on_another_thread_does_not_block_a_plain_resume(self):
        self.corrupt_unrelated_run()
        fresh = self.bridge("start", "--sandbox", "read-only", "go")
        self.wait_terminal(fresh["run_id"])
        again = self.bridge("resume", fresh["thread_id"], "more")
        self.assertIn("run_id", again)

    def test_a_corrupt_run_whose_thread_cannot_be_recovered_still_refuses(self):
        """Its events stream is where the thread id is recovered from. With
        that gone too, nothing can rule it out and the guard must hold."""
        out = self.bridge("start", "--sandbox", "read-only", "go")
        self.wait_terminal(out["run_id"])
        run_dir = self.project / ".codex-runs" / out["run_id"]
        (run_dir / "meta.json").write_text("{")
        (run_dir / "events.jsonl").write_text("")
        fresh = self.bridge("start", "--sandbox", "read-only", "other")
        self.wait_terminal(fresh["run_id"])
        refused = self.bridge("resume", fresh["thread_id"], "more", expect_rc=1)
        self.assertIn(out["run_id"], json.dumps(refused))

    def test_the_refusal_says_what_it_actually_found(self):
        """The message claimed a live turn on the thread. When an unreadable
        run is what triggered it, there may be no live turn at all — the guard
        is refusing because it cannot tell, which is a different sentence and
        has a different remedy."""
        out = self.bridge("start", "--sandbox", "read-only", "go")
        self.wait_terminal(out["run_id"])
        run_dir = self.project / ".codex-runs" / out["run_id"]
        (run_dir / "meta.json").write_text("{")
        (run_dir / "events.jsonl").write_text("")
        fresh = self.bridge("start", "--sandbox", "read-only", "other")
        self.wait_terminal(fresh["run_id"])
        refused = self.bridge("resume", fresh["thread_id"], "more", expect_rc=1)
        self.assertNotIn("already has a live turn", refused["error"])
        self.assertIn(str(run_dir), json.dumps(refused),
                      "the remedy is removing that directory, so name it")


class DoctorDoesNotInventACollision(AsReadyBase):
    """`doctor` grouped a waiting member with the predecessor it is queued
    behind and reported them as uncoordinated concurrent writers — "none of you
    can tell another agent's change from your own" — about a run that has not
    started a process and cannot until the other one ends."""

    def test_a_waiter_and_its_predecessor_are_not_reported_as_colliding(self):
        self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")
        report = self.bridge("doctor", expect_rc=None) if False else \
            json.loads(self.bridge_raw("doctor").stdout.strip().splitlines()[-1])
        text = json.dumps(report.get("warnings") or [])
        self.assertNotIn(
            rid, text,
            "doctor named a waiting member as a live concurrent writer")


if __name__ == "__main__":
    unittest.main()
