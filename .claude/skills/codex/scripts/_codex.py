"""Talking to the Codex CLI: argv composition, spawning, and its thread database.

Two invariants live in this module and unify the whole bridge. Both are forced
by Codex's flag surface differing per subcommand — `exec` has `-s` and `-C`;
`exec resume` and `exec review` have neither:

  1. The sandbox is ALWAYS expressed as `-c sandbox_mode="<mode>"`, never `-s`.
  2. The working directory is ALWAYS set on the child process, never via `-C`.

Applying them uniformly closes the settings-drift hole by construction, instead
of by remembering to special-case two subcommands.
"""

from __future__ import annotations

import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from _events import first_thread_id
from _registry import read_meta, update_meta
from _util import codex_home, nfc, now_iso

SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")

# How long to wait for `thread.started` before returning `thread_id: null`. It
# is the first line Codex emits and arrives in well under a second; the window
# is generous only so a cold start cannot lose the id, and missing it is not an
# error because `status` backfills it from events.jsonl.
THREAD_ID_WAIT = 15.0


# -- argv -------------------------------------------------------------------

def toml_cfg(key: str, value: str):
    """`-c` values are parsed as TOML, falling back to a raw string only if that
    fails — so a string value is emitted quoted. This is the canonical form."""
    return ["-c", f'{key}="{value}"']


def build_argv(meta: dict, *, kind: str, prompt=None, thread_ref=None, review_args=None):
    """Compose the Codex argv for a run from its recorded settings.

    Every per-invocation setting is re-asserted on every call, including on
    resume. `codex exec resume` inherits none of them from the thread: it
    re-derives them from whatever config layer is in effect, so an unre-asserted
    resume drifts to `danger-full-access` under the user's config or down to
    `read-only` under isolation, silently dropping the reasoning effort either
    way. Re-asserting is what makes a run's settings stable across turns, and
    anti-escalation is one consequence of that rather than the whole of it.
    """
    argv = ["codex", "exec"]
    if kind == "resume":
        argv.append("resume")
        if thread_ref == "--last":
            argv.append("--last")
        elif thread_ref:
            argv.append(thread_ref)
    elif kind == "review":
        argv.append("review")

    argv.append("--json")

    if meta.get("isolated", True):
        argv.append("--ignore-user-config")
    if meta.get("skip_git_repo_check"):
        argv.append("--skip-git-repo-check")

    # Invariant 1.
    argv += toml_cfg("sandbox_mode", meta["sandbox"])

    if meta.get("priority"):
        argv += toml_cfg("service_tier", "priority")
    if meta.get("effort"):
        argv += toml_cfg("model_reasoning_effort", meta["effort"])
    for raw in meta.get("extra_config") or []:
        argv += ["-c", raw]

    if meta.get("model"):
        argv += ["-m", meta["model"]]
    if meta.get("schema_path"):
        argv += ["--output-schema", meta["schema_path"]]

    argv += ["-o", str(Path(meta["run_dir"]) / "last-message.txt")]

    if kind == "start":
        for d in meta.get("add_dirs") or []:
            argv += ["--add-dir", d]
    for img in meta.get("images") or []:
        argv += ["-i", img]

    if kind == "review":
        argv += list(review_args or [])

    if prompt is not None:
        argv.append(prompt)
    return argv


# Situational facts only — no methodology. Codex is being asked a question it
# cannot ask a follow-up about, and the single most expensive failure mode in a
# non-interactive turn is spending the whole turn asking one.
PREAMBLE = (
    "[Run context: you are a single non-interactive `codex exec` turn. Nobody is "
    "watching a prompt, so a clarifying question ends this turn with the work not "
    "done — take the most reasonable reading, proceed, and state what you assumed. "
    "Your final message is what the caller receives; put the answer there, not only "
    "in files you touched.]"
)


def apply_preamble(prompt: str, enabled: bool) -> str:
    return f"{PREAMBLE}\n\n{prompt}" if enabled else prompt


# -- spawning ---------------------------------------------------------------

