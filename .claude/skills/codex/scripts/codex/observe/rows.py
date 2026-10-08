"""Describing runs and groups: the status row and its summary, the turn-failure excerpt, whether a row or a group is still live, and a note for runs no listing can show."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from codex.codex_cli import scan_progress, stderr_tail as read_stderr_tail
from codex.registry import TERMINAL_STATES, is_live, read_meta, reap, still_writing, unreadable_runs
from codex.util import clip

# Advisory: a run idle this long is shown `stalled`, never killed for it. One long command is legitimately silent, which is why `in_progress_item` is reported beside it.
STALL_SECONDS = 300

FAILED_STATES = ("failed", "interrupted", "orphaned", "timed_out")


def row_is_live(row: dict) -> bool:
    """`is_live` for a row: its state is not terminal, or its Codex still writes."""
    return row["state"] not in TERMINAL_STATES or bool(row.get("codex_still_running"))


def turn_failed_excerpt(info):
    return clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400) if info["turn_failed"] else None


def settled(run_dir: Path, meta: dict, read):
    """`(meta, read(meta))` that agree with each other. The run's state is read before and after its events, and the events again if the state moved meanwhile: a run records its end only once Codex has stopped writing, so the second read is final. Either single order can contradict itself — the earlier state beside events that already show the end, or the later state beside events read before the last line landed."""
    meta = reap(run_dir, meta)
    data = read(meta)
    again = read_meta(run_dir)
    if again:
        again = reap(run_dir, again)
        if again.get("state") != meta.get("state"):
            return again, read(again)
    return meta, data


def progress(run_dir: Path, meta: dict):
    """The event-stream summary for a reaped run. A trailing fragment counts as unparsed only once nothing will write again."""
    return scan_progress(run_dir / "events.jsonl", terminal=not is_live(meta))


def run_row(run_dir: Path, meta: dict, project: Path, excerpt: int = 400):
    """The row `status` prints for one run, reaped first so a dead supervisor is never reported live."""
    meta, info = settled(run_dir, meta, lambda m: progress(run_dir, m))
    events_path = run_dir / "events.jsonl"
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

    stderr_tail = read_stderr_tail(run_dir / "stderr.log")

    # Optional fields appear only when they say something, so a present field is worth reading.
    extra = {key: meta[key] for key in ("error", "group", "sandbox_changed_from", "codex_started_at",
                                        "waits_for", "predecessor_state") if meta.get(key)}
    if meta.get("worktree"):
        extra["worktree"] = meta["worktree"]["path"]
    if stderr_tail:
        extra["stderr_tail"] = stderr_tail
    if still_writing(meta):
        extra["codex_still_running"] = True
    if info["unparsed_events"]:
        extra["unparsed_events"] = info["unparsed_events"]

    def some(*keys):
        return {k: extra[k] for k in keys if k in extra}

    # Where the run stands and what it last said first, then its settings, then paths and process ids.
    return {
        "run_id": meta.get("run_id"), "label": meta.get("label"), "state": state, "exit_code": meta.get("exit_code"),
        **some("error"), "turn_failed": turn_failed_excerpt(info),
        "elapsed_seconds": elapsed, "codex_elapsed_seconds": codex_elapsed, "idle_seconds": idle,
        "turns_completed": info["turns_completed"], "commands": info["commands"],
        "files_changed": info["files_changed"], "in_progress_item": info["in_progress_item"],
        "last_agent_message": clip(info["last_agent_message"] or "", excerpt) or None,
        **some("stderr_tail", "codex_still_running", "unparsed_events"),
        "config_error_events": info["errors"], "usage": info["usage"],
        "thread_id": meta.get("thread_id") or info["thread_id"],
        "parent_run_id": meta.get("parent_run_id"), "kind": meta.get("kind"), **some("group"),
        "sandbox": meta.get("sandbox"), **some("sandbox_changed_from"),
        "model": meta.get("model"), "effort": meta.get("effort"), "isolated": meta.get("isolated"),
        "service_tier": meta.get("service_tier"), "cwd": meta.get("cwd"), **some("worktree"),
        "started_at": meta.get("started_at"), **some("codex_started_at"), "ended_at": meta.get("ended_at"),
        "codex_pid": meta.get("codex_pid"), "pgid": meta.get("pgid"), "events": str(events_path),
        **some("waits_for", "predecessor_state"),
    }


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


def summary_row(row):
    """What the default listing shows of a run, from a row built with a 160-character excerpt. `--run` and `--group` return the whole row."""
    out = {k: row.get(k) for k in ("run_id", "label", "state", "group", "idle_seconds")}
    out["last_agent_message"] = row.get("last_agent_message")
    if row.get("codex_still_running"):
        out["codex_still_running"] = True
    return out


def note_unreadable(out: dict, runs_dir):
    """Name runs whose meta.json will not parse, so a listing they are missing from does not look complete."""
    bad = unreadable_runs(runs_dir)
    if bad:
        out["runs_unreadable"] = len(bad)
        out["unreadable"] = bad
    return out
