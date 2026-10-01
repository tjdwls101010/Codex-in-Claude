"""`log`: a run's or a group's events, filtered to a level, from a byte cursor, followed to the end on request."""

from __future__ import annotations

from pathlib import Path

from codex.codex_cli import CursorOutOfRange, event_lines
from codex.errors import Refusal
from codex.git import resolve_project
from codex.observe.follow import closing_line, follow, group_tail
from codex.observe.rows import group_snapshot, member_rows
from codex.registry import (
    group_manifest, group_runs, implicit_run, is_live, iter_runs, read_meta, reap, resolve_runs_dir, run,
)


def log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        yield from log_group(args, project, runs_dir)
        return
    if args.run:
        rd, meta = run(runs_dir, args.run)
    else:
        candidates = list(iter_runs(runs_dir))
        if not candidates:
            raise Refusal("no runs in this registry", runs_dir=str(runs_dir))
        rd, meta, _ = implicit_run(candidates)

    events_path = rd / "events.jsonl"
    rel_to = Path(meta.get("cwd") or project)
    run_id = meta.get("run_id")
    cursor = [args.since or 0]

    def dump():
        try:
            lines, cursor[0] = event_lines(events_path, cursor[0], args.level, rel_to)
        except CursorOutOfRange as e:
            raise Refusal(str(e), run_id=run_id, since=cursor[0])
        for line in lines:
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
        return [f"run.still-running run={m.get('run_id')} state={m.get('state')}", trailer()]

    yield from follow(step, timeout=args.follow_timeout)


def log_group(args, project, runs_dir):
    """Every member's events interleaved, each physical line prefixed with its member, ending on the group's terminal line."""
    members = group_runs(runs_dir, args.group)
    if not members:
        yield f"group.empty group={args.group}" + group_tail(runs_dir, args.group)[1] + "\n"
        return
    labels = {m.get("run_id"): m.get("label") for m in (group_manifest(runs_dir, args.group) or {}).get("members", [])}
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
            entries, cursors[i] = event_lines(rd / "events.jsonl", cursors[i], args.level, Path(m.get("cwd") or project))
            for entry in entries:
                for line in entry.split("\n"):
                    yield prefixes[i] + line + "\n"

    def step():
        yield from drain()
        rows = member_rows(members, project)
        running, done, failed, _ = group_snapshot(rows)
        if not running or not args.follow:
            # Drained again after the state was read, so events written just before the end are not lost.
            yield from drain()
            yield closing_line(runs_dir, args.group, rows)
            return None
        return [f"group.still-running group={args.group} running={len(running)} done={len(done)} failed={len(failed)}"]

    yield from follow(step, timeout=args.follow_timeout)
