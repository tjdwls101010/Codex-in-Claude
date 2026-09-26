"""`show`: one run-scoped item in full — a command's output, capped and with the truncation stated, or a file change's paths."""

from __future__ import annotations

from codex.codex_cli.events import find_item, strip_wrapper
from codex.errors import Refusal
from codex.git.repo import resolve_project
from codex.registry.runs import find_run, refuse_unresolved_run, resolve_runs_dir

# `show --item` cap; truncation is always announced with how much was withheld.
SHOW_MAX_BYTES = 20000


def show(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rd, meta = find_run(runs_dir, args.run)
    refuse_unresolved_run(args.run, rd, meta, runs_dir)
    found, events = find_item(rd / "events.jsonl", args.item)
    if not found:
        ids = [f"{(e.get('item') or {}).get('id')}:{(e.get('item') or {}).get('type')}"
               for e in events if e.get("type") == "item.completed"]
        raise Refusal(f"no item {args.item!r} in run {meta['run_id']}", available=ids[:60])
    out = {"run_id": meta["run_id"], "item_id": args.item, "item_type": found.get("type")}
    if found.get("type") == "command_execution":
        text = found.get("aggregated_output") or ""
        raw = text.encode("utf-8", "replace")
        out.update(command=strip_wrapper(found.get("command") or ""), exit_code=found.get("exit_code"),
                   total_bytes=len(raw), truncated=len(raw) > args.max_bytes)
        if out["truncated"]:
            out["shown_bytes"] = args.max_bytes
            out["output"] = raw[: args.max_bytes].decode("utf-8", "replace")
            out["truncation_notice"] = (f"{len(raw) - args.max_bytes} of {len(raw)} bytes withheld; "
                                        f"raise --max-bytes to see more")
        else:
            out["output"] = text
    elif found.get("type") == "file_change":
        out["changes"] = found.get("changes") or []
    else:
        out["item"] = found
    return out
