"""A run's life: detached start, every terminal state, the stop ladder, and what a dead supervisor means.

`orphaned` answers "is anyone recording this run?", not "is anything still running?" — a supervisor lost to SIGKILL leaves its `codex exec` child alive and writing. Every surface that decides liveness has to ask both.
"""

from __future__ import annotations

import os
import signal
import time
import unittest

from support.harness import (BridgeCase, FIXTURES, LEGACY_PREDECESSOR, LEGACY_WAITER, alive, engine,
                             wait_until)


class DetachedStart(BridgeCase):

    def test_start_returns_a_handle_while_the_turn_is_still_running(self):
        t0 = time.monotonic()
        out = self.bridge("start", "x", env={"FAKE_CODEX_HANG": 30})
        self.assertLess(time.monotonic() - t0, 10, "start waited for the turn")
        self.assertIn(out["state"], ("starting", "running"))
        self.assertTrue(out["thread_id"])
        self.assertIn(self.row(out["run_id"])["state"], ("starting", "running"))

    def test_the_run_finishes_after_the_launcher_has_exited(self):
        out = self.bridge("start", "x")
        row = self.wait_state(out["run_id"])
        self.assertEqual((row["state"], row["exit_code"]), ("completed", 0))
        self.assertEqual(row["thread_id"], out["thread_id"])
        self.assertIsNotNone(row["ended_at"])


class TerminalStates(BridgeCase):

    def test_a_nonzero_exit_is_failed_and_the_follower_says_so(self):
        out = self.bridge("start", "x", env={"FAKE_CODEX_EXIT": 4})
        p = self.bridge_raw("log", "--run", out["run_id"], "--follow", "--follow-timeout", 30)
        self.assertIn(f"run.failed run={out['run_id']} exit=4", p.stdout)
        self.assertEqual(self.row(out["run_id"])["exit_code"], 4)

    def test_turn_failed_is_surfaced_without_reading_the_log(self):
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": FIXTURES / "turn-failed.jsonl",
                                             "FAKE_CODEX_EXIT": 1})
        row = self.wait_state(out["run_id"])
        self.assertIn("rate limit", row["turn_failed"])
        self.assertIn("rate limit", self.bridge("result", "--run", out["run_id"])["turn_failed"])

    def test_stderr_is_surfaced_without_codexs_routine_stdin_notice(self):
        out = self.bridge("start", "x", env={"FAKE_CODEX_STDERR": "boom: config broken"})
        row = self.wait_state(out["run_id"])
        self.assertIn("boom: config broken", row["stderr_tail"])
        self.assertNotIn("Reading additional input", row["stderr_tail"])

    def test_a_deadline_is_its_own_state(self):
        out = self.bridge("start", "--timeout", 1.5, "x", env={"FAKE_CODEX_HANG": 60})
        row = self.wait_state(out["run_id"], timeout=30)
        self.assertEqual(row["state"], "timed_out")
        self.assertIn("timed out", row["error"])

    def test_the_deadline_counts_from_launch_not_from_the_thread_id(self):
        t0 = time.monotonic()
        out = self.bridge("start", "--timeout", 1.5, "x", env={"FAKE_CODEX_PRE_DELAY": 8, "FAKE_CODEX_HANG": 60})
        self.assertEqual(self.wait_state(out["run_id"], timeout=30)["state"], "timed_out")
        self.assertLess(time.monotonic() - t0, 6)

    def grandchild(self, pidfile):
        pid = wait_until(lambda: pidfile.exists() and int(pidfile.read_text()), timeout=20)
        self.assertTrue(pid, "the run never started its descendant")
        self.addCleanup(lambda: alive(pid) and os.kill(pid, signal.SIGKILL))
        return pid

    def test_a_deadline_ends_the_whole_process_group(self):
        cases = [({}, "codex exits on SIGINT and leaves a descendant that ignores it"),
                 ({"FAKE_CODEX_IGNORE_SIGINT": 1}, "codex and its descendant ignore SIGINT"),
                 ({"FAKE_CODEX_IGNORE_SIGINT": 1, "FAKE_CODEX_IGNORE_SIGTERM": 1}, "only SIGKILL ends them")]
        for n, (env, why) in enumerate(cases):
            with self.subTest(why=why):
                pidfile = self.tmp / f"grandchild-{n}.pid"
                out = self.bridge("start", "--timeout", 1, "x",
                                  env={"FAKE_CODEX_HANG": 60, "FAKE_CODEX_GRANDCHILD": pidfile, **env})
                grandchild = self.grandchild(pidfile)
                self.assertEqual(self.wait_state(out["run_id"], timeout=40)["state"], "timed_out")
                self.assertTrue(wait_until(lambda: not alive(grandchild), timeout=5), "a process of the run outlived its deadline")
                self.assertFalse(alive(self.meta(out["run_id"])["codex_pid"]))

    def test_stop_ends_a_descendant_its_codex_left_behind(self):
        pidfile = self.tmp / "grandchild.pid"
        out, _m = self.running("x", FAKE_CODEX_GRANDCHILD=pidfile)
        grandchild = self.grandchild(pidfile)
        res = self.bridge("stop", "--run", out["run_id"])["stopped"][0]
        self.assertTrue(wait_until(lambda: not alive(grandchild), timeout=10), "stop left a process of the run alive")
        self.assertEqual(res["signals_sent"], ["SIGINT", "SIGKILL"], "what was sent is what is reported")

    def test_a_timed_run_that_is_stopped_is_interrupted_not_timed_out(self):
        out, _m = self.running("--timeout", 600, "x")
        self.bridge("stop", "--run", out["run_id"])
        self.assertEqual(self.wait_state(out["run_id"])["state"], "interrupted")

    def test_killing_the_whole_process_group_leaves_nothing_stuck_running(self):
        out, m = self.running("x")
        os.killpg(int(m["pgid"]), signal.SIGKILL)
        row = self.wait_state(out["run_id"])
        self.assertEqual(row["state"], "orphaned")
        self.assertIsNotNone(row["ended_at"])

    def test_a_dead_codex_leaves_its_supervisor_to_record_the_outcome(self):
        out, m = self.running("x")
        os.kill(int(m["codex_pid"]), signal.SIGKILL)
        self.assertEqual(self.wait_state(out["run_id"])["state"], "failed")


