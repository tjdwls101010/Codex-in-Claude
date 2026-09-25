"""Building a run, and describing one.

One function does the first job — `create_run` — and everything about a run's
identity is decided inside it: which directory it runs in, which settings it
carries, whether it gets its own worktree, and what prompt Codex actually
receives. `start`, `resume` and every batch member funnel through it,
which is what keeps a batch member and a hand-typed `start` from drifting apart.

`run_row` does the second: the one-line summary that `status` prints, for a
single run and for a group member alike.

This module is deliberately below the batch layer in the import order.
`_batch.py` needs both of these; putting them here rather than in the CLI
entrypoint is what lets the batch subsystem live in one file without importing
the entrypoint back.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from core.supervisor import THREAD_ID_WAIT, spawn_supervised
from codex.argv import SANDBOX_MODES, apply_preamble, build_argv
from codex.catalog import check_model_effort, model_catalog
from codex.config import user_defaults
from core import settings
from codex.events import first_thread_id
from core.registry import (
    TERMINAL_STATES, claim_run_dir, ensure_runs_dir, is_live, iter_runs, read_meta, reap,
    resolve_project, resolve_runs_dir, still_writing, thread_turn_lock,
    unreadable_runs, write_meta,
)
from util import clip, fail, git_toplevel, is_within, now_iso

WRITING_SANDBOXES = ("workspace-write", "danger-full-access")


def concurrent_writers(runs_dir, cwd, exclude_run_id=None):
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
    for rd, m in iter_runs(runs_dir):
        if m.get("run_id") == exclude_run_id:
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
        if not is_live(m):
            continue
        out.append({"run_id": m.get("run_id"), "state": m.get("state"),
                    "sandbox": m.get("sandbox"), "group": m.get("group"),
                    **({"codex_still_running": True} if still_writing(m) else {})})
    return out
from worktree import (
    add as worktree_add, uncommitted_count as worktree_uncommitted,
)



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
                    if is_live(m)]
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


def refuse_concurrent_turn(runs_dir, thread_id, force):
    """F4 reproduced two turns run concurrently on one thread: rc 0, no
    warning. A resumed run shares its parent's process group with nothing —
    two live turns on the same thread would race on the same rollout file —
    so a live turn on the target thread is refused unless the caller opts in
    with --force.

    Called from inside `create_run`, under `thread_turn_lock`, and from nowhere
    else. It used to be the caller's job, which left the check and the new run's
    publication in different critical sections — i.e. in none — so two resumes
    a fraction of a second apart both passed it. One caller, one lock, one
    place."""
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
    live = [reap(rd, m) for rd, m in iter_runs(runs_dir)
            if thread_id in (m.get("thread_id"), m.get("resume_ref"))]
    # `still_writing` as well as the state: a run whose supervisor was killed is
    # recorded `orphaned` — terminal — while its `codex exec` keeps appending to
    # the thread's rollout. Terminal answers "is anyone recording this?"; the
    # question here is "is anything still writing this thread?", and those come
    # apart exactly when a supervisor dies alone.
    live = [{"run_id": m.get("run_id"), "state": m.get("state"),
             **({"codex_still_running": True} if still_writing(m) else {})}
            for m in live
            if is_live(m)]
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
    # there is no command that removes a single run. A guard whose only escape
    # is `rm -rf` is one callers learn to route around.
    blind = [name for name in unreadable_runs(runs_dir)
             if thread_of_unreadable(runs_dir / name) in (None, thread_id)]
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
    if not prompt.strip():
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

    r = settings.resolve(sandbox=args.sandbox, model=args.model, effort=args.effort,
                         priority=getattr(args, "priority", None),
                         inherit_config=getattr(args, "inherit_config", False),
                         base=base, user=user_defaults())
    # Checked here, before anything is written or claimed, so a refusal costs nothing. Guarded because the catalog lookup is a subprocess.
    adopted = r["adopted"]
    if adopted["model"] or adopted["effort"]:
        check_model_effort(adopted["model"], adopted["effort"], catalog=model_catalog(), fail=fail,
                           model_source=adopted["model_source"], effort_source=adopted["effort_source"])

    return {"cwd": cwd, "prompt": prompt, "isolated": r["isolated"],
            "sandbox": r["sandbox"], "model": r["model"], "effort": r["effort"],
            "service_tier": r["service_tier"]}


def publish_run(args, s, *, kind, base, project, runs_dir, thread_ref, group):
    """Stage 2 — take the thread's turn lock, claim a run directory, publish it.

    From the lock to the first `write_meta` is one critical section per thread:
    the answer to "is this thread busy?" is only true until someone else
    publishes, and publishing is what the lock waits for.

    Returns `(run_id, run_dir, meta)`.
    """
    with thread_turn_lock(runs_dir, thread_ref):
        refuse_concurrent_turn(runs_dir, thread_ref,
                               getattr(args, "force", False))
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
            "timeout_seconds": getattr(args, "timeout", None),
            # The manifest is the authority on membership and order; this copy lets
            # a single run say which group it belongs to without one, so `status`
            # can still answer that after a manifest is lost or hand-deleted.
            "group": group,
            "worktree": None,       # filled in by stage 3, once nothing can still refuse
            "started_at": now_iso(),
            # When Codex itself began, as distinct from when this run object was built.
            "codex_started_at": None,
            "ended_at": None, "exit_code": None, "state": "starting",
            "codex_pid": None, "supervisor_pid": None, "pgid": None,
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


def create_run(args, *, kind: str, base=None, thread_ref=None,
               group=None, batch=None, worktree_base=None):
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))

    s = resolve_settings(args, kind=kind, base=base, project=project,
                         thread_ref=thread_ref)
    run_id, run_dir, meta = publish_run(
        args, s, kind=kind, base=base, project=project, runs_dir=runs_dir,
        thread_ref=thread_ref, group=group)

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
                              thread_ref=thread_ref)
    write_meta(run_dir, meta)

    # Stage 5 — hand back a handle.
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
           "cwd": str(cwd), "sandbox": s["sandbox"], "isolated": s["isolated"]}
    if group:
        out["group"] = group
    if wt_info:
        out["worktree"] = wt_info
    if "sandbox_changed_from" in meta:
        out["sandbox_changed_from"] = meta["sandbox_changed_from"]
    if s["sandbox"] in WRITING_SANDBOXES and not wt_info:
        others = concurrent_writers(runs_dir, cwd, exclude_run_id=run_id)
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
