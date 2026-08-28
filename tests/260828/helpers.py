"""Scaffolding for the 260828 round.

A copy of the earlier rounds' rather than an import of one, for the reason
260823's own header gives: every round names its scaffolding `helpers`, and the
discovery start directory goes on `sys.path` first, so an import across rounds
resolves to whichever suite is being run.

This round only needs a temp git project and a way to run the bridge in it — the
seam is the CLI surface, not the event stream — so the fake `codex` and the
run-lifecycle waits the other rounds carry are left out.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SKILL_DIR = REPO / ".claude" / "skills" / "codex"
SKILL_MD = SKILL_DIR / "SKILL.md"
SPEC_MD = REPO / ".claude" / "harness-spec.md"
BRIDGE = SKILL_DIR / "scripts" / "codex_bridge.py"
FAKE_CODEX_DIR = REPO / "tests" / "legacy" / "fake_codex"


def help_text(*path) -> str:
    """The real rewrapped `--help` a caller reads, not the parser's `help=`."""
    p = subprocess.run(
        [sys.executable, str(BRIDGE), *path, "--help"],
        capture_output=True, text=True, timeout=60)
    return p.stdout


class BridgeCase(unittest.TestCase):
    """A throwaway git project to run the bridge inside."""

    def setUp(self):
        # resolve(): on macOS /var is a symlink to /private/var and the bridge
        # resolves every path it records.
        self.tmp = Path(tempfile.mkdtemp(prefix="codex-260828-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
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
        self.env["CLAUDE_CODE_SESSION_ID"] = "test-260828"
        self.codex_home = self.tmp / "codex-home"
        self.codex_home.mkdir(exist_ok=True)
        self.env["CODEX_HOME"] = str(self.codex_home)

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

    def tasks_file(self, *items) -> Path:
        path = self.tmp / "tasks.jsonl"
        path.write_text("".join(json.dumps(i) + "\n" for i in items))
        return path
