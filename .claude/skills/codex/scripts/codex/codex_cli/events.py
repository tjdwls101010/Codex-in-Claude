"""Reading and filtering the `codex exec --json` event stream.

`file_change` events carry paths and a kind, never file contents. The context risk is one field, `command_execution.aggregated_output`, which holds a command's whole stdout. That is why the levels split where they do, and why `normal` splits on exit code rather than size: a failed command's output is the case where the output is what the caller needs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from codex.util import clip, nfc

LEVELS = ("compact", "normal", "full", "raw")

# The agent's own messages are never filtered at any level, so command output in `compact` would usually be a second copy of a summary the caller already has; each command line's size marker says when it is not.
DEFAULT_LEVEL = "compact"

# `normal`: head and tail kept of a failed command's output — a stack trace's top frames and its final error line.
FAIL_HEAD_BYTES = 1200
FAIL_TAIL_BYTES = 1200

# `full`: per-item cap.
FULL_ITEM_BYTES = 4000

# Command lines are echoed at every level and a heredoc can be thousands of characters.
CMD_MAX_CHARS = 300

# How often a follower asks whether anything changed. A tick reads forward from a byte offset, so it is cheap.
FOLLOW_INTERVAL = 1.0


class CursorOutOfRange(ValueError):
    """`--since` is not a cursor this run's file produced: past its end, or not on a line boundary. Almost always one fed back from a different run."""


# -- reading ----------------------------------------------------------------

def read_events(path: Path, since: int = 0):
    """Read complete JSONL lines from a byte offset; returns `(events, new_cursor)`.

    Only whole lines are consumed and the cursor lands after the last complete one, because the file is appended to live: nothing is duplicated or skipped across polls. A line that will not parse comes back as `{"type": "_unparsed", "raw": ...}` rather than being dropped.
    """
    if not path.exists():
        return [], since
    since = max(0, since)
    size = path.stat().st_size
    if since > size:
        raise CursorOutOfRange(f"--since {since} is past the end of this run's events file ({size} bytes); check the `run=` of the trailer it came from")
    if since == size:
        return [], since
    with path.open("rb") as fh:
        # A cursor this function produced always lands just after a newline. Reading from anywhere else would start mid-line and destroy the event that straddles it.
        if since:
            fh.seek(since - 1)
            if fh.read(1) != b"\n":
                raise CursorOutOfRange(f"--since {since} is not a line boundary of this run's events file, so it is not a cursor this run printed; check the `run=` of the trailer it came from")
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
    """`thread.started` is the first line Codex emits, and a resumed turn repeats the same id."""
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
    """Drop the `/bin/zsh -lc "..."` wrapper Codex puts around every command; it is identical on every line."""
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
    """Render events as text lines at the given level."""
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
            out.append("turn.failed " + clip(json.dumps(ev.get("error") or {}, ensure_ascii=False), 400))
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
            # Without a start line a long build and a hung run look the same to a poller.
            return [f"cmd.start[{iid}] {cmd}"]
        output = item.get("aggregated_output") or ""
        nbytes = len(output.encode("utf-8", "replace"))
        exit_code = item.get("exit_code")
        # The size is shown even when the output is withheld, so fetching it with `show` is a decision rather than a guess.
        lines.append(f"cmd[{iid}] exit={exit_code} out={nbytes}B {cmd}")
        if level == "compact" or not output:
            return lines
        if level == "normal":
            if exit_code not in (0, None):
                lines.append(_indent(head_tail(output, FAIL_HEAD_BYTES, FAIL_TAIL_BYTES)))
        elif level == "full":
            lines.append(_indent(head_tail(output, FULL_ITEM_BYTES // 2, FULL_ITEM_BYTES // 2)))
        return lines

    if evtype == "item.started":
        return []

    if itype == "agent_message":
        # Never truncated at any level: this is the answer the run was for.
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
        lines.append("error " + clip(item.get("message") or "", 400))
    elif itype == "todo_list":
        if level in ("normal", "full"):
            lines.append("todo " + clip(json.dumps(item.get("items") or [], ensure_ascii=False), 400))
    elif itype == "web_search":
        lines.append("search " + clip(item.get("query") or "", 200))
    elif itype == "mcp_tool_call":
        lines.append(f"mcp[{iid}] {item.get('server')}/{item.get('tool')} status={item.get('status')}")
    else:
        lines.append(f"{itype}[{iid}] " + clip(json.dumps(item, ensure_ascii=False), 300))
    return lines


# -- summarising ------------------------------------------------------------

def scan_progress(events_path: Path, terminal: bool = False):
    """One pass over the event stream for everything `status` and `result` report.

    `terminal` says nothing will write again, so a trailing line with no newline is a fragment to count as unparsed rather than one to wait for.
    """
    info = {"thread_id": None, "last_agent_message": None, "usage": None,
            "in_progress_item": None, "turns_completed": 0, "errors": 0,
            "files_changed": 0, "commands": 0, "turn_failed": None,
            # Lines this skill could not read, kept apart from `errors` (Codex reporting a problem with the work).
            "unparsed_events": 0}
    started, completed = {}, set()
    events, cursor = read_events(events_path, 0)
    if terminal:
        try:
            if events_path.stat().st_size > cursor:
                info["unparsed_events"] += 1
        except OSError:
            pass
    for ev in events:
        t = ev.get("type")
        if t == "_unparsed":
            info["unparsed_events"] += 1
        elif t == "thread.started":
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
    # A started item that never completed is what tells a run busy inside one long command from one that stopped.
    for iid, it in started.items():
        if iid not in completed:
            info["in_progress_item"] = {
                "id": iid, "type": it.get("type"),
                "command": clip(strip_wrapper(it.get("command") or ""), 160) or None}
    return info


def find_item(events_path: Path, item_id: str):
    """Look one item up by id. Item ids restart at `item_0` in every run, so this is only meaningful within one run."""
    found = None
    events, _ = read_events(events_path, 0)
    for ev in events:
        if ev.get("type") in ("item.started", "item.completed"):
            it = ev.get("item") or {}
            if it.get("id") == item_id:
                found = it  # completed supersedes started
    return found, events
