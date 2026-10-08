"""Reading what a run's Codex wrote: the `codex exec --json` event stream, rendered as `log` prints it and summarised, and its stderr. Every reader here hands back the skill's terms, so nothing outside this unit parses an event or a line Codex prints.

`file_change` events carry paths and a kind, never file contents. The context risk is one field, `command_execution.aggregated_output`, which holds a command's whole stdout. That is why a command is shown by its exit code and size, and why only a failed one's output is excerpted: there the output is what the caller needs, and elsewhere the agent's own messages, never cut, usually say what it showed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from codex.util import clip, nfc

# Head and tail kept of a failed command's output — a stack trace's top frames and its final error line.
FAIL_HEAD_BYTES = 1200
FAIL_TAIL_BYTES = 1200

# Every command line is echoed, and a heredoc can be thousands of characters.
CMD_MAX_CHARS = 300


# -- reading ----------------------------------------------------------------

def read_events(path: Path):
    """Read the complete JSONL lines; returns `(events, bytes read)`.

    Only whole lines are read, because the file is appended to live: a line still being written is not an event yet. A line that will not parse comes back as `{"type": "_unparsed", "raw": ...}` rather than being dropped.
    """
    if not path.exists():
        return [], 0
    blob = path.read_bytes()
    cut = blob.rfind(b"\n")
    if cut == -1:
        return [], 0
    complete, cursor = blob[: cut + 1], cut + 1
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

# Codex quotes the command unless it is one bare word.
_WRAP = re.compile(r"""^/bin/(?:ba|z|)sh\s+-l?c\s+(?:(?P<q>['"])(?P<body>.*)(?P=q)|(?P<bare>[^\s'"]+))\s*$""", re.S)


def strip_wrapper(cmd: str) -> str:
    """Drop the `/bin/zsh -lc "..."` wrapper Codex puts around every command; it is identical on every line."""
    if not cmd:
        return ""
    m = _WRAP.match(cmd.strip())
    return (m.group("body") if m.group("q") else m.group("bare")) if m else cmd


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

def event_lines(path: Path, rel_to: Path = None):
    """A run's events as `log` prints them, paths shown relative to `rel_to`. A line can hold newlines of its own (an output excerpt under it)."""
    events, _read = read_events(path)
    # A command that finished is shown by its result alone; one still running by its start, so a long build is not silence.
    finished = {(ev.get("item") or {}).get("id") for ev in events if ev.get("type") == "item.completed"}
    out = []
    for ev in events:
        t = ev.get("type")
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
            out.extend(_format_item(t, ev.get("item") or {}, finished, rel_to))
        elif t == "_unparsed":
            out.append("unparsed " + clip(ev.get("raw", ""), 200))
        else:
            rest = {k: v for k, v in ev.items() if k != "type"}
            out.append(f"{t} " + clip(json.dumps(rest, ensure_ascii=False), 200))
    return out


def _format_item(evtype: str, item: dict, finished, project):
    itype = item.get("type")
    lines = []

    if itype == "command_execution":
        cmd = clip(strip_wrapper(item.get("command") or ""), CMD_MAX_CHARS)
        if evtype == "item.started":
            return [] if item.get("id") in finished else [f"cmd.running {cmd}"]
        output = item.get("aggregated_output") or ""
        nbytes = len(output.encode("utf-8", "replace"))
        exit_code = item.get("exit_code")
        lines.append(f"cmd exit={exit_code} out={nbytes}B {cmd}")
        if exit_code not in (0, None) and output:
            lines.append(_indent(head_tail(output, FAIL_HEAD_BYTES, FAIL_TAIL_BYTES)))
        return lines

    if evtype == "item.started":
        return []

    if itype == "agent_message":
        # Never cut: this is the answer the run was for.
        lines.append("msg " + (item.get("text") or "").strip())
    elif itype in ("reasoning", "todo_list"):
        pass
    elif itype == "file_change":
        changes = item.get("changes") or []
        for ch in changes:
            p = ch.get("path") or ""
            lines.append(f"file {ch.get('kind')} {relativize(p, project) if project else p}")
        if not changes:
            lines.append("file (no changes listed)")
    elif itype == "error":
        lines.append("error " + clip(item.get("message") or "", 400))
    elif itype == "web_search":
        lines.append("search " + clip(item.get("query") or "", 200))
    elif itype == "mcp_tool_call":
        lines.append(f"mcp {item.get('server')}/{item.get('tool')} status={item.get('status')}")
    else:
        lines.append(f"{itype} " + clip(json.dumps(item, ensure_ascii=False), 300))
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
    events, cursor = read_events(events_path)
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


def changed_paths(events_path: Path):
    """The paths a run's file changes name, as Codex recorded them — absolute in practice — in NFC."""
    paths = set()
    for ev in read_events(events_path)[0]:
        item = ev.get("item") or {}
        if item.get("type") != "file_change":
            continue
        for ch in item.get("changes") or []:
            p = ch.get("path") if isinstance(ch, dict) else ch
            if p:
                paths.add(str(Path(nfc(str(p)))))
    return paths


# -- stderr -------------------------------------------------------------------

# Codex always prints this when stdin is not a TTY; it is not a failure.
STDIN_NOTICE = "Reading additional input from stdin"


def stderr_tail(path: Path, limit: int = 800):
    """The last `limit` characters of a run's stderr without blank lines or the notice Codex always prints, or None when nothing is left."""
    if not path.exists() or not path.stat().st_size:
        return None
    txt = path.read_text(encoding="utf-8", errors="replace")
    txt = "\n".join(ln for ln in txt.splitlines() if ln.strip() and STDIN_NOTICE not in ln)
    return txt[-limit:] or None
