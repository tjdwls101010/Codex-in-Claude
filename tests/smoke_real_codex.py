"""S5: the real Codex CLI, end to end. Opt-in because it spends tokens: `CODEX_BRIDGE_REAL=1 python3 tests/smoke_real_codex.py`.

A thread is started, followed, collected and resumed with no `--sandbox`, and the rollout Codex itself writes is the judge of what each turn ran under: `codex exec resume` has no sandbox flag, so only the bridge's re-assertion keeps the second turn on the first turn's sandbox.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support.harness import ENTRY


@unittest.skipUnless(os.environ.get("CODEX_BRIDGE_REAL") == "1", "set CODEX_BRIDGE_REAL=1 to run against the real Codex CLI")
class RealCodex(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codex-smoke-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project = self.tmp / "project"
        self.project.mkdir()
        (self.project / "notes.txt").write_text("smoke\n")
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=s@example.com", "-c", "user.name=s", "commit", "-qm", "init"]):
            subprocess.run(["git", "-C", str(self.project), *args], check=True)
        # A home of its own keeps the rollouts this test reads apart from the user's; the login is copied in, nothing else.
        self.home = self.tmp / "codex-home"
        self.home.mkdir()
        real_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        for name in ("auth.json", "config.toml"):
            if (real_home / name).exists():
                shutil.copy(real_home / name, self.home / name)
        self.env = {**os.environ, "CODEX_HOME": str(self.home)}

    def cli(self, *args, timeout=600):
        p = subprocess.run(["python3", str(ENTRY), *args, "--project", str(self.project)],
                           cwd=self.project, env=self.env, capture_output=True, text=True, timeout=timeout)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def turn_sandboxes(self, thread_id):
        rollouts = list((self.home / "sessions").rglob(f"rollout-*-{thread_id}.jsonl"))
        self.assertEqual(len(rollouts), 1, rollouts)
        lines = [json.loads(line) for line in rollouts[0].read_text().splitlines() if line.strip()]
        return [line["payload"]["sandbox_policy"]["type"] for line in lines if line.get("type") == "turn_context"]

    def test_a_resumed_turn_keeps_the_sandbox_its_thread_started_with(self):
        for sandbox in ("read-only", "workspace-write"):
            with self.subTest(sandbox=sandbox):
                started = json.loads(self.cli("start", "--sandbox", sandbox, "--label", "smoke", "Reply with exactly the word: first"))
                run_id, thread_id = started["run_id"], started["thread_id"]
                self.cli("log", "--run", run_id, "--follow", "--follow-timeout", "500")
                first = json.loads(self.cli("result", "--run", run_id))
                self.assertEqual(first["state"], "completed", first)
                self.assertIn("first", first["message"].lower())

                resumed = json.loads(self.cli("resume", run_id, "Reply with exactly the word: second"))
                self.cli("log", "--run", resumed["run_id"], "--follow", "--follow-timeout", "500")
                second = json.loads(self.cli("result", "--run", resumed["run_id"]))
                self.assertEqual(second["state"], "completed", second)
                self.assertIn("second", second["message"].lower())

                self.assertEqual(self.turn_sandboxes(thread_id), [sandbox, sandbox])


if __name__ == "__main__":
    unittest.main()
