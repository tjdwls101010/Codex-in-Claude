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
import unicodedata
from pathlib import Path

from _events import final_usage, first_thread_id
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
        # `--` terminates option parsing, and it is required rather than tidy.
        # Two measured failures without it:
        #   * `codex exec`'s `-i/--image <FILE>...` takes MULTIPLE values, so it
        #     greedily swallows the following positional — the prompt becomes a
        #     second image path, Codex finds no prompt, falls back to stdin
        #     (which is /dev/null) and exits having done nothing.
        #   * a prompt beginning with `-` is rejected outright as an unknown
        #     flag; Codex's own error even suggests `--`.
        argv.append("--")
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


# Situational facts again, and for the same reason — but these are facts Codex
# has no way to observe from inside its own turn, and it does not hold back on
# them. Measured (V-18), asked what tree it was in: without this paragraph a run
# answered "it is the shared workspace with the person who started me, so we are
# looking at the same tree" — wrong, and asserted rather than hedged. With it,
# the same run answered correctly and propagated N-1 to reason about the others.
# The failure this prevents is fabrication, not omission, which is why it is not
# optional for batch runs. Cost: 113 input tokens.
#
# Facts only, no methodology (B19). Nothing here tells Codex how to cooperate
# with the other runs; being told they exist is enough to stop it assuming they
# do not.
BATCH_PREAMBLE = (
    "[Batch context: you are one of {n} Codex runs started together as group "
    '"{group}". The others are running in parallel right now and may be editing '
    "other paths.]"
)

WORKTREE_PREAMBLE = (
    "[Working tree: yours is an isolated git worktree at {path}, created from "
    "commit {base}. It is not the tree the person who started you is looking at, "
    "and it does not contain the {uncommitted} uncommitted file(s) that exist in "
    "theirs.]"
)


def apply_preamble(prompt: str, enabled: bool, batch=None) -> str:
    """Prepend the run-context paragraphs. `--no-preamble` turns off all of them
    together — a caller switching it off is saying it will brief Codex itself,
    and half a briefing is worse than none."""
    if not enabled:
        return prompt
    parts = [PREAMBLE]
    if batch:
        parts.append(BATCH_PREAMBLE.format(n=batch["n"], group=batch["group"]))
        if batch.get("worktree"):
            parts.append(WORKTREE_PREAMBLE.format(
                path=batch["worktree"], base=(batch.get("base") or "?")[:12],
                uncommitted=batch.get("uncommitted", 0)))
    return "\n\n".join(parts + [prompt])


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
    if timeout is None:
        # A background run re-execs `__supervise --run-dir`, so nothing can be
        # handed to it on the command line. meta.json is the only channel that
        # survives that hop, which is why the deadline is recorded there.
        timeout = meta.get("timeout_seconds")
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
    if timeout is not None and meta.get("foreground"):
        # Foreground only: the supervisor *is* the caller's process here, so
        # Codex needs its own group for a timeout to kill the tree without
        # killing the caller.
        #
        # Doing the same in the background would be a silent bug rather than a
        # nicety. There the supervisor is already a session leader, and Codex
        # shares its group — which is what lets `stop`'s killpg reach the
        # supervisor, whose handler records `interrupted`. Split them and the
        # signal reaches only Codex, the handler never fires, and a deliberately
        # stopped run is recorded `failed`. Since batch members routinely carry
        # --timeout, that would surface as intermittent lifecycle-test failures
        # that read as flakiness.
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
        # A distinct terminal state, not `interrupted`: the caller needs to tell
        # "I stopped it" from "Codex failed" from "it ran out of the time I gave
        # it", and only the third is answered by raising --timeout. Measured
        # (V-16): the thread stays resumable across this SIGINT, with the
        # pre-timeout turn's context intact — so `timed_out` is recoverable,
        # not a failure.
        update_meta(run_dir, state="timed_out", exit_code=rc, ended_at=now_iso(),
                    error=f"timed out after {timeout}s")
        return rc

    if not tid:
        tid = first_thread_id(events_path)
    state = "completed" if rc == 0 else ("interrupted" if interrupted["flag"] else "failed")
    fields = {"state": state, "exit_code": rc, "ended_at": now_iso()}
    if tid:
        fields["thread_id"] = tid
    # Copy final usage into meta. It is already in events.jsonl, but leaving it
    # there means anything wanting the number has to scan the whole stream —
    # and `batch start`'s projected_cost wants it for several past runs at once,
    # before spawning anything. The supervisor is the one place that pays this
    # scan exactly once, at a point where the stream is complete.
    usage = final_usage(events_path)
    if usage:
        fields["usage"] = usage
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
            if not sel or "id" not in sel:
                return []
            order = " ORDER BY updated_at DESC" if "updated_at" in cols else ""
            params = [limit]
            where = ""
            if cwd_filter and "cwd" in cols:
                # macOS stores non-ASCII filenames as NFD while argv/JSON carry
                # NFC, so a Korean cwd never string-equals its own column value
                # unless both normal forms are tried.
                where = " WHERE cwd = ? OR cwd = ?"
                params = [nfc(str(cwd_filter)),
                          unicodedata.normalize("NFD", str(cwd_filter))] + params
            rows = con.execute(
                f"SELECT {','.join(sel)} FROM threads{where}{order} LIMIT ?",
                params).fetchall()
        finally:
            con.close()
    except Exception:
        return []
    return [dict(zip(sel, row)) for row in rows]
