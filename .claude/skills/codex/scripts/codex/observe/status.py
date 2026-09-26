"""`status`: whether runs are live, how far along, and what they last said — the default listing, one run or thread, a group, and a group followed to its end."""

from __future__ import annotations

from codex.git.repo import resolve_project
from codex.observe.follow import follow, group_tail
from codex.observe.rows import group_snapshot, note_unreadable, row_is_live, run_row, summary_row
from codex.registry.groups import list_groups, resolve_group, unstarted_members, vanished_members
from codex.registry.runs import find_run, iter_runs, read_meta, refuse_unresolved_run, resolve_runs_dir

# The default listing keeps every live run plus this many newest.
LISTING_ROWS = 20


def status(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        return follow_group(args, project, runs_dir) if args.follow else status_group(args, project, runs_dir)

    if args.run:
        rd, m = find_run(runs_dir, args.run)
        refuse_unresolved_run(args.run, rd, m, runs_dir)
        rows = [run_row(rd, m, project)]
    else:
        rows = [run_row(rd, m, project, excerpt=400 if args.thread else 160)
                for rd, m in iter_runs(runs_dir) if not args.thread or m.get("thread_id") == args.thread]
    by_thread = {}
    for r in rows:
        by_thread.setdefault(r["thread_id"] or "(unknown)", []).append(r["run_id"])
    # Summaries come from every row before the display cap, so no live run falls off `running`.
    running, done, failed, _ = group_snapshot(rows)
    shown = rows
    if not args.run and not args.all and len(rows) > LISTING_ROWS:
        shown = [r for r in rows[:-LISTING_ROWS] if row_is_live(r)] + rows[-LISTING_ROWS:]
    if not (args.run or args.thread):
        shown = [summary_row(r) for r in shown]
    out = {"project": str(project), "runs_dir": str(runs_dir), "runs": shown,
           "threads": by_thread, "running": running, "done": done, "failed": failed,
           "total_runs": len(rows), "runs_truncated": len(rows) - len(shown),
           # Listed even when none of their members is shown: this is how a later session finds a batch.
           "groups": list_groups(runs_dir)}
    return note_unreadable(out, runs_dir)


def status_group(args, project, runs_dir):
    rows = [run_row(rd, m, project) for rd, m in resolve_group(runs_dir, args.group)]
    never = unstarted_members(runs_dir, args.group) + vanished_members(runs_dir, args.group)
    running, done, failed, gstate = group_snapshot(rows, len(never))
    out = {"project": str(project), "group": args.group, "runs": rows,
           "running": running, "done": done, "failed": failed,
           "total_runs": len(rows), "runs_truncated": 0, "group_state": gstate}
    if never:
        out["unstarted"] = never
    return note_unreadable(out, runs_dir)


def follow_group(args, project, runs_dir):
    """One line per member state change, then one terminal line."""
    members = resolve_group(runs_dir, args.group)
    never, tail = group_tail(runs_dir, args.group)
    if not members:
        yield f"group.empty group={args.group}" + tail + "\n"
        return
    seen = {}

    def step():
        rows = []
        for rd, m in members:
            row = run_row(rd, read_meta(rd) or m, project)
            rows.append(row)
            prev = seen.get(row["run_id"])
            if prev != row["state"]:
                line = f"run {row['run_id']} {prev or '-'} -> {row['state']}"
                if row.get("exit_code") is not None and row["state"] != "completed":
                    line += f" exit={row['exit_code']}"
                yield line + "\n"
                seen[row["run_id"]] = row["state"]
        running, done, failed, gstate = group_snapshot(rows, len(never))
        if not running:
            yield f"group.{gstate} group={args.group} done={len(done)} failed={len(failed)}" + tail + "\n"
            return None
        return len(running), [f"group.still-running group={args.group} running={len(running)} "
                              f"done={len(done)} failed={len(failed)}"]

    yield from follow(step, timeout=args.follow_timeout, heartbeat=getattr(args, "heartbeat", None))
