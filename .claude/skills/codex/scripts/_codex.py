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

import json
import os
import re
import shutil
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

RESERVED_CONFIG_KEYS = {
    "sandbox_mode": "--sandbox",
    "service_tier": "--priority / --no-priority",
    "model_reasoning_effort": "--effort",
    "model": "--model",
}


def reserved_config_key(raw: str):
    """The key in a raw `--config k=v`, if this wrapper is the one that sets it.

    These four are not configuration this skill passes through — they are what
    it records in the registry and re-asserts on every turn, which is the only
    reason a resumed run cannot silently change its sandbox. A raw `-c` naming
    one of them makes the registry's copy a lie: `status` keeps reporting what
    was asked for while the run does something else, and because `extra_config`
    is inherited by every later resume, it does so for the rest of the thread.

    Refused rather than reordered around. Reordering (see `build_argv`) stops
    the override from taking effect, but silently ignoring what a caller
    explicitly typed is its own D27 failure — the caller has to be told that
    `--sandbox` is where that decision lives.
    """
    key = str(raw).split("=", 1)[0].strip()
    return key if key in RESERVED_CONFIG_KEYS else None


def toml_cfg(key: str, value: str):
    """`-c` values are parsed as TOML, falling back to a raw string only if that
    fails — so a string value is emitted quoted. This is the canonical form."""
    return ["-c", f'{key}="{value}"']


# -- the model catalog ------------------------------------------------------
# Nothing about models or efforts is written down in this skill. It is asked of
# Codex, because both lists move: `--model` is not pinned for the reason D19
# gives — a hardcoded model name is a guaranteed future bug — and the effort
# list rots faster still, since which efforts are valid depends on the model.
# Measured on codex-cli 0.146.0: `ultra` is offered by gpt-5.6-sol and
# gpt-5.6-terra, absent from gpt-5.6-luna, and gpt-5.5 stops at `xhigh`. Any
# static list is already wrong for some model on the day it is written.

# Deliberately short. The lookup reads a local cache file and returns in ~30 ms
# measured; anything slower than this is a `codex` that is not answering, and
# the honest response to that is to skip the check rather than to hold up the
# run. A generous window here is paid on the critical path of every run start.
CATALOG_TIMEOUT = 5.0

# One lookup per process. The catalog cannot change inside a single CLI
# invocation, and without this a `batch start` of N members pays N+1 identical
# subprocess calls — once in `load_tasks` and once per `create_run`.
_CATALOG_CACHE = []


def codex_version():
    exe = shutil.which("codex")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           timeout=20, stdin=subprocess.DEVNULL)
    except Exception:
        return None
    return (r.stdout or r.stderr).strip() or None


