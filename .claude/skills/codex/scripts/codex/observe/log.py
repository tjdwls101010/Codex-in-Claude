"""`log`: what one run did, read once from its events."""

from __future__ import annotations

from pathlib import Path

from codex.codex_cli import event_lines
from codex.git import resolve_project
from codex.registry import reap, resolve_runs_dir, run


def log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rd, meta = run(runs_dir, args.run)
    for line in event_lines(rd / "events.jsonl", Path(meta.get("cwd") or project)):
        yield line + "\n"
    # Read after the events, so the state is never older than what was printed.
    yield f"run={meta.get('run_id')} state={reap(rd, meta).get('state')}\n"
