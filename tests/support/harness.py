"""Scaffolding shared by every test: a throwaway git project, the fake `codex` first on PATH, a pinned empty CODEX_HOME, and the CLI driven as a subprocess.

The CLI is the seam because what is under test includes detached supervisors, process groups and signal delivery, none of which survive being faked in-process.
"""

from __future__ import annotations

import importlib
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

REPO = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO / ".claude" / "skills" / "codex"
# The one place the entrypoint is named. CODEX_BRIDGE_ENTRY points the whole suite at another copy of the scripts, which is how a deliberately broken engine is checked to turn tests red without touching the real one.
ENTRY = Path(os.environ.get("CODEX_BRIDGE_ENTRY") or SKILL_DIR / "scripts" / "cli_codex.py")
SUPPORT = Path(__file__).resolve().parent
FAKE_CODEX_DIR = SUPPORT / "fake_codex"
FIXTURES = SUPPORT / "fixtures"
LEGACY_REGISTRY = SUPPORT / "legacy_registry"

# The engine module each name maps to. Races that have to be staged below the CLI (a stale snapshot racing a completion, many writers on one meta.json) import through `engine()`, so this is the one place a test learns a module's name.
ENGINE_MODULES = {"registry": "_registry"}


def engine(name):
    if str(ENTRY.parent) not in sys.path:
        sys.path.insert(0, str(ENTRY.parent))
    return importlib.import_module(ENGINE_MODULES[name])


TERMINAL = ("completed", "failed", "interrupted", "orphaned", "timed_out")

# Run ids in legacy_registry/: a 0.6 `review` run, a finished phase-1 member with a boolean `priority`, and an `--as-ready` member still `waiting` on it.
LEGACY_REVIEW = "20260803-204347-reviewer-4efc"
LEGACY_PREDECESSOR = "20260810-100000-p1-aaaa"
LEGACY_WAITER = "20260810-100500-p2-bbbb"


def alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def wait_until(pred, timeout=30, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = pred()
        if value:
            return value
        time.sleep(interval)
    return pred()


class BridgeCase(unittest.TestCase):
    """One temp project per test. `self.project` is a git repository with one commit, so worktrees can be cut from HEAD."""

    def setUp(self):
        # resolve(): on macOS /var is a symlink to /private/var and the bridge records resolved paths.
        self.tmp = Path(tempfile.mkdtemp(prefix="codex-test-")).resolve()
        self.addCleanup(self._cleanup)
        self.project = self.tmp / "proj"
        self.project.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "Test")
        (self.project / "tracked.txt").write_text("one\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

        self.argv_log = self.tmp / "argv.jsonl"
        self.codex_home = self.tmp / "codex-home"
        self.codex_home.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("FAKE_CODEX_") and k not in ("CODEX_HOME", "CLAUDE_PLUGIN_ROOT")}
        self.env["PATH"] = f"{FAKE_CODEX_DIR}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["FAKE_CODEX_ARGV_LOG"] = str(self.argv_log)
        # Pinned and empty: the bridge reads config.toml for the user's defaults, and a suite that inherited the developer's would assert against whatever they configured.
        self.env["CODEX_HOME"] = str(self.codex_home)
        self.env["CLAUDE_CODE_SESSION_ID"] = "test-session"

    def _cleanup(self):
        for runs in {self.project / ".codex-runs", *getattr(self, "extra_runs_dirs", ())}:
            if not runs.is_dir():
                continue
            for d in runs.iterdir():
                try:
                    m = json.loads((d / "meta.json").read_text())
                except Exception:
                    continue
                for key in ("supervisor_pid", "codex_pid"):
                    pid = m.get(key)
                    if pid and int(pid) != os.getpid():
                        try:
                            os.kill(int(pid), signal.SIGKILL)
                        except OSError:
                            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- driving the CLI -------------------------------------------------------

    def git(self, *args, cwd=None, check=True):
        return subprocess.run(["git", "-C", str(cwd or self.project), *map(str, args)],
                              capture_output=True, text=True, check=check)

    def bridge_raw(self, *args, env=None, cwd=None, timeout=90, entry=None, stdin=None):
        full = dict(self.env)
        full.update({k: str(v) for k, v in (env or {}).items()})
        return subprocess.run([sys.executable, str(entry or ENTRY), *map(str, args)],
                              cwd=str(cwd or self.project), env=full, capture_output=True,
                              text=True, timeout=timeout,
                              input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL)

    def bridge(self, *args, rc=0, **kw):
        """Run a command that answers with one line of JSON, and parse it."""
        p = self.bridge_raw(*args, **kw)
        self.assertEqual(p.returncode, rc, f"rc={p.returncode} for {args}\nstdout={p.stdout}\nstderr={p.stderr}")
        lines = p.stdout.splitlines()
        self.assertEqual(len(lines), 1, f"expected one line of JSON for {args}, got {p.stdout!r}")
        return json.loads(lines[0])

    def spawn(self, *args, env=None):
        """Start the CLI without waiting, for races and for killing it midway."""
        full = dict(self.env)
        full.update({k: str(v) for k, v in (env or {}).items()})
        p = subprocess.Popen([sys.executable, str(ENTRY), *map(str, args)], cwd=str(self.project),
                             env=full, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL, text=True, start_new_session=True)
        self.addCleanup(self._kill_group, p)
        return p

    def _kill_group(self, p):
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
        p.communicate(timeout=10)

    def log(self, *args, **kw):
        """`log` output split into (event lines, cursor)."""
        p = self.bridge_raw("log", *args, **kw)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        body, cursor = [], None
        for ln in p.stdout.splitlines():
            if ln.startswith("# cursor="):
                cursor = int(ln.split()[1].split("=", 1)[1])
            else:
                body.append(ln)
        return body, cursor

    # -- reading what happened ------------------------------------------------

    @property
    def runs_dir(self):
        return self.project / ".codex-runs"

    def meta(self, run_id, runs_dir=None):
        return json.loads(((runs_dir or self.runs_dir) / run_id / "meta.json").read_text())

    def write_meta(self, run_id, meta, runs_dir=None):
        d = (runs_dir or self.runs_dir) / run_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps(meta))

    def detached_process(self):
        """A live process in a process group of its own that is not this test's child, so a signal ends it outright instead of leaving a zombie that still answers `kill -0`. Returns its pid, which is also its pgid."""
        p = subprocess.run([sys.executable, "-c",
                            "import os, sys, time\n"
                            "if os.fork(): os._exit(0)\n"
                            "os.setsid()\n"
                            "print(os.getpid(), flush=True)\n"
                            "sys.stdout.close(); os.close(1)\n"
                            "time.sleep(300)"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           text=True, timeout=10)
        pid = int(p.stdout.split()[0])
        self.addCleanup(lambda: alive(pid) and os.killpg(pid, signal.SIGKILL))
        return pid

    def install_legacy_registry(self):
        """Copy the registry an older release left behind into this project, and give its `waiting` member a live supervisor stand-in. Returns the stand-in's pid."""
        shutil.copytree(LEGACY_REGISTRY, self.runs_dir, dirs_exist_ok=True)
        for f in self.runs_dir.rglob("*.json"):
            f.write_text(f.read_text().replace("@RUNS@", str(self.runs_dir)).replace("@PROJECT@", str(self.project)))
        sup = self.detached_process()
        self.write_meta(LEGACY_WAITER, {**self.meta(LEGACY_WAITER), "supervisor_pid": sup, "pgid": sup})
        return sup

    def run_dirs(self):
        return sorted(p.name for p in self.runs_dir.iterdir()
                      if p.is_dir() and not p.name.startswith(".")) if self.runs_dir.is_dir() else []

    def invocations(self):
        """Every codex invocation the bridge made, in order (catalog lookups excluded)."""
        if not self.argv_log.exists():
            return []
        return [json.loads(ln) for ln in self.argv_log.read_text().splitlines() if ln.strip()]

    def runs_invoked(self):
        return [r for r in self.invocations() if r["argv"][:1] == ["exec"]]

    def last_argv(self):
        runs = self.runs_invoked()
        self.assertTrue(runs, "codex was never asked to run")
        return runs[-1]["argv"]

    def config_values(self, argv):
        """The `-c key=value` entries of an argv, as a dict of raw values."""
        return dict(argv[i + 1].split("=", 1) for i, t in enumerate(argv) if t == "-c")

    def tasks_file(self, *items, name="tasks.jsonl"):
        """A --tasks-file; a bare string is a `{"prompt": ...}` task."""
        path = self.tmp / name
        path.write_text("".join(json.dumps(i if isinstance(i, dict) else {"prompt": i}) + "\n" for i in items))
        return path

    # -- waiting ----------------------------------------------------------------

    def row(self, run_id, *extra):
        return self.bridge("status", "--run", run_id, *extra)["runs"][0]

    def wait_state(self, run_id, states=TERMINAL, timeout=60, extra=()):
        """Poll `status --run` (which reaps) until the run is in one of `states`."""
        found = wait_until(lambda: (lambda r: r if r["state"] in states else None)(self.row(run_id, *extra)),
                           timeout=timeout, interval=0.1)
        if not found:
            self.fail(f"{run_id} never reached {states}; last={self.row(run_id, *extra)['state']}")
        return found

    def wait_all(self, out):
        """Wait for every spawned member of a `batch start` reply."""
        for r in out["runs"]:
            if r.get("run_id"):
                self.wait_state(r["run_id"])

    def running(self, *args, hang=60, **env):
        """Start a run that stays in its turn, and return (reply, meta) once both pids are recorded."""
        out = self.bridge("start", *args, env={"FAKE_CODEX_HANG": hang, **env})
        m = wait_until(lambda: (lambda m: m if m.get("codex_pid") and m.get("state") == "running" else None)(
            self.meta(out["run_id"])), timeout=30)
        self.assertTrue(m, "the run never reached running")
        return out, m

    def orphan_still_writing(self, *args, hang=60, **env):
        """A run recorded `orphaned` whose codex is demonstrably still going: its supervisor is killed and its child is not."""
        out, m = self.running(*args, hang=hang, **env)
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        wait_until(lambda: not alive(m["supervisor_pid"]), timeout=10)
        self.assertEqual(self.row(out["run_id"])["state"], "orphaned")
        self.assertTrue(alive(m["codex_pid"]), "fixture needs codex to outlive its supervisor")
        return out, m
