"""B31 — `batch start --resume-from --as-ready` starts each member as its own
predecessor finishes, instead of waiting for the slowest of the previous group.

Today `--resume-from` is a barrier: `pair_with_previous` refuses the whole batch
while any previous member is live. That barrier is not a concurrency
requirement. Its own comment gives the reason — checking per member would refuse
only after earlier tasks had already resumed, leaving a phase 2 half started
against a phase 1 half finished. It exists to prevent a partial start. The
invariant it is standing in for is one turn per thread, and that is per thread,
not per group: member 3's phase 2 is safe to begin the moment member 3's phase 1
is done, whatever member 1 is doing.

No group supervisor and no queue, because a queued run with no supervisor
process is D34 — `reap` brands it `orphaned` within thirty seconds. Each
phase-2 member spawns its own supervisor immediately, exactly as today, and that
supervisor waits before it spawns Codex.

The ordering asserted below is impossible under a barrier, and that is the whole
claim: a phase-2 member starts AFTER its own predecessor ends and BEFORE the
slowest phase-1 member ends.
"""

from __future__ import annotations

import json
import os
import signal
import time
import unittest

from helpers import BridgeCase


class AsReadyBase(BridgeCase):

    def phase_one(self, *, hang=0, n=2, group="p1"):
        tasks = self.tasks_file(*[f"p1 task {i}" for i in range(n)])
        out = self.bridge("batch", "start", "--group", group,
                          "--tasks-file", tasks,
                          env_extra={"FAKE_CODEX_HANG": hang} if hang else None)
        return out, [r["run_id"] for r in out["runs"]]

    def phase_two(self, *, group="p2", previous="p1", n=2, extra=(), **kw):
        tasks = self.tasks_file(*[f"p2 task {i}" for i in range(n)])
        return self.bridge("batch", "start", "--group", group,
                           "--resume-from", previous, "--as-ready",
                           "--tasks-file", tasks, *extra, **kw)

    def wait_for_state(self, run_id, state, timeout=30):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.meta(run_id).get("state") == state:
                return self.meta(run_id)
            time.sleep(0.05)
        self.fail(f"{run_id} never reached {state!r} "
                  f"(last: {self.meta(run_id).get('state')})")


class PipelineOrdering(AsReadyBase):
    """Phase 1 with two members that finish at very different times.

    The spread comes from stopping one of them rather than from per-member
    timings: the fake `codex` reads its hang from the environment, which is per
    batch, and `stop --run` reaches exactly one member. That also makes the
    releasing terminal state `interrupted` rather than `completed`, which is the
    case worth covering — the rule is that ANY terminal state releases.
    """

    def setUp(self):
        super().setUp()
        _, self.members = self.phase_one(hang=10, n=2)
        self.bridge("stop", "--run", self.members[0])
        self.wait_terminal(self.members[0])

    def tearDown(self):
        self.bridge_raw("stop", "--all")

    def test_the_two_predecessors_really_are_in_different_states(self):
        """The premise. With both live the batch is refused outright, and with
        both finished there is no barrier left to beat."""
        self.assertEqual(self.meta(self.members[0])["state"], "interrupted")
        self.assertNotIn(self.meta(self.members[1])["state"],
                         ("completed", "failed", "interrupted", "orphaned",
                          "timed_out"))

    def test_phase_two_starts_at_all_while_a_predecessor_is_live(self):
        """A barrier refuses this outright — that is the whole difference."""
        out = self.phase_two()
        self.assertEqual(out["spawned"], 2)

    def test_the_ready_member_starts_before_the_slow_predecessor_ends(self):
        out = self.phase_two()
        first = out["runs"][0]["run_id"]
        self.wait_for_state(first, "running")
        started = self.meta(first)["codex_started_at"]
        self.assertIsNotNone(started, "codex_started_at was never recorded")
        self.assertGreater(
            started, self.meta(self.members[0])["ended_at"],
            "a member started before its own predecessor finished — that is "
            "the invariant, not the feature")
        self.assertIsNone(
            self.meta(self.members[1])["ended_at"],
            "the slow predecessor had already finished, so this proves nothing")

    def test_the_other_member_waits_for_its_own_predecessor(self):
        out = self.phase_two()
        second = out["runs"][1]["run_id"]
        # `waits_for` is in meta before the supervisor is handed the run, but
        # `waiting` is written by that supervisor — and `batch start` returns as
        # soon as it has a thread id, which for a chained member is the
        # predecessor's and is therefore known immediately.
        self.assertEqual(self.meta(second)["waits_for"], self.members[1])
        self.wait_for_state(second, "waiting")

    def test_the_waiter_starts_once_its_predecessor_finishes(self):
        out = self.phase_two()
        second = out["runs"][1]["run_id"]
        self.wait_for_state(second, "waiting")
        self.bridge("stop", "--run", self.members[1])
        self.wait_terminal(self.members[1])
        m = self.wait_for_state(second, "running", timeout=30)
        self.assertGreater(m["codex_started_at"],
                           self.meta(self.members[1])["ended_at"])


