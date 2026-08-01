#!/usr/bin/env python3
"""Drive the OpenAI Codex CLI as a managed subagent.

Python 3.10+, standard library only. Every subcommand prints exactly one line of
JSON on stdout, except `log`, which prints compact text plus a trailing
`# cursor=<n>` line — JSON framing per event would itself be a meaningful
fraction of the context the filter exists to save.

This file is the entrypoint and holds the CLI surface and the subcommand
handlers. The machinery lives in siblings, which Python resolves via the
script's own directory (`sys.path[0]`), so it works from any cwd and under both
the plugin and symlink installs:

    _util.py       time/text/path primitives, JSON output, pid liveness
    _registry.py   <project>/.codex-runs — locating, reading and reaping runs
    _events.py     reading the event stream, the filter levels, summarising
    _codex.py      argv composition, the two invariants, spawning, thread DB

Start here for "what can it do"; go to `_codex.py` for "what exactly does it run"
and `_events.py` for "what reaches my context".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _codex import (  # noqa: E402
    SANDBOX_MODES, THREAD_ID_WAIT, apply_preamble, build_argv, query_threads,
    spawn_supervised, state_db_path, supervise,
)
from _events import (  # noqa: E402
    CursorOutOfRange, DEFAULT_LEVEL, LEVELS, find_item, format_events, read_events,
    scan_progress, strip_wrapper,
)
from _batch import (  # noqa: E402
    claim_group, derived_groups, group_path, list_groups, member_run_ids,
    read_group, valid_name, write_members,
)
from _worktree import (  # noqa: E402
    add as worktree_add, is_dirty as worktree_dirty,
    missing_at_base as worktree_missing_at_base, prune as worktree_prune,
    registered as worktrees_registered, remove as worktree_remove,
    resolve_base as worktree_base_sha, uncommitted_count as worktree_uncommitted,
)
from _registry import (  # noqa: E402
    TERMINAL_STATES, claim_run_dir, ensure_runs_dir, find_run, iter_runs, read_meta,
    reap, resolve_project, resolve_runs_dir, update_meta, update_meta_if, write_meta,
)
from _util import (  # noqa: E402
    BridgeError, clip, codex_home, emit, fail, failures_raise, git_toplevel,
    is_within, nfc, now_iso, pid_alive,
)

# `show --item` default cap. A silently truncated blob is worse than a loud one,
# so truncation is always announced along with how much was withheld.
SHOW_MAX_BYTES = 20000

# Advisory only. `idle_seconds` is always reported alongside it, so this number
# never decides anything by itself: one long `command_execution` is legitimately
# silent, which is why silence alone is not failure — silence plus no
# in-progress item is.
STALL_SECONDS = 300


# --------------------------------------------------------------------------
# start / resume / review — all three build a run the same way
# --------------------------------------------------------------------------

def read_prompt(args) -> str:
    if getattr(args, "prompt_file", None):
        try:
            return Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as e:
            fail(f"cannot read prompt file: {e}")
    p = getattr(args, "prompt", None)
    if p == "-" or p is None:
        if not sys.stdin.isatty():
            data = sys.stdin.read()
            if data.strip():
                return data
        if p is None:
            return ""
    return p or ""


def resolve_implicit_run(candidates):
    """D27: pick a run nobody named, without silently crossing into another
    run's identity.

    `candidates` must be oldest-first (`iter_runs` order). Reaping first means
    the decision is made on live state, not a meta.json a dead supervisor never
    updated. Exactly one non-terminal run is unambiguous. Zero non-terminal
    runs falls back to the newest run, and the caller must echo which one it
    picked. Two or more is exactly the F4 reproduction — a read-only caller
    silently inheriting another run's label and sandbox — so it fails loud
    with the candidate list instead of guessing.
    """
    reaped = [(rd, reap(rd, m)) for rd, m in candidates]
    non_terminal = [(rd, m) for rd, m in reaped if m.get("state") not in TERMINAL_STATES]
    if len(non_terminal) == 1:
        rd, m = non_terminal[0]
        return rd, m, "the only non-terminal run"
    if len(non_terminal) >= 2:
        fail("multiple non-terminal runs; an implicit target is ambiguous — "
             "pass an explicit run id, thread id, or thread name",
             candidates=[{"run_id": m.get("run_id"), "label": m.get("label"),
                          "state": m.get("state"), "sandbox": m.get("sandbox"),
                          "thread_id": m.get("thread_id")} for rd, m in non_terminal])
    if not reaped:
        return None, None, None
    rd, m = reaped[-1]
    return rd, m, "the newest run (no non-terminal runs)"


def refuse_concurrent_turn(runs_dir, thread_id, force):
    """F4 reproduced two turns run concurrently on one thread: rc 0, no
    warning. A resumed run shares its parent's process group with nothing —
    two live turns on the same thread would race on the same rollout file —
    so a live turn on the target thread is refused unless the caller opts in
    with --force."""
    if not thread_id or force:
        return
    live = [reap(rd, m) for rd, m in iter_runs(runs_dir) if m.get("thread_id") == thread_id]
    live = [m for m in live if m.get("state") not in TERMINAL_STATES]
    if live:
        fail("thread already has a live turn; pass --force to run a second turn "
             "concurrently", thread_id=thread_id,
             live_runs=[{"run_id": m.get("run_id"), "state": m.get("state")}
                        for m in live])


def create_run(args, *, kind: str, base=None, review_args=None, thread_ref=None,
               group=None, batch=None, worktree_base=None):
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))

    cwd = (Path(args.cwd).expanduser().resolve() if getattr(args, "cwd", None)
           else (Path(base["cwd"]) if base else project))
    if not cwd.is_dir():
        fail(f"cwd does not exist: {cwd}")

    prompt = read_prompt(args)
    if kind != "review" and not prompt.strip():
        fail("a prompt is required (positional, --prompt-file, or stdin via '-')")

    if kind == "resume" and not thread_ref:
        # `build_argv` omits the ref when there is none, producing a bare
        # `codex exec resume` that fails asynchronously — after this command
        # has already reported a run started. A run whose Codex process died
        # before emitting `thread.started` has a run id and a terminal state
        # but no conversation, and that is the usual way to get here.
        fail("nothing to resume: that run never recorded a thread id, so there "
             "is no conversation to continue",
             run_id=(base or {}).get("run_id"), state=(base or {}).get("state"))

    isolated = base["isolated"] if base else True
    if getattr(args, "inherit_config", False):
        isolated = False
    if getattr(args, "isolate", False):
        isolated = True

    sandbox = args.sandbox or (base["sandbox"] if base else "workspace-write")
    if getattr(args, "priority", None) is not None:
        priority = args.priority
    elif base and isolated == base["isolated"]:
        # Isolation state unchanged from the parent: inherit its priority like
        # every other recorded setting.
        priority = base.get("priority")
    else:
        # No base, or --inherit-config/--isolate just flipped isolation: priority
        # is only re-injected to undo what isolation removed, so it follows the
        # new isolation state rather than carrying over the parent's value.
        priority = isolated

    try:
        run_id, run_dir = claim_run_dir(
            runs_dir, args.label or (base.get("label") if base else None))
    except FileExistsError as e:
        fail(str(e), runs_dir=str(runs_dir))

    meta = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "thread_id": base.get("thread_id") if base else None,
        "parent_run_id": base.get("run_id") if base else None,
        "kind": kind,
        "label": args.label or (base.get("label") if base else None),
        "prompt_preview": clip(prompt, 300),
        "cwd": str(cwd),
        "project": str(project),
        "sandbox": sandbox,
        "model": args.model or (base.get("model") if base else None),
        "effort": args.effort or (base.get("effort") if base else None),
        "isolated": isolated,
        "priority": priority,
        "schema_path": (str(Path(args.schema).expanduser().resolve())
                        if getattr(args, "schema", None)
                        else (base.get("schema_path") if base else None)),
        "images": [str(Path(i).expanduser().resolve())
                   for i in (getattr(args, "image", None) or [])],
        "add_dirs": [str(Path(d).expanduser().resolve())
                     for d in (getattr(args, "add_dir", None) or [])],
        "extra_config": (list(args.config) if getattr(args, "config", None)
                         else (base.get("extra_config") if base else [])) or [],
        # Only where Codex's own guard does not apply. The wrapper does not
        # silently disable a Codex safety default just to keep its own argv
        # uniform.
        "skip_git_repo_check": git_toplevel(cwd) is None,
        "preamble": not args.no_preamble,
        "claude_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"),
        "foreground": bool(getattr(args, "foreground", False)),
        "timeout_seconds": getattr(args, "timeout", None),
        # The manifest is the authority on membership and order; this copy lets
        # a single run say which group it belongs to without one, so `status`
        # can still answer that after a manifest is lost or hand-deleted.
        "group": group,
        "worktree": None,       # filled in below, once nothing can still refuse
        "started_at": now_iso(),
        "ended_at": None, "exit_code": None, "state": "starting",
        "codex_pid": None, "supervisor_pid": None, "pgid": None,
    }

    if base and args.sandbox and args.sandbox != base["sandbox"]:
        # A sandbox change is never silent, in either direction.
        meta["sandbox_changed_from"] = base["sandbox"]

    if meta["schema_path"] and not Path(meta["schema_path"]).exists():
        fail(f"schema file not found: {meta['schema_path']}")
    for img in meta["images"]:
        if not Path(img).exists():
            fail(f"image not found: {img}")

    # Cut the worktree last, after every check that can still refuse this run.
    # It cannot be cut before `claim_run_dir` — it lives at `<run_dir>/wt`, and
    # the run id naming that directory does not exist until then — but cutting
    # it any earlier than here leaks. A member rejected afterwards never gets a
    # meta.json and so never gets a run_id, and `batch clean` resolves
    # worktrees through the manifest's run ids: the worktree would survive
    # every documented removal path while `batch clean` reported the group
    # fully cleaned.
    wt_info = None
    if worktree_base:
        source, wt = cwd, run_dir / "wt"
        ok, err = worktree_add(source, wt, worktree_base)
        if not ok:
            fail(f"could not create the worktree for this member: {err}",
                 base=worktree_base, path=str(wt))
        cwd = wt
        wt_info = {"path": str(wt), "base": worktree_base,
                   "uncommitted_in_caller_tree": worktree_uncommitted(source),
                   "source": str(source)}
        meta["cwd"] = str(cwd)
        meta["worktree"] = wt_info

    if batch and wt_info:
        batch = {**batch, "worktree": wt_info["path"], "base": wt_info["base"],
                 "uncommitted": wt_info["uncommitted_in_caller_tree"]}
    send = (apply_preamble(prompt, meta["preamble"], batch=batch)
            if prompt.strip() else None)
    meta["argv"] = build_argv(meta, kind=kind, prompt=send,
                              thread_ref=thread_ref, review_args=review_args)
    write_meta(run_dir, meta)

    if meta["foreground"]:
        supervise(run_dir, timeout=getattr(args, "timeout", None))
        m = read_meta(run_dir) or {}
        info = scan_progress(run_dir / "events.jsonl")
        return {"run_id": run_id, "thread_id": m.get("thread_id"),
                "state": m.get("state"), "exit_code": m.get("exit_code"),
                "events": str(run_dir / "events.jsonl"), "project": str(project),
                "cwd": str(cwd), "sandbox": sandbox, "isolated": isolated,
                "last_agent_message": info["last_agent_message"],
                "usage": info["usage"]}

    spawn_supervised(run_dir)
    # Hand back a usable handle as soon as the thread id exists, and never block
    # the caller past that window.
    deadline = time.time() + THREAD_ID_WAIT
    thread_id = None
    while time.time() < deadline:
        m = read_meta(run_dir) or {}
        thread_id = m.get("thread_id")
        if thread_id or m.get("state") in TERMINAL_STATES:
            break
        time.sleep(0.05)
    m = read_meta(run_dir) or {}
    out = {"run_id": run_id, "thread_id": thread_id,
           "state": m.get("state", "starting"),
           "events": str(run_dir / "events.jsonl"), "project": str(project),
           "cwd": str(cwd), "sandbox": sandbox, "isolated": isolated}
    if group:
        out["group"] = group
    if wt_info:
        out["worktree"] = wt_info
    if "sandbox_changed_from" in meta:
        out["sandbox_changed_from"] = meta["sandbox_changed_from"]
    return out


def cmd_start(args):
    emit(create_run(args, kind="start"))


# --------------------------------------------------------------------------
# batch — start N runs as one addressable group
# --------------------------------------------------------------------------

TASK_FIELDS = ("prompt", "kind", "label", "model", "effort", "sandbox", "schema",
               "image", "cwd", "resume", "review")

# Checking the field *names* is not enough. A value of the wrong type reaches
# argv composition unexamined and surfaces as a Python error from deep inside
# `create_run` — `{"prompt": 123}` becomes `AttributeError: 'int' object has no
# attribute 'strip'`. The batch's own D11 net catches that now, but only after
# the earlier members have already spawned; a tasks file this broken should
# cost nothing, and the way to make it cost nothing is to read it fully before
# starting anything.
TASK_FIELD_TYPES = {"prompt": str, "kind": str, "label": str, "model": str,
                    "effort": str, "sandbox": str, "schema": str, "cwd": str,
                    "resume": str, "image": list, "review": dict}


def load_tasks(args):
    """Build the ordered task list from `--task` and `--tasks-file`.

    Both may be given; `--task` entries come first, because that is the order
    they were typed in and `--resume-from` pairs positionally. A `--task` is
    always `kind: start` — it is a bare prompt with nowhere to say otherwise.
    """
    tasks = [{"prompt": p, "kind": "start"} for p in (args.task or [])]
    if args.tasks_file:
        try:
            raw = Path(args.tasks_file).read_text(encoding="utf-8")
        except OSError as e:
            fail(f"cannot read tasks file: {e}")
        for n, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                fail(f"tasks file line {n} is not valid JSON: {e}", line=clip(line, 200))
            if not isinstance(item, dict):
                fail(f"tasks file line {n} is not a JSON object", line=clip(line, 200))
            unknown = set(item) - set(TASK_FIELDS)
            if unknown:
                # Loud, because the failure mode of a silently ignored field is
                # a run that quietly used the group default instead.
                fail(f"tasks file line {n} has unknown field(s): {sorted(unknown)}",
                     known_fields=list(TASK_FIELDS))
            for field, want in TASK_FIELD_TYPES.items():
                if field in item and not isinstance(item[field], want):
                    fail(f"tasks file line {n}: {field!r} must be "
                         f"{want.__name__}, got {type(item[field]).__name__}",
                         line=clip(line, 200))
            if any(not isinstance(i, str) for i in item.get("image") or []):
                fail(f"tasks file line {n}: 'image' must be a list of paths",
                     line=clip(line, 200))
            item.setdefault("kind", "start")
            if item["kind"] not in ("start", "resume", "review"):
                fail(f"tasks file line {n}: kind must be start, resume or review",
                     got=item["kind"])
            if (item["kind"] == "resume" and not item.get("resume")
                    and not getattr(args, "resume_from", None)):
                # --resume-from supplies the target positionally, so under it
                # an unnamed resume is the normal form rather than an omission.
                fail(f"tasks file line {n}: kind 'resume' needs a 'resume' field "
                     f"naming a run id or thread id")
            tasks.append(item)
    if not tasks:
        fail("batch start needs at least one --task or a --tasks-file")
    return tasks


def task_args(base_args, item):
    """A per-task argv namespace: the group-level options as defaults, the
    task's own fields overriding them.

    Group options are defaults rather than constraints on purpose — a batch is
    usually "the same thing N ways", and the exceptions are exactly what the
    per-item fields exist to express.
    """
    ns = argparse.Namespace(**vars(base_args))
    ns.prompt = item.get("prompt")
    ns.prompt_file = None
    for field in ("label", "model", "effort", "sandbox", "cwd"):
        if item.get(field) is not None:
            setattr(ns, field, item[field])
    if item.get("schema") is not None:
        ns.schema = item["schema"]
    ns.image = item.get("image") or []
    ns.add_dir = getattr(base_args, "add_dir", None) or []
    return ns


def projected_cost(runs_dir: Path, n_runs: int):
    """What N runs will cost at the floor, computed from this project's own
    history rather than a constant.

    D37. A baked-in number rots: the isolation overhead measured at design time
    moved 2.92x -> 1.09x within two weeks (R8), so any constant written here
    would be wrong by the time anyone read it. The median input_tokens over
    recent isolated, completed runs is the same measurement taken fresh.

    It is a floor and it is reported, not enforced (D10): the caller decides
    whether N runs is worth it, and this only makes the decision informed
    instead of blind.
    """
    samples = []
    for _rd, m in reversed(list(iter_runs(runs_dir))):
        if m.get("state") != "completed" or not m.get("isolated"):
            continue
        tokens = (m.get("usage") or {}).get("input_tokens")
        if tokens:
            samples.append(int(tokens))
        if len(samples) >= 10:
            break
    if len(samples) < 3:
        return {"runs": n_runs, "input_floor_per_run": None, "input_floor_total": None,
                "samples": len(samples),
                "note": "not enough completed isolated runs in this project to "
                        "measure a floor yet (need 3)"}
    samples.sort()
    per_run = samples[len(samples) // 2]
    return {"runs": n_runs, "input_floor_per_run": per_run,
            "input_floor_total": per_run * n_runs, "samples": len(samples),
            "note": "floor only, measured from this project's recent isolated runs. "
                    "Real cost is higher and grows with each resume. Do not budget "
                    "from this number — re-measure."}


WRITING_SANDBOXES = ("workspace-write", "danger-full-access")


def wants_worktree(item, args):
    """Whether this member would be isolated if the batch turns isolation on.

    D35 assigns per member, not per batch, and each exclusion has its own
    reason rather than a shared one:

      * **`read-only`** has nothing to isolate — it cannot write.
      * **`kind: review`** is excluded even though its sandbox defaults to
        `workspace-write`, and this is the exclusion that matters most. A
        freshly cut worktree has zero lines of `git diff HEAD` (measured,
        V-15), so a reviewer inside one reviews nothing: the uncommitted work
        it was started to look at exists only in the caller's tree.
      * **an explicit `cwd`** was a decision the caller already made, and an
        inferred default does not overrule a stated one.
      * **`kind: resume`** continues a thread whose directory is inherited from
        its parent run; `--cwd` is not even accepted on resume, so a new
        worktree here would be a directory the thread has never seen.
    """
    if item["kind"] in ("review", "resume"):
        return False
    if item.get("cwd") or getattr(args, "cwd", None):
        return False
    sandbox = item.get("sandbox") or args.sandbox or "workspace-write"
    return sandbox in WRITING_SANDBOXES


def plan_worktrees(tasks, args, project):
    """Decide isolation for the batch, then report why in the same breath.

    Returns `(eligible_indices, base_sha, note)`. The threshold is two writing
    members because one writer has nobody to collide with, and isolating it
    would only put its results somewhere the caller has to go and fetch.
    """
    eligible = {i for i, t in enumerate(tasks) if wants_worktree(t, args)}
    if getattr(args, "no_worktree", False):
        return set(), None, "worktrees disabled by --no-worktree"
    forced = getattr(args, "worktree", False)
    if not eligible:
        return set(), None, ("no member writes to the tree, so there is nothing "
                             "to isolate" if forced else None)
    if len(eligible) < 2 and not forced:
        return set(), None, ("only one member writes to the tree; a lone writer "
                             "has nobody to collide with. Pass --worktree to "
                             "isolate it anyway.")
    if git_toplevel(project) is None:
        return set(), None, (f"{project} is not a git repository, so worktrees "
                             "are unavailable; members share the caller's tree")
    ref = getattr(args, "base", None)
    base = worktree_base_sha(project, ref)
    if not base and ref:
        # An unresolvable --base was typed by the caller, so it is a mistake to
        # report rather than a condition to degrade around. Silently sharing the
        # caller's tree instead would answer a typo with the one outcome the
        # flag was used to avoid.
        fail(f"--base {ref!r} does not resolve to a commit in {project}")
    if not base:
        return set(), None, ("this repository has no HEAD yet (nothing is "
                             "committed), so there is no commit to cut a "
                             "worktree from; members share the caller's tree")
    return eligible, base, None


def pair_with_previous(tasks, runs_dir, previous: str, *, force=False):
    """Turn each task into a resume of the corresponding member of `previous`.

    The pairing is positional against the manifest's member list, and that is
    the whole reason the manifest records start order (D36). The alternative —
    ordering by run id or timestamp — is a coin flip precisely here: a batch
    starts its members within the same second and usually under the same label,
    which audit F15 recorded as the normal case rather than the unlucky one.

    A task that already names what it resumes keeps it. Explicit beats inferred,
    the same rule that governs a per-item `cwd`.
    """
    manifest = read_group(runs_dir, previous)
    if manifest is None:
        fail(f"no such group to resume from: {previous}",
             known_groups=list_groups(runs_dir)[:20])
    started = [m for m in manifest.get("members") or [] if m.get("run_id")]
    if not started:
        fail(f"group {previous!r} has no members that started, so there is "
             f"nothing to resume")
    # A run id is not a thread. A member whose Codex process died before
    # emitting `thread.started` — an early crash, a failed login — has a run
    # directory and a terminal state but no thread, and `codex exec resume`
    # with nothing to resume is not an error Codex reports back here: it
    # produces a ref-less argv that fails asynchronously, long after this
    # command has already told the caller it spawned fine.
    threadless = [m["run_id"] for m in started
                  if not (find_run(runs_dir, m["run_id"])[1] or {}).get("thread_id")]
    if threadless:
        fail(f"{len(threadless)} member(s) of {previous!r} never recorded a "
             f"thread id, so there is no conversation to continue for them — "
             f"they failed before Codex started one",
             members=threadless)
    prior = started
    if len(tasks) != len(prior):
        # Loud, because the failure mode of pairing a short list is a phase-2
        # task silently landing on the wrong phase-1 thread — every member
        # after the mismatch continues work it was not written for.
        fail(f"--resume-from pairs one task to one member in order, but "
             f"{previous!r} has {len(prior)} started member(s) and this batch "
             f"has {len(tasks)} task(s)",
             previous_members=[m["run_id"] for m in prior])
    # Checked for the whole group before a single member starts, rather than
    # left to `refuse_concurrent_turn` per member. Per member it would still
    # refuse — but only after the earlier tasks had already resumed, leaving a
    # phase 2 that is half started against a phase 1 that is half finished.
    live = []
    for m in prior:
        rd, meta = find_run(runs_dir, m["run_id"])
        if meta and reap(rd, meta).get("state") not in TERMINAL_STATES:
            live.append({"run_id": m["run_id"], "state": meta.get("state")})
    if live and not force:
        fail(f"group {previous!r} still has members running; resuming a thread "
             f"mid-turn would run two turns on it at once", running=live)

    paired = []
    for slot, (task, prev) in enumerate(zip(tasks, prior)):
        kind, named = task["kind"], task.get("resume")
        if kind == "review":
            # Rewriting it would turn a read-only review into a full agentic
            # turn on someone else's thread, which is a larger authority than
            # the caller asked for and is invisible in the output.
            fail(f"task {slot} is a review, but every task in a --resume-from "
                 f"batch continues one member of {previous!r}; a review cannot "
                 f"be that continuation")
        if kind != "resume" and named:
            # Neither reading is safe to pick silently: honouring `resume`
            # leaves this member's phase-1 counterpart unresumed while the
            # output still claims it was paired, and ignoring it discards a
            # target the caller wrote down.
            fail(f"task {slot} names a thread to resume but its kind is "
                 f"{kind!r}; under --resume-from, set kind to 'resume' to keep "
                 f"that target or drop the 'resume' field to be paired with "
                 f"{prev['run_id']}")
        if named:
            paired.append(task)
            continue
        paired.append({**task, "kind": "resume", "resume": prev["run_id"]})
    return paired, [m["run_id"] for m in prior]


def cmd_batch_start(args):
    if not valid_name(args.group):
        fail("group name must be alphanumeric with . _ - and no path separators",
             got=args.group)
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))
    tasks = load_tasks(args)

    previous = getattr(args, "resume_from", None)
    if previous:
        tasks, paired_with = pair_with_previous(
            tasks, runs_dir, previous, force=getattr(args, "force", False))

    # Claim the name before spawning anything. D36: a reused group name would
    # make "the members of p1" ambiguous, and --resume-from pairs positionally
    # against exactly that list. Failing here costs nothing — no Codex process
    # has started yet.
    try:
        claim_group(runs_dir, args.group, derived_from=previous)
    except FileExistsError:
        existing = read_group(runs_dir, args.group) or {}
        fail(f"group {args.group!r} already exists in this project; group names "
             f"are single-use so that membership and start order stay unambiguous",
             created_at=existing.get("created_at"),
             members=len(existing.get("members") or []))

    isolated_idx, wt_base, wt_note = plan_worktrees(tasks, args, project)
    batch_ctx = {"n": len(tasks), "group": args.group}

    members, results = [], []
    for index, item in enumerate(tasks):
        entry = {"index": index, "kind": item["kind"],
                 "label": item.get("label") or args.label}
        try:
            with failures_raise():
                out = spawn_task(task_args(args, item), item, group=args.group,
                                 runs_dir=runs_dir, project=project,
                                 batch=batch_ctx,
                                 worktree_base=wt_base if index in isolated_idx
                                 else None)
        except Exception as e:
            # D11: one member failing to spawn does not take the batch with it.
            # The failure is recorded in place so the caller sees which slot is
            # missing rather than a shorter list than it asked for.
            #
            # `Exception`, not `BridgeError`: a BridgeError is a refusal this
            # code anticipated, but the failures that actually cost a batch are
            # the ones it did not — a bad value in a tasks file reaching
            # `prompt.strip()` as an AttributeError, an OSError from a full
            # disk. Letting those escape aborts the batch *after* members are
            # already running, which is the one outcome D11 exists to prevent.
            entry["error"] = e.msg if isinstance(e, BridgeError) else str(e)
            entry.update(e.extra if isinstance(e, BridgeError)
                         else {"error_type": type(e).__name__})
            members.append(entry)
            results.append(entry)
            write_members(runs_dir, args.group, members)
            continue
        entry["run_id"] = out["run_id"]
        entry["thread_id"] = out.get("thread_id")
        entry["cwd"] = out.get("cwd")
        entry["sandbox"] = out.get("sandbox")
        if out.get("worktree"):
            entry["worktree"] = out["worktree"]["path"]
        members.append(entry)
        results.append({**entry, "state": out.get("state")})
        # After every member, not once at the end: see write_members. A member
        # that has spawned is a live process, and it must be reachable through
        # the group from the instant it exists.
        write_members(runs_dir, args.group, members)
    spawned = [m for m in members if m.get("run_id")]
    isolated = [m for m in members if m.get("worktree")]
    out = {"group": args.group, "runs": results,
           "spawned": len(spawned), "requested": len(tasks),
           "projected_cost": projected_cost(runs_dir, len(spawned)),
           "manifest": str(group_path(runs_dir, args.group))}
    if previous:
        # Phase 2 works in phase 1's worktrees — it inherits each thread's cwd
        # rather than being given a new one. That is also why `batch clean` now
        # refuses to clean phase 1: the manifest records this link.
        out["resumed_from"] = {"group": previous, "members": paired_with}
    if isolated:
        # D17: a dirty caller tree is stated, never refused. The number is what
        # tells the caller their uncommitted work is not in what these runs see
        # — and the same fact goes to Codex itself in the preamble.
        out["worktrees"] = {
            "count": len(isolated), "base": wt_base,
            "uncommitted_files_in_caller_tree": worktree_uncommitted(project),
            "note": "each writing member has its own checkout at "
                    "<run_dir>/wt. Their changes are not in your tree; "
                    "`result --group` reports which paths more than one wrote. "
                    "`batch clean --group` removes them once you have collected."}
        missing = worktree_missing_at_base(project, wt_base)
        if missing:
            # V-14: project instructions reach a worktree run, but only from a
            # base where the file exists. A --base older than the commit that
            # added AGENTS.md produces runs with no project guidance, and
            # neither side can notice on its own.
            out["worktrees"]["missing_at_base"] = missing
            out["worktrees"]["missing_note"] = (
                f"{', '.join(missing)} exists in your tree but not at the base "
                f"these worktrees were cut from, so these runs start without "
                f"the project instructions a HEAD-based run would have had.")
    elif wt_note:
        out["worktrees"] = {"count": 0, "note": wt_note}
    emit(out)


def spawn_task(ns, item, *, group, runs_dir, project, batch=None,
               worktree_base=None):
    """Start one member. Mirrors cmd_start/cmd_resume/cmd_review's dispatch,
    minus their argv parsing, which `task_args` has already done."""
    kind = item["kind"]
    if kind == "start":
        return create_run(ns, kind="start", group=group, batch=batch,
                          worktree_base=worktree_base)
    if kind == "resume":
        rd, base = find_run(runs_dir, item["resume"])
        if not base:
            # Not in the registry: it may still be a real Codex thread started
            # outside this skill, so pass the ref through rather than refusing.
            return create_run(ns, kind="resume", thread_ref=item["resume"],
                              group=group, batch=batch)
        refuse_concurrent_turn(runs_dir, base.get("thread_id"),
                               getattr(ns, "force", False))
        return create_run(ns, kind="resume", base=base,
                          thread_ref=base.get("thread_id"), group=group,
                          batch=batch)
    review = item.get("review") or {}
    review_args = []
    if review.get("uncommitted"):
        review_args.append("--uncommitted")
    if review.get("base"):
        review_args += ["--base", str(review["base"])]
    if review.get("commit"):
        review_args += ["--commit", str(review["commit"])]
    return create_run(ns, kind="review", review_args=review_args, group=group,
                      batch=batch)


def cmd_batch_clean(args):
    """Remove a finished group's worktrees and release its name.

    There is no automatic cleanup and no hook (D06, D23): a worktree holds the
    only copy of what a run produced, and nothing should delete that on a
    schedule the caller did not choose.

    Four things stop a clean without `--force`, and only the first two are
    checks this code performs. The other two are git's own refusal, and a fact
    about groups that outlive each other.
    """
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    manifest = read_group(runs_dir, args.group)
    if manifest is None:
        fail(f"no such group in this project: {args.group}",
             known_groups=list_groups(runs_dir)[:20])

    live, removed, kept = [], [], []
    for rid in member_run_ids(runs_dir, args.group) or []:
        rd, meta = find_run(runs_dir, rid)
        if not meta:
            continue
        meta = reap(rd, meta)
        if meta.get("state") not in TERMINAL_STATES:
            live.append({"run_id": rid, "state": meta.get("state")})

    # 1. A live member is still writing into the very directory being removed.
    if live and not args.force:
        fail(f"group {args.group!r} still has running members; stop them first "
             f"or pass --force", running=live)
    # One flag lifts all three protections, and a caller usually reaches for it
    # to get past one of them. What it actually overrode therefore has to be in
    # the result, not only in --help: the caller who forced past a dependent
    # group needs to see that a running member's directory went with it.
    overrode = {}
    if args.force and live:
        overrode["running_members"] = live

    # 2. A group that another group resumed into. `--resume-from` puts phase 2
    #    in phase 1's worktrees, so cleaning phase 1 pulls the tree out from
    #    under runs that are still using it. Free to detect thanks to the
    #    manifest's `derived_from`.
    children = derived_groups(runs_dir, args.group)
    if children and not args.force:
        fail(f"group {args.group!r} was resumed by another group, whose members "
             f"are working in these worktrees", derived_groups=children)
    if args.force and children:
        overrode["derived_groups"] = children

    worktree_prune(project)
    for rid in member_run_ids(runs_dir, args.group) or []:
        rd, meta = find_run(runs_dir, rid)
        wt = (meta or {}).get("worktree")
        if not wt:
            continue
        path = Path(wt["path"])
        if not path.exists():
            continue
        # 3. Uncommitted changes in the worktree, i.e. results nobody collected.
        #    Not implemented here: `git worktree remove` refuses a dirty tree by
        #    itself (measured, V-13), and git's definition of dirty is the
        #    correct one. Its refusal is reported as the reason.
        # Who is actually living here, asked of the registry rather than of the
        # group graph. The `derived_from` check above is a better error message
        # when the chain is intact, but it is only one hop and it evaporates the
        # moment an intermediate manifest is cleaned: p1 -> p2 -> p3, clean p2,
        # and p1 looks unreferenced while p3 is still running in p1's worktree.
        # A run's own recorded cwd cannot go stale that way.
        occupants = [m for _rd, m in iter_runs(runs_dir)
                     if m.get("state") not in TERMINAL_STATES
                     and m.get("run_id") != rid
                     and is_within(m.get("cwd"), path)]
        if occupants and not args.force:
            kept.append({"run_id": rid, "path": str(path),
                         "reason": "another run is still working in this "
                                   "worktree",
                         "occupied_by": [m["run_id"] for m in occupants]})
            continue
        if occupants:
            overrode.setdefault("removed_under_live_runs", []).extend(
                m["run_id"] for m in occupants)
        dirty = worktree_dirty(path)
        ok, err = worktree_remove(project, path, force=args.force)
        if ok and dirty and args.force:
            overrode.setdefault("discarded_uncommitted", []).append(str(path))
        (removed if ok else kept).append(
            {"run_id": rid, "path": str(path),
             **({} if ok else {"reason": err, "dirty": dirty})})

    # The name is released only when nothing was left behind, so a caller who
    # sees `cleaned: true` can reuse the name and one who does not still has a
    # group to address the leftovers by. This is also the only way to reclaim a
    # name from a `batch start` that died before it recorded any member.
    released = not kept
    if released:
        group_path(runs_dir, args.group).unlink(missing_ok=True)
    out = {"group": args.group, "removed": removed, "kept": kept,
           "name_released": released,
           "note": None if released else
           "these worktrees hold uncommitted changes — collect them, or pass "
           "--force to discard. The group name stays claimed until they are gone."}
    if overrode:
        out["forced_past"] = overrode
        out["forced_note"] = (
            "--force lifted every protection at once, not only the one you were "
            "after. What it overrode is listed above; none of it is recoverable "
            "from here.")
    emit(out)


def cmd_resume(args):
    # `resume` mirrors `codex exec resume [SESSION_ID] [PROMPT]`, which is two
    # optional positionals — argparse cannot tell which one a lone argument is,
    # and would bind `resume --last "do the thing"` to the session id, silently
    # losing the prompt. Disambiguate here instead: with --last there is no ref
    # to give, so everything positional is the prompt.
    rest = list(args.rest)
    if args.last:
        args.ref = None
    else:
        args.ref = rest.pop(0) if rest else None
    if len(rest) > 1:
        fail("too many positional arguments for resume",
             expected="resume <ref> <prompt>  |  resume --last <prompt>",
             got=list(args.rest))
    args.prompt = rest[0] if rest else None

    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)

    base, thread_ref, resolved_from = None, None, None
    if args.last:
        # F4: this used to be `runs[-1]` with no filter on cwd, label or kind —
        # a read-only caller could inherit another run's label AND its
        # danger-full-access sandbox. resolve_implicit_run enforces D27: exactly
        # one non-terminal run is unambiguous, zero falls back to the newest and
        # says so, two or more fails loud with the candidate list.
        candidates = [(rd, m) for rd, m in iter_runs(runs_dir) if m.get("thread_id")]
        if candidates:
            _, base, resolved_from = resolve_implicit_run(candidates)
            thread_ref = base["thread_id"]
        else:
            # Nothing in the registry: fall back to Codex's own thread list for
            # this directory, which is what lets Claude pick up a session the
            # user started in the Codex TUI.
            rows = query_threads(cwd_filter=str(project), limit=1)
            if not rows:
                fail("no previous run in this project's registry and no Codex thread "
                     "recorded for this directory", project=str(project))
            thread_ref = rows[0]["id"]
            resolved_from = "Codex's own thread list (no registry entry)"
    else:
        if not args.ref:
            fail("resume needs a run id, thread id, thread name, or --last")
        _, base = find_run(runs_dir, args.ref)
        if base and not base.get("thread_id"):
            # The pass-through below exists for refs this registry has never
            # seen. This one it has, and it has no thread: the run's Codex
            # process died before emitting `thread.started`. Handing the run id
            # to Codex as if it were a thread name only moves the failure
            # somewhere the caller cannot read it.
            fail("nothing to resume: that run never recorded a thread id, so "
                 "there is no conversation to continue",
                 run_id=base.get("run_id"), state=base.get("state"))
        # An unknown ref is not an error: `codex exec resume` also accepts a
        # thread name, so pass it through.
        thread_ref = (base or {}).get("thread_id") or args.ref

    # F4's second reproduction: two turns run concurrently on one thread, rc 0,
    # no warning. Refuse a second live turn on the same thread unless the
    # caller explicitly opts in.
    refuse_concurrent_turn(runs_dir, thread_ref, args.force)

    # A resumed run is a NEW run pointing at the SAME thread, so each turn gets
    # its own event log while the thread stays linked.
    out = create_run(args, kind="resume", base=dict(base) if base else None,
                     thread_ref=thread_ref)
    if args.last:
        # The escalation F4 reproduced was invisible precisely because nothing
        # was echoed — say which run (and its label/sandbox) this run inherited.
        out["resolved_from_run_id"] = base.get("run_id") if base else None
        out["resolved_from"] = resolved_from
        out["label"] = base.get("label") if base else None
    emit(out)


def cmd_review(args):
    chosen = [n for n, v in (("--uncommitted", args.uncommitted), ("--base", args.base),
                             ("--commit", args.commit), ("prompt", args.prompt)) if v]
    if len(chosen) != 1:
        fail("review takes exactly one of --uncommitted, --base <ref>, --commit <sha>, "
             "or a prompt; the Codex CLI rejects combinations", given=chosen)
    if args.title and not args.commit:
        fail("--title is only valid with --commit")

    if args.uncommitted:
        review_args = ["--uncommitted"]
    elif args.base:
        review_args = ["--base", args.base]
    elif args.commit:
        review_args = ["--commit", args.commit]
        if args.title:
            review_args += ["--title", args.title]
    else:
        review_args = []
    emit(create_run(args, kind="review", review_args=review_args))


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

def run_row(run_dir: Path, meta: dict, project: Path):
    meta = reap(run_dir, meta)
    events_path = run_dir / "events.jsonl"
    info = scan_progress(events_path)
    now = time.time()

    elapsed = None
    try:
        t0 = datetime.fromisoformat(meta["started_at"].replace("Z", "+00:00")).timestamp()
        elapsed = int(now - t0)
    except Exception:
        pass
    idle = None
    if events_path.exists() and events_path.stat().st_size > 0:
        idle = int(now - events_path.stat().st_mtime)

    state = meta.get("state")
    if state == "running" and idle is not None and idle >= STALL_SECONDS:
        state = "stalled"

    stderr_tail = None
    sp = run_dir / "stderr.log"
    if sp.exists() and sp.stat().st_size:
        txt = sp.read_text(encoding="utf-8", errors="replace")
        # Codex always writes `Reading additional input from stdin...` here when
        # stdin is not a TTY. It is normal output, not failure; surfacing it as
        # an error would train the reader to ignore this field entirely.
        txt = "\n".join(l for l in txt.splitlines()
                        if l.strip() and "Reading additional input from stdin" not in l)
        stderr_tail = txt[-800:] or None

    # Measured: review runs report all-zero usage even after real work. Zero
    # would be a wrong number; null is a true one.
    usage = info["usage"]
    review_zero = meta.get("kind") == "review" and usage is not None and not any(usage.values())

    row = {
        "run_id": meta.get("run_id"),
        "thread_id": meta.get("thread_id") or info["thread_id"],
        "parent_run_id": meta.get("parent_run_id"), "kind": meta.get("kind"),
        "label": meta.get("label"), "state": state,
        "codex_pid": meta.get("codex_pid"), "pgid": meta.get("pgid"),
        "started_at": meta.get("started_at"), "ended_at": meta.get("ended_at"),
        "elapsed_seconds": elapsed, "idle_seconds": idle,
        "exit_code": meta.get("exit_code"), "sandbox": meta.get("sandbox"),
        "model": meta.get("model"), "effort": meta.get("effort"),
        "isolated": meta.get("isolated"),
        "cwd": meta.get("cwd"),
        "usage": None if review_zero else usage,
        "turns_completed": info["turns_completed"], "commands": info["commands"],
        "files_changed": info["files_changed"], "config_error_events": info["errors"],
        "in_progress_item": info["in_progress_item"],
        "last_agent_message": clip(info["last_agent_message"] or "", 400) or None,
        # F8: `turn.failed` was parsed by _events.py and never surfaced, so a
        # failed run showed `message: null` and the reason needed a second
        # `log` call. Clipped like the neighbouring `turn.failed` log line.
        "turn_failed": (clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400)
                        if info["turn_failed"] else None),
        "events": str(events_path),
    }
    if review_zero:
        row["usage_note"] = "review runs report zero usage; unavailable, not free"
    if meta.get("sandbox_changed_from"):
        row["sandbox_changed_from"] = meta["sandbox_changed_from"]
    if stderr_tail:
        row["stderr_tail"] = stderr_tail
    if meta.get("error"):
        row["error"] = meta["error"]
    return row


def resolve_group(runs_dir: Path, name: str):
    """Group members as (run_dir, meta), in start order. Fails if the group is
    unknown. Members that never spawned are skipped — they are recorded in the
    manifest with an `error` and no run id."""
    ids = member_run_ids(runs_dir, name)
    if ids is None:
        fail(f"no such group: {name}", runs_dir=str(runs_dir),
             known_groups=list_groups(runs_dir))
    out = []
    for rid in ids:
        rd, m = find_run(runs_dir, rid)
        if m:
            out.append((rd, m))
    return out


def group_snapshot(rows):
    """The one place group state is derived, so `status --group` and
    `--follow`'s exit line can never disagree about whether a group is done."""
    running = [r["run_id"] for r in rows if r["state"] in ("running", "starting", "stalled")]
    done = [r["run_id"] for r in rows if r["state"] == "completed"]
    failed = [r["run_id"] for r in rows
              if r["state"] in ("failed", "interrupted", "orphaned", "timed_out")]
    if running:
        state = "running"
    elif failed or not rows:
        # `partial` covers "a member failed", "the user stopped it" and "a member
        # timed out" alike. It means "this group did not all succeed", not
        # "Codex broke" — worth stating, because a --follow exit line saying
        # `group.partial` after a deliberate `stop --group` otherwise reads as
        # an error.
        state = "partial"
    else:
        state = "completed"
    return running, done, failed, state


