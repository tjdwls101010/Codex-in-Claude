"""`start`, `resume` and `stop`."""

from __future__ import annotations

import os

from codex.errors import Refusal
from codex.git.repo import resolve_project
from codex.registry.groups import resolve_group
from codex.registry.runs import (
    find_run, is_live, iter_runs, reap, refuse_unresolved_run, resolve_implicit_run, resolve_runs_dir,
)
from codex.runs.create import create_run
from codex.runs.supervisor import stop_run


def start(args):
    return create_run(args, kind="start")


def resume(args):
    """`args.ref` and `args.prompt` arrive split out of `resume [REF] PROMPT` by the command surface; with `--last` there is no ref."""
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    base, resolved_from = None, None
    if args.last:
        candidates = [(rd, m) for rd, m in iter_runs(runs_dir) if m.get("thread_id")]
        if not candidates:
            raise Refusal("--last found no run with a thread in this project's registry; "
                          "name the thread to resume", runs_dir=str(runs_dir))
        _, base, resolved_from = resolve_implicit_run(candidates)
        thread_ref = base["thread_id"]
    else:
        _, base = find_run(runs_dir, args.ref)
        if base and not base.get("thread_id"):
            raise Refusal(f"run {base.get('run_id')} has no thread id, so there is nothing to resume; `status --run` shows why",
                          run_id=base.get("run_id"), state=base.get("state"))
        # A ref this registry has never seen may be a thread started elsewhere, so it is passed through.
        thread_ref = (base or {}).get("thread_id") or args.ref

    # A resumed run is a new run on the same thread, so each turn has its own event log.
    out = create_run(args, kind="resume", base=dict(base) if base else None, thread_ref=thread_ref)
    if args.last:
        # Say which run was inherited, and so which label and sandbox.
        out.update(resolved_from_run_id=base.get("run_id"), resolved_from=resolved_from, label=base.get("label"))
    return out


def stop(args):
    """Exactly one of `--run`, `--group` or `--all` is set; the command surface refuses the rest."""
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.run:
        targets = []
        for ref in args.run:
            rd, m = find_run(runs_dir, ref)
            refuse_unresolved_run(ref, rd, m, runs_dir)
            targets.append((rd, m))
    else:
        # A group resolves to its recorded members' process groups; nothing is ever matched by name.
        pool = resolve_group(runs_dir, args.group) if args.group else iter_runs(runs_dir)
        targets = [(rd, m) for rd, m in ((rd, reap(rd, m)) for rd, m in pool) if is_live(m)]
    return {"stopped": [stop_run(rd, m, grace=args.grace) for rd, m in targets],
            "claude_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID")}