class TheLadderOrder(unittest.TestCase):
    """`core.supervisor.end_group`'s order of signals, observed at `os.killpg` — the only place the order is visible."""

    def ladder(self, **kw):
        supervisor = engine("core.supervisor")
        calls = []
        real = supervisor.os.killpg
        supervisor.os.killpg = lambda pgid, sig: calls.append(signal.Signals(sig).name)
        try:
            sent = supervisor.end_group(4242, grace=0, before_kill=lambda: calls.append("record"), **kw)
        finally:
            supervisor.os.killpg = real
        return calls, sent

    def test_a_deadline_sends_sigterm_even_after_codex_has_exited(self):
        calls, sent = self.ladder(done=lambda: True, every_rung=True)
        self.assertEqual(calls, ["SIGINT", "SIGTERM", "record", "SIGKILL"])
        self.assertEqual(sent, ["SIGINT", "SIGTERM", "SIGKILL"])

    def test_a_stop_ends_at_the_first_rung_that_suffices_then_sweeps(self):
        calls, _ = self.ladder(done=lambda: True)
        self.assertEqual(calls, ["SIGINT", "record", "SIGKILL"])

    def test_nothing_done_climbs_every_rung_once(self):
        calls, sent = self.ladder(done=lambda: False)
        self.assertEqual(calls, ["SIGINT", "SIGTERM", "record", "SIGKILL"])
        self.assertEqual(sent, ["SIGINT", "SIGTERM", "SIGKILL"])


class StopLadder(BridgeCase):
    """Signals go to the run's recorded process group, SIGINT first, escalating only if Codex does not exit."""

    def test_sigint_alone_ends_a_cooperative_run_and_keeps_its_thread(self):
        out, _m = self.running("x")
        res = self.bridge("stop", "--run", out["run_id"])["stopped"][0]
        self.assertEqual(res["signals_sent"], ["SIGINT"])
        self.assertEqual(res["thread_id"], out["thread_id"])
        self.assertEqual(self.wait_state(out["run_id"])["state"], "interrupted")

    def test_the_ladder_escalates_when_sigint_is_ignored(self):
        out, m = self.running("x", FAKE_CODEX_IGNORE_SIGINT=1)
        res = self.bridge("stop", "--run", out["run_id"], "--grace", 0.5)["stopped"][0]
        self.assertEqual(res["signals_sent"], ["SIGINT", "SIGTERM"])
        self.assertFalse(alive(m["codex_pid"]))

    def test_stopping_one_run_leaves_a_concurrent_one_running(self):
        a, am = self.running("--label", "a", "x")
        b, bm = self.running("--label", "b", "x")
        self.assertNotEqual(am["pgid"], bm["pgid"])
        self.bridge("stop", "--run", a["run_id"])
        self.wait_state(a["run_id"])
        self.assertEqual(self.row(b["run_id"])["state"], "running")
        self.assertTrue(alive(bm["codex_pid"]))

    def test_run_is_repeatable_and_all_reaches_every_live_run(self):
        a, _ = self.running("x")
        b, _ = self.running("x")
        c, _ = self.running("x")
        done = self.bridge("start", "quick")
        self.wait_state(done["run_id"])
        two = self.bridge("stop", "--run", a["run_id"], "--run", b["run_id"])["stopped"]
        self.assertEqual({s["run_id"] for s in two}, {a["run_id"], b["run_id"]})
        rest = self.bridge("stop", "--all")["stopped"]
        self.assertIn(c["run_id"], {s["run_id"] for s in rest})
        self.assertNotIn(done["run_id"], {s["run_id"] for s in rest}, "--all is the live runs only")

    def test_stopping_a_finished_run_does_not_rewrite_its_outcome(self):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        self.assertEqual(self.bridge("stop", "--run", out["run_id"])["stopped"][0]["state"], "completed")
        self.assertEqual(self.row(out["run_id"])["state"], "completed")

    def test_an_unknown_group_is_refused(self):
        self.assertIn("nope", self.bridge("stop", "--group", "nope", rc=1)["error"])


