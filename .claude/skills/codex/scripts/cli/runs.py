"""`start`, `resume` and `stop`."""

from __future__ import annotations

import os

from cli.guards import refuse_competing_selectors
from codex.git.repo import resolve_project
from codex.registry.groups import resolve_group
from codex.registry.runs import (
    find_run, is_live, iter_runs, reap, refuse_unresolved_run, resolve_implicit_run, resolve_runs_dir,
)
from codex.util import emit, fail
from core.runs import create_run
from core.supervisor import stop_run



def cmd_start(args):
    emit(create_run(args, kind="start"))


def cmd_resume(args):
    # `[REF] PROMPT` is two optional positionals argparse cannot tell apart; with --last everything positional is the prompt.
    rest = list(args.rest)
    args.ref = None if args.last else (rest.pop(0) if rest else None)
    if len(rest) > 1:
        fail("too many positional arguments: resume takes [REF] PROMPT",
             expected="resume <ref> <prompt>  |  resume --last <prompt>", got=list(args.rest))
    args.prompt = rest[0] if rest else None

    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    base, resolved_from = None, None
    if args.last:
        candidates = [(rd, m) for rd, m in iter_runs(runs_dir) if m.get("thread_id")]
        if not candidates:
            fail("--last found no run with a thread in this project's registry; "
                 "name the thread to resume", runs_dir=str(runs_dir))
        _, base, resolved_from = resolve_implicit_run(candidates)
        thread_ref = base["thread_id"]
    else:
        if not args.ref:
            fail("resume needs a run id, thread id, thread name, or --last")
        _, base = find_run(runs_dir, args.ref)
        if base and not base.get("thread_id"):
            fail(f"run {base.get('run_id')} has no thread id, so there is nothing to resume; `status --run` shows why",
                 run_id=base.get("run_id"), state=base.get("state"))
        # A ref this registry has never seen may be a thread started elsewhere, so it is passed through.
        thread_ref = (base or {}).get("thread_id") or args.ref

    # A resumed run is a new run on the same thread, so each turn has its own event log.
    out = create_run(args, kind="resume", base=dict(base) if base else None, thread_ref=thread_ref)
    if args.last:
        # Say which run was inherited, and so which label and sandbox.
        out.update(resolved_from_run_id=base.get("run_id"), resolved_from=resolved_from, label=base.get("label"))
    emit(out)


def cmd_stop(args):
    refuse_competing_selectors(args, "stop", "--run", "--group", "--all")
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.run:
        targets = []
        for ref in args.run:
            rd, m = find_run(runs_dir, ref)
            refuse_unresolved_run(ref, rd, m, runs_dir)
            targets.append((rd, m))
    elif args.group or args.all:
        # A group resolves to its recorded members' process groups; nothing is ever matched by name.
        pool = resolve_group(runs_dir, args.group) if args.group else iter_runs(runs_dir)
        targets = [(rd, m) for rd, m in ((rd, reap(rd, m)) for rd, m in pool) if is_live(m)]
    else:
        fail("stop needs --run <id> (repeatable), --group <name>, or --all")
    emit({"stopped": [stop_run(rd, m, grace=args.grace) for rd, m in targets],
          "claude_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID")})
