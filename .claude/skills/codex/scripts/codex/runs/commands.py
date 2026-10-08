"""`start`, `resume` and `stop`, and the `next` a started run's reply names."""

from __future__ import annotations

import os

from codex.errors import Refusal
from codex.git import resolve_project
from codex.registry import find_run, group_runs, live_runs, resolve_runs_dir, run
from codex.runs.create import create_run
from codex.runs.supervisor import stop_run
from codex.util import with_next


def start(args):
    return follow_up(create_run(args, kind="start"), args)


def follow_up(out, args):
    """The reply with its `next`: the call that waits for the run it made and prints its result."""
    return with_next(out, "state", "result", "--run", out["run_id"], "--wait", project=args.project, runs_dir=args.runs_dir)


def resume(args):
    """`args.ref` and `args.prompt` arrive split out of `resume REF [PROMPT]` by the command surface."""
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    _, base = find_run(runs_dir, args.ref)
    if base and not base.get("thread_id"):
        raise Refusal(f"run {base.get('run_id')} has no thread id, so there is nothing to resume; `status --run` shows why",
                      run_id=base.get("run_id"), state=base.get("state"))
    # A ref this registry has never seen may be a thread started elsewhere, so it is passed through.
    thread_ref = (base or {}).get("thread_id") or args.ref
    # A resumed run is a new run on the same thread, so each turn has its own event log.
    return follow_up(create_run(args, kind="resume", base=dict(base) if base else None, thread_ref=thread_ref), args)


def stop(args):
    """Exactly one of `--run` or `--group` is set; the command surface refuses the rest."""
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.run:
        targets = [run(runs_dir, ref) for ref in args.run]
    else:
        # A group resolves to its recorded members' process groups; nothing is ever matched by name.
        targets = live_runs(runs_dir, among=group_runs(runs_dir, args.group))
    return {"stopped": [stop_run(rd, m) for rd, m in targets],
            "claude_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID")}
