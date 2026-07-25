"""T1 — the SessionEnd cleanup hook.

Driven with real `sleep` processes in their own process groups, never a real
Codex: the thing being tested is the selection logic and the signalling, and a
real Codex would add cost and nondeterminism without testing anything more.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "codex_session_cleanup.py"
SESSION = "session-under-test"


def alive(proc):
    """Liveness via Popen.poll(), never os.kill(pid, 0).

    These processes are children of the test process, so a killed one stays a
    zombie until it is reaped — and `os.kill(pid, 0)` succeeds on a zombie,
    which would make every "was it stopped?" assertion silently wrong in both
    directions. poll() reaps. (The hook itself is never the parent of a Codex
    process, so it has no such problem.)
    """
    return proc.poll() is None


class HookTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codexhook-")).resolve()
        self.project = self.tmp / "proj"
        (self.project / "deep" / "nested").mkdir(parents=True)
        self.runs = self.project / ".codex-runs"
        self.runs.mkdir()
        self.spawned = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for p in self.spawned:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:
                pass
        for p in self.spawned:
            # Reap, or Python warns about a still-running subprocess at GC and
            # the suite's output fills with noise nobody will read.
            try:
                p.wait(timeout=5)
            except Exception:
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_run(self, run_id, *, state="running", session=SESSION, detached=False,
                 spawn=True):
        d = self.runs / run_id
        d.mkdir()
        meta = {"run_id": run_id, "state": state, "detached": detached,
                "claude_session_id": session, "thread_id": f"t-{run_id}",
                "started_at": "2026-07-25T00:00:00.000Z"}
        proc = None
        if spawn:
            proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(120)"],
                start_new_session=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            self.spawned.append(proc)
            meta.update(codex_pid=proc.pid, supervisor_pid=proc.pid,
                        pgid=os.getpgid(proc.pid))
        (d / "meta.json").write_text(json.dumps(meta))
        return d, meta, proc

    def run_hook(self, cwd=None, session_id=SESSION, reason="clear", env_session=None,
                 timeout=10):
        payload = {"session_id": session_id, "cwd": str(cwd or self.project),
                   "hook_event_name": "SessionEnd", "reason": reason,
                   "transcript_path": "/tmp/x.jsonl", "permission_mode": "default"}
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        if env_session:
            env["CLAUDE_CODE_SESSION_ID"] = env_session
        t0 = time.time()
        p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, timeout=timeout)
        return p, time.time() - t0

    def meta_of(self, run_dir):
        return json.loads((run_dir / "meta.json").read_text())

    def wait_dead(self, proc, timeout=6):
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False


class FastPath(HookTestCase):

    def test_no_runs_dir_exits_immediately(self):
        """The common case in every project that never uses Codex. SessionEnd's
        default timeout is 1.5 s, so this path has to cost effectively nothing."""
        shutil.rmtree(self.runs)
        p, elapsed = self.run_hook()
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertLess(elapsed, 0.6,
                        f"no-runs-dir path took {elapsed:.3f}s of a 1.5s budget")

    def test_empty_runs_dir_exits_quickly(self):
        p, elapsed = self.run_hook()
        self.assertEqual(p.returncode, 0)
        self.assertLess(elapsed, 0.6)

    def test_runs_dir_found_from_a_nested_cwd(self):
        """The registry sits at the git top level but the session's cwd can be
        any subdirectory of it."""
        d, meta, meta_p = self.make_run("nested-target")
        p, _ = self.run_hook(cwd=self.project / "deep" / "nested")
        self.assertEqual(p.returncode, 0)
        self.assertTrue(self.wait_dead(meta_p))

    def test_unreadable_meta_does_not_crash_the_hook(self):
        (self.runs / "broken").mkdir()
        (self.runs / "broken" / "meta.json").write_text("{not json")
        d, meta, meta_p = self.make_run("good")
        p, _ = self.run_hook()
        self.assertEqual(p.returncode, 0)
        self.assertTrue(self.wait_dead(meta_p))


class Selection(HookTestCase):

    def test_kills_only_this_sessions_non_detached_running_runs(self):
        mine, m_mine, m_mine_p = self.make_run("mine")
        other, m_other, m_other_p = self.make_run("other-session", session="a-different-session")
        det, m_det, m_det_p = self.make_run("detached-run", detached=True)
        done, m_done, m_done_p = self.make_run("already-done", state="completed")

        p, _ = self.run_hook()
        self.assertEqual(p.returncode, 0)

        self.assertTrue(self.wait_dead(m_mine_p),
                        "this session's running, non-detached run must be stopped")
        self.assertTrue(alive(m_other_p),
                        "another session's run must be left alone")
        self.assertTrue(alive(m_det_p),
                        "--detach exists precisely so a run can outlive the session")
        self.assertTrue(alive(m_done_p),
                        "a run already marked finished must not be signalled")

        self.assertEqual(self.meta_of(mine)["state"], "interrupted")
        self.assertEqual(self.meta_of(det)["state"], "running")
        self.assertEqual(self.meta_of(done)["state"], "completed")
        self.assertIn("mine", p.stdout)
        self.assertNotIn("other-session", p.stdout)

    def test_matches_on_the_env_session_id_when_input_disagrees(self):
        """Either source is accepted; relying on one alone is a silent single
        point of failure."""
        mine, meta, meta_p = self.make_run("env-matched")
        p, _ = self.run_hook(session_id="something-else", env_session=SESSION)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(self.wait_dead(meta_p))

    def test_matches_on_the_input_session_id_with_no_env(self):
        mine, meta, meta_p = self.make_run("input-matched")
        p, _ = self.run_hook(session_id=SESSION, env_session=None)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(self.wait_dead(meta_p))

    def test_no_matching_session_kills_nothing(self):
        mine, meta, meta_p = self.make_run("someone-elses", session="foreign")
        p, _ = self.run_hook(session_id="mine", env_session="mine")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertTrue(alive(meta_p),
                        "a session-id mismatch must fail toward killing nothing")

    def test_a_run_with_no_pgid_is_skipped_not_crashed_on(self):
        d, _, _ = self.make_run("no-pgid", spawn=False)
        p, _ = self.run_hook()
        self.assertEqual(p.returncode, 0)
        self.assertEqual(self.meta_of(d)["state"], "running",
                         "nothing was signalled, so nothing should be recorded")

    def test_a_dead_pgid_is_handled(self):
        d, meta, meta_p = self.make_run("already-exited")
        os.killpg(meta["pgid"], signal.SIGKILL)
        self.assertTrue(self.wait_dead(meta_p))
        p, _ = self.run_hook()
        self.assertEqual(p.returncode, 0)
        self.assertEqual(self.meta_of(d)["stop_signals"], "already-gone")


class Behaviour(HookTestCase):

    def test_records_reason_and_signal_in_meta(self):
        d, meta, meta_p = self.make_run("recorded")
        p, _ = self.run_hook(reason="prompt_input_exit")
        self.assertTrue(self.wait_dead(meta_p))
        m = self.meta_of(d)
        self.assertEqual(m["state"], "interrupted")
        self.assertEqual(m["stopped_by"], "SessionEnd(prompt_input_exit)")
        self.assertIn("SIGINT", m["stop_signals"])
        self.assertTrue(m["ended_at"])

    def test_sigint_comes_first_so_the_thread_stays_resumable(self):
        d, meta, meta_p = self.make_run("sigint-first")
        p, _ = self.run_hook()
        self.assertTrue(self.wait_dead(meta_p))
        self.assertEqual(self.meta_of(d)["stop_signals"], "SIGINT",
                         "a process that dies on SIGINT must never see SIGTERM — "
                         "escalating early would cut off the rollout flush")

    def test_escalates_to_sigterm_for_a_process_that_ignores_sigint(self):
        d = self.runs / "stubborn"
        d.mkdir()
        p = subprocess.Popen(
            [sys.executable, "-c",
             "import signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
             "time.sleep(120)"],
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.spawned.append(p)
        (d / "meta.json").write_text(json.dumps({
            "run_id": "stubborn", "state": "running", "detached": False,
            "claude_session_id": SESSION, "codex_pid": p.pid,
            "supervisor_pid": p.pid, "pgid": os.getpgid(p.pid)}))

        hp, elapsed = self.run_hook()
        self.assertEqual(hp.returncode, 0)
        self.assertTrue(self.wait_dead(p))
        self.assertEqual(self.meta_of(d)["stop_signals"], "SIGINT+SIGTERM")
        self.assertLess(elapsed, 1.5,
                        f"the hook must stay inside its budget even when "
                        f"escalating; took {elapsed:.3f}s")

    def test_several_runs_are_all_signalled_within_budget(self):
        procs = [self.make_run(f"parallel-{i}")[2] for i in range(5)]
        p, elapsed = self.run_hook()
        self.assertEqual(p.returncode, 0)
        for pr in procs:
            self.assertTrue(self.wait_dead(pr))
        self.assertLess(elapsed, 1.5,
                        f"five runs took {elapsed:.3f}s of a 1.5s budget")

    def test_fires_on_clear_and_resume_too(self):
        """SessionEnd fires on /clear and /resume as well as real termination;
        after a /clear nobody is watching the run either."""
        for reason in ("clear", "resume", "logout", "other"):
            with self.subTest(reason=reason):
                d, meta, meta_p = self.make_run(f"r-{reason}")
                p, _ = self.run_hook(reason=reason)
                self.assertEqual(p.returncode, 0)
                self.assertTrue(self.wait_dead(meta_p))
                self.assertEqual(self.meta_of(d)["stopped_by"],
                                 f"SessionEnd({reason})")

    def test_malformed_stdin_does_not_crash(self):
        p = subprocess.run([sys.executable, str(HOOK)], input="not json at all",
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0,
                         "a hook that crashes on bad input is worse than one that "
                         "does nothing")


if __name__ == "__main__":
    unittest.main()
