"""Building a run, and describing one.

One function does the first job — `create_run` — and everything about a run's
identity is decided inside it: which directory it runs in, which settings it
carries, whether it gets its own worktree, and what prompt Codex actually
receives. `start`, `resume`, `review` and every batch member funnel through it,
which is what keeps a batch member and a hand-typed `start` from drifting apart.

`run_row` does the second: the one-line summary that `status` prints, for a
single run and for a group member alike.

This module is deliberately below the batch layer in the import order.
`_batch.py` needs both of these; putting them here rather than in the CLI
entrypoint is what lets the batch subsystem live in one file without importing
the entrypoint back.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from _codex import (
    SANDBOX_MODES, THREAD_ID_WAIT, apply_preamble, build_argv,
    check_model_effort, model_catalog, spawn_supervised, supervise, user_defaults,
)
from _events import first_thread_id, scan_progress
from _registry import (
    TERMINAL_STATES, claim_run_dir, ensure_runs_dir, iter_runs, read_meta, reap,
    resolve_project, resolve_runs_dir, still_writing, thread_turn_lock,
    unreadable_runs, write_meta,
)
from _util import clip, fail, git_toplevel, is_within, now_iso

WRITING_SANDBOXES = ("workspace-write", "danger-full-access")


def ordered_by_waiting(a: dict, b: dict, by_id: dict) -> bool:
    """True if one of these two runs is queued behind the other.

    Two runs chained by `--as-ready` share a working directory and are both
    non-terminal, which is the shape every collision check looks for — but they
    are the one arrangement that cannot collide, because the later one does not
    spawn Codex until the earlier one has stopped. Reporting them as
    uncoordinated writers is a confident falsehood about the safest case.
    """
    return (a.get("run_id") in wait_chain(b.get("waits_for"), by_id)
            or b.get("run_id") in wait_chain(a.get("waits_for"), by_id))


def concurrent_writers(runs_dir, cwd, exclude_run_id=None, waits_for=None):
    """Other live runs that can write to this same directory.

    Compared on each run's recorded `cwd`, never on its git top level: every
    worktree of one repository shares a top level, so that comparison would
    warn about the very isolation that makes the situation safe.

    Reported, never refused (D17). Concurrency here is sometimes exactly what
    the caller wants — but it is never something they can see, and a session
    that cannot see it will not go looking. Measured: an e2e session continued
    three writing threads with three `resume` calls into one directory and
    escaped damage only because the three edits landed in three different
    files. `resume` has no worktree option, so nothing but this could have
    told it.
    """
    out = []
    runs = list(iter_runs(runs_dir))
    chain = (wait_chain(waits_for, {m.get("run_id"): m for _rd, m in runs})
             if waits_for else set())
    for rd, m in runs:
        if m.get("run_id") == exclude_run_id:
            continue
        # A run this one is queued behind shares its directory by design and
        # cannot be writing at the same time.
        if m.get("run_id") in chain:
            continue
        if m.get("sandbox") not in WRITING_SANDBOXES:
            continue
        if not (is_within(m.get("cwd"), cwd) or is_within(cwd, m.get("cwd"))):
            continue
        # Reaped before being judged alive, like every other place that turns
        # registry state into a liveness claim. meta.json says `running` until
        # something notices the supervisor died, so trusting it as written
        # names dead runs as live writers — and a warning that cries wolf is
        # one the caller learns to skip past, which costs more than not having
        # it. Reaped only for the few candidates that already matched the
        # directory and the sandbox, so this is not a registry-wide write.
        m = reap(rd, m)
        if m.get("state") in TERMINAL_STATES and not still_writing(m):
            continue
        out.append({"run_id": m.get("run_id"), "state": m.get("state"),
                    "sandbox": m.get("sandbox"), "group": m.get("group"),
                    **({"codex_still_running": True} if still_writing(m) else {})})
    return out
from _worktree import (
    add as worktree_add, uncommitted_count as worktree_uncommitted,
)

# Advisory only. `idle_seconds` is always reported alongside it, so this number
# never decides anything by itself: one long `command_execution` is legitimately
# silent, which is why silence alone is not failure — silence plus no
# in-progress item is.
STALL_SECONDS = 300


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
    non_terminal = [(rd, m) for rd, m in reaped
                    if m.get("state") not in TERMINAL_STATES or still_writing(m)]
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


def wait_chain(start, by_id, limit=64):
    """Every run this one is transitively queued behind, `start` included.

    Bounded because `waits_for` is a field on disk like any other: a hand-edited
    or half-written cycle would otherwise hang the guard rather than refuse.
    """
    chain, cur = set(), start
    while cur and cur not in chain and len(chain) < limit:
        chain.add(cur)
        cur = (by_id.get(cur) or {}).get("waits_for")
    return chain


def thread_of_unreadable(run_dir):
    """The thread a run whose meta.json will not parse was on, or None.

    `events.jsonl` is written by Codex and `meta.json` by this wrapper, so one
    being corrupt says nothing about the other, and the thread is announced in
    the first line of the stream.
    """
    try:
        return first_thread_id(run_dir / "events.jsonl")
    except Exception:
        return None


def refuse_concurrent_turn(runs_dir, thread_id, force, waits_for=None):
    """F4 reproduced two turns run concurrently on one thread: rc 0, no
    warning. A resumed run shares its parent's process group with nothing —
    two live turns on the same thread would race on the same rollout file —
    so a live turn on the target thread is refused unless the caller opts in
    with --force.

    Called from inside `create_run`, under `thread_turn_lock`, and from nowhere
    else. It used to be the caller's job, which left the check and the new run's
    publication in different critical sections — i.e. in none — so two resumes
    a fraction of a second apart both passed it. One caller, one lock, one
    place: the same reason `review_argv` has one home (R20)."""
    if not thread_id or force:
        return
    # Matched on the recorded thread id OR on the ref the run was launched
    # against. They are usually the same string, and when they are not, the
    # second is the only one that exists yet: a resume of a ref this registry
    # has never seen publishes with `thread_id: null`, because the real id only
    # arrives later, from the spawned Codex process's `thread.started`. That is
    # after this lock is released, so comparing on `thread_id` alone left the
    # headline case — picking up a thread started in the Codex TUI — completely
    # unguarded. Reproduced 5 times in 5: two resumes of one fresh ref, both
    # rc 0, both spawning `codex exec resume <same ref>`.
    # One scan, and the run-id map only when there is a chain to walk: this
    # guard runs on the critical path of every resume, and a registry scan is
    # 0.63 s at 2,000 runs.
    runs = list(iter_runs(runs_dir))
    chain = (wait_chain(waits_for, {m.get("run_id"): m for _rd, m in runs})
             if waits_for else set())
    live = [reap(rd, m) for rd, m in runs
            if thread_id in (m.get("thread_id"), m.get("resume_ref"))]
    # `--as-ready` publishes a member while its predecessor is still mid-turn,
    # which is exactly what this guard refuses — so the exemption is scoped to
    # the caller's own wait chain rather than granted by `--force`. `--force`
    # waives the check for every collision on the thread, including ones nobody
    # planned; this waives it for the runs whose finishing this one's supervisor
    # is about to block on. The invariant is re-established before Codex spawns,
    # not abandoned.
    #
    # The chain, not just the direct predecessor: with p1 → p2 → p3 every stage
    # is ordered by construction, so registering p3 while p1 is still running is
    # safe — but exempting one id refused it and named the grandparent as the
    # live turn, which forced the caller to poll each stage until it visibly
    # started before the next could be registered. That is the waiting the flag
    # exists to remove. Exempting every *waiting* run instead would be too much:
    # a waiter starts the moment its predecessor ends, so a turn begun now could
    # still overlap one that is not behind anything of ours.
    # `still_writing` as well as the state: a run whose supervisor was killed is
    # recorded `orphaned` — terminal — while its `codex exec` keeps appending to
    # the thread's rollout. Terminal answers "is anyone recording this?"; the
    # question here is "is anything still writing this thread?", and those come
    # apart exactly when a supervisor dies alone.
    live = [{"run_id": m.get("run_id"), "state": m.get("state"),
             **({"codex_still_running": True} if still_writing(m) else {})}
            for m in live
            if (m.get("state") not in TERMINAL_STATES or still_writing(m))
            and m.get("run_id") not in chain]
    if live:
        fail("thread already has a live turn; pass --force to run a second turn "
             "concurrently", thread_id=thread_id, live_runs=live)
    # `iter_runs` drops a run whose meta.json will not parse, which is what
    # keeps one broken run from breaking every view — but it made this guard
    # blind in the one direction that matters: the state lives in the file that
    # will not parse, so such a run cannot be shown to have finished. Unknown is
    # not terminal (R23).
    #
    # Its thread, though, is often recoverable — `events.jsonl` is a separate
    # file and the thread is announced in it — and a corrupt run on some other
    # thread threatens nothing here. Refusing on all of them made one corrupt
    # run anywhere in the project block every resume in it, with no way out:
    # there is no command that removes a single run, and `--as-ready` may not be
    # combined with `--force`. A guard whose only escape is `rm -rf` is one
    # callers learn to route around.
    blind = [name for name in unreadable_runs(runs_dir)
             if name not in chain
             and thread_of_unreadable(runs_dir / name) in (None, thread_id)]
    if blind:
        fail("cannot tell whether this thread is free: "
             f"{len(blind)} run(s) in this project have a meta.json that will "
             "not parse, and their thread cannot be recovered from their event "
             "stream either. Remove the run director"
             f"{'ies' if len(blind) > 1 else 'y'} named below, or pass --force "
             "to start a turn without knowing.",
             thread_id=thread_id,
             unreadable_runs=[{"run_id": name, "run_dir": str(runs_dir / name)}
                              for name in blind])


# Building a run is five stages, and the thread's turn lock in the middle is why
# they are worth naming. Everything that can still REFUSE a run happens before
# the lock is taken; everything that makes the run VISIBLE happens inside it;
# everything SLOW happens after it is released. Two of this project's
# refinements are that ordering and nothing else — R26 (the check and the
# publication have to sit in one critical section, or two resumes a fraction of
# a second apart both see an idle thread) and R18/§worktree below (a checkout
# cut before the run is published is reachable by no removal path at all) — and
# both are invisible while the stages are one 290-line function.


def resolve_settings(args, *, kind, base, project, thread_ref):
    """Stage 1 — resolve what this run will be, and refuse it here if at all.

    Nothing in this stage writes anything or claims a name, so every refusal it
    makes costs nothing: no run directory, no group slot burned, no Codex
    process. That is why the model/effort check lives here rather than next to
    the code that uses its values.
    """
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

    # Isolated unless the caller asks for their config. `--isolate` used to
    # state the default explicitly and was retired for saying nothing on a fresh
    # run and too much on a resumed one — it re-asserted a recorded choice with
    # no way to take it back.
    isolated = base["isolated"] if base else True
    if getattr(args, "inherit_config", False):
        isolated = False

    sandbox = args.sandbox or (base["sandbox"] if base else "workspace-write")

    # Model, effort and service tier, in four steps: an explicit flag, then
    # whatever the thread recorded if its isolation has not changed, then the
    # user's `config.toml`, then whatever the server does with silence.
    #
    # Step two is the one worth naming. An empty record is a record: a thread
    # that ran on the server's default keeps running on it, whatever
    # `config.toml` says by the time it is resumed. That is B3's stability
    # rule, and it is why this is not an `or` chain — `or` cannot tell
    # "recorded nothing" from "has nothing recorded yet".
    #
    # `user_defaults` is consulted only under isolation, exactly as the tier
    # always has been: `--ignore-user-config` is what removed those values, and
    # under `--inherit-config` Codex reads the same file itself, so putting
    # them back would be this wrapper restating what it chose not to suppress.
    inherits = bool(base) and isolated == base["isolated"]
    user = {} if inherits or not isolated else user_defaults()
    model = args.model or (base.get("model") if inherits else user.get("model"))
    effort = args.effort or (base.get("effort") if inherits else user.get("effort"))
    if getattr(args, "priority", None) is True:
        tier = "priority"
    elif getattr(args, "priority", None) is False:
        tier = None
    elif inherits:
        # `service_tier` replaced a boolean `priority` in the same release that
        # started reading the tier from config.toml. A thread recorded under
        # the old one holds the boolean and not the key, so reading only the
        # key drops Fast mode from the rest of that conversation — silently,
        # and on exactly the threads that had asked for it. The key is checked
        # for presence rather than truth, because a new record whose tier is
        # None is a choice this must not overwrite.
        tier = (base["service_tier"] if "service_tier" in base
                else ("priority" if base.get("priority") else None))
    else:
        tier = user.get("service_tier")

    # D38's catalog check, and it follows the *value* rather than the flag.
    # What must never be re-checked is a value inherited from the thread being
    # resumed — a model retired upstream would otherwise turn every resume of
    # that thread into a refusal, breaking the continuity `resume` exists for.
    # Everything else is being adopted here for the first time, and a
    # `config.toml` nobody has edited in a year is exactly where a retired
    # model sits waiting.
    #
    # Guarded rather than left to `check_model_effort`'s own early return,
    # because the catalog argument is evaluated first: calling it
    # unconditionally spawns a `codex debug models` subprocess on the critical
    # path of every run, including the ones that pin nothing.
    fresh_model = args.model or user.get("model")
    fresh_effort = args.effort or user.get("effort")
    if fresh_model or fresh_effort:
        check_model_effort(
            fresh_model, fresh_effort, catalog=model_catalog(), fail=fail,
            model_source=None if args.model else "config.toml",
            effort_source=None if args.effort else "config.toml")

    return {"cwd": cwd, "prompt": prompt, "isolated": isolated,
            "sandbox": sandbox, "model": model, "effort": effort,
            "service_tier": tier}


def publish_run(args, s, *, kind, base, project, runs_dir, thread_ref, group,
                waits_for):
    """Stage 2 — take the thread's turn lock, claim a run directory, publish it.

    From the lock to the first `write_meta` is one critical section per thread:
    the answer to "is this thread busy?" is only true until someone else
    publishes, and publishing is what the lock waits for.

    Returns `(run_id, run_dir, meta)`.
    """
    with thread_turn_lock(runs_dir, thread_ref):
        refuse_concurrent_turn(runs_dir, thread_ref,
                               getattr(args, "force", False),
                               waits_for=waits_for)
        if (kind == "resume" and base is None
                and not getattr(args, "sandbox", None)
                and not unreadable_runs(runs_dir)):
            # `codex exec resume` has no `-s`, so a resumed turn's sandbox is
            # whatever config layer happens to be in effect — which is why this
            # wrapper re-asserts the one it recorded on every turn. A thread it
            # never started has no record to re-assert, and `sandbox` above then
            # invents `workspace-write` for a conversation whose own policy
            # nobody knows. Inventing a write policy is the direction that
            # cannot be undone, so it is refused instead; passed once, it is
            # recorded against the thread from then on.
            #
            # `base is None` has two causes and only one of them is this one:
            # a run whose meta.json will not parse also resolves to no base.
            # Telling that caller "this thread has no registry entry" would
            # send them looking for a run sitting right there. So this sits
            # behind `refuse_concurrent_turn`, which names the unreadable run
            # specifically — and skips entirely when anything in the registry
            # was unreadable, because "never recorded" is a claim about the
            # whole registry and reading all of it is what earns the right to
            # make it. `--force` takes the same caller past that guard, which
            # is why the condition and not the ordering has to carry this.
            fail("this thread has no registry entry, so its original sandbox "
                 "was never recorded and there is nothing to re-assert. Pass "
                 "--sandbox explicitly; it is recorded against the thread from "
                 "then on.",
                 thread=thread_ref, sandbox=sorted(SANDBOX_MODES))
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
            "prompt_preview": clip(s["prompt"], 300),
            "cwd": str(s["cwd"]),
            "project": str(project),
            "sandbox": s["sandbox"],
            "model": s["model"],
            "effort": s["effort"],
            "isolated": s["isolated"],
            "service_tier": s["service_tier"],
            "schema_path": (str(Path(args.schema).expanduser().resolve())
                            if getattr(args, "schema", None)
                            else (base.get("schema_path") if base else None)),
            "images": [str(Path(i).expanduser().resolve())
                       for i in (getattr(args, "image", None) or [])],
            "add_dirs": [str(Path(d).expanduser().resolve())
                         for d in (getattr(args, "add_dir", None) or [])],
            # Only where Codex's own guard does not apply. The wrapper does not
            # silently disable a Codex safety default just to keep its own argv
            # uniform.
            "skip_git_repo_check": git_toplevel(s["cwd"]) is None,
            "claude_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"),
            "foreground": bool(getattr(args, "foreground", False)),
            "timeout_seconds": getattr(args, "timeout", None),
            # The manifest is the authority on membership and order; this copy lets
            # a single run say which group it belongs to without one, so `status`
            # can still answer that after a manifest is lost or hand-deleted.
            "group": group,
            "worktree": None,       # filled in by stage 3, once nothing can still refuse
            "started_at": now_iso(),
            # When Codex itself began, as distinct from when this run object was
            # built. They were the same thing to within milliseconds until
            # `--as-ready` put an unbounded wait between them, and everything
            # that reasons about whether two turns overlapped on one thread has
            # to use this one — a waiter's `started_at` precedes its
            # predecessor's `ended_at` by construction, which reads as exactly
            # the overlap the one-turn-per-thread invariant forbids.
            "codex_started_at": None,
            "ended_at": None, "exit_code": None, "state": "starting",
            "codex_pid": None, "supervisor_pid": None, "pgid": None,
            # Set only under `--as-ready`: the run this member's supervisor
            # waits for before it spawns Codex, and how that run ended.
            "waits_for": waits_for, "predecessor_state": None,
            # What this run was launched against, recorded even when it is not (yet)
            # a thread id. `thread_id` cannot hold it — a ref may be a thread *name*
            # — and leaving it nowhere is what made `refuse_concurrent_turn` blind
            # to a thread the registry has not seen before.
            "resume_ref": thread_ref,
            # Who is building this run, so `reap` can ask instead of guessing from
            # meta.json's mtime. There is a real window between publishing the run
            # and handing it to a supervisor — `git worktree add` may take a minute
            # — and during it this pid is the only evidence the run is alive.
            "creator_pid": os.getpid(),
        }

        if base and args.sandbox and args.sandbox != base["sandbox"]:
            # A sandbox change is never silent, in either direction.
            meta["sandbox_changed_from"] = base["sandbox"]

        if meta["schema_path"] and not Path(meta["schema_path"]).exists():
            fail(f"schema file not found: {meta['schema_path']}")
        for img in meta["images"]:
            if not Path(img).exists():
                fail(f"image not found: {img}")

        # Every check that could still refuse this run has passed, so publish it
        # before cutting anything. `write_meta` is what makes the run — and the
        # group it names — visible to `iter_runs`, and a checkout that exists while
        # the registry has never heard of the run is reachable by nothing at all:
        # not `batch clean --group`, which needs a run id, and not `status`, which
        # needs a meta.json. This process can die at any instant from here on, and
        # what it has already put on disk has to be findable without it.
        #
        # The reasoning below was written about *rejection* and is still right; it
        # was silent about *death*, which is the case that actually leaked.
        write_meta(run_dir, meta)
    # Lock released here, before the worktree is cut: `git worktree add` is
    # allowed a minute, and holding a thread's turn lock across it would turn
    # a loud refusal into a silent wait.
    return run_id, run_dir, meta


def cut_worktree(run_dir: Path, meta: dict, source: Path, worktree_base: str):
    """Stage 3 — give this run its own checkout, after every refusal has passed.

    Returns `(cwd, wt_info)`; `meta` is updated in place and rewritten.

    It cannot be cut before `claim_run_dir` — it lives at `<run_dir>/wt`, and
    the run id naming that directory does not exist until then — but cutting it
    any earlier than here leaks. A member rejected afterwards never gets a
    meta.json and so never gets a run_id, and `batch clean` resolves worktrees
    through the manifest's run ids: the worktree would survive every documented
    removal path while `batch clean` reported the group fully cleaned.
    """
    wt = run_dir / "wt"
    ok, err = worktree_add(source, wt, worktree_base)
    if not ok:
        fail(f"could not create the worktree for this member: {err}",
             base=worktree_base, path=str(wt))
    wt_info = {"path": str(wt), "base": worktree_base,
               "uncommitted_in_caller_tree": worktree_uncommitted(source),
               "source": str(source)}
    meta["cwd"] = str(wt)
    meta["worktree"] = wt_info
    # Immediately, not with the rest of meta at the end of `create_run`.
    # Between here and there lies `THREAD_ID_WAIT`, up to fifteen seconds of
    # waiting for Codex to name its thread, and a checkout whose path is
    # written nowhere is one `batch clean` skips: its loop takes the path from
    # `meta["worktree"]`. Publishing the run without it closes half a hole and
    # leaves the other half exactly as wide.
    write_meta(run_dir, meta)
    return wt, wt_info


def create_run(args, *, kind: str, base=None, review_args=None, thread_ref=None,
               group=None, batch=None, worktree_base=None, waits_for=None):
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))

    s = resolve_settings(args, kind=kind, base=base, project=project,
                         thread_ref=thread_ref)
    run_id, run_dir, meta = publish_run(
        args, s, kind=kind, base=base, project=project, runs_dir=runs_dir,
        thread_ref=thread_ref, group=group, waits_for=waits_for)

    cwd, wt_info = s["cwd"], None
    if worktree_base:
        cwd, wt_info = cut_worktree(run_dir, meta, s["cwd"], worktree_base)

    # Stage 4 — the argv, which is the last thing written before anything runs.
    if batch and wt_info:
        batch = {**batch, "worktree": wt_info["path"], "base": wt_info["base"],
                 "uncommitted": wt_info["uncommitted_in_caller_tree"]}
    send = (apply_preamble(s["prompt"], batch=batch)
            if s["prompt"].strip() else None)
    meta["argv"] = build_argv(meta, kind=kind, prompt=send,
                              thread_ref=thread_ref, review_args=review_args)
    write_meta(run_dir, meta)

    # Stage 5 — hand back a handle, or block for the whole turn.
    if meta["foreground"]:
        supervise(run_dir, timeout=getattr(args, "timeout", None))
        m = read_meta(run_dir) or {}
        info = scan_progress(run_dir / "events.jsonl")
        return {"run_id": run_id, "thread_id": m.get("thread_id"),
                "state": m.get("state"), "exit_code": m.get("exit_code"),
                "events": str(run_dir / "events.jsonl"), "project": str(project),
                "cwd": str(cwd), "sandbox": s["sandbox"],
                "isolated": s["isolated"],
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
        # `waiting` is the third exit. A member chained behind another reaches
        # neither a thread id of its own nor a terminal state until its
        # predecessor finishes, so without this the poll runs its full fifteen
        # seconds per member — six minutes for a batch of twenty-four, in the
        # command whose entire purpose is not making the caller wait. Nothing is
        # lost by leaving early: the thread is the predecessor's and was already
        # known at creation.
        if thread_id or m.get("state") in TERMINAL_STATES + ("waiting",):
            break
        time.sleep(0.05)
    m = read_meta(run_dir) or {}
    out = {"run_id": run_id, "thread_id": thread_id,
           "state": m.get("state", "starting"),
           "events": str(run_dir / "events.jsonl"), "project": str(project),
           "cwd": str(cwd), "sandbox": s["sandbox"], "isolated": s["isolated"]}
    if group:
        out["group"] = group
    if wt_info:
        out["worktree"] = wt_info
    if "sandbox_changed_from" in meta:
        out["sandbox_changed_from"] = meta["sandbox_changed_from"]
    if s["sandbox"] in WRITING_SANDBOXES and not wt_info:
        others = concurrent_writers(runs_dir, cwd, exclude_run_id=run_id,
                                    waits_for=waits_for)
        if others:
            out["concurrent_writers"] = others
            # The remedy this used to name — `batch start --worktree` with
            # `--resume-from` — cuts nothing: `wants_worktree` excludes every
            # resume, so that phase reports success and leaves the writers
            # exactly where they were. A remedy that does not work is worse
            # than none, because the caller stops looking for one.
            out["concurrent_writers_note"] = (
                f"{len(others)} other live run(s) can write to {cwd}. None of you "
                "can tell another agent's change from your own. Only a member "
                "starting fresh can be given a checkout of its own, with "
                "`batch start --worktree`; a resumed thread keeps the directory "
                "it already lives in, so runs already under way can no longer "
                "be separated.")
    return out


def run_row(run_dir: Path, meta: dict, project: Path):
    meta = reap(run_dir, meta)
    events_path = run_dir / "events.jsonl"
    info = scan_progress(events_path,
                          terminal=(meta.get("state") in TERMINAL_STATES
                                    and not still_writing(meta)))
    now = time.time()

    def stamp(field):
        try:
            return datetime.fromisoformat(
                meta[field].replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    elapsed = None
    t0 = stamp("started_at")
    if t0 is not None:
        elapsed = int(now - t0)
    # How long the TURN has taken, as distinct from how long the run has
    # existed. They differ only for a member that waited — but that is the one
    # the question is usually asked about, and `elapsed_seconds` alone reports
    # an hour queued plus a minute working as sixty-one minutes of work. This
    # round added `codex_started_at` because `started_at` stopped being a
    # reliable clock; leaving the field callers actually read on the old one
    # would have kept the ambiguity while looking like it had been fixed.
    # Measured to `ended_at` where there is one, so a finished turn's duration
    # stops growing — `elapsed_seconds` keeps its own meaning, and its own
    # long-standing habit of counting from the start until now regardless.
    codex_elapsed = None
    t1 = stamp("codex_started_at")
    if t1 is not None:
        # `ended_at` on a still-writing run is whatever moment an unrelated
        # caller's `reap` happened to stamp, not when the turn ended — freezing
        # the duration there reports a turn as over while it runs.
        end = None if still_writing(meta) else stamp("ended_at")
        codex_elapsed = int((end if end is not None else now) - t1)
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
        "elapsed_seconds": elapsed, "codex_elapsed_seconds": codex_elapsed,
        "idle_seconds": idle,
        "exit_code": meta.get("exit_code"), "sandbox": meta.get("sandbox"),
        "model": meta.get("model"), "effort": meta.get("effort"),
        "isolated": meta.get("isolated"),
        # The one recorded setting that costs money, so it is read back rather
        # than only written. Its value is the tier's own name — the config
        # file's spelling, passed through — not a boolean, so `fast` and
        # `priority` show as what they are: two advertised names, both measured
        # to run clean over `-c`.
        "service_tier": meta.get("service_tier"),
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
    if still_writing(meta):
        # Terminal states answer "is anyone recording this". Every consumer of a
        # row that asks "is this still going" — the status buckets,
        # `group_snapshot`, and through it `--follow`'s exit — needs the other
        # question answered too, and only the row can carry it to them.
        row["codex_still_running"] = True
    if info["unparsed_events"]:
        # Only when there are some. Every row carrying a zero would put the
        # field in front of a caller a thousand times for each time it means
        # anything, which is how a field stops being read.
        row["unparsed_events"] = info["unparsed_events"]
    if meta.get("waits_for"):
        row["waits_for"] = meta["waits_for"]
    if meta.get("predecessor_state"):
        row["predecessor_state"] = meta["predecessor_state"]
    if meta.get("codex_started_at"):
        # Distinct from `started_at` only for a member that waited, but always
        # reported: anything comparing turns across runs has to use this one.
        row["codex_started_at"] = meta["codex_started_at"]
    if meta.get("group"):
        # A run's group is the one fact a later session cannot re-derive.
        # `create_run` records it here precisely so `status` can answer it, and
        # for a while `status` did not: a session recovering a batch it did not
        # start saw N unrelated runs, concluded they were individual `start`s,
        # and had no group name to give `--resume-from`. Measured in an e2e
        # session, which then reasoned correctly from that false premise and
        # continued three writers into one shared directory.
        row["group"] = meta["group"]
    if meta.get("worktree"):
        row["worktree"] = meta["worktree"]["path"]
    if review_zero:
        row["usage_note"] = "review runs report zero usage; unavailable, not free"
    if meta.get("sandbox_changed_from"):
        row["sandbox_changed_from"] = meta["sandbox_changed_from"]
    if stderr_tail:
        row["stderr_tail"] = stderr_tail
    if meta.get("error"):
        row["error"] = meta["error"]
    return row


