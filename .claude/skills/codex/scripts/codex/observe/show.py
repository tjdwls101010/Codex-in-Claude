"""`show`: one run-scoped item in full — a command's output, capped and with the truncation stated, or a file change's paths."""

from __future__ import annotations

from codex.codex_cli import find_item
from codex.errors import Refusal
from codex.git import resolve_project
from codex.registry import resolve_runs_dir, run

# `show --item` cap; truncation is always announced with how much was withheld.
SHOW_MAX_BYTES = 20000


def show(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rd, meta = run(runs_dir, args.run)
    found, available = find_item(rd / "events.jsonl", args.item)
    if not found:
        raise Refusal(f"no item {args.item!r} in run {meta['run_id']}", available=available[:60])
    out = {"run_id": meta["run_id"], "item_id": args.item, "item_type": found["type"]}
    if found["kind"] == "command":
        text = found["output"]
        raw = text.encode("utf-8", "replace")
        out.update(command=found["command"], exit_code=found["exit_code"],
                   total_bytes=len(raw), truncated=len(raw) > args.max_bytes)
        if out["truncated"]:
            out["shown_bytes"] = args.max_bytes
            out["truncation_notice"] = (f"{len(raw) - args.max_bytes} of {len(raw)} bytes withheld; "
                                        f"raise --max-bytes to see more")
            out["output"] = raw[: args.max_bytes].decode("utf-8", "replace")
        else:
            out["output"] = text
    elif found["kind"] == "file_change":
        out["changes"] = found["changes"]
    else:
        out["item"] = found["item"]
    return out
