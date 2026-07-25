"""T1 — `doctor` must produce a correct, specific diagnosis for each failure mode.

`doctor` is the single command the skill points at for "something is wrong", so
a wrong or vague diagnosis here is worse than none: it sends the reader off in
the wrong direction with confidence.
"""

import json
import os
import stat
import unittest
from pathlib import Path

from helpers import BridgeTestCase


class Doctor(BridgeTestCase):

    def doctor(self, expect_rc=0, **kw):
        return self.bridge("doctor", expect_rc=expect_rc, **kw)

    def test_healthy_environment_reports_ok(self):
        rep = self.doctor()
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["blockers"], [])
        self.assertIn("0.144.1-fake", rep["codex_version"])
        self.assertTrue(rep["runs_dir_writable"])
        self.assertEqual(rep["python"].split(".")[0], "3")

    def test_codex_absent_from_path_is_a_blocker(self):
        rep = self.doctor(expect_rc=2, env_extra={"PATH": "/nonexistent"})
        self.assertFalse(rep["ok"])
        self.assertIsNone(rep["codex_path"])
        self.assertIn("`codex` is not on PATH", rep["blockers"])

    def test_login_failure_is_a_blocker(self):
        rep = self.doctor(expect_rc=2, env_extra={"FAKE_CODEX_LOGIN_RC": "1"})
        self.assertFalse(rep["login_ok"])
        self.assertTrue(any("not authenticated" in b for b in rep["blockers"]))
        self.assertIn("Not logged in", rep["login_status"])

    def test_codex_home_override_is_reported_not_assumed(self):
        """~/.codex is not reliably the Codex home; the legacy skill's
        instruction to read it is already wrong on this machine."""
        home = self.tmp / "custom-codex-home"
        home.mkdir()
        rep = self.doctor(env_extra={"CODEX_HOME": str(home)})
        self.assertEqual(rep["codex_home"], str(home))
        self.assertTrue(rep["codex_home_from_env"])
        self.assertTrue(rep["codex_home_exists"])

    def test_missing_codex_home_is_a_blocker(self):
        rep = self.doctor(expect_rc=2,
                          env_extra={"CODEX_HOME": str(self.tmp / "gone")})
        self.assertFalse(rep["codex_home_exists"])
        self.assertTrue(any("CODEX_HOME does not exist" in b for b in rep["blockers"]))

    def test_dangerous_config_sandbox_is_warned_with_its_reason(self):
        home = self.tmp / "danger-home"
        home.mkdir()
        (home / "config.toml").write_text(
            'model = "gpt-5.6-sol"\n'
            'sandbox_mode = "danger-full-access"\n'
            'approval_policy = "never"\n')
        rep = self.doctor(env_extra={"CODEX_HOME": str(home)})
        self.assertEqual(rep["config_sandbox_mode"], "danger-full-access")
        self.assertEqual(rep["config_approval_policy"], "never")
        warning = next(w for w in rep["warnings"] if "danger-full-access" in w)
        # The warning has to explain the mechanism, not just flag the value —
        # otherwise the reader cannot tell whether it affects them.
        self.assertIn("no -s flag", warning)
        self.assertIn("-c sandbox_mode=", warning)

    def test_safe_config_sandbox_produces_no_warning(self):
        home = self.tmp / "safe-home"
        home.mkdir()
        (home / "config.toml").write_text('sandbox_mode = "workspace-write"\n')
        rep = self.doctor(env_extra={"CODEX_HOME": str(home)})
        self.assertEqual(rep["config_sandbox_mode"], "workspace-write")
        self.assertFalse([w for w in rep["warnings"] if "danger-full-access" in w])

    def test_unwritable_runs_dir_is_a_blocker(self):
        runs = self.tmp / "locked-runs"
        runs.mkdir()
        os.chmod(runs, stat.S_IRUSR | stat.S_IXUSR)  # r-x, no write
        self.addCleanup(os.chmod, runs, 0o755)
        rep = self.bridge("doctor", "--runs-dir", str(runs), expect_rc=2)
        self.assertFalse(rep["runs_dir_writable"])
        self.assertTrue(any("not writable" in b for b in rep["blockers"]))

    def test_doctor_does_not_create_the_runs_dir(self):
        """A diagnostic that changes what it diagnoses is a bad diagnostic."""
        self.assertFalse((self.project / ".codex-runs").exists())
        rep = self.doctor()
        self.assertFalse(rep["runs_dir_exists"])
        self.assertTrue(rep["runs_dir_writable"])
        self.assertFalse((self.project / ".codex-runs").exists(),
                         "doctor must not have created the registry")
        leftovers = list(self.project.glob(".codex-write-probe-*"))
        self.assertEqual(leftovers, [], "the write probe must clean up after itself")

    def test_project_agents_md_is_surfaced(self):
        """AGENTS.md survives --ignore-user-config, so it is in every run's
        context whether or not the caller intended it."""
        rep = self.doctor()
        self.assertIsNone(rep["project_agents_md"])
        (self.project / "AGENTS.md").write_text("# notes\nAlways use tabs.\n")
        rep = self.doctor()
        self.assertTrue(rep["project_agents_md"].endswith("AGENTS.md"))
        warning = next(w for w in rep["warnings"] if "AGENTS.md" in w)
        self.assertIn("--ignore-user-config", warning)

    def test_resolved_paths_are_reported_for_diagnosing_install_shape(self):
        """CLAUDE_SKILL_DIR does not exist and CLAUDE_PLUGIN_ROOT may or may
        not; doctor printing what it resolved is what makes a broken path a
        one-command diagnosis instead of a mystery."""
        rep = self.doctor()
        self.assertTrue(rep["bridge_path"].endswith("codex_bridge.py"))
        self.assertTrue(Path(rep["skill_dir"]).is_dir())
        self.assertIn("plugin_root_env", rep)

        rep = self.doctor(env_extra={"CLAUDE_PLUGIN_ROOT": "/some/plugin/root"})
        self.assertEqual(rep["plugin_root_env"], "/some/plugin/root")

    def test_detached_running_runs_are_called_out(self):
        r = self.start("bg", "--detach", env_extra={"FAKE_CODEX_HANG": "60"})
        rep = self.doctor()
        self.assertIn(r["run_id"], rep["detached_running"])
        self.assertTrue(any("outlive this session" in w for w in rep["warnings"]))
        self.bridge("stop", "--run", r["run_id"])

    def test_missing_thread_db_degrades_quietly(self):
        home = self.tmp / "no-db-home"
        home.mkdir()
        rep = self.doctor(env_extra={"CODEX_HOME": str(home)})
        self.assertIsNone(rep["thread_db"])
        self.assertFalse(rep["thread_db_readable"])
        self.assertTrue(rep["ok"], "a missing thread DB is a degradation, not a blocker")

    def test_unreadable_thread_db_warns_but_does_not_block(self):
        """The DB filename is version-stamped, so its schema will change; a
        Codex upgrade must degrade this feature, not break the skill."""
        home = self.tmp / "bad-db-home"
        home.mkdir()
        (home / "state_9.sqlite").write_bytes(b"this is not a sqlite database")
        rep = self.doctor(env_extra={"CODEX_HOME": str(home)})
        self.assertTrue(rep["thread_db"].endswith("state_9.sqlite"))
        self.assertFalse(rep["thread_db_readable"])
        self.assertTrue(rep["ok"])
        self.assertTrue(any("version-stamped" in w for w in rep["warnings"]))

    def test_highest_versioned_state_db_wins(self):
        home = self.tmp / "multi-db"
        home.mkdir()
        for n in (3, 10, 5):
            (home / f"state_{n}.sqlite").write_bytes(b"")
        rep = self.doctor(env_extra={"CODEX_HOME": str(home)})
        self.assertTrue(rep["thread_db"].endswith("state_10.sqlite"),
                        "10 > 5 numerically, even though '10' < '5' as a string")


if __name__ == "__main__":
    unittest.main()
