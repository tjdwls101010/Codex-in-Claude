"""Installs: the skill reached through a symlink, from a directory that has nothing to do with the project, must run exactly as it does in place.

A user-level install is `~/.claude/skills/codex -> <checkout>`, so the path the caller types is the link while the running script's own path is the target. The launcher exits as soon as it has a handle; a detached supervisor it re-executes finishes the run.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from support.harness import BridgeCase, ENTRY, alive, wait_until


class ThroughASymlink(BridgeCase):

    def setUp(self):
        super().setUp()
        skills = self.tmp / "홈 디렉터리" / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "codex").symlink_to(ENTRY.parent.parent, target_is_directory=True)
        self.linked = skills / "codex" / "scripts" / ENTRY.name
        self.elsewhere = self.tmp / "unrelated"
        self.elsewhere.mkdir()

    def test_a_run_started_through_the_link_is_finished_by_its_detached_supervisor(self):
        launcher = subprocess.Popen([sys.executable, str(self.linked), "start", "--project", str(self.project),
                                     "--label", "via-link", "x"],
                                    cwd=str(self.elsewhere), env={**self.env, "FAKE_CODEX_HANG": "2"},
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    text=True)
        stdout, stderr = launcher.communicate(timeout=60)
        self.assertEqual(launcher.returncode, 0, stderr)
        out = json.loads(stdout)
        meta = self.meta(out["run_id"])
        self.assertNotEqual(meta["supervisor_pid"], launcher.pid)
        self.assertTrue(alive(meta["supervisor_pid"]), "the supervisor outlives the launcher")
        self.assertEqual(self.runs_invoked()[-1]["cwd"], str(self.project))

        def finished():
            p = self.bridge_raw("result", "--project", self.project, "--run", out["run_id"],
                                entry=self.linked, cwd=self.elsewhere)
            res = json.loads(p.stdout)
            return res if res["state"] == "completed" else None

        res = wait_until(finished, timeout=30, interval=0.2)
        self.assertTrue(res)
        self.assertEqual(res["message"], "OK")

    def test_doctor_through_the_link_reports_the_installed_skill(self):
        p = self.bridge_raw("doctor", "--project", self.project, entry=self.linked, cwd=self.elsewhere)
        rep = json.loads(p.stdout)
        self.assertEqual(rep["project"], str(self.project))
        self.assertEqual(rep["skill_dir"], str(ENTRY.parent.parent.resolve()))


if __name__ == "__main__":
    unittest.main()
