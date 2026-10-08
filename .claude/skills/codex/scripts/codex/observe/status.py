"""`status`: whether runs are live, how far along, and what they last said — the default listing, one run, and a group."""

from __future__ import annotations

from codex.git import resolve_project
from codex.observe.rows import group_snapshot, note_unreadable, row_is_live, run_row, summary_row
from codex.registry import group_view, iter_runs, list_groups, resolve_runs_dir, run

# The default listing keeps every live run plus this many newest.
LISTING_ROWS = 20


def status(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        return status_group(args, project, runs_dir)

    if args.run:
        # One run is answered by its row itself, so its state is the first thing read.
        return run_row(*run(runs_dir, args.run), project)
    rows = [run_row(rd, m, project, excerpt=160) for rd, m in iter_runs(runs_dir)]
    # Summaries come from every row before the display cap, so no live run falls off `running`.
    running, done, failed, _ = group_snapshot(rows)
    shown = rows
    if len(rows) > LISTING_ROWS:
        shown = [r for r in rows[:-LISTING_ROWS] if row_is_live(r)] + rows[-LISTING_ROWS:]
    # The listing counts finished runs rather than naming them: their ids grow with the registry and say nothing the caller acts on. Groups are listed even when none of their members is shown: this is how a later session finds a batch.
    out = {"running": running, "counts": {"live": len(running), "completed": len(done), "failed": len(failed)},
           "total_runs": len(rows), "runs_truncated": len(rows) - len(shown), "groups": list_groups(runs_dir),
           "runs": [summary_row(r) for r in shown], "project": str(project), "runs_dir": str(runs_dir)}
    return note_unreadable(out, runs_dir)


def status_group(args, project, runs_dir):
    members, never, _epoch = group_view(runs_dir, args.group)
    rows = [run_row(rd, m, project) for rd, m in members]
    running, done, failed, gstate = group_snapshot(rows, len(never))
    out = {"group": args.group, "group_state": gstate, "running": running, "done": done, "failed": failed,
           "total_runs": len(rows), "runs_truncated": 0}
    if never:
        out["unstarted"] = never
    out.update(runs=rows, project=str(project))
    return note_unreadable(out, runs_dir)
