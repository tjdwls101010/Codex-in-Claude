"""`batch start` and `batch clean`."""

from __future__ import annotations

from codex.git.repo import resolve_project
from codex.registry.groups import claim_group, group_path, read_group, valid_name
from codex.registry.runs import ensure_runs_dir, resolve_runs_dir
from codex.errors import Refusal
from codex.util import emit
from core.groups import (
    check_task_settings, clean_group, load_tasks, pair_with_previous, plan_worktrees, spawn_members, worktree_report,
)


def cmd_batch_start(args):
    if not valid_name(args.group):
        raise Refusal("group name must be 1–64 ASCII letters, digits, `.`, `_` or `-`, starting with a letter or digit (no path separators)", got=args.group)
    if getattr(args, "base", None) and not getattr(args, "worktree", False):
        # Refused before the claim, so a typo does not burn the name.
        raise Refusal("--base requires --worktree", base=args.base)
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
        raise Refusal(f"group {args.group!r} already exists; `batch clean --group {args.group}` releases the name once nothing is left",
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
