"""`log`: a run's or a group's events, filtered to a level, from a byte cursor, followed to the end on request."""

from __future__ import annotations

from pathlib import Path

from codex.codex_cli.events import CursorOutOfRange, format_events, read_events
from codex.errors import Refusal
from codex.git.repo import resolve_project
from codex.observe.follow import follow, group_tail
from codex.observe.rows import group_snapshot, run_row
from codex.registry.groups import read_group, resolve_group
from codex.registry.runs import (
    find_run, is_live, iter_runs, read_meta, reap, refuse_unresolved_run, resolve_implicit_run, resolve_runs_dir,
)


def log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        yield from log_group(args, project, runs_dir)
        return
    if args.run:
        rd, meta = find_run(runs_dir, args.run)
        refuse_unresolved_run(args.run, rd, meta, runs_dir)
    else:
        candidates = list(iter_runs(runs_dir))
        if not candidates:
            raise Refusal("no runs in this registry", runs_dir=str(runs_dir))
        rd, meta, _ = resolve_implicit_run(candidates)

    events_path = rd / "events.jsonl"
    rel_to = Path(meta.get("cwd") or project)
    run_id = meta.get("run_id")
    cursor = [args.since or 0]

    def dump():
        try:
            events, cursor[0] = read_events(events_path, cursor[0])
        except CursorOutOfRange as e:
            raise Refusal(str(e), run_id=run_id, since=cursor[0])
        for line in format_events(events, args.level, rel_to):
            yield line + "\n"

    trailer = lambda: f"# cursor={cursor[0]} run={run_id}"  # noqa: E731
    if not args.follow:
        yield from dump()
        yield trailer() + "\n"
        return

    def step():
        yield from dump()
        m = reap(rd, read_meta(rd) or {})
        # The terminal line means the run stopped moving, so a run whose Codex still writes is not over.
        if not is_live(m):
            yield from dump()
            yield f"run.{m.get('state')} run={m.get('run_id')} exit={m.get('exit_code')}\n"
            yield trailer() + "\n"
            return None
        return 1, [f"run.still-running run={m.get('run_id')} state={m.get('state')}", trailer()]

    yield from follow(step, timeout=args.follow_timeout, heartbeat=args.heartbeat)


def log_group(args, project, runs_dir):
    """Every member's events interleaved, each physical line prefixed with its member, ending on the group's terminal line."""
    members = resolve_group(runs_dir, args.group)
    never, tail = group_tail(runs_dir, args.group)
    if not members:
        yield f"group.empty group={args.group}" + tail + "\n"
        return
    labels = {m.get("run_id"): m.get("label") for m in (read_group(runs_dir, args.group) or {}).get("members", [])}
    prefixes, header = [], []
    for i, (_rd, m) in enumerate(members):
        rid = m.get("run_id")
        label = labels.get(rid) or m.get("label")
        # Flattened: a label is caller text, and one holding a newline could forge a terminal line in a line protocol.
        label = " ".join(label.split()) if label else label
        prefixes.append(f"[{i}:{label}] " if label else f"[{i}] ")
        header.append(f"{i}={rid}" + (f":{label}" if label else ""))
    yield f"group.members group={args.group} " + " ".join(header) + "\n"
    cursors = [0] * len(members)

    def drain():
        for i, (rd, m) in enumerate(members):
            events, cursors[i] = read_events(rd / "events.jsonl", cursors[i])
            for entry in format_events(events, args.level, Path(m.get("cwd") or project)):
                for line in entry.split("\n"):
                    yield prefixes[i] + line + "\n"

    def step():
        yield from drain()
        rows = [run_row(rd, read_meta(rd) or m, project) for rd, m in members]
        running, done, failed, gstate = group_snapshot(rows, len(never))
        if not running or not args.follow:
            # Drained again after the state was read, so events written just before the end are not lost.
            yield from drain()
            yield f"group.{gstate} group={args.group} done={len(done)} failed={len(failed)}" + tail + "\n"
            return None
        return len(running), [f"group.still-running group={args.group} running={len(running)} "
                              f"done={len(done)} failed={len(failed)}"]

    yield from follow(step, timeout=args.follow_timeout, heartbeat=args.heartbeat)
