"""A terminal state answers "is anyone recording this?", never "is anything
still writing?" — and every surface that confuses the two.

`reap` writes `orphaned` when a run's supervisor dies. That is correct and the
legacy suite pins it. But `Popen` makes Codex a child, Unix does not
cascade-kill children, and the run's `codex exec` keeps appending to its rollout
file. So `orphaned` is a terminal state that can still be writing.

The corruption this permits — two turns on one rollout — was closed by
consulting `still_writing` at the two sites that decide whether a THREAD is
free. That fixed the two sites a review named and not the class: twelve places
turn run state into a liveness claim, and the other ten each produce a caller
acting on a false answer. `stop` reports success having signalled nothing;
`batch clean` deletes a live run's checkout with no `--force`; `--follow` prints
its terminal line and exits while events are still arriving; `result` hands back
two different "final" messages ten seconds apart, neither caveated.

This file is the class, not the instances.
"""

from __future__ import annotations

import json
import os
import signal
import time
import unittest

from helpers import BridgeCase


def alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


class StillWritingCase(BridgeCase):
    """Fixture: a run recorded terminal whose Codex is demonstrably still going."""

    def orphan_still_writing(self, **env):
        out = self.bridge("start", "--sandbox", "read-only", "go",
                          env_extra={"FAKE_CODEX_HANG": 30, **env})
        rid = out["run_id"]
        deadline = time.time() + 15
        while time.time() < deadline and not self.meta(rid).get("codex_pid"):
            time.sleep(0.1)
        m = self.meta(rid)
        self.assertTrue(alive(m["codex_pid"]), "fixture needs a live codex")
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        self.addCleanup(self._reap_codex, m["codex_pid"])
        # `status` is what drives `reap`, which is what writes `orphaned`.
        row = self.bridge("status", "--run", rid)["runs"][0]
        self.assertEqual(row["state"], "orphaned")
        self.assertTrue(alive(m["codex_pid"]),
                        "and its codex is still running, which is the point")
        return rid, m

    def _reap_codex(self, pid):
        try:
            os.kill(int(pid), 9)
        except Exception:
            pass


class StopReachesIt(StillWritingCase):
    """F1. `stop` is the escape hatch every other refusal points at — SKILL.md,
    the orchestration reference, and `batch clean`'s own refusal text all say
    "stop them first". It filtered its targets on state before signalling, so
    for this run it returned an empty `stopped` list with rc 0 while the process
    kept writing. A false success is the worst answer this project can give."""

    def batch_with_orphan(self):
        tasks = self.tasks_file("one")
        out = self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks,
                          env_extra={"FAKE_CODEX_HANG": 30})
        rid = out["runs"][0]["run_id"]
        deadline = time.time() + 15
        while time.time() < deadline and not self.meta(rid).get("codex_pid"):
            time.sleep(0.1)
        m = self.meta(rid)
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        self.addCleanup(self._reap_codex, m["codex_pid"])
        self.bridge("status", "--run", rid)
        return rid, m

    def test_stop_group_signals_a_still_writing_member(self):
        rid, m = self.batch_with_orphan()
        out = self.bridge("stop", "--group", "g")
        self.assertEqual([s["run_id"] for s in out["stopped"]], [rid],
                         "an empty `stopped` with rc 0, while a codex keeps "
                         "writing, is a success reply for something that did "
                         "not happen")
        deadline = time.time() + 10
        while time.time() < deadline and alive(m["codex_pid"]):
            time.sleep(0.1)
        self.assertFalse(alive(m["codex_pid"]))

    def test_stop_all_signals_it_too(self):
        rid, m = self.orphan_still_writing()
        out = self.bridge("stop", "--all")
        self.assertIn(rid, [s["run_id"] for s in out["stopped"]])
        deadline = time.time() + 10
        while time.time() < deadline and alive(m["codex_pid"]):
            time.sleep(0.1)
        self.assertFalse(alive(m["codex_pid"]))


class CleanDoesNotDeleteLiveWork(StillWritingCase):
    """F2. `batch clean`'s own comment says the first thing that stops a clean is
    "a live member is still writing into the very directory being removed" — and
    its liveness list was blind to exactly that member. git independently
    refuses to remove a *dirty* worktree, so work already written is safe; a run
    that has just committed, or is still reading before it writes, is not."""

    def two_member_batch_with_one_orphan(self):
        tasks = self.tasks_file("one", "two")
        out = self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks,
                          env_extra={"FAKE_CODEX_HANG": 30})
        rid = out["runs"][0]["run_id"]
        deadline = time.time() + 15
        while time.time() < deadline and not self.meta(rid).get("codex_pid"):
            time.sleep(0.1)
        m = self.meta(rid)
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        self.addCleanup(self._reap_codex, m["codex_pid"])
        self.addCleanup(self.bridge_raw, "stop", "--all")
        self.bridge("status", "--group", "g")
        return rid, m

    def test_a_plain_clean_refuses_while_a_member_still_writes(self):
        rid, _m = self.two_member_batch_with_one_orphan()
        out = self.bridge("batch", "clean", "--group", "g", expect_rc=1)
        self.assertIn(rid, json.dumps(out),
                      "the member still writing must be named as the reason")

    def test_the_name_is_not_released_either(self):
        self.two_member_batch_with_one_orphan()
        self.bridge("batch", "clean", "--group", "g", expect_rc=1)
        out = self.bridge("batch", "start", "--group", "g",
                          "--tasks-file", self.tasks_file("x"), expect_rc=1)
        self.assertIn("already exists", out["error"])


