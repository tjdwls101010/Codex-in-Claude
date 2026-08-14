"""M1 — a run whose supervisor died but whose Codex is still working is alive.

`reap` judges liveness from `supervisor_pid` alone and never consults
`codex_pid`. Unix does not cascade-kill children, so killing a supervisor leaves
its `codex exec` process running and writing. `reap` then writes `orphaned` —
terminal — and every waiter chained behind that run releases immediately,
putting a second `codex exec resume` onto a rollout file the first one is still
appending to. That is the F4 corruption the whole guard system exists to
prevent.

The round's earlier fix for the chain (an abandoned *waiter* must not release
its successors) closed the half that cannot corrupt anything: a waiter owns no
Codex process. This is the half that does.

`orphaned` still means what it meant — nobody is recording this run's outcome —
but it must not be reached while the work itself is demonstrably still going.
"""

from __future__ import annotations

import json
import os
import signal
import time
import unittest

from helpers import BridgeCase
from test_as_ready import AsReadyBase


def alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


class AnOrphanCanStillBeWriting(BridgeCase):
    """`orphaned` keeps its meaning — the legacy suite pins it deliberately, and
    changing it would leave a run whose Codex hangs forever stuck `running`,
    which is the stale row `reap` exists to clear. What changes is that nothing
    deciding whether a THREAD is free may read terminal as "not writing"."""

    def orphan_with_live_codex(self):
        out = self.bridge("start", "--sandbox", "read-only", "go",
                          env_extra={"FAKE_CODEX_HANG": 25})
        rid = out["run_id"]
        deadline = time.time() + 15
        while time.time() < deadline and not self.meta(rid).get("codex_pid"):
            time.sleep(0.1)
        m = self.meta(rid)
        self.assertTrue(alive(m["codex_pid"]), "fixture needs a live codex")
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        self.assertTrue(alive(m["codex_pid"]),
                        "killing the supervisor must not take its child")
        row = self.bridge("status", "--run", rid)["runs"][0]
        self.assertEqual(row["state"], "orphaned",
                         "the recorder is gone, and saying so is right")
        return rid, out["thread_id"], m

    def test_the_thread_is_not_free_while_that_codex_writes(self):
        rid, thread, _m = self.orphan_with_live_codex()
        refused = self.bridge("resume", thread, "second turn", expect_rc=1)
        self.assertIn(rid, json.dumps(refused),
                      "a terminal state answers 'is anyone recording this', not "
                      "'is anything still writing this thread' — and two turns "
                      "on one rollout file is the corruption")

    def test_the_thread_frees_up_once_that_codex_is_gone(self):
        rid, thread, m = self.orphan_with_live_codex()
        os.kill(int(m["codex_pid"]), signal.SIGKILL)
        deadline = time.time() + 10
        while time.time() < deadline and alive(m["codex_pid"]):
            time.sleep(0.1)
        again = self.bridge("resume", thread, "second turn")
        self.assertIn("run_id", again)


class TheChainDoesNotReleaseOntoALiveTurn(AsReadyBase):
    """The same fact from the waiter's side, which is where it corrupts."""

    def test_a_waiter_does_not_start_while_its_predecessor_codex_lives(self):
        _, members = self.phase_one(hang=25, n=1)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        out = self.phase_two(n=1)
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid, "waiting")

        pred = self.meta(members[0])
        self.assertTrue(alive(pred["codex_pid"]))
        os.kill(int(pred["supervisor_pid"]), signal.SIGKILL)

        deadline = time.time() + 12
        while time.time() < deadline:
            if self.meta(rid).get("codex_started_at"):
                self.assertFalse(
                    alive(self.meta(members[0])["codex_pid"]),
                    "the successor started a turn while its predecessor's "
                    "codex was still writing the same rollout file")
                return
            time.sleep(0.2)
        self.assertIsNone(self.meta(rid).get("codex_started_at"))


if __name__ == "__main__":
    unittest.main()
