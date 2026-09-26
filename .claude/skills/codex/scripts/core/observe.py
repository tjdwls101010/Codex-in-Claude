"""Describing runs and groups: the status row, the turn-failure excerpt, and whether a row or a group is still live."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from codex.codex_cli.events import scan_progress
from core.registry import TERMINAL_STATES, is_live, reap, still_writing
from util import clip

# Advisory: a run idle this long is shown `stalled`, never killed for it. One long command is legitimately silent, which is why `in_progress_item` is reported beside it.
STALL_SECONDS = 300

FAILED_STATES = ("failed", "interrupted", "orphaned", "timed_out")


def row_is_live(row: dict) -> bool:
    """`is_live` for a row: its state is not terminal, or its Codex still writes."""
    return row["state"] not in TERMINAL_STATES or bool(row.get("codex_still_running"))


def turn_failed_excerpt(info):
    return clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400) if info["turn_failed"] else None


def progress(run_dir: Path, meta: dict):
    """The event-stream summary for a reaped run. A trailing fragment counts as unparsed only once nothing will write again."""
    return scan_progress(run_dir / "events.jsonl", terminal=not is_live(meta))


def run_row(run_dir: Path, meta: dict, project: Path, excerpt: int = 400):
    """The row `status` prints for one run, reaped first so a dead supervisor is never reported live."""
    meta = reap(run_dir, meta)
    events_path = run_dir / "events.jsonl"
    info = progress(run_dir, meta)
    now = time.time()

    def stamp(field):
        try:
            return datetime.fromisoformat(meta[field].replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    t0 = stamp("started_at")
    elapsed = int(now - t0) if t0 is not None else None
    # How long the turn has taken, as distinct from how long the run has existed. A still-writing run's `ended_at` is only when something reaped it, so its clock keeps running.
    codex_elapsed = None
    t1 = stamp("codex_started_at")
    if t1 is not None:
        end = None if still_writing(meta) else stamp("ended_at")
        codex_elapsed = int((end if end is not None else now) - t1)
    idle = None
    if events_path.exists() and events_path.stat().st_size > 0:
        idle = int(now - events_path.stat().st_mtime)

    state = meta.get("state")
    if state == "running" and idle is not None and idle >= STALL_SECONDS:
        state = "stalled"

    stderr_tail = None
    sp = run_dir / "stderr.log"
    if sp.exists() and sp.stat().st_size:
        txt = sp.read_text(encoding="utf-8", errors="replace")
        # Codex always prints this when stdin is not a TTY; it is not a failure.
        txt = "\n".join(ln for ln in txt.splitlines()
                        if ln.strip() and "Reading additional input from stdin" not in ln)
        stderr_tail = txt[-800:] or None

    row = {
        "run_id": meta.get("run_id"),
        "thread_id": meta.get("thread_id") or info["thread_id"],
        "parent_run_id": meta.get("parent_run_id"), "kind": meta.get("kind"),
        "label": meta.get("label"), "state": state,
        "codex_pid": meta.get("codex_pid"), "pgid": meta.get("pgid"),
        "started_at": meta.get("started_at"), "ended_at": meta.get("ended_at"),
        "elapsed_seconds": elapsed, "codex_elapsed_seconds": codex_elapsed,
        "idle_seconds": idle,
        "exit_code": meta.get("exit_code"), "sandbox": meta.get("sandbox"),
        "model": meta.get("model"), "effort": meta.get("effort"),
        "isolated": meta.get("isolated"),
        "service_tier": meta.get("service_tier"),
        "cwd": meta.get("cwd"),
        "usage": info["usage"],
        "turns_completed": info["turns_completed"], "commands": info["commands"],
        "files_changed": info["files_changed"], "config_error_events": info["errors"],
        "in_progress_item": info["in_progress_item"],
        "last_agent_message": clip(info["last_agent_message"] or "", excerpt) or None,
        "turn_failed": turn_failed_excerpt(info),
        "events": str(events_path),
    }
    # Optional fields appear only when they say something, so a present field is worth reading.
    if still_writing(meta):
        row["codex_still_running"] = True
    if info["unparsed_events"]:
        row["unparsed_events"] = info["unparsed_events"]
    for key in ("waits_for", "predecessor_state", "codex_started_at", "group", "sandbox_changed_from", "error"):
        if meta.get(key):
            row[key] = meta[key]
    if meta.get("worktree"):
        row["worktree"] = meta["worktree"]["path"]
    if stderr_tail:
        row["stderr_tail"] = stderr_tail
    return row


def group_snapshot(rows, unstarted=0):
    """`(running, done, failed, group_state)` — the one place group state is derived, so every group view agrees.

    `partial` means "not every member succeeded" (a stop, a timeout and a failure alike); members that never started count against `completed`.
    """
    running = [r["run_id"] for r in rows if row_is_live(r)]
    done = [r["run_id"] for r in rows if r["state"] == "completed"]
    failed = [r["run_id"] for r in rows if r["state"] in FAILED_STATES and not row_is_live(r)]
    if running:
        state = "running"
    elif failed or unstarted or not rows:
        state = "partial"
    else:
        state = "completed"
    return running, done, failed, state
