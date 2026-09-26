"""`batch start` and `batch clean`."""

from __future__ import annotations

from codex.batch.clean import clean_group
from codex.batch.rounds import pair_with_previous
from codex.batch.spawn import spawn_members
from codex.batch.tasks import check_task_settings, load_tasks
from codex.batch.worktrees import plan_worktrees, worktree_report
from codex.errors import Refusal
from codex.git.repo import resolve_project
from codex.registry.groups import claim_group, group_path, read_group
from codex.registry.runs import ensure_runs_dir, resolve_runs_dir


def start(args):
    """The group name's rule and `--base` without `--worktree` are the command surface's to refuse, before this is called."""
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
    out = {"group": args.group, "spawned": len([m for m in members if m.get("run_id")]), "requested": len(tasks)}
    if previous:
        out["resumed_from"] = {"group": previous, "members": paired_with}
    cut = [m for m in members if m.get("worktree")]
    if cut:
        out["worktrees"] = worktree_report(project, runs_dir, base, len(cut))
    elif note:
        out["worktrees"] = {"count": 0, "note": note}
    out.update(runs=results, manifest=str(group_path(runs_dir, args.group)))
    return out


def clean(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    return clean_group(project, runs_dir, args.group, force=args.force,
                       explicit_registry=bool(args.project or args.runs_dir))
