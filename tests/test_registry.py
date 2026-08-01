"""T1 — the run registry: layout, isolation between runs, and state reporting."""

import json
import os
import time
import unicodedata
import unittest
from pathlib import Path

from helpers import BRIDGE, BridgeTestCase, codex_bridge


class RegistryLayout(BridgeTestCase):

    def test_runs_dir_is_self_ignoring(self):
        """`.codex-runs/.gitignore` containing `*` is what keeps the registry
        out of the user's history without editing the user's own .gitignore."""
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        gi = self.project / ".codex-runs" / ".gitignore"
        self.assertTrue(gi.is_file())
        self.assertEqual(gi.read_text().strip(), "*")

        out = self.bridge_raw("status")  # any command; we only want git's view
        self.assertEqual(out.returncode, 0)
        import subprocess
        porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=self.project,
                                   capture_output=True, text=True).stdout
        self.assertNotIn(".codex-runs", porcelain,
                         "the registry must be invisible to git")

    def test_run_directory_contents(self):
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        d = self.project / ".codex-runs" / r["run_id"]
        for name in ("meta.json", "events.jsonl", "stderr.log", "last-message.txt"):
            self.assertTrue((d / name).is_file(), f"missing {name}")
        meta = json.loads((d / "meta.json").read_text())
        for key in ("run_id", "thread_id", "cwd", "project", "sandbox", "isolated",
                    "argv", "claude_session_id", "detached", "started_at", "state"):
            self.assertIn(key, meta)
        self.assertEqual(meta["claude_session_id"], "test-session-aaaa")

    def test_run_ids_are_unique_and_ordering_survives_same_second_starts(self):
        """Four runs in one second share a run-id timestamp, so ordering cannot
        come from the id — it comes from millisecond `started_at`."""
        ids = []
        for i in range(4):
            r = self.start(f"run {i}", "--label", "same-label")
            ids.append(r["run_id"])
        for rid in ids:
            self.wait_for_state(rid)
        self.assertEqual(len(set(ids)), 4, "labels collide but run ids must not")
        for rid in ids:
            self.assertIn("same-label", rid)

        listed = [r["run_id"] for r in self.bridge("status", "--all")["runs"]]
        self.assertEqual(listed, ids, "status must list runs in start order")
        # `--last` must land on the genuinely newest run, not the one whose
        # random suffix happens to sort highest.
        r = self.bridge("resume", "--last", "continue")
        self.wait_for_state(r["run_id"])
        self.assertEqual(r["parent_run_id"] if "parent_run_id" in r else
                         self.bridge("status", "--run", r["run_id"])["runs"][0]["parent_run_id"],
                         ids[-1])

    def test_label_is_slugified(self):
        r = self.start("x", "--label", "feat/add auth!! 한글")
        self.wait_for_state(r["run_id"])
        self.assertTrue((self.project / ".codex-runs" / r["run_id"]).is_dir())
        self.assertNotIn("/", r["run_id"])

    def test_parallel_starts_do_not_interleave(self):
        """Two runs started at once must each own a complete, separate log."""
        import subprocess
        import sys as _sys
        procs = []
        for i in range(3):
            env = dict(self.env)
            env["FAKE_CODEX_DELAY"] = "0.05"
            env["FAKE_CODEX_THREAD_ID"] = f"thread-{i}"
            procs.append(subprocess.Popen(
                [_sys.executable, str(BRIDGE),
                 "start", "--label", f"p{i}", f"prompt {i}"],
                cwd=str(self.project), env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True))
        results = []
        for p in procs:
            out, err = p.communicate(timeout=90)
            self.assertEqual(p.returncode, 0, err)
            results.append(json.loads(out.strip().splitlines()[-1]))

        self.assertEqual(len({r["run_id"] for r in results}), 3)
        self.assertEqual({r["thread_id"] for r in results},
                         {"thread-0", "thread-1", "thread-2"})
        for r in results:
            self.wait_for_state(r["run_id"])
            ev = Path(r["events"]).read_text().strip().splitlines()
            # Each log holds exactly one complete stream, not a mix of three.
            self.assertEqual(sum(1 for l in ev if '"thread.started"' in l), 1)
            self.assertEqual(sum(1 for l in ev if '"turn.completed"' in l), 1)


