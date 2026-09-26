"""`doctor`: one line describing the environment a run would start in, exit 2 when something it can see will stop a run.
"""

from __future__ import annotations

import os
import signal
import unittest

from support.harness import BridgeCase, FAKE_CODEX_DIR


class Doctor(BridgeCase):

    def test_a_healthy_environment(self):
        rep = self.bridge("doctor")
        self.assertEqual(rep["blockers"], [])
        self.assertEqual(rep["codex_path"], str(FAKE_CODEX_DIR / "codex"))
        self.assertEqual(rep["codex_home"], str(self.codex_home))
        self.assertTrue(rep["codex_home_from_env"])
        self.assertTrue(rep["login_ok"])
        self.assertEqual(rep["effective_defaults"], {"model": None, "effort": None, "service_tier": None})
        self.assertEqual(rep["models_catalog"], 2)
        self.assertFalse((self.project / ".codex-runs").exists(), "a diagnostic does not create what it diagnoses")

    def test_a_relative_codex_home_means_the_directory_it_named_when_the_command_ran(self):
        (self.project / "rel-home").mkdir()
        rep = self.bridge("doctor", env={"CODEX_HOME": "rel-home"})
        self.assertEqual(rep["codex_home"], str(self.project / "rel-home"))
        sub = self.project / "sub"
        sub.mkdir()
        out = self.bridge("start", "--cwd", sub, "x", env={"CODEX_HOME": "rel-home"})
        self.wait_state(out["run_id"])
        self.assertEqual(self.runs_invoked()[-1]["codex_home"], str(self.project / "rel-home"),
                         "codex runs elsewhere, so it has to be handed the path the caller meant")

    def test_what_an_unnamed_run_would_use(self):
        (self.codex_home / "config.toml").write_text(
            'model = "fake-big"\nmodel_reasoning_effort = "high"\nservice_tier = "fast"\n'
            'sandbox_mode = "danger-full-access"\n')
        rep = self.bridge("doctor")
        self.assertEqual(rep["effective_defaults"], {"model": "fake-big", "effort": "high", "service_tier": "fast"})
        self.assertEqual(rep["config_sandbox_mode"], "danger-full-access")
        self.assertTrue(any("danger-full-access" in w for w in rep["warnings"]))

    def test_blockers_exit_3(self):
        cases = [({"PATH": "/usr/bin:/bin"}, "not on PATH"),
                 ({"FAKE_CODEX_LOGIN_RC": 1}, "not authenticated"),
                 ({"CODEX_HOME": str(self.tmp / "missing")}, "CODEX_HOME does not exist")]
        for env, message in cases:
            with self.subTest(env=env):
                rep = self.bridge("doctor", rc=3, env=env)
                self.assertTrue(any(message in b for b in rep["blockers"]), rep["blockers"])

    def test_a_config_that_will_not_load_is_not_called_an_auth_problem(self):
        rep = self.bridge("doctor", rc=3, env={"FAKE_CODEX_LOGIN_RC": 1,
                                               "FAKE_CODEX_LOGIN_OUT": "Error loading configuration: config.toml:1:26"})
        blocker = next(b for b in rep["blockers"] if "login status" in b)
        self.assertIn("not an auth one", blocker)

    def test_an_unwritable_registry_is_a_blocker(self):
        self.runs_dir.mkdir()
        os.chmod(self.runs_dir, 0o500)
        self.addCleanup(os.chmod, self.runs_dir, 0o700)
        rep = self.bridge("doctor", rc=3)
        self.assertFalse(rep["runs_dir_writable"])

    def test_the_project_agents_md_is_named(self):
        (self.project / "AGENTS.md").write_text("# rules\n")
        rep = self.bridge("doctor")
        self.assertEqual(rep["project_agents_md"], str(self.project / "AGENTS.md"))
        self.assertTrue(any("AGENTS.md" in w for w in rep["warnings"]))

    def test_unreadable_runs_are_counted(self):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        (self.runs_dir / out["run_id"] / "meta.json").write_text("{ truncated")
        rep = self.bridge("doctor")
        self.assertEqual(rep["runs_unreadable"], 1)
        self.assertEqual(rep["runs_dir_runs"], 0)

    def test_live_writers_in_one_tree_are_reported_and_dead_ones_are_not(self):
        sub = self.project / "sub"
        sub.mkdir()
        a, am = self.running("x")
        b, _ = self.running("--cwd", sub, "y")
        warn = [w for w in self.bridge("doctor")["warnings"] if "overlap" in w]
        self.assertEqual(len(warn), 1)
        self.assertIn(a["run_id"], warn[0])
        self.assertIn(b["run_id"], warn[0])
        os.killpg(int(am["pgid"]), signal.SIGKILL)
        self.wait_state(a["run_id"])
        self.assertFalse([w for w in self.bridge("doctor")["warnings"] if "overlap" in w])

    def test_only_checkouts_this_skill_cut_are_counted(self):
        out = self.bridge("batch", "start", "--group", "g", "--worktree", "--task", "a")
        self.wait_all(out)
        mine = self.tmp / "users-own-worktree"
        self.git("worktree", "add", "--detach", mine, "HEAD")
        self.assertEqual(self.bridge("doctor")["worktrees"], 1)
        self.assertEqual(self.bridge("doctor")["groups"], ["g"])


if __name__ == "__main__":
    unittest.main()
