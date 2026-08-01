"""Reading and filtering the `codex exec --json` event stream.

This module is where the context budget is actually spent or saved, so it is
worth being precise about where the risk lives.

`file_change` events carry **paths and a kind, never file contents**. They are
cheap and always safe to show. The entire context risk is one field:
`command_execution.aggregated_output`, which holds the command's full stdout —
so a run that `cat`s a 2,000-line file puts that whole file in there, and a
build that prints 50,000 lines puts all of them there.

That asymmetry is the reason the levels split where they do, and the reason
`normal` splits on **exit code** rather than on size: a failed command's output
is precisely the case where the output is the thing the caller needs, and a
successful one is precisely the case where it is not.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from _util import clip, nfc

LEVELS = ("compact", "normal", "full", "raw")


class CursorOutOfRange(ValueError):
    """`--since` points past the end of the events file.

    F11: the old guard (`since >= size`) accepted this silently, printed
    nothing, and exited 0 — echoing the bad cursor straight back so the next
    poll stays stuck forever, indistinguishable from "no new events yet". A
    cursor this far out is almost always one fed back from a different run.
    """


# Chosen from the measured table in docs/measurements/filter-calibration.md.
# The reasoning is recorded next to that table and restated in
# references/event-stream.md; do not change this without re-running it.
DEFAULT_LEVEL = "compact"

# `normal`: bytes of head and tail kept for a FAILED command's output. Enough
# for a stack trace's top frames and its final error line, which is where the
# diagnosis nearly always is.
FAIL_HEAD_BYTES = 1200
FAIL_TAIL_BYTES = 1200

# `full`: per-item cap. Structurally complete, still bounded.
FULL_ITEM_BYTES = 4000

# Command lines are echoed at every level and a heredoc can be thousands of
# characters, so they are capped independently of any output.
CMD_MAX_CHARS = 300


# -- reading ----------------------------------------------------------------

def read_events(path: Path, since: int = 0):
    """Read complete JSONL lines from a byte offset.

    Returns `(events, new_cursor)`. Only whole lines are consumed and the cursor
    lands after the last complete one, because the file is being appended to
    live and a trailing partial line must be left for the next poll. That is
    what makes `--since` exact in both directions: nothing duplicated, nothing
    skipped, across any number of consecutive polls.
    """
    if not path.exists():
        return [], since
    since = max(0, since)
    size = path.stat().st_size
    if since > size:
        raise CursorOutOfRange(
            f"--since {since} is past the end of the events file ({size} bytes)")
    if since == size:
        return [], since
    with path.open("rb") as fh:
        fh.seek(since)
        blob = fh.read()
    cut = blob.rfind(b"\n")
    if cut == -1:
        return [], since
    complete, cursor = blob[: cut + 1], since + cut + 1
    events = []
    for line in complete.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"type": "_unparsed", "raw": line})
    return events, cursor


def first_thread_id(events_path: Path):
    """`thread.started` is the first line Codex emits, and on resume it repeats
    the *same* id — so the first line always names the thread this run is on."""
    try:
        with events_path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line).get("thread_id")
                except json.JSONDecodeError:
                    return None
    except Exception:
        pass
    return None


# -- text shaping -----------------------------------------------------------

_WRAP = re.compile(r"""^/bin/(?:ba|z|)sh\s+-l?c\s+(?P<q>['"])(?P<body>.*)(?P=q)\s*$""", re.S)


def strip_wrapper(cmd: str) -> str:
    """Codex wraps every shell command as `/bin/zsh -lc "..."`. The wrapper is
    byte-identical on every line and carries no information, so in a log whose
    whole job is to be small it is pure noise."""
    if not cmd:
        return ""
    m = _WRAP.match(cmd.strip())
    return m.group("body") if m else cmd


def head_tail(s: str, head: int, tail: int) -> str:
    b = s.encode("utf-8", "replace")
    if len(b) <= head + tail:
        return s
    dropped = len(b) - head - tail
    return (b[:head].decode("utf-8", "replace")
            + f"\n… [{dropped} bytes omitted] …\n"
            + b[-tail:].decode("utf-8", "replace"))


def relativize(p: str, project: Path) -> str:
    try:
        return str(Path(nfc(p)).relative_to(Path(nfc(str(project)))))
    except Exception:
        return nfc(p)


def _indent(text: str, prefix: str = "    | ") -> str:
    return "\n".join(prefix + ln for ln in text.splitlines())


# -- filtering --------------------------------------------------------------

def format_events(events, level: str, project: Path = None):
    """Render a batch of events as compact text lines at the given level."""
    out = []
    for ev in events:
        t = ev.get("type")

        if level == "raw":
            out.append(json.dumps(ev, ensure_ascii=False))
            continue

        if t == "thread.started":
            out.append(f"thread {ev.get('thread_id')}")
        elif t == "turn.started":
            out.append("turn.started")
        elif t == "turn.completed":
            u = ev.get("usage") or {}
            out.append("turn.completed in={} cached={} out={} reasoning={}".format(
                u.get("input_tokens", "?"), u.get("cached_input_tokens", "?"),
                u.get("output_tokens", "?"), u.get("reasoning_output_tokens", "?")))
        elif t == "turn.failed":
            out.append("turn.failed " + clip(json.dumps(ev.get("error") or {},
                                                        ensure_ascii=False), 400))
        elif t in ("item.started", "item.completed"):
            out.extend(_format_item(t, ev.get("item") or {}, level, project))
        elif t == "_unparsed":
            out.append("unparsed " + clip(ev.get("raw", ""), 200))
        else:
            rest = {k: v for k, v in ev.items() if k != "type"}
            out.append(f"{t} " + clip(json.dumps(rest, ensure_ascii=False), 200))
    return out


def _format_item(evtype: str, item: dict, level: str, project):
    iid = item.get("id", "?")
    itype = item.get("type")
    lines = []

    if itype == "command_execution":
        cmd = clip(strip_wrapper(item.get("command") or ""), CMD_MAX_CHARS)
        if evtype == "item.started":
            # Liveness matters: without a start line, a three-minute build and a
            # hung run produce identical output when polled with --since.
            return [f"cmd.start[{iid}] {cmd}"]
        output = item.get("aggregated_output") or ""
        nbytes = len(output.encode("utf-8", "replace"))
        exit_code = item.get("exit_code")
        # The byte count is shown even when the output is withheld: it costs one
        # integer and it is what turns `show --item` into a decision the caller
        # can make instead of a guess.
        lines.append(f"cmd[{iid}] exit={exit_code} out={nbytes}B {cmd}")
        if level == "compact" or not output:
            return lines
        if level == "normal":
            if exit_code not in (0, None):
                lines.append(_indent(head_tail(output, FAIL_HEAD_BYTES, FAIL_TAIL_BYTES)))
        elif level == "full":
            lines.append(_indent(head_tail(output, FULL_ITEM_BYTES // 2,
                                           FULL_ITEM_BYTES // 2)))
        return lines

    if evtype == "item.started":
        # Non-command items complete fast enough that a start line is pure cost.
        return []

    if itype == "agent_message":
        # Never truncated at any level: this is the answer, and it is the thing
        # the run was for.
        lines.append("msg " + (item.get("text") or "").strip())
    elif itype == "reasoning":
        if level == "full":
            lines.append("reasoning " + clip(item.get("text") or "", 2000))
    elif itype == "file_change":
        changes = item.get("changes") or []
        for ch in changes:
            p = ch.get("path") or ""
            lines.append(f"file {ch.get('kind')} {relativize(p, project) if project else p}")
        if not changes:
            lines.append(f"file[{iid}] (no changes listed)")
    elif itype == "error":
        # Informational config warnings, not fatal — but never hidden, because
        # the one time it is not a warning you need to see it.
        lines.append("error " + clip(item.get("message") or "", 400))
    elif itype == "todo_list":
        if level in ("normal", "full"):
            lines.append("todo " + clip(json.dumps(item.get("items") or [],
                                                   ensure_ascii=False), 400))
    elif itype == "web_search":
        lines.append("search " + clip(item.get("query") or "", 200))
    elif itype == "mcp_tool_call":
        lines.append(f"mcp[{iid}] {item.get('server')}/{item.get('tool')} "
                     f"status={item.get('status')}")
    else:
        lines.append(f"{itype}[{iid}] " + clip(json.dumps(item, ensure_ascii=False), 300))
    return lines


# -- summarising ------------------------------------------------------------

def scan_progress(events_path: Path):
    """One pass over the durable event log for everything `status` reports."""
    info = {"thread_id": None, "last_agent_message": None, "usage": None,
            "in_progress_item": None, "turns_completed": 0, "errors": 0,
            "files_changed": 0, "commands": 0, "turn_failed": None}
    started, completed = {}, set()
    events, _ = read_events(events_path, 0)
    for ev in events:
        t = ev.get("type")
        if t == "thread.started":
            info["thread_id"] = ev.get("thread_id")
        elif t == "turn.completed":
            info["turns_completed"] += 1
            info["usage"] = ev.get("usage")
        elif t == "turn.failed":
            info["turn_failed"] = ev.get("error")
        elif t == "item.started":
            it = ev.get("item") or {}
            started[it.get("id")] = it
        elif t == "item.completed":
            it = ev.get("item") or {}
            completed.add(it.get("id"))
            itype = it.get("type")
            if itype == "agent_message":
                info["last_agent_message"] = (it.get("text") or "").strip()
            elif itype == "error":
                info["errors"] += 1
            elif itype == "file_change":
                info["files_changed"] += len(it.get("changes") or [])
            elif itype == "command_execution":
                info["commands"] += 1
    # An item that started and never completed is what distinguishes a run that
    # is busy inside one long command from a run that has simply stopped.
    for iid, it in started.items():
        if iid not in completed:
            info["in_progress_item"] = {
                "id": iid, "type": it.get("type"),
                "command": clip(strip_wrapper(it.get("command") or ""), 160) or None}
    return info


def find_item(events_path: Path, item_id: str):
    """Look one item up by id within a run.

    `item.id` restarts at `item_0` on every invocation — it is per-invocation,
    not per-thread — so this lookup is only meaningful scoped to a single run,
    which is exactly how it is called.
    """
    found = None
    events, _ = read_events(events_path, 0)
    for ev in events:
        if ev.get("type") in ("item.started", "item.completed"):
            it = ev.get("item") or {}
            if it.get("id") == item_id:
                found = it  # last write wins, so completed supersedes started
    return found, events