class AnOrphanThatIsStillWriting(BridgeCase):

    def test_status_calls_it_orphaned_but_counts_it_as_running(self):
        out, _m = self.orphan_still_writing("x")
        listing = self.bridge("status", "--all")
        self.assertIn(out["run_id"], listing["running"])
        self.assertNotIn(out["run_id"], listing["failed"])
        self.assertTrue(self.row(out["run_id"])["codex_still_running"])

    def test_stop_reaches_its_codex_through_the_process_group(self):
        for selector in (("--run",), ("--all",)):
            with self.subTest(selector=selector):
                out, m = self.orphan_still_writing("x")
                args = ("stop", "--run", out["run_id"]) if selector == ("--run",) else ("stop", "--all")
                self.assertIn(out["run_id"], [s["run_id"] for s in self.bridge(*args)["stopped"]])
                self.assertTrue(wait_until(lambda: not alive(m["codex_pid"]), timeout=10))

    def test_follow_does_not_announce_an_end_while_it_writes(self):
        out, _m = self.orphan_still_writing("x")
        t0 = time.monotonic()
        p = self.bridge_raw("log", "--run", out["run_id"], "--follow", "--follow-timeout", 2)
        self.assertGreaterEqual(time.monotonic() - t0, 1.5)
        self.assertIn("run.still-running", p.stdout)
        self.assertNotIn("run.orphaned", p.stdout)

    def test_its_turn_time_keeps_growing(self):
        out, _m = self.orphan_still_writing("x")
        first = self.row(out["run_id"])["codex_elapsed_seconds"]
        time.sleep(2.2)
        self.assertGreater(self.row(out["run_id"])["codex_elapsed_seconds"], first)

    def test_once_its_codex_is_gone_the_follower_ends_on_orphaned(self):
        out, m = self.orphan_still_writing("x")
        os.kill(int(m["codex_pid"]), signal.SIGKILL)
        wait_until(lambda: not alive(m["codex_pid"]), timeout=10)
        p = self.bridge_raw("log", "--run", out["run_id"], "--follow", "--follow-timeout", 10)
        self.assertIn(f"run.orphaned run={out['run_id']}", p.stdout)


class LegacyWaitingRun(BridgeCase):
    """Releases before 0.8 could leave a batch member `waiting` on its predecessor. Another install's registry can still hold one, and it must stay stoppable and must keep its thread and worktree protected."""

    def setUp(self):
        super().setUp()
        self.supervisor = self.install_legacy_registry()

    def test_it_is_live_everywhere_liveness_is_decided(self):
        self.assertEqual(self.row(LEGACY_WAITER)["state"], "waiting")
        self.assertIn(LEGACY_WAITER, self.bridge("status", "--all")["running"])
        refused = self.bridge("resume", LEGACY_PREDECESSOR, "another turn", rc=1)
        self.assertIn(LEGACY_WAITER, str(refused["live_runs"]))
        self.assertIn(LEGACY_WAITER, str(self.bridge("batch", "clean", "--group", "p2", rc=1)["running"]))
        p = self.bridge_raw("status", "--group", "p2", "--follow", "--follow-timeout", 1.5)
        self.assertRegex(p.stdout.splitlines()[-1], r"^group\.still-running group=p2 ")
        p = self.bridge_raw("log", "--run", LEGACY_WAITER, "--follow", "--follow-timeout", 1.5)
        self.assertIn("run.still-running", p.stdout)

    def test_each_stop_selector_ends_it(self):
        for args in (("--run", LEGACY_WAITER), ("--group", "p2"), ("--all",)):
            with self.subTest(args=args):
                sup = self.install_legacy_registry()
                stopped = self.bridge("stop", *args)["stopped"]
                self.assertEqual([s["run_id"] for s in stopped], [LEGACY_WAITER])
                self.assertEqual(stopped[0]["state"], "interrupted")
                self.assertTrue(wait_until(lambda: not alive(sup), timeout=10))

    def test_a_waiting_run_whose_supervisor_is_gone_is_reaped(self):
        os.killpg(self.supervisor, signal.SIGKILL)
        wait_until(lambda: not alive(self.supervisor), timeout=10)
        self.assertEqual(self.row(LEGACY_WAITER)["state"], "orphaned")


if __name__ == "__main__":
    unittest.main()