def follow_group(args, project, runs_dir):
    """Print one line per member state change, then a terminal line, then exit.

    Deliberately symmetrical with `log --follow`, so pairing it with the Monitor
    tool needs nothing new learned — and pairing is the intended use, because
    the Bash tool's 600-second ceiling cannot be crossed by blocking.

    A terminal line is always printed, including on --follow-timeout. Without
    one, a group that is quietly still working and a group whose follower died
    look identical, which is the failure B21 exists to prevent.

    This holds no state: if the follower dies, nothing is lost, because
    `status --group` re-derives everything from the registry. Do not cache
    group state here.
    """
    members = resolve_group(runs_dir, args.group)
    if not members:
        sys.stdout.write(f"group.empty group={args.group}\n")
        sys.stdout.flush()
        return
    seen = {}
    deadline = time.time() + args.follow_timeout if args.follow_timeout else None
    while True:
        rows = []
        for rd, m in members:
            m = read_meta(rd) or m
            row = run_row(rd, m, project)
            rows.append(row)
            prev = seen.get(row["run_id"])
            if prev != row["state"]:
                line = f"run {row['run_id']} {prev or '-'} -> {row['state']}"
                if row.get("exit_code") is not None and row["state"] != "completed":
                    line += f" exit={row['exit_code']}"
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
                seen[row["run_id"]] = row["state"]
        running, done, failed, gstate = group_snapshot(rows)
        if not running:
            sys.stdout.write(f"group.{gstate} group={args.group} "
                             f"done={len(done)} failed={len(failed)}\n")
            sys.stdout.flush()
            return
        if deadline and time.time() >= deadline:
            sys.stdout.write(f"group.still-running group={args.group} "
                             f"running={len(running)} done={len(done)} "
                             f"failed={len(failed)}\n")
            sys.stdout.flush()
            return
        time.sleep(args.interval)


