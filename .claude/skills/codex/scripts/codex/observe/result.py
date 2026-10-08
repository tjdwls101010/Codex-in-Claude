"""`result`: what a run or a group concluded, at once or — with `--wait` — once it has ended. The answer is read, not parsed, so it comes as text after a JSON header whose byte counts say where each answer ends; a --schema run's answer is parsed, so it stays one JSON document, indented to be read as printed."""

from __future__ import annotations

import json

from codex.errors import Refusal
from codex.git import resolve_project
from codex.observe.collect import final_message, member_result, overlaps, written_paths
from codex.observe.follow import GroupWatch, wait_until
from codex.observe.rows import group_snapshot, progress, turn_failed_excerpt
from codex.registry import TERMINAL_STATES, group_view, is_live, read_meta, reap, resolve_runs_dir, run, still_writing


def result(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        if args.wait:
            # Ended once no readable member is live. A slot that never started and a member that will not parse are not waited for, which could be forever; `unstarted` names them.
            watch = GroupWatch(runs_dir, args.group, project)
            wait_until(lambda: not group_snapshot(watch.now()[0])[0], args.wait_timeout)
            # Collected from the watch too: the name may have been released, or taken by another batch, while it waited.
            return result_group(args, project, *watch.view())
        members, gaps, _epoch = group_view(runs_dir, args.group)
        return result_group(args, project, members, gaps)
    rd, meta = run(runs_dir, args.run)
    if args.wait:
        # The run found now is the one waited for, even if a later turn on its thread starts meanwhile. One whose meta.json stops parsing ends the wait, since its state can no longer be read, and is refused below as it would have been at the start.
        def ended():
            now = read_meta(rd)
            return not now or not is_live(reap(rd, now))
        wait_until(ended, args.wait_timeout)
        rd, meta = run(runs_dir, rd.name)
    meta = reap(rd, meta)
    info = progress(rd, meta)
    # A live run has no final answer yet: what it has said so far is not the object its schema shapes.
    answer_due = meta.get("schema_path") and not is_live(meta)
    try:
        # A --schema answer is parsed, and a replaced byte would parse into a different object than the one written.
        message = final_message(rd, info, errors="strict" if answer_due else "replace")
    except UnicodeDecodeError as e:
        raise Refusal("the final message of a --schema run is not valid UTF-8", run_id=meta["run_id"], parse_error=str(e))
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
        # The answer stays one JSON document: the object itself, never the text again beside it, and `json` null until there is one.
        out["schema_path"] = meta["schema_path"]
        if not answer_due:
            out["json"] = None
            return [json.dumps(out, ensure_ascii=False, indent=2) + "\n"]
        if not message:
            raise Refusal("the --schema run has no final message", run_id=meta["run_id"], state=meta.get("state"))
        try:
            out["json"] = json.loads(message)
        except json.JSONDecodeError as e:
            # Loud rather than lenient: a malformed object handed back as if it had the schema's shape is worse.
            raise Refusal("the final message of a --schema run is not valid JSON",
                          run_id=meta["run_id"], parse_error=str(e), message=message)
        return [json.dumps(out, ensure_ascii=False, indent=2) + "\n"]
    # The caller reads this answer rather than parsing it, so it follows the header as written, its extent given in bytes.
    out["message_bytes"] = len(message.encode("utf-8"))
    return [json.dumps(out, ensure_ascii=False) + "\n"] + ([message + "\n"] if message else [])


def result_group(args, project, found_members, never):
    """A group's result from its members, `(run_dir, meta)` in start order, and its gaps."""
    members, shown, per_run_paths, totals = [], [], {}, {"input_tokens": 0, "output_tokens": 0}
    for index, (rd, meta) in enumerate(found_members):
        meta = reap(rd, meta)
        row, info, text = member_result(rd, meta)
        members.append({"index": index, **row})
        shown.append(text)
        per_run_paths[meta["run_id"]] = written_paths(
            rd / "events.jsonl", (meta.get("worktree") or {}).get("path") or meta.get("cwd"))
        for key in totals:
            totals[key] += int((info["usage"] or {}).get(key) or 0)
    found = overlaps(per_run_paths)
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
