"""`result`: what a run or a group concluded. The answer is read, not parsed, so it comes as text after a JSON header whose byte counts say where each answer ends; a --schema run's answer is parsed, so it stays JSON."""

from __future__ import annotations

import json

from codex.errors import Refusal
from codex.git.repo import resolve_project
from codex.observe.collect import changed_paths, final_message, member_result, overlaps
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
    message = final_message(rd, info)
    out = {"run_id": meta["run_id"], "state": meta.get("state"), "exit_code": meta.get("exit_code"),
           "thread_id": meta.get("thread_id") or info["thread_id"]}
    if meta.get("state") not in TERMINAL_STATES:
        out["note"] = f"run is still {meta.get('state')}; this is a partial result"
    elif still_writing(meta):
        # The same call later would return a different message, so this one is not final.
        out["note"] = "codex is still writing although the run is orphaned; this is a partial result"
    turn_failed = turn_failed_excerpt(info)
    if turn_failed:
        out["turn_failed"] = turn_failed
    out.update(files_changed=info["files_changed"], commands=info["commands"], usage=info["usage"])
    if info["unparsed_events"]:
        out["unparsed_events"] = info["unparsed_events"]
    if meta.get("schema_path"):
        # The caller parses this answer, so it stays one JSON document: the object itself, never the text again beside it.
        out["schema_path"] = meta["schema_path"]
        if not message:
            raise Refusal("the --schema run has no final message", run_id=meta["run_id"], state=meta.get("state"))
        try:
            out["json"] = json.loads(message)
        except json.JSONDecodeError as e:
            # Loud rather than lenient: a malformed object handed back as if it had the schema's shape is worse.
            raise Refusal("the final message of a --schema run is not valid JSON",
                          run_id=meta["run_id"], parse_error=str(e), message=message)
        return out
    # The caller reads this answer rather than parsing it, so it follows the header as written, its extent given in bytes.
    out["message_bytes"] = len(message.encode("utf-8"))
    return [json.dumps(out, ensure_ascii=False) + "\n"] + ([message + "\n"] if message else [])


def result_group(args, project, runs_dir):
    members, shown, per_run_paths, totals = [], [], {}, {"input_tokens": 0, "output_tokens": 0}
    for index, (rd, meta) in enumerate(resolve_group(runs_dir, args.group)):
        meta = reap(rd, meta)
        row, info, text = member_result(rd, meta)
        members.append({"index": index, **row})
        shown.append(text)
        per_run_paths[meta["run_id"]] = changed_paths(
            rd / "events.jsonl", (meta.get("worktree") or {}).get("path") or meta.get("cwd"))
        for key in totals:
            totals[key] += int((info["usage"] or {}).get(key) or 0)
    found = overlaps(per_run_paths)
    never = unstarted_members(runs_dir, args.group) + vanished_members(runs_dir, args.group)
    running, done, failed, gstate = group_snapshot(members, len(never))
    header = {"group": args.group, "group_state": gstate, "done": done, "failed": failed, "running": running,
              "unstarted": never, "overlaps": found,
              "overlaps_note": ("paths written by more than one member. Under worktree "
                                "isolation this is a merge conflict ahead, not damage "
                                "already done.") if found else None,
              "totals": totals, "members": members, "project": str(project)}
    pieces = [json.dumps(header, ensure_ascii=False) + "\n"]
    for member, text in zip(members, shown):
        # Flattened: a label is caller text, and one holding a newline could forge a separator line.
        label = " ".join(member["label"].split()) if member.get("label") else None
        size = (f"{member['shown_bytes']}/{member['message_bytes']}" if member["message_truncated"]
                else str(member["message_bytes"]))
        pieces.append(f"--- [{member['index']}" + (f":{label}" if label else "") + f"] run={member['run_id']} "
                      f"state={member['state']} bytes={size}\n")
        if text:
            pieces.append(text + "\n")
    return pieces