class ReportsDoNotSayFinished(StillWritingCase):
    """F4. Every surface that answers "is this done" said yes."""

    def test_result_marks_its_answer_as_partial(self):
        rid, _m = self.orphan_still_writing()
        out = self.bridge("result", "--run", rid)
        self.assertIsNotNone(
            out.get("note"),
            "a `result` taken while codex is still writing can be superseded "
            "by the same call ten seconds later; handing both back as final "
            "with no caveat is two different answers, both presented as the "
            "answer")

    def test_the_status_summary_counts_it_as_running(self):
        rid, _m = self.orphan_still_writing()
        out = self.bridge("status", "--all")
        self.assertIn(rid, out["running"])
        self.assertNotIn(rid, out["failed"])

    def test_follow_does_not_print_a_terminal_line_while_it_writes(self):
        rid, _m = self.orphan_still_writing(FAKE_CODEX_DELAY="0.4")
        t0 = time.monotonic()
        p = self.bridge_raw("log", "--run", rid, "--follow",
                            "--follow-timeout", "3")
        self.assertGreaterEqual(
            time.monotonic() - t0, 2.5,
            "`--follow` promises a terminal line means the run stopped moving; "
            "it returned immediately while events were still arriving")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_turn_time_keeps_growing_while_the_turn_does(self):
        rid, _m = self.orphan_still_writing()
        first = self.bridge("status", "--run", rid)["runs"][0]
        time.sleep(3)
        second = self.bridge("status", "--run", rid)["runs"][0]
        self.assertGreater(
            second["codex_elapsed_seconds"], first["codex_elapsed_seconds"],
            "the turn is still running, so its duration cannot be frozen at "
            "whatever `ended_at` an unrelated caller's reap happened to stamp")


class TheCollisionReportStaysHonest(StillWritingCase):
    """F3. `concurrent_writers` and `doctor` are the only surfaces that can show
    two runs sharing a directory across threads — `resume` has no worktree
    option, so nothing else could tell you."""

    def test_a_new_writer_is_told_about_the_still_writing_run(self):
        out = self.bridge("start", "--sandbox", "workspace-write", "first",
                          env_extra={"FAKE_CODEX_HANG": 30})
        rid = out["run_id"]
        deadline = time.time() + 15
        while time.time() < deadline and not self.meta(rid).get("codex_pid"):
            time.sleep(0.1)
        m = self.meta(rid)
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        self.addCleanup(self._reap_codex, m["codex_pid"])
        self.bridge("status", "--run", rid)

        second = self.bridge("start", "--sandbox", "workspace-write", "second")
        self.addCleanup(self.bridge_raw, "stop", "--all")
        self.assertIn(rid, json.dumps(second.get("concurrent_writers") or []),
                      "it is writing this very directory, and nothing else can "
                      "tell the new run that")


class RefusalsNameTheRightReason(BridgeCase):
    """F5 and F6 — two messages that stated something other than what happened."""

    def test_a_corrupt_named_target_is_not_called_absent(self):
        """F5. `find_run` returns (run_dir, None) for present-but-corrupt, and
        the new named-ref check tested only the meta — the sixth instance of the
        mistake `refuse_unresolved_run` exists to fix, fifty lines below a
        function that already does it correctly."""
        tasks = self.tasks_file("p1")
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tasks)
        rid = out["runs"][0]["run_id"]
        self.wait_terminal(rid)
        (self.project / ".codex-runs" / rid / "meta.json").write_text("{ broken")

        named = self.tmp / "named.jsonl"
        named.write_text(json.dumps(
            {"kind": "resume", "prompt": "x", "resume": rid}) + "\n")
        refused = self.bridge("batch", "start", "--group", "p2",
                              "--resume-from", "p1", "--as-ready",
                              "--tasks-file", named, expect_rc=1)
        self.assertNotIn("no such run", refused["error"],
                         "it exists; its meta will not parse, and those send "
                         "the caller to fix different things")

    def test_the_clean_note_does_not_blame_absent_worktrees(self):
        """F6. The most reachable defect of the round: no kill, no corruption,
        no race. A live `--as-ready` waiter has no worktree, so a forced clean
        answered with a note about worktrees holding uncommitted changes,
        recommending the `--force` that had just been passed and provably
        cannot release the name."""
        self.bridge("batch", "start", "--group", "p1",
                    "--tasks-file", self.tasks_file("work"),
                    env_extra={"FAKE_CODEX_HANG": 20})
        out = self.bridge("batch", "start", "--group", "p2",
                          "--resume-from", "p1", "--as-ready",
                          "--tasks-file", self.tasks_file("next"))
        rid = out["runs"][0]["run_id"]
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.meta(rid).get("state") == "waiting":
                break
            time.sleep(0.05)
        self.addCleanup(self.bridge_raw, "stop", "--all")

        cleaned = self.bridge("batch", "clean", "--group", "p2", "--force")
        self.assertFalse(cleaned["name_released"])
        note = cleaned.get("note") or ""
        self.assertNotIn("uncommitted changes", note,
                         "there are no worktrees here and nothing is dirty")
        self.assertIn("stop", note,
                      "the one remedy that works has to be the one named")
        self.assertIn(rid, note + json.dumps(cleaned),
                      "and it has to say which run")


if __name__ == "__main__":
    unittest.main()
