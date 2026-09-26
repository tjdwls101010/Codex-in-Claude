"""`status`, `log`, `show` and `result`, for one run and for a group.

A follower holds no state `status --group` could not re-derive, so one that dies loses nothing, and every follow ends on a terminal line — including on `--follow-timeout` — so silence never stands in for an outcome.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from cli.guards import note_unreadable, refuse_competing_selectors, refuse_unusable_follow_options
from codex.codex_cli.events import CursorOutOfRange, FOLLOW_INTERVAL, find_item, format_events, read_events, strip_wrapper
from codex.git.repo import resolve_project
from codex.registry.groups import list_groups, read_group, resolve_group, unstarted_members, vanished_members
from codex.registry.runs import (
    TERMINAL_STATES, find_run, is_live, iter_runs, read_meta, reap, refuse_unresolved_run, resolve_implicit_run,
    resolve_runs_dir, still_writing, unreadable_runs,
)
from codex.util import emit, fail
from core.groups import changed_paths, member_result, overlaps
from core.observe import group_snapshot, progress, row_is_live, run_row, turn_failed_excerpt

# `show --item` cap; truncation is always announced with how much was withheld.
SHOW_MAX_BYTES = 20000

# The default listing keeps every live run plus this many newest.
LISTING_ROWS = 20


def write(*lines):
    for line in lines:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()


def follow(step, *, timeout, heartbeat):
    """Call `step()` every FOLLOW_INTERVAL until it returns None — it has printed its terminal line — or `timeout` passes.

    While unfinished, `step()` returns `(live count, lines to print if the deadline has passed)`. With `heartbeat`, a `still-running` line is printed on the first tick at or after each interval.
    """
    started = beat_at = time.time()
    while True:
        pending = step()
        if pending is None:
            return
        running, deadline_lines = pending
        now = time.time()
        if timeout and now - started >= timeout:
            write(*deadline_lines)
            return
        if heartbeat and now - beat_at >= heartbeat:
            write(f"still-running elapsed={int(now - started)} running={running}")
            beat_at = now
        time.sleep(FOLLOW_INTERVAL)


def summary_row(row):
    """What the default listing shows of a run, from a row built with a 160-character excerpt. `--run`, `--thread` and `--group` return the whole row."""
    out = {k: row.get(k) for k in ("run_id", "label", "state", "group", "idle_seconds")}
    out["last_agent_message"] = row.get("last_agent_message")
    if row.get("codex_still_running"):
        out["codex_still_running"] = True
    return out


def cmd_status(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    refuse_competing_selectors(args, "status", "--run", "--thread", "--group")
    if args.follow and not args.group:
        fail("--follow requires --group; to follow one run use `log --run <id> --follow`", run=args.run)
    refuse_unusable_follow_options(args)
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
    emit(note_unreadable(out, runs_dir))


def status_group(args, project, runs_dir):
    rows = [run_row(rd, m, project) for rd, m in resolve_group(runs_dir, args.group)]
    never = unstarted_members(runs_dir, args.group) + vanished_members(runs_dir, args.group)
    running, done, failed, gstate = group_snapshot(rows, len(never))
    out = {"project": str(project), "group": args.group, "runs": rows,
           "running": running, "done": done, "failed": failed,
           "total_runs": len(rows), "runs_truncated": 0, "group_state": gstate}
    if never:
        out["unstarted"] = never
    emit(note_unreadable(out, runs_dir))


def group_tail(runs_dir, name):
    """The counts a group's closing line appends when non-zero."""
    never = unstarted_members(runs_dir, name) + vanished_members(runs_dir, name)
    bad = len(unreadable_runs(runs_dir))
    return never, (f" unstarted={len(never)}" if never else "") + (f" unreadable={bad}" if bad else "")


def follow_group(args, project, runs_dir):
    """One line per member state change, then one terminal line."""
    members = resolve_group(runs_dir, args.group)
    never, tail = group_tail(runs_dir, args.group)
    if not members:
        return write(f"group.empty group={args.group}" + tail)
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
                write(line)
                seen[row["run_id"]] = row["state"]
        running, done, failed, gstate = group_snapshot(rows, len(never))
        if not running:
            return write(f"group.{gstate} group={args.group} done={len(done)} failed={len(failed)}" + tail)
        return len(running), [f"group.still-running group={args.group} running={len(running)} "
                              f"done={len(done)} failed={len(failed)}"]

    follow(step, timeout=args.follow_timeout, heartbeat=getattr(args, "heartbeat", None))


