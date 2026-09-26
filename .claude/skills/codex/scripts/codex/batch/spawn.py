"""Spawning a batch: each member's slot recorded before it starts, each member started as `start` or `resume` would, and one member's failure kept to its slot."""

from __future__ import annotations

from codex.batch.tasks import task_args
from codex.errors import Refusal
from codex.registry.groups import write_members
from codex.registry.runs import find_run
from codex.runs.create import create_run


def spawn_task(ns, item, *, group, runs_dir, batch=None, worktree_base=None):
    """Start one member, as `start` or `resume` would. A resume target outside the registry is passed through: it may be a thread started elsewhere."""
    if item["kind"] == "resume":
        _rd, base = find_run(runs_dir, item["resume"])
        if not base:
            return create_run(ns, kind="resume", thread_ref=item["resume"], group=group, batch=batch)
        return create_run(ns, kind="resume", base=base, thread_ref=base.get("thread_id"), group=group, batch=batch)
    return create_run(ns, kind="start", group=group, batch=batch, worktree_base=worktree_base)


def spawn_members(args, tasks, *, runs_dir, epoch, isolated, base):
    """Spawn every task in order. A member that fails keeps its slot with the error, and the others still start. Returns `(manifest members, reply rows)`."""
    batch_ctx = {"n": len(tasks), "group": args.group}
    members, results = [], []
    for index, item in enumerate(tasks):
        entry = {"index": index, "kind": item["kind"], "label": item.get("label") or args.label}
        # The slot is recorded before the spawn, so a checkout cut by a batch killed mid-spawn still belongs to the group.
        members.append(entry)
        write_members(runs_dir, args.group, members, epoch=epoch)
        try:
            out = spawn_task(task_args(args, item), item, group=args.group, runs_dir=runs_dir, batch=batch_ctx,
                             worktree_base=base if index in isolated else None)
        except Exception as e:
            # Any exception, not only an anticipated refusal: escaping would abort the batch with members already running.
            entry["error"] = e.error if isinstance(e, Refusal) else str(e)
            entry.update(e.fields if isinstance(e, Refusal) else {"error_type": type(e).__name__})
            results.append(entry)
            write_members(runs_dir, args.group, members, epoch=epoch)
            continue
        entry.update(run_id=out["run_id"], thread_id=out.get("thread_id"), cwd=out.get("cwd"),
                     sandbox=out.get("sandbox"))
        if out.get("worktree"):
            entry["worktree"] = out["worktree"]["path"]
        results.append({**entry, "state": out.get("state")})
        write_members(runs_dir, args.group, members, epoch=epoch)
    return members, results