class WhatTheCallerGetsBack(AsReadyBase):

    def test_batch_start_does_not_block_on_the_thread_id_handshake(self):
        """`create_run` polls up to THREAD_ID_WAIT for a thread id and breaks
        only on that or a terminal state. A waiting member reaches neither, so
        without a third break condition the command whose whole point is not
        making the caller wait blocks fifteen seconds per member."""
        self.phase_one(hang=8)
        t0 = time.monotonic()
        self.phase_two()
        self.assertLess(time.monotonic() - t0, 12,
                        "batch start --as-ready blocked on the handshake")

    def test_a_waiting_member_still_reports_the_thread_it_will_continue(self):
        self.phase_one(hang=8)
        out = self.phase_two()
        for row in out["runs"]:
            self.assertIsNotNone(row.get("thread_id"),
                                 "the thread is inherited from the predecessor, "
                                 "so it is known before Codex starts")


class TimeoutBoundsTheTurnNotTheWait(AsReadyBase):
    """`--timeout` is consumed by `proc.wait()`, which happens after the wait
    loop has already released — so a deadline a caller sets to keep an
    unattended pipeline honest does not apply while a member is queued.

    That is documented, and documenting it is why it needs a test: a later
    change that made the deadline cover the wait too would leave the sentence
    quietly wrong, which is the failure the doc-versus-CLI checks exist for.
    """

    def test_a_waiting_member_is_not_timed_out_while_it_waits(self):
        self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1, extra=("--timeout", "1"))
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")
        time.sleep(3)
        self.assertEqual(
            self.meta(rid)["state"], "waiting",
            "a 1-second --timeout ended a wait it does not bound")

    def test_the_deadline_still_applies_once_the_turn_starts(self):
        """The other half: the flag must not become a no-op for chained
        members either."""
        _, members = self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1, extra=("--timeout", "1"),
                             env_extra={"FAKE_CODEX_HANG": 20})
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")
        self.bridge("stop", "--run", members[0])
        self.wait_terminal(members[0])
        m = self.wait_terminal(rid, timeout=30)
        self.assertEqual(m["state"], "timed_out")


class WaitingIsVisibleEverywhere(AsReadyBase):
    """`waiting` is not in TERMINAL_STATES, but several sites test membership of
    a hardcoded ACTIVE tuple instead, and a state missing from both is invisible
    rather than merely unhandled."""

    def running_group(self):
        self.phase_one(hang=8)
        return self.phase_two()

    def test_a_group_of_waiters_is_not_reported_as_completed(self):
        out = self.running_group()
        status = self.bridge("status", "--group", "p2")
        self.assertNotEqual(status["group_state"], "completed",
                            "a group whose members have not started anything "
                            "cannot be done")
        for r in out["runs"]:
            self.assertIn(self.meta(r["run_id"])["state"],
                          ("waiting", "running", "starting", "completed"))

    def test_follow_does_not_return_on_its_first_tick(self):
        self.running_group()
        t0 = time.monotonic()
        p = self.bridge_raw("status", "--group", "p2", "--follow",
                            "--follow-timeout", "3")
        self.assertGreaterEqual(time.monotonic() - t0, 2.5,
                                "--follow returned immediately, so it read the "
                                "waiting members as a finished group")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_stop_group_reaches_a_waiting_member(self):
        out = self.running_group()
        stopped = self.bridge("stop", "--group", "p2")
        self.assertEqual(
            sorted(s["run_id"] for s in stopped["stopped"]),
            sorted(r["run_id"] for r in out["runs"]),
            "a waiting member was filtered out of stop's targets")
        for s in stopped["stopped"]:
            self.assertTrue(s.get("signalled"),
                            f"not signalled: {s.get('reason')}")

    def test_stop_run_finds_a_process_group_to_signal(self):
        out = self.running_group()
        rid = out["runs"][0]["run_id"]
        stopped = self.bridge("stop", "--run", rid)
        self.assertNotEqual(stopped["stopped"][0].get("reason"),
                            "no process group recorded")


