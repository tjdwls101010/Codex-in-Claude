"""Scaffolding for the 260814 round.

Same seam as the earlier rounds, and the same reason: the fake `codex` and the
fixtures are the legacy suite's, reached by path rather than copied, because two
copies of a model of the real CLI drift the moment one of them is fixed.

`BridgeCase` here is a cut-down copy of the 260813 round's rather than an import
of it. Both rounds name their scaffolding `helpers`, and `unittest discover`
puts its own start directory on `sys.path` first — so an import across rounds
resolves to whichever suite is being run, which is a failure that would look
like a test bug rather than a path bug. Only what this round's one subprocess
test needs is copied.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SKILL_DIR = REPO / ".claude" / "skills" / "codex"
SKILL_MD = SKILL_DIR / "SKILL.md"
BRIDGE = SKILL_DIR / "scripts" / "codex_bridge.py"
FAKE_CODEX_DIR = REPO / "tests" / "legacy" / "fake_codex"

sys.path.insert(0, str(BRIDGE.parent))


class BridgeCase(unittest.TestCase):
    """A throwaway git project with the fake `codex` first on PATH."""

    def setUp(self):
        # resolve(): on macOS /var is a symlink to /private/var and the bridge
        # resolves every path it records, so an unresolved base makes every path
        # comparison here spuriously unequal.
        self.tmp = Path(tempfile.mkdtemp(prefix="codex-260814-")).resolve()
        self.addCleanup(self._cleanup)
        self.project = self.tmp / "proj"
        self.project.mkdir(parents=True)
        self.git("init", "-q", str(self.project), cwd=self.tmp)
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.project / "f.txt").write_text("x\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("FAKE_CODEX_")}
        self.env["PATH"] = f"{FAKE_CODEX_DIR}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["CLAUDE_CODE_SESSION_ID"] = "test-260814"

    def _cleanup(self):
        # A supervisor left running keeps writing into a temp dir the next test
        # is about to reuse.
        runs = self.project / ".codex-runs"
        if runs.is_dir():
            for d in runs.iterdir():
                try:
                    m = json.loads((d / "meta.json").read_text())
                except Exception:
                    continue
                for pid in (m.get("supervisor_pid"), m.get("codex_pid")):
                    if not pid or int(pid) == os.getpid():
                        continue
                    try:
                        os.kill(int(pid), 9)
                    except Exception:
                        pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.project), *args],
                              capture_output=True, text=True)

    def bridge_raw(self, *args, timeout=90):
        return subprocess.run(
            [sys.executable, str(BRIDGE), *[str(a) for a in args]],
            cwd=str(self.project), env=self.env, capture_output=True,
            text=True, timeout=timeout)

    def bridge(self, *args, expect_rc=0, **kw):
        """Run the bridge and parse its one line of JSON."""
        p = self.bridge_raw(*args, **kw)
        self.assertEqual(
            p.returncode, expect_rc,
            f"rc={p.returncode} for {args}\nstdout={p.stdout}\nstderr={p.stderr}")
        try:
            return json.loads(p.stdout.strip().splitlines()[-1])
        except Exception as e:
            self.fail(f"non-JSON stdout for {args}: {e}\n"
                      f"stdout={p.stdout!r}\nstderr={p.stderr!r}")

    def meta(self, run_id):
        return json.loads(
            (self.project / ".codex-runs" / run_id / "meta.json").read_text())

    def wait_terminal(self, run_id, timeout=60):
        """Block until a run stops moving."""
        from _registry import TERMINAL_STATES
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.meta(run_id).get("state") in TERMINAL_STATES:
                return
            time.sleep(0.05)
        self.fail(f"{run_id} never reached a terminal state "
                  f"(last: {self.meta(run_id).get('state')})")
