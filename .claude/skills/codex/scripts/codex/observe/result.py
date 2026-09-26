"""`result`: what a run or a group concluded."""

from __future__ import annotations

import json

from codex.errors import Refusal
from codex.git.repo import resolve_project
from codex.observe.collect import changed_paths, member_result, overlaps
from codex.observe.rows import group_snapshot, progress, turn_failed_excerpt
from codex.registry.groups import resolve_group, unstarted_members, vanished_members
from codex.registry.runs import TERMINAL_STATES, find_run, reap, refuse_unresolved_run, resolve_runs_dir, still_writing


def result(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        return result_group(args, project, runs_dir)
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
            raise Refusal("the --schema run has no final message", run_id=meta["run_id"], state=meta.get("state"))
        try:
            out["json"] = json.loads(message)
        except json.JSONDecodeError as e:
            # Loud rather than lenient: a malformed object handed back as if it had the schema's shape is worse.
            raise Refusal("the final message of a --schema run is not valid JSON",
                          run_id=meta["run_id"], parse_error=str(e), message=message)
        # The parsed object is the answer; the same text again as `message` would double it.
        del out["message"]
    return out


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
    return {"group": args.group, "project": str(project), "results": results,
            "overlaps": found, "totals": totals, "group_state": gstate,
            "done": done, "failed": failed, "running": running, "unstarted": never,
            "overlaps_note": ("paths written by more than one member. Under worktree "
                              "isolation this is a merge conflict ahead, not damage "
                              "already done.") if found else None}
