"""Shared scaffolding for the T1 suite.

Tests drive `codex_bridge.py` as a subprocess rather than importing and calling
its subcommands, because the thing under test includes process spawning, process
groups and signal delivery -- none of which survive being faked in-process. Pure
functions (argv composition, filtering, cursors) are imported directly.
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

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parent
BRIDGE = REPO / ".claude" / "skills" / "codex" / "scripts" / "codex_bridge.py"
FAKE_DIR = TESTS_DIR / "fake_codex"
FIXTURES = TESTS_DIR / "fixtures"

# Importing this module is what puts the skill's scripts on sys.path, so a test
# that wants a pure function reaches for its own module (`_codex.build_argv`,
# `_util.nfc`) after importing helpers — not through the entrypoint, which owns
# only the CLI surface.
sys.path.insert(0, str(BRIDGE.parent))


class BridgeTestCase(unittest.TestCase):
    """A temp git project, the fake `codex` first on PATH, an argv log."""

    fixture = None          # basename under tests/fixtures, or None for the shim default
    project_name = "proj"

    def setUp(self):
        # resolve(): on macOS /var is a symlink to /private/var, and the bridge
        # resolves every path it records — so an unresolved base makes every
        # path comparison in these tests spuriously unequal.
        self.tmp = Path(tempfile.mkdtemp(prefix="codexbridge-")).resolve()
        self.addCleanup(self._cleanup)
        self.project = self.tmp / self.project_name
        self.project.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True,
                       capture_output=True)
        self.argv_log = self.tmp / "argv.jsonl"
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("FAKE_CODEX_")}
        self.env["PATH"] = f"{FAKE_DIR}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["FAKE_CODEX_ARGV_LOG"] = str(self.argv_log)
        self.env["CLAUDE_CODE_SESSION_ID"] = "test-session-aaaa"
        if self.fixture:
            self.env["FAKE_CODEX_FIXTURE"] = str(FIXTURES / self.fixture)

    def _cleanup(self):
        # Never leave a supervisor behind: a stray one keeps writing into a temp
        # dir the next test is about to reuse.
        runs = self.project / ".codex-runs"
        if runs.is_dir():
            for d in runs.iterdir():
                meta = d / "meta.json"
                if not meta.is_file():
                    continue
                try:
                    m = json.loads(meta.read_text())
                except Exception:
                    continue
                for pid in (m.get("supervisor_pid"), m.get("codex_pid")):
                    if pid:
                        try:
                            os.kill(int(pid), 9)
                        except Exception:
                            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- invoking the bridge -------------------------------------------------

    def bridge_raw(self, *args, env_extra=None, cwd=None, timeout=90):
        env = dict(self.env)
        if env_extra:
            env.update({k: str(v) for k, v in env_extra.items()})
        return subprocess.run(
            [sys.executable, str(BRIDGE), *[str(a) for a in args]],
            cwd=str(cwd or self.project), env=env, capture_output=True,
            text=True, timeout=timeout,
        )

    def bridge(self, *args, expect_rc=0, **kw):
        """Run the bridge and parse its one line of JSON."""
        p = self.bridge_raw(*args, **kw)
        self.assertEqual(
            p.returncode, expect_rc,
            f"rc={p.returncode} for {args}\nstdout={p.stdout}\nstderr={p.stderr}")
        try:
            return json.loads(p.stdout.strip().splitlines()[-1])
        except Exception as e:  # pragma: no cover - only fires on a real bug
            self.fail(f"non-JSON stdout for {args}: {e}\nstdout={p.stdout!r}\n"
                      f"stderr={p.stderr!r}")

    def log_lines(self, *args, **kw):
        """Run `log` and split into (content lines, cursor)."""
        p = self.bridge_raw("log", *args, **kw)
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.splitlines()
        cursor = None
        body = []
        for ln in lines:
            if ln.startswith("# cursor="):
                # Trailer is `# cursor=<n> run=<id>` (F11) — take only the
                # cursor field, whitespace-delimited from `run=`.
                cursor = int(ln[len("# cursor="):].split(" ", 1)[0])
            else:
                body.append(ln)
        return body, cursor

    # -- assertions and waiting ---------------------------------------------

    def argv_records(self):
        if not self.argv_log.exists():
            return []
        return [json.loads(l) for l in self.argv_log.read_text().splitlines() if l.strip()]

    def last_argv(self):
        recs = self.argv_records()
        self.assertTrue(recs, "the fake codex was never invoked")
        return recs[-1]["argv"]

    def wait_for_state(self, run_id, states=("completed", "failed", "interrupted", "orphaned"),
                       timeout=60):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            st = self.bridge("status", "--run", run_id)
            last = st["runs"][0]
            if last["state"] in states:
                return last
            time.sleep(0.15)
        self.fail(f"run {run_id} never reached {states}; last state={last and last['state']}")

    def start(self, prompt="do a thing", *extra, **kw):
        return self.bridge("start", *extra, prompt, **kw)

    def assertFlagPair(self, argv, flag, value, msg=None):
        """Assert `flag value` appear adjacent in argv."""
        for i, tok in enumerate(argv):
            if tok == flag and i + 1 < len(argv) and argv[i + 1] == value:
                return
        self.fail(msg or f"expected {flag} {value!r} in argv, got: {argv}")

    def assertNoFlag(self, argv, *flags):
        for f in flags:
            self.assertNotIn(f, argv, f"{f} must never be emitted; argv={argv}")