class ADeadWaiterIsNoticed(AsReadyBase):
    """`reap` returns early for any state outside ("running", "starting"), so a
    waiter whose supervisor is killed would sit in `waiting` forever — blocking
    `batch clean`, further chaining, and every implicit-target command."""

    def test_a_killed_waiter_becomes_orphaned(self):
        self.phase_one(hang=10)
        out = self.phase_two()
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")
        os.kill(int(self.meta(rid)["supervisor_pid"]), signal.SIGKILL)
        deadline = time.time() + 20
        while time.time() < deadline:
            row = self.bridge("status", "--run", rid)["runs"][0]
            if row["state"] == "orphaned":
                return
            time.sleep(0.2)
        self.fail(f"still {self.meta(rid)['state']!r} after its supervisor died")

    def test_a_live_waiter_is_not_orphaned_by_being_looked_at(self):
        """The trap on the other side: `reap` judges liveness from
        `supervisor_pid`, which is written only after Codex spawns. Teaching it
        about `waiting` without recording the pid first reproduces D34 exactly —
        every waiter branded orphaned on the first `status` call."""
        self.phase_one(hang=10)
        out = self.phase_two()
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")
        for _ in range(6):
            row = self.bridge("status", "--run", rid)["runs"][0]
            self.assertNotEqual(row["state"], "orphaned",
                                "a waiting member with a live supervisor was "
                                "reaped as dead")
            time.sleep(0.2)


class AFailedPredecessorStillReleases(AsReadyBase):
    """Today's barrier does not look at phase 1's success either — it checks
    liveness only. Any terminal state releases, and 'fix what went wrong' is a
    legitimate phase-2 task; what must not happen is the successor not being
    able to tell."""

    def test_a_failed_predecessor_lets_its_successor_start(self):
        tasks = self.tasks_file("will fail")
        self.bridge("batch", "start", "--group", "p1", "--tasks-file", tasks,
                    env_extra={"FAKE_CODEX_EXIT": 3})
        p1 = self.bridge("status", "--group", "p1")["runs"][0]["run_id"]
        self.wait_terminal(p1)
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.wait_terminal(rid, timeout=40)
        self.assertIn(self.meta(rid)["state"], ("completed", "failed"))

    def test_the_successor_records_how_its_predecessor_ended(self):
        tasks = self.tasks_file("will fail")
        self.bridge("batch", "start", "--group", "p1", "--tasks-file", tasks,
                    env_extra={"FAKE_CODEX_EXIT": 3})
        p1 = self.bridge("status", "--group", "p1")["runs"][0]["run_id"]
        self.wait_terminal(p1)
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.wait_terminal(rid, timeout=40)
        self.assertEqual(self.meta(rid).get("predecessor_state"), "failed")


class MutualExclusionClosesBehindAWaiter(AsReadyBase):
    """Keeping `waiting` out of TERMINAL_STATES is what preserves one turn per
    thread: the waiter publishes with its predecessor's thread id and a
    non-terminal state, so a third run against that thread is still refused.
    Without a test, a future tidy-up deletes the thing holding the invariant."""

    def test_a_third_turn_on_the_same_thread_is_still_refused(self):
        _, members = self.phase_one(hang=10)
        out = self.phase_two()
        self.wait_for_state(out["runs"][0]["run_id"], "waiting")
        thread = self.meta(members[0])["thread_id"]
        refused = self.bridge("resume", thread, "a third turn", expect_rc=1)
        self.assertIn("live turn", refused["error"])


class Refusals(AsReadyBase):

    def test_as_ready_without_resume_from_is_refused(self):
        out = self.bridge("batch", "start", "--group", "g", "--as-ready",
                          "--tasks-file", self.tasks_file("a"), expect_rc=1)
        self.assertIn("--resume-from", out["error"])

    def test_that_refusal_does_not_burn_the_group_name(self):
        self.bridge("batch", "start", "--group", "g", "--as-ready",
                    "--tasks-file", self.tasks_file("a"), expect_rc=1)
        again = self.bridge("batch", "start", "--group", "g",
                            "--tasks-file", self.tasks_file("a"))
        self.assertEqual(again["spawned"], 1)

    def test_as_ready_with_force_is_refused(self):
        self.phase_one()
        out = self.phase_two(extra=("--force",), expect_rc=1)
        self.assertIn("--force", out["error"])

    def test_resume_from_without_as_ready_still_barriers(self):
        """The default does not change."""
        self.phase_one(hang=8)
        out = self.bridge("batch", "start", "--group", "p2",
                          "--resume-from", "p1",
                          "--tasks-file", self.tasks_file("a", "b"),
                          expect_rc=1)
        self.assertIn("still has members running", out["error"])


if __name__ == "__main__":
    unittest.main()
