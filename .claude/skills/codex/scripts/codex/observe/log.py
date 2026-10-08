"""`log`: what one run did, read once from its events."""

from __future__ import annotations

from pathlib import Path

from codex.codex_cli import DEFAULT_LEVEL, event_lines
from codex.git import resolve_project
from codex.registry import resolve_runs_dir, run


def log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rd, meta = run(runs_dir, args.run)
    lines, cursor = event_lines(rd / "events.jsonl", 0, DEFAULT_LEVEL, Path(meta.get("cwd") or project))
    for line in lines:
        yield line + "\n"
    yield f"# cursor={cursor} run={meta.get('run_id')}\n"
