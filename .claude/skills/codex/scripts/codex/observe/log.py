"""`log`: what one run did, read once from its events."""

from __future__ import annotations

from pathlib import Path

from codex.codex_cli import event_lines
from codex.git import resolve_project
from codex.observe.rows import settled
from codex.registry import resolve_runs_dir, run


def log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rd, meta = run(runs_dir, args.run)
    meta, lines, _writing = settled(rd, meta, lambda _m: event_lines(rd / "events.jsonl", Path(meta.get("cwd") or project)))
    for line in lines:
        yield line + "\n"
    yield f"run={meta.get('run_id')} state={meta.get('state')}\n"
