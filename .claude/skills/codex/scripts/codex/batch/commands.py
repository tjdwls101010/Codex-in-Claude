"""`batch` and `clean`, and the `next` a batch's reply names."""

from __future__ import annotations

from codex.batch.clean import clean_group
from codex.batch.spawn import spawn_members
from codex.batch.tasks import check_task_settings, load_tasks
from codex.batch.worktrees import plan_worktrees, worktree_report
from codex.git import resolve_project
from codex.registry import claim_group, ensure_runs_dir, group_path, resolve_runs_dir
from codex.util import with_next


def batch(args):
    """The group name's rule is the command surface's to refuse, before this is called."""
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))
    tasks = load_tasks(args)
    check_task_settings(tasks, args, runs_dir)

    # Claimed before anything spawns, so a duplicate name costs nothing.
    epoch = claim_group(runs_dir, args.group, requested=len(tasks))["epoch"]

    isolated, base, note = plan_worktrees(tasks, args, project, runs_dir)
    members, results = spawn_members(args, tasks, runs_dir=runs_dir, epoch=epoch, isolated=isolated, base=base)
    out = {"group": args.group, "spawned": len([m for m in members if m.get("run_id")]), "requested": len(tasks)}
    cut = [m for m in members if m.get("worktree")]
    if cut:
        out["worktrees"] = worktree_report(project, runs_dir, base, len(cut))
    elif note:
        out["worktrees"] = {"count": 0, "note": note}
    out.update(runs=results, manifest=str(group_path(runs_dir, args.group)))
    # The call that waits for the group and prints its result, left out when nothing started to wait for.
    if not out["spawned"]:
        return out
    return with_next(out, "requested", "result", "--group", args.group, "--wait", project=args.project,
                     runs_dir=args.runs_dir)


def clean(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    return clean_group(project, runs_dir, args.group, force=args.force,
                       explicit_registry=bool(args.project or args.runs_dir))