def cmd_log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    refuse_unusable_follow_options(args)
    if args.group:
        if args.since is not None:
            fail("--since takes one run's cursor and a group has one per member; use `log --run <id> --since <n>`", group=args.group)
        return log_group(args, project, runs_dir)
    if args.run:
        rd, meta = find_run(runs_dir, args.run)
        refuse_unresolved_run(args.run, rd, meta, runs_dir)
    else:
        candidates = list(iter_runs(runs_dir))
        if not candidates:
            fail("no runs in this registry", runs_dir=str(runs_dir))
        rd, meta, _ = resolve_implicit_run(candidates)

    events_path = rd / "events.jsonl"
    rel_to = Path(meta.get("cwd") or project)
    run_id = meta.get("run_id")
    cursor = [args.since or 0]

    def dump():
        try:
            events, cursor[0] = read_events(events_path, cursor[0])
        except CursorOutOfRange as e:
            fail(str(e), run_id=run_id, since=cursor[0])
        for line in format_events(events, args.level, rel_to):
            sys.stdout.write(line + "\n")
        sys.stdout.flush()

    trailer = lambda: f"# cursor={cursor[0]} run={run_id}"  # noqa: E731
    if not args.follow:
        dump()
        return write(trailer())

    def step():
        dump()
        m = reap(rd, read_meta(rd) or {})
        # The terminal line means the run stopped moving, so a run whose Codex still writes is not over.
        if not is_live(m):
            dump()
            return write(f"run.{m.get('state')} run={m.get('run_id')} exit={m.get('exit_code')}", trailer())
        return 1, [f"run.still-running run={m.get('run_id')} state={m.get('state')}", trailer()]

    follow(step, timeout=args.follow_timeout, heartbeat=args.heartbeat)


def log_group(args, project, runs_dir):
    """Every member's events interleaved, each physical line prefixed with its member, ending on the group's terminal line."""
    members = resolve_group(runs_dir, args.group)
    never, tail = group_tail(runs_dir, args.group)
    if not members:
        return write(f"group.empty group={args.group}" + tail)
    labels = {m.get("run_id"): m.get("label") for m in (read_group(runs_dir, args.group) or {}).get("members", [])}
    prefixes, header = [], []
    for i, (_rd, m) in enumerate(members):
        rid = m.get("run_id")
        label = labels.get(rid) or m.get("label")
        # Flattened: a label is caller text, and one holding a newline could forge a terminal line in a line protocol.
        label = " ".join(label.split()) if label else label
        prefixes.append(f"[{i}:{label}] " if label else f"[{i}] ")
        header.append(f"{i}={rid}" + (f":{label}" if label else ""))
    write(f"group.members group={args.group} " + " ".join(header))
    cursors = [0] * len(members)

    def drain():
        for i, (rd, m) in enumerate(members):
            events, cursors[i] = read_events(rd / "events.jsonl", cursors[i])
            for entry in format_events(events, args.level, Path(m.get("cwd") or project)):
                for line in entry.split("\n"):
                    sys.stdout.write(prefixes[i] + line + "\n")
        sys.stdout.flush()

    def step():
        drain()
        rows = [run_row(rd, read_meta(rd) or m, project) for rd, m in members]
        running, done, failed, gstate = group_snapshot(rows, len(never))
        if not running or not args.follow:
            # Drained again after the state was read, so events written just before the end are not lost.
            drain()
            return write(f"group.{gstate} group={args.group} done={len(done)} failed={len(failed)}" + tail)
        return len(running), [f"group.still-running group={args.group} running={len(running)} "
                              f"done={len(done)} failed={len(failed)}"]

    follow(step, timeout=args.follow_timeout, heartbeat=args.heartbeat)


