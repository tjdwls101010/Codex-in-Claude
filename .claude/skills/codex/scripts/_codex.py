"""Talking to the Codex CLI: argv composition, the model catalog, and spawning.

Two invariants live in this module and unify the whole bridge. Both are forced
by Codex's flag surface differing per subcommand — `exec` has `-s` and `-C`;
`exec resume` has neither:

  1. The sandbox is ALWAYS expressed as `-c sandbox_mode="<mode>"`, never `-s`.
  2. The working directory is ALWAYS set on the child process, never via `-C`.

Applying them uniformly closes the settings-drift hole by construction, instead
of by remembering to special-case two subcommands.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from _events import first_thread_id
from _registry import read_meta, update_meta
from util import now_iso

SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")

# How long to wait for `thread.started` before returning `thread_id: null`. It
# is the first line Codex emits and arrives in well under a second; the window
# is generous only so a cold start cannot lose the id, and missing it is not an
# error because `status` backfills it from events.jsonl.
THREAD_ID_WAIT = 15.0

# Seconds a timed-out run gets after SIGINT to flush its rollout before SIGTERM, the same first rung `stop --grace` defaults to.
DEADLINE_GRACE = 5.0


# -- argv -------------------------------------------------------------------

def toml_cfg(key: str, value: str):
    """`-c` values are parsed as TOML, falling back to a raw string only if that
    fails — so a string value is emitted quoted. This is the canonical form."""
    return ["-c", f'{key}="{value}"']


def build_argv(meta: dict, *, kind: str, prompt=None, thread_ref=None):
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

    argv.append("--json")

    if meta.get("isolated", True):
        argv.append("--ignore-user-config")
    if meta.get("skip_git_repo_check"):
        argv.append("--skip-git-repo-check")

    # `codex`'s `-c` is last-value-wins for a repeated key, so anything this
    # wrapper considers its own has to be emitted after anything it does not.
    # `--config` used to put the caller's raw entries here and was emitted
    # *after* the line below, so `--config 'sandbox_mode="danger-full-access"'`
    # simply won: the run executed fully privileged while the registry, and
    # therefore `status`, went on reporting `read-only` (R24). The flag is gone,
    # so there is nothing above this line today — the ordering is stated because
    # it is the rule anything added here has to obey.

    # Invariant 1.
    argv += toml_cfg("sandbox_mode", meta["sandbox"])

    if meta.get("service_tier"):
        argv += toml_cfg("service_tier", meta["service_tier"])
    if meta.get("effort"):
        argv += toml_cfg("model_reasoning_effort", meta["effort"])

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
# "may be running" rather than "are running right now", and "{n} tasks" rather
# than "{n} runs". Both hedges are load-bearing. Members are spawned in
# sequence, so by the time the last one reads this the first may already have
# finished — and a member that failed to spawn was never a run at all, while it
# was always a task. Asserting either as fact would make this paragraph commit
# the exact error it exists to prevent: stating something unobservable without
# hedging.
BATCH_PREAMBLE = (
    "[Batch context: you are one run in a batch of {n} tasks launched together "
    'as group "{group}". Other runs from this batch may be executing alongside '
    "you and editing other paths.]"
)

WORKTREE_PREAMBLE = (
    "[Working tree: yours is an isolated git worktree at {path}, created from "
    "commit {base}. It is not the tree the person who started you is looking at, "
    "and {uncommitted}]"
)


def uncommitted_clause(n) -> str:
    """The caller's uncommitted work is absent from this checkout either way;
    only the count can be unknown.

    This paragraph exists to correct a confident falsehood — Codex otherwise
    assumes it is looking at the caller's tree — so it is the last place that
    should manufacture one. `uncommitted_count` answering 0 for "git would not
    say" put a clean-tree claim in front of the model on evidence it never had.
    """
    if n is None:
        return ("it does not contain the uncommitted file(s) that exist in "
                "theirs — git could not count them, so how many is unknown.")
    if n == 0:
        # Spelled out rather than left to the sentence below, which for zero
        # reads as a double negative around a number — "it does not contain the
        # 0 uncommitted file(s) that exist in theirs" — and a clean tree is the
        # ordinary case, not the edge one.
        return "there is no uncommitted work in theirs for it to be missing."
    return f"it does not contain the {n} uncommitted file(s) that exist in theirs."


def apply_preamble(prompt: str, batch=None) -> str:
    """Prepend the run-context paragraphs.

    Not optional. `--no-preamble` switched all of them off together and was
    never used in 51 real delegations, which on its own would only argue for
    leaving it alone — what argues for removing it is V-18: these paragraphs
    were measured *correcting a confident falsehood* rather than merely adding
    facts, and they cost 113 input tokens. A caller who wants to state the same
    things itself can write them into the prompt, which is the same channel."""
    parts = [PREAMBLE]
    if batch:
        parts.append(BATCH_PREAMBLE.format(n=batch["n"], group=batch["group"]))
        if batch.get("worktree"):
            parts.append(WORKTREE_PREAMBLE.format(
                path=batch["worktree"], base=(batch.get("base") or "?")[:12],
                uncommitted=uncommitted_clause(batch.get("uncommitted"))))
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
            [sys.executable, str(Path(__file__).resolve().parent / "cli_codex.py"),
             "__supervise", "--run-dir", str(run_dir)],
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True, cwd=str(run_dir),
        )
    finally:
        log.close()
    return p.pid


def supervise(run_dir: Path) -> int:
    """Spawn Codex, record what happened, exit. Runs as its own process."""
    meta = read_meta(run_dir)
    if not meta:
        return 1
    # The supervisor is a re-exec of `__supervise --run-dir`, so meta.json is the only channel the deadline survives.
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
    if not Path(meta["cwd"]).is_dir():
        # `Popen` raises the same FileNotFoundError for a missing cwd as for a
        # missing executable, so the two have to be told apart here.
        update_meta(run_dir, state="failed", exit_code=1, ended_at=now_iso(),
                    error=f"the working directory recorded for this run is gone: "
                          f"{meta['cwd']}")
        out.close()
        err.close()
        return 1
    try:
        proc = subprocess.Popen(
            meta["argv"], cwd=meta["cwd"], stdout=out, stderr=err,
            stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        update_meta(run_dir, state="failed", exit_code=127, ended_at=now_iso(),
                    error="codex not found on PATH")
        return 127
    finally:
        out.close()
        err.close()

    # Codex stays in this supervisor's process group (the supervisor is a session leader), which is what lets `stop`'s killpg reach the supervisor, whose handler records `interrupted`.
    # The deadline counts from launch: the thread-id wait below is part of the time the run was given.
    ends_at = time.time() + timeout if timeout is not None else None
    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = None
    update_meta(run_dir, state="running", codex_pid=proc.pid,
                supervisor_pid=os.getpid(), pgid=pgid,
                codex_started_at=now_iso())

    deadline = time.time() + THREAD_ID_WAIT
    if ends_at is not None:
        deadline = min(deadline, ends_at)
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
        rc = proc.wait(timeout=None if ends_at is None else max(0.0, ends_at - time.time()))
    except subprocess.TimeoutExpired:
        # A distinct terminal state, not `interrupted`: the caller needs to tell
        # "I stopped it" from "Codex failed" from "it ran out of the time I gave
        # it", and only the third is answered by raising --timeout. The thread
        # stays resumable across the SIGINT, with the pre-timeout turn's context
        # intact.
        fields = {"state": "timed_out", "ended_at": now_iso(), "error": f"timed out after {timeout}s"}
        rc, group = None, pgid or proc.pid
        # SIGINT lets Codex flush its rollout. Every rung is sent even after Codex exits, because a descendant of it can outlive it in the same group.
        for sig, wait in ((signal.SIGINT, DEADLINE_GRACE), (signal.SIGTERM, 3.0)):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(group, sig)
            try:
                rc = proc.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                pass
        # This supervisor is in the group it is about to SIGKILL, so the outcome is written first.
        update_meta(run_dir, exit_code=rc if rc is not None else -signal.SIGKILL, **fields)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(group, signal.SIGKILL)
        return rc

    if not tid:
        tid = first_thread_id(events_path)
    state = "completed" if rc == 0 else ("interrupted" if interrupted["flag"] else "failed")
    fields = {"state": state, "exit_code": rc, "ended_at": now_iso()}
    if tid:
        fields["thread_id"] = tid
    update_meta(run_dir, **fields)
    return rc
