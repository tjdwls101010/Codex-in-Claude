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
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from _events import final_usage, first_thread_id
from _registry import read_meta, update_meta
from _util import codex_home, now_iso

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


# -- the user's own defaults ------------------------------------------------
# Isolation is the default and `--ignore-user-config` takes the whole file, so
# for a year an unnamed run took Codex's *server* default rather than the model
# the user had configured. Measured across 21 benchmark sessions: not one argv
# carried a model or an effort.
#
# These three keys go back in. `sandbox_mode` is deliberately not among them —
# it is the invariant this skill owns and re-asserts on every turn, and reading
# it from a file the caller can edit is R24 arriving by another road. The
# principle is not "the skill has defaults" but "the skill has none of its own
# and respects the user's": policy lives in the user's file, and the edit path
# is Codex's own `/model` and `/fast`.
USER_DEFAULT_KEYS = ("model", "model_reasoning_effort", "service_tier")

# `key = value` at the top level. A regex and not a TOML parser because
# `tomllib` is 3.11 and this skill's floor is 3.10.
_SCALAR_RE = re.compile(
    r"""^([A-Za-z_][\w-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s#]+))""")


def config_scalars(keys, path=None):
    """Named top-level scalars from `config.toml`, as strings.

    The scan stops at the first `[table]` header, and that is the load-bearing
    part rather than an optimisation: `model` under `[profiles.work]` is a
    different setting from the top-level one, and Codex applies the top-level
    value unless a profile is selected — which this wrapper never does. A
    pattern that matched anywhere in the file would silently adopt a profile's
    model for every run.

    Every failure answers `{}`: an unreadable or absent config means there is
    nothing to respect, not that a run should be refused.
    """
    path = Path(path) if path else codex_home() / "config.toml"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            break
        m = _SCALAR_RE.match(s)
        if not m or m.group(1) not in keys:
            continue
        out[m.group(1)] = next(g for g in m.groups()[1:] if g is not None)
    return out


def user_defaults():
    """`{model, effort, service_tier}` from the user's `config.toml`.

    Read fresh rather than cached: a `batch start` reads it once per member and
    the file is a few hundred bytes, while a cache would mean the value a run
    records depends on how long the process had been alive.
    """
    raw = config_scalars(USER_DEFAULT_KEYS)
    return {"model": raw.get("model"),
            "effort": raw.get("model_reasoning_effort"),
            "service_tier": raw.get("service_tier")}


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


def check_model_effort(model, effort, *, catalog, fail, model_source=None,
                       effort_source=None):
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

    `fail` is passed in because the two callers report errors differently: the
    CLI exits, a batch member raises inside `failures_raise`.

    The two `*_source` strings name where a value came from when it was not
    typed on the command line, and they are per value rather than shared: with
    a `--model` flag and an effort taken from `config.toml`, blaming both on
    the config would send the caller to edit a file that is not the problem.
    """
    if not catalog or (not model and not effort):
        return
    ms = f" (from {model_source})" if model_source else ""
    es = f" (from {effort_source})" if effort_source else ""
    by_slug = {m["slug"]: m for m in catalog}
    if model and model not in by_slug:
        fail(f"unknown model {model!r}{ms}: this Codex install does not offer it. "
             f"The catalog refreshes on any Codex run, so if this name is newer "
             f"than your last run, start one and retry.",
             known_models=sorted(by_slug),
             hint="`models` prints the catalog with each model's efforts")
    if not effort:
        return
    if model:
        allowed = by_slug[model]["efforts"]
        if allowed and effort not in allowed:
            fail(f"model {model!r} does not accept effort {effort!r}{es} — valid "
                 f"efforts differ per model.", model=model, valid_efforts=allowed,
                 default_effort=by_slug[model].get("default_effort"))
        return
    # No model named, so no single list governs. The union still catches a typo;
    # a value valid only on some other model passes here and is refused by the
    # API exactly as it is today. No new hole, one fewer.
    union = sorted({e for m in catalog for e in m["efforts"]})
    if union and effort not in union:
        fail(f"unknown effort {effort!r}{es}: no model in this Codex install "
             f"accepts it.",
             valid_efforts=union,
             hint="efforts are per-model; `models` shows which model takes which")


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
            [sys.executable, str(Path(__file__).resolve().parent / "codex_bridge.py"),
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
    # `batch start`'s projected_cost reads final usage from meta for several past runs at once.
    usage = final_usage(events_path)
    if usage:
        fields["usage"] = usage
    update_meta(run_dir, **fields)
    return rc
