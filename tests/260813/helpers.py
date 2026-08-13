"""Scaffolding for the 260813 round.

Same seam as the legacy suite — the bridge is driven as a subprocess, because
what is under test includes process spawning, process groups and signal
delivery, none of which survive being faked in-process.

The fake `codex` is the legacy suite's, deliberately not a copy. It models the
real CLI's argv parsing (`-i`'s greedy consumption, the `--` terminator), and
two copies of that model drift the moment one of them is fixed — after which
each suite is verifying a different CLI and neither says which.
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
BRIDGE = REPO / ".claude" / "skills" / "codex" / "scripts" / "codex_bridge.py"
FAKE_CODEX_DIR = REPO / "tests" / "legacy" / "fake_codex"
FIXTURES = REPO / "tests" / "legacy" / "fixtures"

sys.path.insert(0, str(BRIDGE.parent))


class BridgeCase(unittest.TestCase):
    """A throwaway git project with the fake `codex` first on PATH."""

    def setUp(self):
        # resolve(): on macOS /var is a symlink to /private/var and the bridge
        # resolves every path it records, so an unresolved base makes every path
        # comparison here spuriously unequal.
        self.tmp = Path(tempfile.mkdtemp(prefix="codex-260813-")).resolve()
        self.addCleanup(self._cleanup)
        self.project = self.tmp / "proj"
        self.project.mkdir(parents=True)
        self.git("init", "-q", str(self.project), cwd=self.tmp)
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.project / "f.txt").write_text("x\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

        self.argv_log = self.tmp / "argv.jsonl"
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("FAKE_CODEX_")}
        self.env["PATH"] = f"{FAKE_CODEX_DIR}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["FAKE_CODEX_ARGV_LOG"] = str(self.argv_log)
        self.env["CLAUDE_CODE_SESSION_ID"] = "test-260813"

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
                    try:
                        os.kill(int(pid), 9)
                    except Exception:
                        pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- driving the bridge --------------------------------------------------

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.project), *args],
                              capture_output=True, text=True)

    def bridge_raw(self, *args, env_extra=None, cwd=None, timeout=90):
        env = dict(self.env)
        if env_extra:
            env.update({k: str(v) for k, v in env_extra.items()})
        return subprocess.run(
            [sys.executable, str(BRIDGE), *[str(a) for a in args]],
            cwd=str(cwd or self.project), env=env, capture_output=True,
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

    # -- reading what happened ----------------------------------------------

    def meta(self, run_id):
        return json.loads(
            (self.project / ".codex-runs" / run_id / "meta.json").read_text())

    def invocations(self):
        """Every argv the bridge actually handed to `codex`."""
        if not self.argv_log.exists():
            return []
        return [json.loads(ln) for ln in
                self.argv_log.read_text().splitlines() if ln.strip()]

    def tasks_file(self, *prompts, kind="start"):
        path = self.tmp / "tasks.jsonl"
        path.write_text("".join(
            json.dumps({"kind": kind, "prompt": p}) + "\n" for p in prompts))
        return path

    def wait_terminal(self, run_id, timeout=60):
        """Block until a run stops moving, and hand back its final meta."""
        from _registry import TERMINAL_STATES
        deadline = time.time() + timeout
        while time.time() < deadline:
            m = self.meta(run_id)
            if m.get("state") in TERMINAL_STATES:
                return m
            time.sleep(0.05)
        self.fail(f"{run_id} never reached a terminal state "
                  f"(last: {self.meta(run_id).get('state')})")