def cmd_status(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rows = []
    if args.run:
        rd, m = find_run(runs_dir, args.run)
        if not m:
            fail(f"no such run: {args.run}", runs_dir=str(runs_dir))
        rows.append(run_row(rd, m, project))
    elif args.group:
        if args.follow:
            return follow_group(args, project, runs_dir)
        for rd, m in resolve_group(runs_dir, args.group):
            rows.append(run_row(rd, m, project))
        running, done, failed, gstate = group_snapshot(rows)
        emit({"project": str(project), "group": args.group, "runs": rows,
              "running": running, "done": done, "failed": failed,
              "total_runs": len(rows), "runs_truncated": 0,
              "group_state": gstate})
    else:
        for rd, m in iter_runs(runs_dir):
            if args.thread and m.get("thread_id") != args.thread:
                continue
            rows.append(run_row(rd, m, project))

    # F3: derive every summary from the FULL list before truncating for
    # display. A phase gate is literally `len(running) == 0` — deriving it
    # from an already-truncated `rows` let live runs older than the newest 20
    # fall off the page, so the gate passed while they were still writing.
    total_runs = len(rows)
    by_thread = {}
    for r in rows:
        by_thread.setdefault(r["thread_id"] or "(unknown)", []).append(r["run_id"])
    running = [r["run_id"] for r in rows if r["state"] in ("running", "stalled")]
    done = [r["run_id"] for r in rows if r["state"] == "completed"]
    failed = [r["run_id"] for r in rows
              if r["state"] in ("failed", "interrupted", "orphaned", "timed_out")]
    known = {r["thread_id"] for r in rows}

    display_rows = rows
    runs_truncated = 0
    if not args.run and not args.all and total_runs > 20:
        tail = rows[-20:]
        # Truncate the display list only — a non-terminal row must survive
        # truncation no matter how old, or `running` above and `runs` below
        # would disagree about which runs are still alive.
        kept_live = [r for r in rows[:-20] if r["state"] not in TERMINAL_STATES]
        display_rows = kept_live + tail
        runs_truncated = total_runs - len(display_rows)

    out = {"project": str(project), "runs_dir": str(runs_dir), "runs": display_rows,
           "threads": by_thread, "running": running, "done": done, "failed": failed,
           "total_runs": total_runs, "runs_truncated": runs_truncated}
    if args.include_external:
        out["external_threads"] = [t for t in query_threads(cwd_filter=str(project))
                                   if t.get("id") not in known]
        out["external_note"] = (
            "Codex threads for this cwd with no registry entry — started outside this "
            "skill. Resumable by id, but their original sandbox was never recorded "
            "here, so pass --sandbox explicitly rather than inheriting a default.")
    emit(out)


# --------------------------------------------------------------------------
# log / show
# --------------------------------------------------------------------------

def cmd_log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.run:
        rd, meta = find_run(runs_dir, args.run)
        if not meta:
            fail(f"no such run: {args.run}", runs_dir=str(runs_dir))
    else:
        # F4: this used to be `runs[-1]` with no filter at all. Apply the same
        # D27 resolution as `resume --last` — exactly one non-terminal run is
        # unambiguous, zero falls back to the newest, two or more fails loud
        # instead of silently picking across concurrent runs.
        candidates = list(iter_runs(runs_dir))
        if not candidates:
            fail("no runs in this project", runs_dir=str(runs_dir))
        rd, meta, _ = resolve_implicit_run(candidates)

    events_path = rd / "events.jsonl"
    rel_to = Path(meta.get("cwd") or project)
    run_id = meta.get("run_id")
    cursor = args.since

    def dump(cur):
        try:
            events, new_cur = read_events(events_path, cur)
        except CursorOutOfRange as e:
            fail(str(e), run_id=run_id, since=cur)
        for line in format_events(events, args.level, rel_to):
            sys.stdout.write(line + "\n")
        return new_cur

    if not args.follow:
        cursor = dump(cursor)
        sys.stdout.write(f"# cursor={cursor} run={run_id}\n")
        sys.stdout.flush()
        return

    # --follow must emit terminal states, not only progress. A monitor that
    # prints happy-path lines only is silent through a crash, and silence is
    # indistinguishable from "still working".
    deadline = time.time() + args.follow_timeout if args.follow_timeout else None
    while True:
        cursor = dump(cursor)
        sys.stdout.flush()
        m = reap(rd, read_meta(rd) or {})
        st = m.get("state")
        if st in TERMINAL_STATES:
            cursor = dump(cursor)
            sys.stdout.write(f"run.{st} run={m.get('run_id')} exit={m.get('exit_code')}\n")
            sys.stdout.write(f"# cursor={cursor} run={run_id}\n")
            sys.stdout.flush()
            return
        if deadline and time.time() > deadline:
            sys.stdout.write(f"run.still-running run={m.get('run_id')} state={st}\n")
            sys.stdout.write(f"# cursor={cursor} run={run_id}\n")
            sys.stdout.flush()
            return
        time.sleep(args.interval)


def cmd_show(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rd, meta = find_run(runs_dir, args.run)
    if not meta:
        fail(f"no such run: {args.run}", runs_dir=str(runs_dir))

    found, events = find_item(rd / "events.jsonl", args.item)
    if not found:
        ids = [f"{(e.get('item') or {}).get('id')}:{(e.get('item') or {}).get('type')}"
               for e in events if e.get("type") == "item.completed"]
        fail(f"no item {args.item!r} in run {meta['run_id']}", available=ids[:60])

    out = {"run_id": meta["run_id"], "item_id": args.item, "item_type": found.get("type")}
    if found.get("type") == "command_execution":
        text = found.get("aggregated_output") or ""
        raw = text.encode("utf-8", "replace")
        out["command"] = strip_wrapper(found.get("command") or "")
        out["exit_code"] = found.get("exit_code")
        out["total_bytes"] = len(raw)
        if len(raw) > args.max_bytes:
            out["truncated"] = True
            out["shown_bytes"] = args.max_bytes
            out["output"] = raw[: args.max_bytes].decode("utf-8", "replace")
            out["truncation_notice"] = (
                f"{len(raw) - args.max_bytes} of {len(raw)} bytes withheld; "
                f"raise --max-bytes to see more")
        else:
            out["truncated"] = False
            out["output"] = text
    elif found.get("type") == "file_change":
        out["changes"] = found.get("changes") or []
    else:
        out["item"] = found
    emit(out)


# --------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------

def signal_run(run_dir: Path, meta: dict, grace: float = 5.0):
    """SIGINT, then SIGTERM, then SIGKILL — to the process group.

    SIGINT first because Codex flushes its rollout and leaves the thread
    resumable: measured, it exits ~0.3 s later and the resumed turn still knows
    what the interrupted turn had finished. Signalling the group, never a
    process name, is what keeps concurrent runs independent — name matching
    would kill every Codex on the machine, including other people's.
    """
    pgid = meta.get("pgid")
    result = {"run_id": meta.get("run_id"), "pgid": pgid}
    if not pgid:
        return {**result, "signalled": False, "reason": "no process group recorded",
                "state": meta.get("state")}

    sent = []
    for sig, wait in ((signal.SIGINT, grace), (signal.SIGTERM, 3.0), (signal.SIGKILL, 1.0)):
        try:
            os.killpg(int(pgid), sig)
            sent.append(sig.name)
        except ProcessLookupError:
            break
        except PermissionError:
            result["error"] = f"not permitted to signal process group {pgid}"
            break
        deadline = time.time() + wait
        gone = False
        while time.time() < deadline:
            if not pid_alive(meta.get("supervisor_pid")) and not pid_alive(meta.get("codex_pid")):
                gone = True
                break
            time.sleep(0.1)
        if gone:
            break

    result["signals_sent"] = sent
    result["signalled"] = bool(sent)
    # Compare-and-set, not a plain write: the supervisor may have recorded its
    # own outcome (`completed`, or `timed_out` if its deadline fired) between
    # the last signal and this line, and that outcome is the true one.
    m = update_meta_if(run_dir, ("running", "starting", "stalled"),
                       state="interrupted", ended_at=now_iso())
    result["state"] = m.get("state")
    result["thread_id"] = m.get("thread_id")
    return result


def cmd_stop(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if args.run:
        targets = []
        for ref in args.run:
            rd, m = find_run(runs_dir, ref)
            if not m:
                fail(f"no such run: {ref}", runs_dir=str(runs_dir))
            targets.append((rd, m))
    elif args.group:
        # Not a name match on process or label — B8 forbids that, and for good
        # reason: matching by name is how concurrent runs end up killing each
        # other. This resolves a group id recorded in the manifest to run ids,
        # then signals each run's own pgid exactly like --run does. The group
        # name never reaches a process.
        targets = []
        for rd, m in resolve_group(runs_dir, args.group):
            m = reap(rd, m)
            if m.get("state") in ("running", "starting", "stalled"):
                targets.append((rd, m))
    elif args.all:
        targets = []
        for rd, m in iter_runs(runs_dir):
            m = reap(rd, m)
            if m.get("state") in ("running", "starting", "stalled"):
                targets.append((rd, m))
    else:
        fail("stop needs --run <id> (repeatable), --group <name>, or --all")
    emit({"stopped": [signal_run(rd, m, grace=args.grace) for rd, m in targets],
          "claude_session_id": session})


# --------------------------------------------------------------------------
# result
# --------------------------------------------------------------------------

GROUP_MESSAGE_CAP = 4000


def changed_paths(events_path: Path):
    """Paths a run wrote, from its `file_change` events."""
    paths = set()
    for ev in read_events(events_path, 0)[0]:
        item = ev.get("item") or {}
        if item.get("type") != "file_change":
            continue
        for ch in item.get("changes") or []:
            p = ch.get("path") if isinstance(ch, dict) else ch
            if p:
                paths.add(str(p))
    return paths


def cmd_result_group(args, project, runs_dir):
    members = resolve_group(runs_dir, args.group)
    results, per_run_paths, totals = [], {}, {"input_tokens": 0, "output_tokens": 0}

    for rd, meta in members:
        meta = reap(rd, meta)
        info = scan_progress(rd / "events.jsonl")
        msg_path = rd / "last-message.txt"
        message = (msg_path.read_text(encoding="utf-8") if msg_path.exists()
                   else info["last_agent_message"]) or ""
        # Cut and measure in the same unit. Slicing characters while reporting
        # bytes made a 3,000-character Korean message — 9,000 bytes, nothing
        # actually removed — report `message_truncated: true`, which is exactly
        # the guess D07's cap exists to replace with a fact.
        raw = message.encode("utf-8", "replace")
        truncated = len(raw) > GROUP_MESSAGE_CAP
        row = {"run_id": meta["run_id"], "label": meta.get("label"),
               "state": meta.get("state"), "exit_code": meta.get("exit_code"),
               # D07: capped per run, with the real size stated. Whether to pull
               # the full text is then a decision the caller makes, not a guess
               # — `result --run <id>` returns it whole.
               # "ignore", not "replace": a byte cut lands mid-character often
               # in any non-ASCII text, and U+FFFD would both re-encode larger
               # than the byte it replaced — pushing the payload back over the
               # cap — and read as corruption in prose that is merely cut short.
               "message": (raw[:GROUP_MESSAGE_CAP].decode("utf-8", "ignore")
                           if truncated else message),
               "message_bytes": len(raw),
               "message_truncated": truncated,
               "usage": info["usage"], "files_changed": info["files_changed"],
               "turn_failed": (clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400)
                               if info["turn_failed"] else None)}
        if meta.get("worktree"):
            row["worktree"] = meta["worktree"]
        results.append(row)
        # Keyed by run, never by worktree: with --resume-from a phase-2 member
        # inherits its predecessor's worktree, so a worktree-keyed set would
        # report every member as overlapping with its own past self.
        per_run_paths[meta["run_id"]] = changed_paths(rd / "events.jsonl")
        for key in totals:
            totals[key] += int((info["usage"] or {}).get(key) or 0)

    # D30: the intersection only. A full path list per run inverts the context
    # discipline this skill exists for, and `log` already prints file_change
    # paths for anyone who wants them. What is genuinely un-derivable, and what
    # a synthesis step needs first, is which paths two runs both touched.
    counts = {}
    for rid, paths in per_run_paths.items():
        for p in paths:
            counts.setdefault(p, []).append(rid)
    overlaps = {p: rids for p, rids in sorted(counts.items()) if len(rids) > 1}

    running, done, failed, gstate = group_snapshot(
        [{"run_id": r["run_id"], "state": r["state"]} for r in results])
    emit({"group": args.group, "project": str(project), "results": results,
          "overlaps": overlaps, "totals": totals, "group_state": gstate,
          "done": done, "failed": failed, "running": running,
          "overlaps_note": ("paths written by more than one member. Under worktree "
                            "isolation this is a merge conflict ahead, not damage "
                            "already done.") if overlaps else None})


def cmd_result(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        return cmd_result_group(args, project, runs_dir)
    if not args.run:
        fail("result needs --run <id> or --group <name>")
    rd, meta = find_run(runs_dir, args.run)
    if not meta:
        fail(f"no such run: {args.run}", runs_dir=str(runs_dir))
    meta = reap(rd, meta)
    info = scan_progress(rd / "events.jsonl")

    msg_path = rd / "last-message.txt"
    message = (msg_path.read_text(encoding="utf-8") if msg_path.exists()
               else info["last_agent_message"])

    usage = info["usage"]
    review_zero = meta.get("kind") == "review" and usage is not None and not any(usage.values())
    out = {"run_id": meta["run_id"], "thread_id": meta.get("thread_id") or info["thread_id"],
           "state": meta.get("state"), "exit_code": meta.get("exit_code"),
           "message": message, "usage": None if review_zero else usage,
           # F8: same clipped `turn.failed` error as `run_row`, so `result`
           # doesn't force a second `log` call to learn why a run failed.
           "turn_failed": (clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400)
                          if info["turn_failed"] else None),
           "files_changed": info["files_changed"], "commands": info["commands"]}
    if review_zero:
        out["usage_note"] = "review runs report zero usage; unavailable, not free"
    if meta.get("state") not in TERMINAL_STATES:
        out["note"] = f"run is still {meta.get('state')}; this is a partial result"

    if meta.get("schema_path"):
        out["schema_path"] = meta["schema_path"]
        if not message:
            fail("run used --schema but produced no final message",
                 run_id=meta["run_id"], state=meta.get("state"))
        try:
            out["json"] = json.loads(message)
        except json.JSONDecodeError as e:
            # Loud, not lenient: handing back a malformed object as though it
            # had the schema's shape is worse than failing here.
            fail("run used --schema but the final message is not valid JSON",
                 run_id=meta["run_id"], parse_error=str(e),
                 message_preview=clip(message, 400))
    emit(out)


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def cmd_doctor(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    report, blockers, warnings = {}, [], []

    report["python"] = sys.version.split()[0]
    if sys.version_info < (3, 10):
        blockers.append(f"python {report['python']} is below the required 3.10")

    exe = shutil.which("codex")
    report["codex_path"] = exe
    report["codex_version"] = None
    if not exe:
        blockers.append("`codex` is not on PATH")
    else:
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
            report["codex_version"] = (r.stdout or r.stderr).strip() or None
        except Exception as e:
            warnings.append(f"could not read `codex --version`: {e}")

    home = codex_home()
    report["codex_home"] = str(home)
    report["codex_home_from_env"] = bool(os.environ.get("CODEX_HOME"))
    report["codex_home_exists"] = home.is_dir()
    if not home.is_dir():
        blockers.append(f"CODEX_HOME does not exist: {home}")

    if exe:
        try:
            r = subprocess.run([exe, "login", "status"], capture_output=True, text=True,
                               timeout=30, stdin=subprocess.DEVNULL)
            report["login_status"] = (r.stdout or r.stderr).strip()[:400]
            report["login_ok"] = r.returncode == 0
            if r.returncode != 0:
                blockers.append("`codex login status` exited non-zero — not authenticated")
        except Exception as e:
            report["login_ok"] = None
            warnings.append(f"could not run `codex login status`: {e}")

    cfg = home / "config.toml"
    report["config_toml"] = str(cfg) if cfg.exists() else None
    cfg_sandbox = cfg_approval = None
    if cfg.exists():
        try:
            txt = cfg.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'(?m)^\s*sandbox_mode\s*=\s*"?([\w-]+)"?', txt)
            cfg_sandbox = m.group(1) if m else None
            m = re.search(r'(?m)^\s*approval_policy\s*=\s*"?([\w-]+)"?', txt)
            cfg_approval = m.group(1) if m else None
        except Exception as e:
            warnings.append(f"could not read config.toml: {e}")
    report["config_sandbox_mode"] = cfg_sandbox
    report["config_approval_policy"] = cfg_approval
    if cfg_sandbox == "danger-full-access":
        warnings.append(
            'config.toml sets sandbox_mode = "danger-full-access". `codex exec resume` '
            "and `codex exec review` have no -s flag and fall back to this value, which "
            "is how a read-only thread becomes fully privileged on its second turn. "
            "This wrapper passes -c sandbox_mode= on every invocation, so that fallback "
            "is never reached — but a bare `codex` command you run yourself will hit it.")

    report["skill_dir"] = str(Path(__file__).resolve().parent.parent)
    report["bridge_path"] = str(Path(__file__).resolve())
    report["plugin_root_env"] = os.environ.get("CLAUDE_PLUGIN_ROOT")

    report["project"] = str(project)
    report["project_is_git_repo"] = git_toplevel(project) is not None
    agents = project / "AGENTS.md"
    report["project_agents_md"] = str(agents) if agents.exists() else None
    if agents.exists():
        warnings.append(
            f"{agents} is injected into every Codex run started in this project. "
            "Project AGENTS.md survives --ignore-user-config (measured), so it is a "
            "briefing channel that works — and equally, its contents are in context "
            "whether or not that was intended.")

    report["runs_dir"] = str(runs_dir)
    report["runs_dir_exists"] = runs_dir.is_dir()
    # Probe without creating: a diagnostic that changes what it diagnoses is a
    # bad diagnostic.
    target = runs_dir if runs_dir.is_dir() else runs_dir.parent
    probe = target / f".codex-write-probe-{os.getpid()}"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        report["runs_dir_writable"] = True
    except Exception as e:
        report["runs_dir_writable"] = False
        blockers.append(f"runs dir is not writable ({target}): {e}")

    # Facts, not a policy. Nothing here deletes anything or nags about a
    # threshold: the run directories hold event streams the caller may still
    # want, and the worktrees hold results nothing else has a copy of. What the
    # caller cannot see without being told is that batch runs leave both behind
    # and that only `batch clean --group` removes them.
    if runs_dir.is_dir():
        total = sum(p.stat().st_size for p in runs_dir.rglob("*") if p.is_file())
        report["runs_dir_bytes"] = total
        report["runs_dir_runs"] = sum(1 for _ in iter_runs(runs_dir))
        report["groups"] = list_groups(runs_dir)
        live_wt = [p for p in worktrees_registered(project) if p.exists()]
        report["worktrees"] = len(live_wt)
        if live_wt:
            warnings.append(
                f"{len(live_wt)} git worktree(s) from batch runs are still "
                f"checked out under {runs_dir}. Each is a full working copy and "
                f"holds its run's uncommitted results; `batch clean --group "
                f"<name>` removes a group's once you have collected them.")

    db = state_db_path()
    report["thread_db"] = str(db) if db else None
    report["thread_db_readable"] = bool(query_threads(limit=1)) if db else False
    if db and not report["thread_db_readable"]:
        warnings.append(
            f"{db} exists but no threads could be read. The filename is "
            "version-stamped, so a Codex upgrade may have changed its schema; "
            "`--include-external` and a registry-less `--last` degrade, nothing else.")

    report["blockers"] = blockers
    report["warnings"] = warnings
    report["ok"] = not blockers
    emit(report, code=0 if not blockers else 2)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def add_common(p):
    p.add_argument("--runs-dir")
    p.add_argument("--project")


def add_run_options(p, *, kind):
    p.add_argument("--label")
    p.add_argument("--sandbox", choices=SANDBOX_MODES)
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--inherit-config", action="store_true")
    p.add_argument("--isolate", action="store_true")
    p.add_argument("--priority", dest="priority", action="store_true", default=None)
    p.add_argument("--no-priority", dest="priority", action="store_false")
    p.add_argument("--schema")
    p.add_argument("--config", action="append", metavar="k=v")
    p.add_argument("--foreground", action="store_true")
    p.add_argument("--timeout", type=float,
                   help="give the run this many seconds, then SIGINT its process "
                        "group and record state=timed_out. Works in background "
                        "and foreground. No default: no flag, no deadline.")
    p.add_argument("--no-preamble", action="store_true")
    if kind in ("start", "resume"):
        p.add_argument("--image", action="append")
        p.add_argument("--prompt-file")
    if kind == "start":
        p.add_argument("--cwd")
        p.add_argument("--add-dir", action="append")


def build_parser():
    ap = argparse.ArgumentParser(prog="codex_bridge.py",
                                 description="Drive the OpenAI Codex CLI as a managed subagent.")
    ap.subparser_map = {}
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="start a new Codex thread")
    add_common(p); add_run_options(p, kind="start")
    p.add_argument("prompt", nargs="?")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("resume", help="continue an existing Codex thread")
    add_common(p); add_run_options(p, kind="resume")
    p.add_argument("--last", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="allow a second turn on a thread that already has one running")
    p.add_argument("rest", nargs="*", metavar="[REF] PROMPT",
                   help="run id / thread id / thread name, then the prompt; "
                        "with --last, just the prompt")
    p.set_defaults(func=cmd_resume, cwd=None, add_dir=None, ref=None, prompt=None)
    ap.subparser_map["resume"] = p

    p = sub.add_parser("review", help="run `codex exec review`")
    add_common(p); add_run_options(p, kind="review")
    p.add_argument("--uncommitted", action="store_true")
    p.add_argument("--base")
    p.add_argument("--commit")
    p.add_argument("--title")
    p.add_argument("--cwd")
    p.add_argument("prompt", nargs="?")
    p.set_defaults(func=cmd_review, image=None, add_dir=None, prompt_file=None)

    p = sub.add_parser("status", help="list runs with state, idle time and usage")
    add_common(p)
    p.add_argument("--run")
    p.add_argument("--thread")
    p.add_argument("--group", help="report on one batch group's members only")
    p.add_argument("--all", action="store_true")
    p.add_argument("--include-external", action="store_true")
    p.add_argument("--follow", action="store_true",
                   help="with --group: print each member state change, then a "
                        "terminal group line, then exit. Pair with Monitor; the "
                        "Bash tool's 600s ceiling cannot be crossed by blocking.")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--follow-timeout", type=float)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("log", help="filtered, incremental event log")
    add_common(p)
    p.add_argument("--run")
    p.add_argument("--since", type=int, default=0)
    p.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL)
    p.add_argument("--follow", action="store_true")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--follow-timeout", type=float)
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("show", help="full output of one event item")
    add_common(p)
    p.add_argument("--run", required=True)
    p.add_argument("--item", required=True)
    p.add_argument("--max-bytes", type=int, default=SHOW_MAX_BYTES)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stop", help="interrupt a run by process group")
    add_common(p)
    p.add_argument("--run", action="append")
    p.add_argument("--group")
    p.add_argument("--all", action="store_true")
    p.add_argument("--grace", type=float, default=5.0)
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("result", help="final message, usage, and schema JSON")
    add_common(p)
    p.add_argument("--run")
    p.add_argument("--group", help="collect every member of a batch group, capped "
                                   "per run, plus the paths more than one wrote")
    p.set_defaults(func=cmd_result)

    p = sub.add_parser("batch", help="start and manage a group of runs")
    bsub = p.add_subparsers(dest="batch_cmd", required=True)
    b = bsub.add_parser("start", help="start N runs as one addressable group")
    add_common(b); add_run_options(b, kind="start")
    b.add_argument("--group", required=True,
                   help="name for this group. Single-use per project: reusing one "
                        "would make membership and start order ambiguous, and "
                        "--resume-from pairs positionally against exactly that list.")
    b.add_argument("--task", action="append",
                   help="a prompt. Repeatable. Always kind=start.")
    b.add_argument("--tasks-file",
                   help="JSONL, one task object per line, for long or "
                        "heterogeneous tasks. Fields: " + ", ".join(TASK_FIELDS))
    b.add_argument("--force", action="store_true",
                   help="allow a resume task to start a second turn on a thread "
                        "that already has a live one")
    b.add_argument("--worktree", action="store_true",
                   help="give every writing member its own git worktree even if "
                        "there is only one of them")
    b.add_argument("--no-worktree", action="store_true",
                   help="never assign worktrees; every member shares the "
                        "caller's tree")
    b.add_argument("--base",
                   help="commit or ref the worktrees are cut from (default HEAD)")
    b.add_argument("--resume-from", metavar="GROUP",
                   help="continue an earlier group: task i resumes member i of "
                        "that group, in its start order, keeping its thread and "
                        "its working directory. One task per started member.")
    b.set_defaults(func=cmd_batch_start)

    b = bsub.add_parser("clean", help="remove a finished group's worktrees")
    add_common(b)
    b.add_argument("--group", required=True)
    b.add_argument("--force", action="store_true",
                   help="remove worktrees that still hold uncommitted changes, "
                        "and ignore live members and dependent groups. This "
                        "discards work nothing else has a copy of.")
    b.set_defaults(func=cmd_batch_clean)

    p = sub.add_parser("doctor", help="diagnose the Codex environment")
    add_common(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("__supervise", help=argparse.SUPPRESS)
    p.add_argument("--run-dir", required=True)
    p.set_defaults(func=lambda a: sys.exit(supervise(Path(a.run_dir))))

    return ap


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    ap = build_parser()
    # `resume` is the only subcommand with two optional positionals
    # (`[REF] PROMPT`). Plain argparse binds them in groups split by any option
    # in between, so `resume <ref> --sandbox read-only "prompt"` loses the
    # prompt. parse_intermixed_args handles exactly that, but it cannot run on a
    # parser that owns subparsers — so dispatch to the subparser itself.
    if raw[:1] == ["resume"]:
        args = ap.subparser_map["resume"].parse_intermixed_args(raw[1:])
    else:
        args = ap.parse_args(raw)
    try:
        args.func(args)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
    except KeyboardInterrupt:
        fail("interrupted")
    except Exception as e:
        fail(f"internal error: {e}")


if __name__ == "__main__":
    main()
