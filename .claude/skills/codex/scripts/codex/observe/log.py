"""`log`: a run's or a group's events, filtered to a level, from a byte cursor, followed to the end on request."""

from __future__ import annotations

from pathlib import Path

from codex.codex_cli import CursorOutOfRange, event_lines
from codex.errors import Refusal
from codex.git import resolve_project
from codex.observe.follow import GroupWatch, closing_line, follow, tail
from codex.observe.rows import group_snapshot
from codex.registry import (
    group_manifest, implicit_run, is_live, iter_runs, read_meta, reap, resolve_runs_dir, run,
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
    """Every member's events interleaved, each physical line prefixed with its member, ending on the group's terminal line. A member a still-starting batch adds is followed from when it appears."""
    watch = GroupWatch(runs_dir, args.group, project)
    if not watch.members:
        yield f"group.empty group={args.group}" + tail(runs_dir, watch.gaps) + "\n"
        return
    labels = {m.get("run_id"): m.get("label") for m in (group_manifest(runs_dir, args.group) or {}).get("members", [])}
    # run id -> [run_dir, prefix, the directory paths are shown relative to, cursor], in the order members appeared.
    followed = {}

    def take(members):
        """Give members not followed yet their prefix; returns their `<index>=<run_id>[:<label>]` entries."""
        added = []
        for rd, m in members:
            rid = m.get("run_id")
            if rid in followed:
                continue
            i = len(followed)
            label = labels.get(rid) or m.get("label")
            # Flattened: a label is caller text, and one holding a newline could forge a terminal line in a line protocol.
            label = " ".join(label.split()) if label else label
            followed[rid] = [rd, f"[{i}:{label}] " if label else f"[{i}] ", Path(m.get("cwd") or project), 0]
            added.append(f"{i}={rid}" + (f":{label}" if label else ""))
        return added

    yield f"group.members group={args.group} " + " ".join(take(watch.members)) + "\n"

    def drain():
        for entry in followed.values():
            rd, prefix, rel_to, cursor = entry
            entries, entry[3] = event_lines(rd / "events.jsonl", cursor, args.level, rel_to)
            for e in entries:
                for line in e.split("\n"):
                    yield prefix + line + "\n"

    def step():
        yield from drain()
        rows, gaps = watch.now()
        take(watch.members)
        running, done, failed, _ = group_snapshot(rows)
        if not running or not args.follow:
            # Drained again after the state was read, so events written just before the end are not lost.
            yield from drain()
            yield closing_line(runs_dir, args.group, rows, gaps)
            return None
        return [f"group.still-running group={args.group} running={len(running)} done={len(done)} failed={len(failed)}"]

    yield from follow(step, timeout=args.follow_timeout)