def spawn_supervised(run_dir: Path) -> int:
    """Start the run under a supervisor process, in its own session.

    A background `codex exec` needs someone to reap it, or nothing ever records
    the exit code and a finished run is indistinguishable from a crashed one.
    Spawning the supervisor into a new session puts supervisor and Codex in one
    process group, which is what lets `stop` signal exactly one run's tree —
    and why it never has to match processes by name, the thing that would make
    concurrent runs kill each other.
    """
    log = (run_dir / "supervisor.log").open("ab")
    try:
        p = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent / "codex_bridge.py"),
             "__supervise", "--run-dir", str(run_dir)],
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True, cwd=str(run_dir),
        )
    finally:
        log.close()
    return p.pid


def supervise(run_dir: Path, timeout=None) -> int:
    """Spawn Codex, record what happened, exit. Runs as its own process."""
    meta = read_meta(run_dir)
    if not meta:
        return 1
    interrupted = {"flag": False}

    def on_signal(signum, _frame):
        # Deliberately does not exit. Codex flushes its rollout on SIGINT and
        # stays resumable; if the supervisor died first, nothing would record
        # the outcome and the run would read as `running` forever.
        interrupted["flag"] = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, on_signal)
        except ValueError:
            pass

    events_path = run_dir / "events.jsonl"
    out = events_path.open("ab")
    err = (run_dir / "stderr.log").open("ab")
    kwargs = {}
    if timeout is not None:
        # Foreground: give Codex its own group so a timeout can kill the tree
        # without killing the caller.
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            meta["argv"], cwd=meta["cwd"], stdout=out, stderr=err,
            stdin=subprocess.DEVNULL, **kwargs)
    except FileNotFoundError:
        update_meta(run_dir, state="failed", exit_code=127, ended_at=now_iso(),
                    error="codex not found on PATH")
        return 127
    finally:
        out.close()
        err.close()

    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = None
    update_meta(run_dir, state="running", codex_pid=proc.pid,
                supervisor_pid=os.getpid(), pgid=pgid)

    deadline = time.time() + THREAD_ID_WAIT
    tid = None
    while time.time() < deadline:
        tid = first_thread_id(events_path)
        if tid:
            update_meta(run_dir, thread_id=tid)
            break
        if proc.poll() is not None:
            break
        time.sleep(0.05)

    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        except Exception:
            pass
        try:
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait()
        update_meta(run_dir, state="interrupted", exit_code=rc, ended_at=now_iso(),
                    error=f"timed out after {timeout}s")
        return rc

    if not tid:
        tid = first_thread_id(events_path)
    state = "completed" if rc == 0 else ("interrupted" if interrupted["flag"] else "failed")
    fields = {"state": state, "exit_code": rc, "ended_at": now_iso()}
    if tid:
        fields["thread_id"] = tid
    update_meta(run_dir, **fields)
    return rc


# -- Codex's own thread database --------------------------------------------
# The filename is version-stamped (state_5.sqlite today), so the schema WILL
# change. Every access here is defensive: introspect the columns, select only
# what exists, and return nothing rather than raising. A Codex upgrade must
# degrade this feature, never break the skill outright.

def state_db_path():
    home = codex_home()
    cands = list(home.glob("state_*.sqlite"))
    if cands:
        def version(p):
            m = re.search(r"state_(\d+)\.sqlite$", p.name)
            return int(m.group(1)) if m else -1
        return sorted(cands, key=version)[-1]
    legacy = home / "state.sqlite"
    return legacy if legacy.exists() else None


def query_threads(cwd_filter=None, limit=50):
    """Threads Codex knows about, including ones this skill never started.

    This is what lets Claude continue a session the user began in the Codex TUI.
    """
    db = state_db_path()
    if not db or not db.exists():
        return []
    want = ["id", "rollout_path", "cwd", "title", "source", "model",
            "reasoning_effort", "sandbox_policy", "approval_mode",
            "cli_version", "updated_at"]
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(threads)")}
            sel = [c for c in want if c in cols]
            if not sel:
                return []
            order = " ORDER BY updated_at DESC" if "updated_at" in cols else ""
            rows = con.execute(
                f"SELECT {','.join(sel)} FROM threads{order} LIMIT ?",
                (limit * 4,)).fetchall()
        finally:
            con.close()
    except Exception:
        return []
    out = []
    for row in rows:
        rec = dict(zip(sel, row))
        if cwd_filter and nfc(str(rec.get("cwd") or "")) != nfc(str(cwd_filter)):
            continue
        out.append(rec)
        if len(out) >= limit:
            break
    return out