class UnicodePaths(BridgeTestCase):
    """The legacy script needed explicit normalisation for exactly this: APFS
    hands back NFD for Hangul while argv carries NFC, so an unnormalised compare
    says a path is not itself."""

    project_name = "한글 프로젝트 dir"

    def test_run_in_a_korean_path_with_a_space(self):
        r = self.start("작업을 해줘")
        row = self.wait_for_state(r["run_id"])
        self.assertEqual(row["state"], "completed")
        rec = self.argv_records()[-1]
        self.assertEqual(codex_bridge.nfc(rec["cwd"]),
                         codex_bridge.nfc(str(self.project)))
        self.assertIn("작업을 해줘", rec["argv"][-1])

    def test_relative_paths_render_correctly_under_nfd(self):
        nfd_project = unicodedata.normalize("NFD", str(self.project))
        nfc_project = unicodedata.normalize("NFC", str(self.project))
        self.assertNotEqual(nfd_project, nfc_project, "test needs a real NFD/NFC split")
        from _events import relativize
        target = nfd_project + "/src/파일.py"
        self.assertEqual(relativize(target, Path(nfc_project)), "src/파일.py",
                         "an NFD path under an NFC project must still relativize")

    def test_log_and_show_work_in_a_korean_project(self):
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        body, cursor = self.log_lines("--run", r["run_id"])
        self.assertTrue(any(l.startswith("msg ") for l in body))
        self.assertIsInstance(cursor, int)


class StateReporting(BridgeTestCase):

    def test_status_reports_usage_and_counts(self):
        self.env["FAKE_CODEX_FIXTURE"] = str(
            Path(__file__).parent / "fixtures" / "mixed-bigout-and-failure.jsonl")
        r = self.start("x")
        row = self.wait_for_state(r["run_id"])
        self.assertEqual(row["state"], "completed")
        self.assertEqual(row["commands"], 3)
        self.assertGreaterEqual(row["turns_completed"], 1)
        self.assertIsNotNone(row["usage"])
        self.assertIsNotNone(row["last_agent_message"])

    def test_stderr_noise_is_not_reported_as_an_error(self):
        """Codex always writes `Reading additional input from stdin...` to
        stderr when stdin is not a TTY."""
        r = self.start("x")
        row = self.wait_for_state(r["run_id"])
        self.assertIsNone(row.get("stderr_tail"),
                          "the routine stdin notice must not surface as stderr output")

    def test_real_stderr_is_surfaced(self):
        r = self.start("x", env_extra={"FAKE_CODEX_STDERR": "something actually broke"})
        row = self.wait_for_state(r["run_id"])
        self.assertIn("something actually broke", row["stderr_tail"])

    def test_nonzero_exit_is_failed_not_completed(self):
        r = self.start("x", env_extra={"FAKE_CODEX_EXIT": "3"})
        row = self.wait_for_state(r["run_id"])
        self.assertEqual(row["state"], "failed")
        self.assertEqual(row["exit_code"], 3)

    def test_missing_codex_binary_is_reported(self):
        r = self.start("x", env_extra={"PATH": "/nonexistent"})
        row = self.wait_for_state(r["run_id"])
        self.assertEqual(row["state"], "failed")
        self.assertEqual(row["exit_code"], 127)

    def test_stall_detection_reports_but_never_kills(self):
        r = self.start("slow", env_extra={"FAKE_CODEX_HANG": "60"})
        # Wait for the stream to land, then age the log past the threshold.
        events = Path(r["events"])
        deadline = time.time() + 30
        while time.time() < deadline and (not events.exists() or events.stat().st_size == 0):
            time.sleep(0.1)
        old = time.time() - (codex_bridge.STALL_SECONDS + 120)
        os.utime(events, (old, old))

        row = self.bridge("status", "--run", r["run_id"])["runs"][0]
        self.assertEqual(row["state"], "stalled")
        self.assertGreaterEqual(row["idle_seconds"], codex_bridge.STALL_SECONDS)
        # Advisory only: the process must still be alive.
        self.assertTrue(codex_bridge.pid_alive(row["codex_pid"]),
                        "a stalled run must never be auto-killed")
        self.bridge("stop", "--run", r["run_id"])

    def test_in_progress_item_is_visible(self):
        """Silence alone is not failure; silence with no in-progress item is."""
        # A real stream truncated at its last item.started — exactly what a poll
        # sees while a command is still running.
        self.env["FAKE_CODEX_FIXTURE"] = str(
            Path(__file__).parent / "fixtures" / "mid-command.jsonl")
        r = self.start("x", env_extra={"FAKE_CODEX_HANG": "30"})
        deadline = time.time() + 30
        row = None
        while time.time() < deadline:
            row = self.bridge("status", "--run", r["run_id"])["runs"][0]
            if row.get("in_progress_item"):
                break
            time.sleep(0.2)
        self.assertIsNotNone(row.get("in_progress_item"),
                             "the fixture ends on an unmatched item.started")
        self.assertEqual(row["in_progress_item"]["type"], "command_execution")
        self.bridge("stop", "--run", r["run_id"])

    def test_orphaned_when_the_supervisor_dies_without_recording(self):
        r = self.start("x", env_extra={"FAKE_CODEX_HANG": "60"})
        row = self.bridge("status", "--run", r["run_id"])["runs"][0]
        os.kill(row["codex_pid"], 9)
        os.kill(json.loads((self.project / ".codex-runs" / r["run_id"] / "meta.json")
                           .read_text())["supervisor_pid"], 9)
        deadline = time.time() + 20
        while time.time() < deadline:
            row = self.bridge("status", "--run", r["run_id"])["runs"][0]
            if row["state"] == "orphaned":
                break
            time.sleep(0.2)
        self.assertEqual(row["state"], "orphaned",
                         "a dead supervisor must not leave the run reading as running")

    def test_runs_are_grouped_by_thread(self):
        r = self.start("first")
        self.wait_for_state(r["run_id"])
        r2 = self.bridge("resume", r["run_id"], "second")
        self.wait_for_state(r2["run_id"])
        st = self.bridge("status", "--all")
        self.assertEqual(sorted(st["threads"][r["thread_id"]]),
                         sorted([r["run_id"], r2["run_id"]]))

    def test_status_of_unknown_run_fails_cleanly(self):
        out = self.bridge("status", "--run", "nope", expect_rc=1)
        self.assertIn("no such run", out["error"])