def model_catalog():
    """What this Codex install actually offers, or None if it cannot be read.

    `codex debug models` reports the catalog Codex fetched from the server into
    `CODEX_HOME/models_cache.json`. Measured: it reads that cache without
    refreshing it, while `codex exec` refreshes on every run — so asking costs
    nothing and changes nothing, and because this skill runs `codex exec` for
    every run, the cache is never staler than the caller's last run.

    Returns None on every failure — no binary, non-zero exit, unparseable
    output, missing fields. Callers treat that as "cannot check", never as
    "invalid": a check that blocks a run because its own lookup broke is worse
    than no check, and `doctor` is where the caller learns it is off.
    """
    if _CATALOG_CACHE:
        return _CATALOG_CACHE[0]
    _CATALOG_CACHE.append(None)

    exe = shutil.which("codex")
    if not exe:
        return None
    # ONE try around everything, parsing included, and the boundary is the
    # point. It first wrapped only the subprocess and `json.loads`, leaving the
    # shaping loop outside — so a catalog that was valid JSON but wrong-typed
    # (`"supported_reasoning_levels": 5`, truthy, so `or []` does not save it)
    # raised TypeError straight past this function into the CLI's top-level
    # handler, and `start` died with `internal error` having spawned nothing.
    # A batch was worse: one malformed entry blocked every member. That is
    # precisely the fail-closed outcome the None-on-failure contract exists to
    # prevent, reached by trusting the shape of someone else's JSON.
    try:
        r = subprocess.run([exe, "debug", "models"], capture_output=True,
                           text=True, timeout=CATALOG_TIMEOUT,
                           stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return None
        models = json.loads(r.stdout)["models"]
        if not isinstance(models, list):
            return None

        out = []
        for m in models:
            if not isinstance(m, dict) or not m.get("slug"):
                continue
            levels = m.get("supported_reasoning_levels")
            # These fields and no others. The raw payload is ~346 KB, almost all
            # of it each model's `base_instructions` — passing it through would
            # make `models` the largest single context leak in a skill whose
            # default event filter exists to withhold a 22 KB `cat`.
            out.append({
                "slug": m["slug"],
                "display_name": m.get("display_name"),
                "default_effort": m.get("default_reasoning_level"),
                "efforts": [lv["effort"] for lv in (levels if isinstance(levels, list) else [])
                            if isinstance(lv, dict) and lv.get("effort")],
                "context_window": m.get("context_window"),
                "visibility": m.get("visibility"),
                "supported_in_api": m.get("supported_in_api"),
            })
    except Exception:
        return None
    _CATALOG_CACHE[0] = out or None
    return _CATALOG_CACHE[0]


def check_model_effort(model, effort, *, catalog, fail):
    """Refuse a model or effort this Codex install does not offer.

    Only values the caller just passed reach here — never one inherited from
    the thread being resumed. A recorded setting was checked when it was first
    passed, and re-checking it would mean a model retired upstream turns every
    resume of an existing thread into a refusal, breaking the continuity
    `resume` exists to provide.

    Checked locally because the alternative is measured: an unknown value
    spawns the run, reaches the API, and returns `turn.failed` with exit 1 —
    loud, but a wasted run late, and for a background run not seen until the
    next `status`. Reading the catalog instead costs ~30 ms and no API call.

    `fail` is passed in for the same reason `review_argv` takes it: the CLI
    exits, a batch member raises inside `failures_raise`.
    """
    if not catalog or (not model and not effort):
        return
    by_slug = {m["slug"]: m for m in catalog}
    if model and model not in by_slug:
        fail(f"unknown model {model!r}: this Codex install does not offer it. "
             f"The catalog refreshes on any Codex run, so if this name is newer "
             f"than your last run, start one and retry.",
             known_models=sorted(by_slug),
             hint="`models` prints the catalog with each model's efforts")
    if not effort:
        return
    if model:
        allowed = by_slug[model]["efforts"]
        if allowed and effort not in allowed:
            fail(f"model {model!r} does not accept effort {effort!r} — valid "
                 f"efforts differ per model.", model=model, valid_efforts=allowed,
                 default_effort=by_slug[model].get("default_effort"))
        return
    # No model named, so no single list governs. The union still catches a typo;
    # a value valid only on some other model passes here and is refused by the
    # API exactly as it is today. No new hole, one fewer.
    union = sorted({e for m in catalog for e in m["efforts"]})
    if union and effort not in union:
        fail(f"unknown effort {effort!r}: no model in this Codex install accepts it.",
             valid_efforts=union,
             hint="efforts are per-model; `models` shows which model takes which")


REVIEW_SELECTORS = ("uncommitted", "base", "commit", "prompt")


def review_argv(*, uncommitted=None, base=None, commit=None, title=None,
                prompt=None, fail):
    """`codex exec review`'s own flag surface, validated in one place.

    Two callers build this — `review` on the command line and a `kind: review`
    member of a batch — and they had drifted. The CLI refused a `--title`
    without a `--commit` and refused combinations the Codex CLI itself rejects;
    the batch path did neither, so a tasks file could ask for `uncommitted` and
    `base` together and get a member that failed asynchronously, or name a
    `title` that was dropped without a word. `load_tasks` already states the
    principle it was breaking: a silently ignored field is a run that quietly
    did something else.

    `fail` is passed in because the two callers report errors differently — one
    exits, one raises inside `failures_raise` so the rest of the batch survives.
    """
    chosen = [n for n, v in (("--uncommitted", uncommitted), ("--base", base),
                             ("--commit", commit), ("prompt", prompt)) if v]
    if len(chosen) != 1:
        fail("review takes exactly one of --uncommitted, --base <ref>, "
             "--commit <sha>, or a prompt; the Codex CLI rejects combinations",
             given=chosen)
    if title and not commit:
        fail("--title is only valid with --commit")
    if uncommitted:
        return ["--uncommitted"]
    if base:
        return ["--base", str(base)]
    if commit:
        return ["--commit", str(commit)] + (["--title", str(title)] if title else [])
    return []


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

    # The caller's raw `-c` entries go FIRST, and the order is the point.
    # `codex`'s `-c` is last-value-wins for a repeated key, so while these were
    # emitted last, `--config 'sandbox_mode="danger-full-access"'` beat the line
    # below it — the run executed fully privileged while the registry, and
    # therefore `status`, went on reporting `read-only`. Measured against the
    # real binary: the same file write is refused with one `-c` and succeeds
    # with both. That is the single thing this wrapper exists to prevent,
    # reachable through a documented flag.
    #
    # `RESERVED_CONFIG_KEYS` refuses that collision at the point a run is built,
    # which is the honest fix. This ordering is the second line: a key nobody
    # thought to reserve still cannot outrank an invariant.
    for raw in meta.get("extra_config") or []:
        argv += ["-c", raw]

    # Invariant 1.
    argv += toml_cfg("sandbox_mode", meta["sandbox"])

    if meta.get("priority"):
        argv += toml_cfg("service_tier", "priority")
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
    if meta.get("foreground"):
        # Foreground only: the supervisor *is* the caller's process here, so
        # Codex needs its own group — for a timeout to kill the tree without
        # killing the caller, and equally so that the `pgid` this run records
        # is its own. Gated on `timeout is not None` until measured, which meant
        # a foreground run without one recorded the *caller's* process group and
        # a later `stop --run` would have signalled the caller. A run's recorded
        # pgid has to belong to the run whatever else is true of it.
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