def cmd_show(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rd, meta = find_run(runs_dir, args.run)
    refuse_unresolved_run(args.run, rd, meta, runs_dir)
    found, events = find_item(rd / "events.jsonl", args.item)
    if not found:
        ids = [f"{(e.get('item') or {}).get('id')}:{(e.get('item') or {}).get('type')}"
               for e in events if e.get("type") == "item.completed"]
        fail(f"no item {args.item!r} in run {meta['run_id']}", available=ids[:60])
    out = {"run_id": meta["run_id"], "item_id": args.item, "item_type": found.get("type")}
    if found.get("type") == "command_execution":
        text = found.get("aggregated_output") or ""
        raw = text.encode("utf-8", "replace")
        out.update(command=strip_wrapper(found.get("command") or ""), exit_code=found.get("exit_code"),
                   total_bytes=len(raw), truncated=len(raw) > args.max_bytes)
        if out["truncated"]:
            out["shown_bytes"] = args.max_bytes
            out["output"] = raw[: args.max_bytes].decode("utf-8", "replace")
            out["truncation_notice"] = (f"{len(raw) - args.max_bytes} of {len(raw)} bytes withheld; "
                                        f"raise --max-bytes to see more")
        else:
            out["output"] = text
    elif found.get("type") == "file_change":
        out["changes"] = found.get("changes") or []
    else:
        out["item"] = found
    emit(out)


def cmd_result(args):
    refuse_competing_selectors(args, "result", "--run", "--group")
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        return result_group(args, project, runs_dir)
    if not args.run:
        fail("result needs --run <id> or --group <name>")
    rd, meta = find_run(runs_dir, args.run)
    refuse_unresolved_run(args.run, rd, meta, runs_dir)
    meta = reap(rd, meta)
    info = progress(rd, meta)
    msg_path = rd / "last-message.txt"
    message = msg_path.read_text(encoding="utf-8") if msg_path.exists() else info["last_agent_message"]
    out = {"run_id": meta["run_id"], "thread_id": meta.get("thread_id") or info["thread_id"],
           "state": meta.get("state"), "exit_code": meta.get("exit_code"),
           "message": message, "usage": info["usage"], "turn_failed": turn_failed_excerpt(info),
           "files_changed": info["files_changed"], "commands": info["commands"]}
    if info["unparsed_events"]:
        out["unparsed_events"] = info["unparsed_events"]
    if meta.get("state") not in TERMINAL_STATES:
        out["note"] = f"run is still {meta.get('state')}; this is a partial result"
    elif still_writing(meta):
        # The same call later would return a different message, so this one is not final.
        out["note"] = "codex is still writing although the run is orphaned; this is a partial result"
    if meta.get("schema_path"):
        out["schema_path"] = meta["schema_path"]
        if not message:
            fail("the --schema run has no final message", run_id=meta["run_id"], state=meta.get("state"))
        try:
            out["json"] = json.loads(message)
        except json.JSONDecodeError as e:
            # Loud rather than lenient: a malformed object handed back as if it had the schema's shape is worse.
            fail("the final message of a --schema run is not valid JSON",
                 run_id=meta["run_id"], parse_error=str(e), message=message)
        # The parsed object is the answer; the same text again as `message` would double it.
        del out["message"]
    emit(out)


def result_group(args, project, runs_dir):
    results, per_run_paths, totals = [], {}, {"input_tokens": 0, "output_tokens": 0}
    for rd, meta in resolve_group(runs_dir, args.group):
        meta = reap(rd, meta)
        row, info = member_result(rd, meta)
        results.append(row)
        per_run_paths[meta["run_id"]] = changed_paths(
            rd / "events.jsonl", (meta.get("worktree") or {}).get("path") or meta.get("cwd"))
        for key in totals:
            totals[key] += int((info["usage"] or {}).get(key) or 0)
    found = overlaps(per_run_paths)
    never = unstarted_members(runs_dir, args.group) + vanished_members(runs_dir, args.group)
    running, done, failed, gstate = group_snapshot(results, len(never))
    emit({"group": args.group, "project": str(project), "results": results,
          "overlaps": found, "totals": totals, "group_state": gstate,
          "done": done, "failed": failed, "running": running, "unstarted": never,
          "overlaps_note": ("paths written by more than one member. Under worktree "
                            "isolation this is a merge conflict ahead, not damage "
                            "already done.") if found else None})
