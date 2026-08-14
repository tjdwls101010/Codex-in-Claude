"""What the Codex review found in the wait chain, and two tests it found wanting.

Codex reviewed this round through the group mode the round added — four
reviewers on four targets, run as one batch. Two of them converged on the same
gap from opposite directions, one reading the implementation and one reading the
test suite, which is the signal worth acting on.

The test-quality half is the uncomfortable one: a reviewer asked which of these
tests were written to pass rather than to catch, and found one whose setup
cannot fail for the reason it claims and one whose stated rationale is
backwards. Both are below.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
import unittest
from pathlib import Path

from helpers import BRIDGE, BridgeCase
from test_as_ready import AsReadyBase

sys.path.insert(0, str(BRIDGE.parent))


class AWaitingRunProtectsItsThread(AsReadyBase):
    """The claim `--as-ready` rests on: a member parked in `waiting` still holds
    its thread against a third turn, because `waiting` is not terminal.

    The round's original test for this put a LIVE predecessor and a waiting
    member on the thread together — so the live predecessor alone would have
    caused the refusal, and the test could not tell the two apart. It passed
    whether or not `waiting` counted for anything.

    Isolating it means the predecessor must be terminal while the member is
    still waiting, which does not happen on its own: the member starts the
    moment its predecessor ends. SIGSTOP freezes the waiter's supervisor without
    killing it, so `reap` still sees a live pid and leaves the state alone.
    """

    def test_a_waiting_member_alone_refuses_a_third_turn(self):
        _, members = self.phase_one(hang=10, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")

        sup = int(self.meta(rid)["supervisor_pid"])
        os.kill(sup, signal.SIGSTOP)
        self.addCleanup(lambda: os.kill(sup, signal.SIGCONT))
        self.bridge("stop", "--run", members[0])
        self.wait_terminal(members[0])

        self.assertEqual(self.meta(rid)["state"], "waiting",
                         "the setup needs a waiting member and a finished "
                         "predecessor at the same time")
        thread = self.meta(members[0])["thread_id"]
        refused = self.bridge("resume", thread, "a third turn", expect_rc=1)
        self.assertIn(rid, json.dumps(refused),
                      "the waiting member is what must refuse this, and it must "
                      "be named as the reason")


class ANamedTargetWaitsToo(AsReadyBase):
    """A `--resume-from` task may name its own `resume` target and keeps it.
    Under `--as-ready` it must wait for THAT target — leaving it unset reported
    the task as paired while it started immediately, so the one shape the flag
    promises to order was the one it did not."""

    def named_batch(self, ref_for_first):
        tasks = self.tmp / "named.jsonl"
        tasks.write_text(
            json.dumps({"kind": "resume", "prompt": "a",
                        "resume": ref_for_first}) + "\n"
            + json.dumps({"kind": "resume", "prompt": "b"}) + "\n")
        return tasks

    def test_a_task_that_names_its_target_waits_for_it(self):
        _, members = self.phase_one(hang=10, n=2)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.bridge("batch", "start", "--group", "p2",
                          "--resume-from", "p1", "--as-ready",
                          "--tasks-file", self.named_batch(members[1]))
        first = out["runs"][0]["run_id"]
        self.assertEqual(self.meta(first)["waits_for"], members[1],
                         "it named member 1, so member 1 is what it waits for")
        self.wait_for_state(first, "waiting")

    def test_a_thread_id_target_is_resolved_to_a_run_id(self):
        """`resume` takes a run id, a thread id or a prefix; `waits_for` is
        joined to the runs directory as a name. Storing the ref raw made the
        supervisor call a perfectly readable run unreadable."""
        _, members = self.phase_one(hang=10, n=2)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        thread = self.meta(members[1])["thread_id"]
        out = self.bridge("batch", "start", "--group", "p2",
                          "--resume-from", "p1", "--as-ready",
                          "--tasks-file", self.named_batch(thread))
        first = out["runs"][0]["run_id"]
        self.assertEqual(self.meta(first)["waits_for"], members[1])
        self.wait_for_state(first, "waiting")
        self.assertNotEqual(self.meta(first)["state"], "failed")

    def test_a_target_outside_the_registry_is_refused(self):
        """Nothing can watch a ref this project has never seen reach a terminal
        state, so pairing it silently would be a wait that never ends."""
        self.phase_one(hang=10, n=2)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.bridge("batch", "start", "--group", "p2",
                          "--resume-from", "p1", "--as-ready",
                          "--tasks-file", self.named_batch("no-such-thread"),
                          expect_rc=1)
        self.assertIn("no such run", out["error"])


class ACyclicChainFailsRatherThanHanging(BridgeCase):
    """`waits_for` is a field on disk, so a hand-edited or half-written cycle is
    possible — and a cycle can never resolve, because every run in it is waiting
    for another run in it. `wait_chain`'s bound keeps a single walk finite; this
    is about the run that would otherwise wait for an answer that cannot come.

    Driven through `await_predecessor` directly rather than the CLI: building a
    cycle needs two run directories pointing at each other, which no sequence of
    commands produces. The assertions are on the contract left on disk, not on
    the function's return value.
    """

    def test_a_run_waiting_on_a_cycle_records_a_failure(self):
        import subprocess

        from _codex import await_predecessor
        from _registry import write_meta

        # A live pid that is not this process: `reap` must see both runs as
        # supervised, or it marks them orphaned and the cycle resolves for the
        # wrong reason. Not `os.getpid()` — the harness kills every recorded
        # supervisor on teardown, and this process is not a supervisor.
        keeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(keeper.kill)

        runs = self.project / ".codex-runs"
        a, b = runs / "run-a", runs / "run-b"
        for d in (a, b):
            d.mkdir(parents=True)
        write_meta(a, {"run_id": "run-a", "state": "waiting", "waits_for": "run-b",
                       "supervisor_pid": keeper.pid})
        write_meta(b, {"run_id": "run-b", "state": "waiting", "waits_for": "run-a",
                       "supervisor_pid": keeper.pid})

        # In a thread with a deadline, because the regression this guards
        # against is an endless wait: without the bound the call never returns,
        # and a test that hangs wedges every run after it instead of going red.
        import threading
        done = {}

        def run():
            done["result"] = await_predecessor(
                a, json.loads((a / "meta.json").read_text()), {"flag": False})

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=15)
        self.assertFalse(t.is_alive(),
                         "await_predecessor never returned — a cycle in "
                         "`waits_for` cannot resolve, so it has to be refused "
                         "rather than waited on")
        self.assertIsNone(done["result"])
        meta = json.loads((a / "meta.json").read_text())
        self.assertEqual(meta["state"], "failed")
        self.assertIn("loops back", meta["error"])
        self.assertIsNotNone(meta["ended_at"])


class TheHandshakeRationale(AsReadyBase):
    """`batch start --as-ready` returns without blocking. The round's original
    test said that was because `create_run`'s thread-id poll gains a `waiting`
    exit — which is backwards: a chained member inherits its predecessor's
    thread id and `create_run` writes it to disk before the supervisor is ever
    spawned, so the poll was already exiting on the thread id.

    The `waiting` exit is not dead, though. A task naming a ref this registry
    has never seen has no thread to inherit, and that is the case it covers.
    """

    def test_a_chained_member_already_knows_its_thread(self):
        self.phase_one(hang=8, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.assertIsNotNone(self.meta(rid)["thread_id"],
                             "inherited from the predecessor at creation")
        self.assertIsNotNone(out["runs"][0].get("thread_id"),
                             "and reported back, so the caller can address it")

    def test_the_command_returns_promptly_either_way(self):
        self.phase_one(hang=8, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        t0 = time.monotonic()
        self.phase_two(n=1)
        self.assertLess(time.monotonic() - t0, 12,
                        "batch start blocked on a member that will not run for "
                        "another eight seconds")


if __name__ == "__main__":
    unittest.main()