class ImplicitTargetResolution(BridgeTestCase):
    """F4: `resume --last` used to pick `runs[-1]` project-wide, no filter on
    cwd, label or kind — a read-only caller could inherit another run's label
    AND its danger-full-access sandbox. D27 replaces that with: exactly one
    non-terminal run wins unambiguously, zero falls back to the newest (and
    says so), two or more fails loud with the candidate list."""

    def _running(self, label):
        r = self.start(f"long {label}", "--label", label,
                       env_extra={"FAKE_CODEX_HANG": "120"})
        deadline = time.time() + 30
        while time.time() < deadline:
            row = self.bridge("status", "--run", r["run_id"])["runs"][0]
            if row["state"] == "running" and row["codex_pid"]:
                return r
            time.sleep(0.1)
        self.fail(f"run {label} never reached running")

    def test_exactly_one_non_terminal_run_wins_even_if_not_the_newest(self):
        stale_live = self._running("stale-live")
        r_newer = self.start("newer, but terminal", "--label", "newer")
        self.wait_for_state(r_newer["run_id"])

        out = self.bridge("resume", "--last", "--force", "continue")
        self.assertEqual(out["resolved_from_run_id"], stale_live["run_id"],
                         "the only non-terminal run must win over a newer terminal one")
        self.assertEqual(out["thread_id"], stale_live["thread_id"])
        self.assertEqual(out["label"], "stale-live")
        self.bridge("stop", "--run", stale_live["run_id"])

    def test_zero_non_terminal_runs_falls_back_to_newest_and_says_so(self):
        r1 = self.start("first", "--label", "a")
        self.wait_for_state(r1["run_id"])
        r2 = self.start("second", "--label", "b")
        self.wait_for_state(r2["run_id"])

        out = self.bridge("resume", "--last", "continue")
        self.assertEqual(out["resolved_from_run_id"], r2["run_id"])
        self.assertEqual(out["label"], "b")
        self.assertIn("newest", out["resolved_from"])

    def test_two_or_more_non_terminal_runs_fails_loud(self):
        a = self._running("a")
        b = self._running("b")

        out = self.bridge("resume", "--last", "continue", expect_rc=1)
        self.assertIn("multiple non-terminal", out["error"])
        ids = {c["run_id"] for c in out["candidates"]}
        self.assertEqual(ids, {a["run_id"], b["run_id"]})

        self.bridge("stop", "--run", a["run_id"])
        self.bridge("stop", "--run", b["run_id"])

    def test_a_second_turn_on_a_live_thread_is_refused_without_force(self):
        a = self._running("a")
        out = self.bridge("resume", a["run_id"], "second turn", expect_rc=1)
        self.assertIn("live turn", out["error"])
        self.assertEqual(out["thread_id"], a["thread_id"])
        self.bridge("stop", "--run", a["run_id"])


if __name__ == "__main__":
    unittest.main()
