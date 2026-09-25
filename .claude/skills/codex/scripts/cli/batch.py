"""`batch start` and `batch clean`."""

from __future__ import annotations

from core.groups import (
    check_task_settings, claim_group, clean_group, group_path, load_tasks, pair_with_previous, plan_worktrees,
    read_group, spawn_members, valid_name, worktree_report,
)
from core.registry import ensure_runs_dir, resolve_project, resolve_runs_dir
from util import emit, fail


def cmd_batch_start(args):
    if not valid_name(args.group):
        fail("group name must be letters, digits, `.`, `_` or `-`, with no path separators", got=args.group)
    if getattr(args, "base", None) and not getattr(args, "worktree", False):
        # Refused before the claim, so a typo does not burn the name.
        fail("--base requires --worktree", base=args.base)
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))
    tasks = load_tasks(args)
    previous = getattr(args, "resume_from", None)
    if previous:
        tasks, paired_with = pair_with_previous(tasks, runs_dir, previous, force=getattr(args, "force", False))
    check_task_settings(tasks, args, runs_dir)

    # Claimed before anything spawns, so a duplicate name costs nothing.
    try:
        epoch = claim_group(runs_dir, args.group, derived_from=previous, requested=len(tasks))["epoch"]
    except FileExistsError:
        existing = read_group(runs_dir, args.group) or {}
        fail(f"group {args.group!r} already exists; `batch clean --group {args.group}` releases the name once nothing is left",
             created_at=existing.get("created_at"), members=len(existing.get("members") or []))

    isolated, base, note = plan_worktrees(tasks, args, project, runs_dir)
    members, results = spawn_members(args, tasks, runs_dir=runs_dir, epoch=epoch, isolated=isolated, base=base)
    out = {"group": args.group, "runs": results,
           "spawned": len([m for m in members if m.get("run_id")]), "requested": len(tasks),
           "manifest": str(group_path(runs_dir, args.group))}
    if previous:
        out["resumed_from"] = {"group": previous, "members": paired_with}
    cut = [m for m in members if m.get("worktree")]
    if cut:
        out["worktrees"] = worktree_report(project, runs_dir, base, len(cut))
    elif note:
        out["worktrees"] = {"count": 0, "note": note}
    emit(out)


def cmd_batch_clean(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    emit(clean_group(project, runs_dir, args.group, force=args.force,
                     explicit_registry=bool(args.project or args.runs_dir)))
