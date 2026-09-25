#!/usr/bin/env python3
"""Drive the OpenAI Codex CLI as a managed subagent.

Python 3.10+, standard library only. Every subcommand prints exactly one line of
JSON on stdout, except the two that stream: `log`, which prints compact text
plus a trailing `# cursor=<n>` line — JSON framing per event would itself be a
meaningful fraction of the context the filter exists to save — and
`status --group --follow`, which prints one line per member state change and
then a terminal `group.<state>` line.

This file is the entrypoint and holds the CLI surface and the subcommand
handlers. The machinery lives in siblings, which Python resolves via the
script's own directory (`sys.path[0]`), so it works from any cwd and under both
the plugin and symlink installs:

    _util.py       time/text/path primitives, JSON output, pid liveness
    _registry.py   <project>/.codex-runs — locating, reading and reaping runs
    _events.py     reading the event stream, the filter levels, summarising
    _codex.py      argv composition, the two invariants, spawning, thread DB
    _worktree.py   cutting a git worktree per writing batch member, and removing it
    _run.py        building a run (`create_run`) and describing one (`run_row`)
    _batch.py      groups: the manifest, the batch subcommands, the group views

Start here for "what can it do"; go to `_codex.py` for "what exactly does it run"
and `_events.py` for "what reaches my context".
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _codex import THREAD_ID_WAIT, supervise  # noqa: E402
from codex.argv import SANDBOX_MODES  # noqa: E402
from codex.catalog import codex_version, model_catalog  # noqa: E402
from codex.config import codex_home, config_scalars, user_defaults  # noqa: E402
from codex.events import (  # noqa: E402
    CursorOutOfRange, DEFAULT_LEVEL, FAIL_HEAD_BYTES, FAIL_TAIL_BYTES,
    FOLLOW_INTERVAL, FULL_ITEM_BYTES, LEVELS, find_item, format_events,
    read_events, scan_progress, strip_wrapper,
)
from _batch import (  # noqa: E402
    TASK_FIELDS, cmd_batch_clean, cmd_batch_start, cmd_result_group, follow_group,
    follow_group_log, group_snapshot, heartbeat_due, list_groups, resolve_group,
    unstarted_members, vanished_members,
)
from worktree import registered as worktrees_registered  # noqa: E402
from _registry import (  # noqa: E402
    ACTIVE_STATES, TERMINAL_STATES, find_run, iter_runs, meta_unreadable,
    read_meta, reap, resolve_project, resolve_runs_dir, still_writing,
    unreadable_runs, update_meta_if,
)
from _run import (  # noqa: E402
    STALL_SECONDS, WRITING_SANDBOXES, create_run, resolve_implicit_run, run_row,
)
from util import (  # noqa: E402
    clip, emit, fail, git_toplevel, is_within, now_iso, pid_alive,
)

# `show --item` default cap. A silently truncated blob is worse than a loud one,
# so truncation is always announced along with how much was withheld.
SHOW_MAX_BYTES = 20000


# --------------------------------------------------------------------------
# start / resume — both build a run the same way, in `_run.py`
# --------------------------------------------------------------------------

def cmd_start(args):
    emit(create_run(args, kind="start"))


def cmd_resume(args):
    # `resume` mirrors `codex exec resume [SESSION_ID] [PROMPT]`, which is two
    # optional positionals — argparse cannot tell which one a lone argument is,
    # and would bind `resume --last "do the thing"` to the session id, silently
    # losing the prompt. Disambiguate here instead: with --last there is no ref
    # to give, so everything positional is the prompt.
    rest = list(args.rest)
    if args.last:
        args.ref = None
    else:
        args.ref = rest.pop(0) if rest else None
    if len(rest) > 1:
        fail("too many positional arguments for resume",
             expected="resume <ref> <prompt>  |  resume --last <prompt>",
             got=list(args.rest))
    args.prompt = rest[0] if rest else None

    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)

    base, thread_ref, resolved_from = None, None, None
    if args.last:
        # F4: this used to be `runs[-1]` with no filter on cwd, label or kind —
        # a read-only caller could inherit another run's label AND its
        # danger-full-access sandbox. resolve_implicit_run enforces D27: exactly
        # one non-terminal run is unambiguous, zero falls back to the newest and
        # says so, two or more fails loud with the candidate list.
        candidates = [(rd, m) for rd, m in iter_runs(runs_dir) if m.get("thread_id")]
        if not candidates:
            fail("--last found no run with a thread in this project's registry; "
                 "name the thread to resume", runs_dir=str(runs_dir))
        _, base, resolved_from = resolve_implicit_run(candidates)
        thread_ref = base["thread_id"]
    else:
        if not args.ref:
            fail("resume needs a run id, thread id, thread name, or --last")
        _, base = find_run(runs_dir, args.ref)
        if base and not base.get("thread_id"):
            # The pass-through below exists for refs this registry has never
            # seen. This one it has, and it has no thread: the run's Codex
            # process died before emitting `thread.started`. Handing the run id
            # to Codex as if it were a thread name only moves the failure
            # somewhere the caller cannot read it.
            fail("nothing to resume: that run never recorded a thread id, so "
                 "there is no conversation to continue",
                 run_id=base.get("run_id"), state=base.get("state"))
        # An unknown ref is not an error: `codex exec resume` also accepts a
        # thread name, so pass it through.
        thread_ref = (base or {}).get("thread_id") or args.ref

    # A resumed run is a NEW run pointing at the SAME thread, so each turn gets
    # its own event log while the thread stays linked.
    out = create_run(args, kind="resume", base=dict(base) if base else None,
                     thread_ref=thread_ref)
    if args.last:
        # The escalation F4 reproduced was invisible precisely because nothing
        # was echoed — say which run (and its label/sandbox) this run inherited.
        out["resolved_from_run_id"] = base.get("run_id") if base else None
        out["resolved_from"] = resolved_from
        out["label"] = base.get("label") if base else None
    emit(out)


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

def refuse_competing_selectors(args, command, *selectors):
    """Two selectors name different things; passing both silently drops one of
    them, and which one depends on which branch happens to come first.

    `status` learned this and was fixed; `stop` and `result` were not, and they
    had drifted in opposite directions — `stop` honoured `--run` and left the
    group's other members running, `result` honoured `--group` and answered a
    different question in a different shape. A caller with a stray `--run` in a
    copy-pasted `stop --group` line got a success reply while the group carried
    on. Three commands, one rule, one place (R28).

    R28 fixed the pair it was written for and left `--all` sitting next to it,
    so `stop --run X --all` still stopped one run and reported success. Which
    flags compete is per command and cannot be inferred here: `stop --all` is a
    third selector, while `status --all` only lifts a row-count cap and is
    meaningful alongside `--run`. Each caller states its own set."""
    given = {name: getattr(args, name.lstrip("-").replace("-", "_"), None)
             for name in selectors}
    given = {k: v for k, v in given.items() if v}
    if len(given) > 1:
        names = " and ".join(sorted(given))
        fail(f"{names} are different questions; pass one. "
             f"`{command}` acts on whichever it sees first, which is not "
             f"necessarily the one you meant.", **{
                 k.lstrip("-").replace("-", "_"): v for k, v in given.items()})


def refuse_unresolved_run(ref, run_dir, meta, runs_dir):
    """"I cannot read that run" and "there is no such run" are different answers
    and were sent through the same door.

    `find_run` hands back `(run_dir, None)` when the directory is there and its
    meta.json will not parse. Five commands tested only the meta and told the
    caller the run never existed, while its directory — and its events.jsonl,
    which is a separate file and usually intact — sat on disk. That is R23's
    failure at a different guard: a caller sent away from work that is still
    there, with nothing to say where to look."""
    if meta:
        return
    if run_dir is not None and meta_unreadable(run_dir):
        fail(f"run {ref} exists but its meta.json will not parse, so nothing "
             f"can be said about its state. Its event stream is a separate "
             f"file and may still be readable.",
             run_id=run_dir.name, run_dir=str(run_dir),
             events=str(run_dir / "events.jsonl"))
    fail(f"no such run: {ref}", runs_dir=str(runs_dir))


def note_unreadable(out: dict, runs_dir):
    """A run whose meta.json will not parse is skipped by `iter_runs`, which is
    what keeps one broken run from breaking every view. Saying nothing about it
    would make the list it is missing from look complete.

    Every listing branch has to say it, not only the default one: `--group` is
    the view a caller polls, and it emits and exits on its own path."""
    bad = unreadable_runs(runs_dir)
    if bad:
        out["runs_unreadable"] = len(bad)
        out["unreadable"] = bad
    return out


def summary_row(row):
    """What the default listing shows of a run, from a row built with a 160-character excerpt. `--run`, `--thread` and `--group` return the whole row."""
    out = {k: row.get(k) for k in ("run_id", "label", "state", "group", "idle_seconds")}
    out["last_agent_message"] = row.get("last_agent_message")
    if row.get("codex_still_running"):
        out["codex_still_running"] = True
    return out


def cmd_status(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    # `--run` and `--group` are two different questions and the branches below
    # answer whichever comes first, so passing both silently drops one of them
    # — including the case where the dropped one is the `--group` that would
    # have made `--follow` mean something. Found by a Codex run reading the
    # commit that added the check below, which is the kind of hole a fix leaves
    # when it guards a symptom instead of the precedence underneath it.
    # `--thread` joined the pair R28 covered without joining the check: the
    # branch order below answers `--run` and drops it, so a caller who named
    # both got one run's row where they asked for a thread's.
    refuse_competing_selectors(args, "status", "--run", "--thread", "--group")
    # `--follow` only ever meant "--group --follow": the other branches emit a
    # snapshot and exit. Accepting it silently is the shape of mistake R13 was
    # about — the tool hands back an answer the caller reads as "I waited for
    # this", and everything they conclude from that instant's state is then
    # correctly reasoned from a false premise.
    if args.follow and not args.group:
        fail("--follow needs --group; a group is what has an end to wait for. "
             "To watch one run, use `log --run <id> --follow`, which streams its "
             "events and ends on the run's terminal line.",
             run=args.run)
    # Same failure one step further out: `--follow-timeout` only shapes a
    # follow, so passing it without `--follow` is an instruction that quietly
    # does nothing.
    if args.follow_timeout is not None and not args.follow:
        fail("--follow-timeout only shapes a --follow, and there is no --follow "
             "here, so nothing would use it.",
             follow=args.follow, group=args.group)
    refuse_unusable_heartbeat(args)
    rows = []
    if args.run:
        rd, m = find_run(runs_dir, args.run)
        refuse_unresolved_run(args.run, rd, m, runs_dir)
        rows.append(run_row(rd, m, project))
    elif args.group:
        if args.follow:
            return follow_group(args, project, runs_dir)
        for rd, m in resolve_group(runs_dir, args.group):
            rows.append(run_row(rd, m, project))
        never = (unstarted_members(runs_dir, args.group)
                 + vanished_members(runs_dir, args.group))
        running, done, failed, gstate = group_snapshot(rows, len(never))
        out = {"project": str(project), "group": args.group, "runs": rows,
               "running": running, "done": done, "failed": failed,
               "total_runs": len(rows), "runs_truncated": 0,
               "group_state": gstate}
        if never:
            out["unstarted"] = never
        note_unreadable(out, runs_dir)
        emit(out)
    else:
        for rd, m in iter_runs(runs_dir):
            if args.thread and m.get("thread_id") != args.thread:
                continue
            rows.append(run_row(rd, m, project, excerpt=400 if args.thread else 160))

    # F3: derive every summary from the FULL list before truncating for
    # display. A phase gate is literally `len(running) == 0` — deriving it
    # from an already-truncated `rows` let live runs older than the newest 20
    # fall off the page, so the gate passed while they were still writing.
    total_runs = len(rows)
    by_thread = {}
    for r in rows:
        by_thread.setdefault(r["thread_id"] or "(unknown)", []).append(r["run_id"])
    running = [r["run_id"] for r in rows
               if r["state"] in ACTIVE_STATES or r.get("codex_still_running")]
    done = [r["run_id"] for r in rows if r["state"] == "completed"]
    failed = [r["run_id"] for r in rows
              if r["state"] in ("failed", "interrupted", "orphaned", "timed_out")
              and not r.get("codex_still_running")]

    display_rows = rows
    runs_truncated = 0
    if not args.run and not args.all and total_runs > 20:
        tail = rows[-20:]
        # Truncate the display list only — a non-terminal row must survive
        # truncation no matter how old, or `running` above and `runs` below
        # would disagree about which runs are still alive.
        kept_live = [r for r in rows[:-20]
                     if r["state"] not in TERMINAL_STATES
                     or r.get("codex_still_running")]
        display_rows = kept_live + tail
        runs_truncated = total_runs - len(display_rows)
    if not (args.run or args.thread):
        display_rows = [summary_row(r) for r in display_rows]

    # Groups are listed even when no run in the (truncated) view belongs to one:
    # discovering that this project has batches at all is the step that makes
    # `status --group` and `--resume-from` reachable.
    out = {"project": str(project), "runs_dir": str(runs_dir), "runs": display_rows,
           "threads": by_thread, "running": running, "done": done, "failed": failed,
           "total_runs": total_runs, "runs_truncated": runs_truncated,
           "groups": list_groups(runs_dir)}
    note_unreadable(out, runs_dir)
    emit(out)


# --------------------------------------------------------------------------
# log / show
# --------------------------------------------------------------------------

def refuse_unusable_heartbeat(args):
    """A beat only a follower can emit, at an interval only a positive number
    can name.

    Both are refusals rather than silent no-ops for C4's reason: a flag that
    parses and decides nothing reads as having been obeyed. `--heartbeat 0`
    especially — it looks like "off", and off is what omitting it already does.
    """
    beat = getattr(args, "heartbeat", None)
    if beat is None:
        return
    if not args.follow:
        fail("--heartbeat is a line a follower prints while it follows, and "
             "there is no --follow here, so nothing would print it.")
    if beat <= 0:
        fail("--heartbeat is an interval in seconds and has to be positive; "
             "omitting it is how a follower stays quiet.", heartbeat=beat)


def cmd_log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    refuse_unusable_heartbeat(args)
    if args.follow_timeout is not None and not args.follow:
        fail("--follow-timeout requires --follow")
    if args.group:
        if args.since is not None:
            # Refused rather than given some collapsed meaning: every member has
            # its own byte offset into its own file, and one integer applied to
            # all of them answers with some member's events silently dropped —
            # which is the failure `--since`'s own out-of-range guard exists to
            # prevent, arriving by another road.
            fail("--since is one cursor and a group has one per member, each a "
                 "byte offset into its own file. `log --run <id> --since` is "
                 "where a cursor belongs; a group follower re-reads from the "
                 "start of each stream instead.",
                 group=args.group)
        follow_group_log(args, project, runs_dir)
        return
    if args.run:
        rd, meta = find_run(runs_dir, args.run)
        refuse_unresolved_run(args.run, rd, meta, runs_dir)
    else:
        # F4: this used to be `runs[-1]` with no filter at all. Apply the same
        # D27 resolution as `resume --last` — exactly one non-terminal run is
        # unambiguous, zero falls back to the newest, two or more fails loud
        # instead of silently picking across concurrent runs.
        candidates = list(iter_runs(runs_dir))
        if not candidates:
            fail("no runs in this project", runs_dir=str(runs_dir))
        rd, meta, _ = resolve_implicit_run(candidates)

    events_path = rd / "events.jsonl"
    rel_to = Path(meta.get("cwd") or project)
    run_id = meta.get("run_id")
    # `None` rather than `0` as the default, so that "not passed" and "passed
    # zero" are two answers: a group refuses the flag, and refusing it only
    # when the value was truthy accepted `--since 0` into a command that has no
    # single cursor to apply it to.
    cursor = args.since or 0

    def dump(cur):
        try:
            events, new_cur = read_events(events_path, cur)
        except CursorOutOfRange as e:
            fail(str(e), run_id=run_id, since=cur)
        for line in format_events(events, args.level, rel_to):
            sys.stdout.write(line + "\n")
        return new_cur

    if not args.follow:
        cursor = dump(cursor)
        sys.stdout.write(f"# cursor={cursor} run={run_id}\n")
        sys.stdout.flush()
        return

    # --follow must emit terminal states, not only progress. A monitor that
    # prints happy-path lines only is silent through a crash, and silence is
    # indistinguishable from "still working".
    started = time.time()
    beat_at = started
    deadline = started + args.follow_timeout if args.follow_timeout else None
    while True:
        cursor = dump(cursor)
        sys.stdout.flush()
        m = reap(rd, read_meta(rd) or {})
        st = m.get("state")
        # A terminal line means the run stopped moving — that is the contract
        # a background watcher is armed on. A run whose supervisor died is
        # terminal while its codex keeps emitting events, so printing it here
        # ends the stream in the middle of the stream.
        if st in TERMINAL_STATES and not still_writing(m):
            cursor = dump(cursor)
            sys.stdout.write(f"run.{st} run={m.get('run_id')} exit={m.get('exit_code')}\n")
            sys.stdout.write(f"# cursor={cursor} run={run_id}\n")
            sys.stdout.flush()
            return
        now = time.time()
        if deadline and now > deadline:
            sys.stdout.write(f"run.still-running run={m.get('run_id')} state={st}\n")
            sys.stdout.write(f"# cursor={cursor} run={run_id}\n")
            sys.stdout.flush()
            return
        beat, beat_at = heartbeat_due(beat_at, args.heartbeat, now)
        if beat:
            sys.stdout.write(f"still-running elapsed={int(now - started)} "
                             f"running=1\n")
            sys.stdout.flush()
        time.sleep(FOLLOW_INTERVAL)


def cmd_show(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rd, meta = find_run(runs_dir, args.run)
    refuse_unresolved_run(args.run, rd, meta, runs_dir)

    found, events = find_item(rd / "events.jsonl", args.item)
    if not found:
        ids = [f"{(e.get('item') or {}).get('id')}:{(e.get('item') or {}).get('type')}"
               for e in events if e.get("type") == "item.completed"]
        fail(f"no item {args.item!r} in run {meta['run_id']}", available=ids[:60])

    out = {"run_id": meta["run_id"], "item_id": args.item, "item_type": found.get("type")}
    if found.get("type") == "command_execution":
        text = found.get("aggregated_output") or ""
        raw = text.encode("utf-8", "replace")
        out["command"] = strip_wrapper(found.get("command") or "")
        out["exit_code"] = found.get("exit_code")
        out["total_bytes"] = len(raw)
        if len(raw) > args.max_bytes:
            out["truncated"] = True
            out["shown_bytes"] = args.max_bytes
            out["output"] = raw[: args.max_bytes].decode("utf-8", "replace")
            out["truncation_notice"] = (
                f"{len(raw) - args.max_bytes} of {len(raw)} bytes withheld; "
                f"raise --max-bytes to see more")
        else:
            out["truncated"] = False
            out["output"] = text
    elif found.get("type") == "file_change":
        out["changes"] = found.get("changes") or []
    else:
        out["item"] = found
    emit(out)


# --------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------

def signal_run(run_dir: Path, meta: dict, grace: float = 5.0):
    """SIGINT, then SIGTERM, then SIGKILL — to the process group.

    SIGINT first because Codex flushes its rollout and leaves the thread
    resumable: measured, it exits ~0.3 s later and the resumed turn still knows
    what the interrupted turn had finished. Signalling the group, never a
    process name, is what keeps concurrent runs independent — name matching
    would kill every Codex on the machine, including other people's.
    """
    pgid = meta.get("pgid")
    result = {"run_id": meta.get("run_id"), "pgid": pgid}
    if not pgid:
        return {**result, "signalled": False, "reason": "no process group recorded",
                "state": meta.get("state")}

    sent = []
    for sig, wait in ((signal.SIGINT, grace), (signal.SIGTERM, 3.0), (signal.SIGKILL, 1.0)):
        try:
            os.killpg(int(pgid), sig)
            sent.append(sig.name)
        except ProcessLookupError:
            break
        except PermissionError:
            result["error"] = f"not permitted to signal process group {pgid}"
            break
        deadline = time.time() + wait
        gone = False
        while time.time() < deadline:
            if not pid_alive(meta.get("supervisor_pid")) and not pid_alive(meta.get("codex_pid")):
                gone = True
                break
            time.sleep(0.1)
        if gone:
            break
    if sent and "error" not in result:
        # A descendant can outlive both Codex and the supervisor in the run's group; once they are gone the group holds nothing else of value.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(int(pgid), signal.SIGKILL)
            if sent[-1] != "SIGKILL":
                sent.append("SIGKILL")

    result["signals_sent"] = sent
    result["signalled"] = bool(sent)
    # Compare-and-set, not a plain write: the supervisor may have recorded its
    # own outcome (`completed`, or `timed_out` if its deadline fired) between
    # the last signal and this line, and that outcome is the true one.
    m = update_meta_if(run_dir, ACTIVE_STATES,
                       state="interrupted", ended_at=now_iso())
    result["state"] = m.get("state")
    result["thread_id"] = m.get("thread_id")
    return result


def cmd_stop(args):
    refuse_competing_selectors(args, "stop", "--run", "--group", "--all")
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if args.run:
        targets = []
        for ref in args.run:
            rd, m = find_run(runs_dir, ref)
            refuse_unresolved_run(ref, rd, m, runs_dir)
            targets.append((rd, m))
    elif args.group:
        # Not a name match on process or label — B8 forbids that, and for good
        # reason: matching by name is how concurrent runs end up killing each
        # other. This resolves a group id recorded in the manifest to run ids,
        # then signals each run's own pgid exactly like --run does. The group
        # name never reaches a process.
        targets = []
        for rd, m in resolve_group(runs_dir, args.group):
            m = reap(rd, m)
            if m.get("state") in ACTIVE_STATES or still_writing(m):
                targets.append((rd, m))
    elif args.all:
        targets = []
        for rd, m in iter_runs(runs_dir):
            m = reap(rd, m)
            if m.get("state") in ACTIVE_STATES or still_writing(m):
                targets.append((rd, m))
    else:
        fail("stop needs --run <id> (repeatable), --group <name>, or --all")
    emit({"stopped": [signal_run(rd, m, grace=args.grace) for rd, m in targets],
          "claude_session_id": session})


# --------------------------------------------------------------------------
# result
# --------------------------------------------------------------------------

def cmd_result(args):
    refuse_competing_selectors(args, "result", "--run", "--group")
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        return cmd_result_group(args, project, runs_dir)
    if not args.run:
        fail("result needs --run <id> or --group <name>")
    rd, meta = find_run(runs_dir, args.run)
    refuse_unresolved_run(args.run, rd, meta, runs_dir)
    meta = reap(rd, meta)
    info = scan_progress(rd / "events.jsonl",
                         terminal=(meta.get("state") in TERMINAL_STATES
                                   and not still_writing(meta)))

    msg_path = rd / "last-message.txt"
    message = (msg_path.read_text(encoding="utf-8") if msg_path.exists()
               else info["last_agent_message"])

    usage = info["usage"]
    out = {"run_id": meta["run_id"], "thread_id": meta.get("thread_id") or info["thread_id"],
           "state": meta.get("state"), "exit_code": meta.get("exit_code"),
           "message": message, "usage": usage,
           # F8: same clipped `turn.failed` error as `run_row`, so `result`
           # doesn't force a second `log` call to learn why a run failed.
           "turn_failed": (clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400)
                          if info["turn_failed"] else None),
           "files_changed": info["files_changed"], "commands": info["commands"]}
    if info["unparsed_events"]:
        out["unparsed_events"] = info["unparsed_events"]
    if meta.get("state") not in TERMINAL_STATES:
        out["note"] = f"run is still {meta.get('state')}; this is a partial result"
    elif still_writing(meta):
        # Terminal and still writing: the same call ten seconds later returns a
        # different final message. Handing both back uncaveated is two answers,
        # each presented as the answer.
        out["note"] = ("this run has no supervisor left to record its outcome, "
                       "but its codex process is still running and still "
                       "writing — so this is a partial result that will change")

    if meta.get("schema_path"):
        out["schema_path"] = meta["schema_path"]
        if not message:
            fail("run used --schema but produced no final message",
                 run_id=meta["run_id"], state=meta.get("state"))
        try:
            out["json"] = json.loads(message)
        except json.JSONDecodeError as e:
            # Loud, not lenient: handing back a malformed object as though it
            # had the schema's shape is worse than failing here.
            fail("run used --schema but the final message is not valid JSON",
                 run_id=meta["run_id"], parse_error=str(e), message=message)
        # The parsed object is the answer; the same text again as `message` would double it.
        del out["message"]
    emit(out)


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------

def cmd_models(args):
    """Which models and reasoning efforts this Codex install offers.

    Exists so that choosing either is a lookup rather than a guess. It is a
    command and not a paragraph in SKILL.md for the reason `model_catalog`
    states: a list written down here would be stale on some Codex version, and
    per-model effort support means it would be wrong for some model
    immediately.
    """
    catalog = model_catalog()
    if catalog is None:
        emit({"models": None,
              "error": "could not read the catalog from `codex debug models`; "
                       "`doctor` reports why. Runs are unaffected — an invalid "
                       "--model or --effort is caught by the API instead.",
              "codex_path": shutil.which("codex")}, code=1)
    emit({"models": catalog, "codex_version": codex_version()})


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def cmd_doctor(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    report, blockers, warnings = {}, [], []

    report["python"] = sys.version.split()[0]
    if sys.version_info < (3, 10):
        blockers.append(f"python {report['python']} is below the required 3.10")

    exe = shutil.which("codex")
    report["codex_path"] = exe
    report["codex_version"] = None
    if not exe:
        blockers.append("`codex` is not on PATH")
    else:
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
            report["codex_version"] = (r.stdout or r.stderr).strip() or None
        except Exception as e:
            warnings.append(f"could not read `codex --version`: {e}")

    home = codex_home()
    report["codex_home"] = str(home)
    report["codex_home_from_env"] = bool(os.environ.get("CODEX_HOME"))
    report["codex_home_exists"] = home.is_dir()
    if not home.is_dir():
        blockers.append(f"CODEX_HOME does not exist: {home}")

    if exe:
        try:
            r = subprocess.run([exe, "login", "status"], capture_output=True, text=True,
                               timeout=30, stdin=subprocess.DEVNULL)
            report["login_status"] = (r.stdout or r.stderr).strip()[:400]
            report["login_ok"] = r.returncode == 0
            if r.returncode != 0:
                # Non-zero does not mean "not authenticated". It means the
                # command did not succeed, and `codex login status` also fails
                # outright when it cannot load config at all — a malformed
                # `config.toml` gives `Error loading configuration: ...` and
                # exit 1 with a perfectly good auth.json sitting right there.
                # Calling that "not authenticated" sends the caller to
                # `codex login`, which fails the same way for the same reason,
                # forever. Measured against codex-cli 0.146.0.
                text = report["login_status"] or ""
                if re.search(r"(?i)error loading config|config\.toml|"
                             r"permission denied|invalid|parse", text):
                    blockers.append(
                        f"`codex login status` could not run at all — an "
                        f"environment or config problem, not an auth one, so "
                        f"`codex login` will fail the same way: "
                        f"{clip(text, 200)}")
                else:
                    blockers.append(
                        "`codex login status` exited non-zero — not authenticated")
        except Exception as e:
            report["login_ok"] = None
            warnings.append(f"could not run `codex login status`: {e}")

    cfg = home / "config.toml"
    report["config_toml"] = str(cfg) if cfg.exists() else None
    # One reader for config.toml, here and in `create_run` — two would drift,
    # and this file's own history has that happening twice (R20, R28). It also
    # fixes what the hand-rolled regex here got wrong: `(?m)^\s*sandbox_mode`
    # matched a key nested under a `[profiles.…]` table and reported a profile's
    # value as the top-level one.
    scalars = config_scalars(("sandbox_mode", "approval_policy"), cfg)
    report["config_sandbox_mode"] = scalars.get("sandbox_mode")
    report["config_approval_policy"] = scalars.get("approval_policy")
    cfg_sandbox = report["config_sandbox_mode"]
    # What a run with no --model/--effort/--priority would actually be handed.
    # It was answerable only by starting one and reading its argv, and the spec
    # carried "the model a run actually uses when none is named" as an open
    # item for three weeks because of that. `sandbox_mode` is absent on purpose:
    # this wrapper never reads it from here.
    report["effective_defaults"] = user_defaults()
    if cfg_sandbox == "danger-full-access":
        warnings.append(
            'config.toml sets sandbox_mode = "danger-full-access". `codex exec resume` '
            "has no -s flag and falls back to this value, which is how a read-only "
            "thread becomes fully privileged on its second turn. "
            "This wrapper passes -c sandbox_mode= on every invocation, so that fallback "
            "is never reached — but a bare `codex` command you run yourself will hit it.")

    catalog = model_catalog()
    report["models_catalog"] = len(catalog) if catalog else None
    if catalog is None:
        # Says why the pre-flight check is off rather than leaving the caller to
        # notice it never fires. Nothing is broken here — this degrades back to
        # the behaviour before the check existed.
        warnings.append(
            "could not read `codex debug models`, so `start`/`resume`/`batch` "
            "cannot check --model or --effort before spawning. Runs still work; "
            "an invalid value is caught by the API instead, one wasted run later.")

    report["skill_dir"] = str(Path(__file__).resolve().parent.parent)
    report["bridge_path"] = str(Path(__file__).resolve())
    report["plugin_root_env"] = os.environ.get("CLAUDE_PLUGIN_ROOT")

    report["project"] = str(project)
    report["project_is_git_repo"] = git_toplevel(project) is not None
    agents = project / "AGENTS.md"
    report["project_agents_md"] = str(agents) if agents.exists() else None
    if agents.exists():
        warnings.append(
            f"{agents} is injected into every Codex run started in this project. "
            "Project AGENTS.md survives --ignore-user-config (measured), so it is a "
            "briefing channel that works — and equally, its contents are in context "
            "whether or not that was intended.")

    report["runs_dir"] = str(runs_dir)
    report["runs_dir_exists"] = runs_dir.is_dir()
    # Probe without creating: a diagnostic that changes what it diagnoses is a
    # bad diagnostic.
    target = runs_dir if runs_dir.is_dir() else runs_dir.parent
    probe = target / f".codex-write-probe-{os.getpid()}"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        report["runs_dir_writable"] = True
    except Exception as e:
        report["runs_dir_writable"] = False
        blockers.append(f"runs dir is not writable ({target}): {e}")

    # Facts, not a policy. Nothing here deletes anything or nags about a
    # threshold: the run directories hold event streams the caller may still
    # want, and the worktrees hold results nothing else has a copy of. What the
    # caller cannot see without being told is that batch runs leave both behind
    # and that only `batch clean --group` removes them.
    if runs_dir.is_dir():
        total = sum(p.stat().st_size for p in runs_dir.rglob("*") if p.is_file())
        report["runs_dir_bytes"] = total
        report["runs_dir_runs"] = sum(1 for _ in iter_runs(runs_dir))
        report["groups"] = list_groups(runs_dir)
        bad = unreadable_runs(runs_dir)
        report["runs_unreadable"] = len(bad)
        if bad:
            # `runs_dir_bytes` counts their files while `runs_dir_runs` does not
            # count them at all. Without this line those two numbers simply
            # disagree and nothing says why.
            warnings.append(
                f"{len(bad)} run director(ies) have an unreadable meta.json and are "
                f"absent from every run listing: {', '.join(bad)}. Their bytes are "
                f"still counted in runs_dir_bytes. Nothing here writes a partial "
                f"meta.json — a truncated one means the disk filled or something "
                f"outside this skill edited it.")
        # §1.7. Grouped by recorded cwd, never by git top level — one
        # repository's worktrees all share a top level, so that comparison
        # would warn on exactly the arrangement that makes it safe.
        live = []
        for rd, m in iter_runs(runs_dir):
            # Reaped, like `concurrent_writers`. meta.json says `running` until
            # something notices the supervisor died, so grouping on it as
            # written names dead runs as live writers — and this is the report
            # a caller consults precisely when they suspect something is stuck,
            # which is exactly when stale state is most likely.
            m = reap(rd, m)
            if m.get("state") in TERMINAL_STATES and not still_writing(m):
                continue
            live.append(m)
        # Overlap, not string equality. `concurrent_writers` — the same check,
        # made at the moment a run is created — has always used `is_within` in
        # both directions, because a run in `/p` and a run in `/p/sub` are two
        # writers in one tree. Grouping on the exact `cwd` string put them in
        # two buckets of one and warned about neither, so the report a caller
        # consults *afterwards* was blind to what the check at creation time had
        # already seen. Two implementations of one question is how they drift;
        # this is the second time that has cost something (R20).
        seen = set()
        for i, m in enumerate(live):
            group = [m] + [o for j, o in enumerate(live) if j != i
                           and (is_within(o.get("cwd"), m.get("cwd"))
                                or is_within(m.get("cwd"), o.get("cwd")))]
            if len(group) < 2:
                continue
            key = tuple(sorted(x.get("run_id") or "" for x in group))
            if key in seen:
                continue
            seen.add(key)
            writers = [x for x in group if x.get("sandbox") in WRITING_SANDBOXES]
            if not writers:
                continue
            warnings.append(
                f"{len(group)} live runs overlap in {m.get('cwd')}, "
                f"{len(writers)} of which can write there: "
                f"{', '.join(x.get('run_id') for x in group)}. None of them can "
                f"tell another agent's change from its own. Runs in their own "
                f"worktrees are exempt and will not appear here.")

        # `registered` is `git worktree list` for the whole repository, so it
        # includes checkouts a user made themselves. Saying "N worktrees from
        # batch runs are checked out under .codex-runs" about one of those is
        # false twice over — it was not from a batch run and it is not under
        # that directory — and `batch clean` cannot touch it either. This
        # command only speaks for what this skill cut.
        live_wt = [p for p in worktrees_registered(project)
                   if p.exists() and is_within(str(p), str(runs_dir))]
        report["worktrees"] = len(live_wt)
        if live_wt:
            warnings.append(
                f"{len(live_wt)} git worktree(s) from batch runs are still "
                f"checked out under {runs_dir}. Each is a full working copy and "
                f"holds its run's uncommitted results; `batch clean --group "
                f"<name>` removes a group's once you have collected them.")

    report["blockers"] = blockers
    report["warnings"] = warnings
    report["ok"] = not blockers
    emit(report, code=0 if not blockers else 2)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

OUTPUT_CONTRACT = """\
Output. Every public command that parses its arguments prints one line of JSON,
success or failure, except `log`, which streams events and ends with
`# cursor=<n>`, and `status --group --follow`, which streams a line per member
state change and then a terminal `group.<state>` line. Anything that does not
parse is argparse's own usage error on stderr instead.
"""

STATUS_EPILOG = """\
The states, and what each one is telling you.

  starting    forked; the supervisor has not reported yet
  waiting     left by releases before 0.8: a batch member queued behind the
              run it continues. Live until its supervisor exits; `stop` ends it
  running     Codex has the turn
  stalled     running, with no events for %(stall)ds. Derived for display,
              never
              stored, and nothing is ever killed for it — the threshold cannot
              tell a slow command from a wedged one and you can. It does not
              look at in_progress_item: read that field alongside it, because
              idle inside a command_execution is a long build and idle with no
              item is worth investigating.
  completed   terminal: Codex finished the turn
  failed      terminal: Codex ended non-zero
  interrupted terminal: you stopped it
  timed_out   terminal: --timeout's deadline passed
  orphaned    terminal, and the odd one: this run's supervisor died without
              writing an outcome, so nothing is left recording it — a machine
              sleep, a hard kill. Codex itself may still be running and still
              writing files. The thread survives either way, so `resume`
              continues it.

A group reports its own `group_state`, and it has three values. `running`;
`completed` when every member reached a terminal state successfully; `partial`
otherwise — which includes after a `stop --group`, so `partial` means "not all
members succeeded", never "Codex failed". `--group` never truncates its listing;
you named the members.

`idle_seconds` is now minus the mtime of the last event.
""" % {"stall": STALL_SECONDS}

RUN_RETURN_EPILOG = """\
When this returns. As soon as there is a handle to hand back; it does not wait
for the turn to finish. The run is spawned under a supervisor process of its
own, so it is not tied to this command's lifetime.

The report waits up to %(wait)ds for the thread id to appear before it is
written, so this can come back with `thread_id: null`. That is a normal return, not a failure — `status`
backfills the id from the first line of events.jsonl — and until a run has one
there is no conversation to continue, so `resume` refuses it.

Nothing announces the end. No callback, no signal: the supervisor writes the
outcome into this run's meta.json and exits, so a run that finished and a run
still working are the same thing to look at until something asks. `status --run
<id>` asks once. `log --run <id> --follow` is the call that ends when the run
does, and it has a line for every terminal state, so a run that dies is not
silence.

Collecting it is a separate call. `result --run <id>` is what hands back the
work, and a run that finished is not a run you have read.

What Codex is actually sent. Your prompt, with one paragraph in front of it
stating what this turn's situation is: that nobody is watching, so a clarifying
question ends the turn with the work not done, and that the final message is
what reaches the caller. It is not optional. Measured, a run without it asserted
something about its own situation that was simply false, so the paragraph
corrects a fabrication rather than merely adding facts, and it costs about 113
input tokens.
""" % {"wait": THREAD_ID_WAIT}


BATCH_START_EPILOG = """\
When this returns. Every spawn has been attempted; it does not wait for a
single turn to finish. Each member is given up to %(wait)ds for its thread id
to appear before the report is written, so a member can come back with
`thread_id: null`. That is a normal return, not a failure — `status` backfills
the id from the first line of events.jsonl — but do not resume a member until
it has one.

Waiting for it, and collecting it. `status --group <name>` is the snapshot and
`status --group <name> --follow` blocks until the group reaches a terminal
state; `--follow-timeout` bounds that wait. Neither returns the work: `result
--group <name>` is a separate call, and a group that finished is not a group
you have read.

A member that failed to spawn keeps its slot with an `error` and no run_id, so
the list is never shorter than the tasks you handed over. Those slots appear as
`unstarted` and make the group `partial`. One member failing never takes the
others down, whatever the cause.

Worktrees. Off unless --worktree is passed, in which case a member is eligible
for its own git checkout at <run_dir>/wt when all of this holds: it is a
kind=start task, its sandbox can write, it names no cwd of its own, the project
is a git repository, and --base resolves. Eligible, not guaranteed — if git
cannot cut the checkout, that member's spawn fails and the others carry on. A
resume, a read-only member and one with an explicit cwd are never isolated, by
any flag. The checkout is cut from --base (default HEAD), so it holds none of
your uncommitted work — which is also why a read-only member never gets one,
since an uncommitted diff it was started to look at lives only in your tree —
and none of what git does not track either, so a canonical interpreter,
a provider cache or a fixture directory kept out of git is absent from it.
`missing_ignored` in the reply names up to 20 of the ones this tree actually
has, with `missing_ignored_truncated` counting any beyond that. Members' results
stay inside those checkouts: `result --group` reports what each member did and
which paths more than one wrote, and moving the changes into your tree is yours
to do. `batch clean --group` removes the checkouts once they are clean, or
discards their contents under --force.

Without it, every member works in your tree, which is what a fan-out of Claude's
own subagents does: the changes are in front of you as they are made and there
is nothing to collect. What you give up is that no member can tell another
member's edit from its own, so `result --group`'s `overlaps` is a report of what
already happened rather than of a merge still ahead.

What a member is told on top of that. The group's size and name, so a run knows
other runs may be editing other paths alongside it — and, where it was given a
worktree, that its tree is not the caller's, which commit it was cut from, and
how many uncommitted files the caller's tree has that its own does not.

Tasks. --task is a bare prompt, kind=start unless --resume-from turns it into
the resume of the member it pairs with. --tasks-file takes one JSON object per
line for everything else; its fields are listed above and generated from the
same tuple the validator checks against. Group-level options are defaults a
per-item field overrides. An unknown field name, or one with the wrong type,
fails the whole command before anything starts, because a silently ignored field
is a member that quietly used the group default instead.
""" % {"wait": THREAD_ID_WAIT}


class HidesSuppressedCommands(argparse.RawDescriptionHelpFormatter):
    """argparse lists every named subparser and prints `==SUPPRESS==` for one
    whose help is suppressed, rather than leaving it out.

    That is the difference between a command list a caller can trust and one
    they have to filter. `__supervise` is a re-exec target this process spawns
    for itself; a listing that names it is a listing SKILL.md cannot defer to,
    which is the whole reason SKILL.md carried a hand-kept copy of it.

    Raw description handling comes along because the epilogs below are laid out
    — argparse's own wrapping would reflow them into one paragraph.
    """

    def _iter_indented_subactions(self, action):
        for sub in super()._iter_indented_subactions(action):
            if sub.help is not argparse.SUPPRESS:
                yield sub


def add_heartbeat(p):
    p.add_argument("--heartbeat", type=float, metavar="SEC",
                   help="print `still-running elapsed=<s> running=<n>` on the "
                        "first poll at or after each SEC of following — a poll "
                        "period, not a timer. Off by default, and refused "
                        "without --follow or at zero or less. What it adds is "
                        "the half nothing else covers: a run that has gone "
                        "quiet shows up as `stalled` in `status --group "
                        "--follow` after 300 idle seconds, while a follower "
                        "that is alive with nothing to say and one that died "
                        "look the same in either follower.")


def add_common(p):
    p.add_argument("--runs-dir",
                   help="where run state lives (default: <project>/.codex-runs)")
    p.add_argument("--project",
                   help="project root whose registry to use (default: the git "
                        "toplevel of the working directory, or that directory "
                        "itself when it is not a repository)")


def add_run_options(p, *, kind):
    p.add_argument("--label",
                   help="short name for the run; appears in its run id and in "
                        "`status`. A resumed run inherits the label of the run "
                        "it was resolved from unless this replaces it.")
    p.add_argument("--sandbox", choices=SANDBOX_MODES,
                   help="what the run may do to the filesystem (default: "
                        "workspace-write). Recorded against the run, and "
                        "re-asserted on every later turn this registry can "
                        "resolve a base for — which is every resume of a run "
                        "this skill started, and none of a thread it did not.")
    p.add_argument("--model",
                   help="model slug. Checked against this install's catalog "
                        "before the run spawns when that catalog can be read, "
                        "and not at all when it cannot — never fail-closed; "
                        "`models` prints it. Four steps decide it when this is "
                        "unset: what a resumed thread recorded, then your "
                        "config.toml's `model`, then nothing at all and the "
                        "server picks. `doctor` prints which of those applies "
                        "here as effective_defaults.")
    p.add_argument("--effort",
                   help="reasoning effort. Valid values differ per model — "
                        "`models` prints each model's, with its default, and "
                        "omitting this is not the same as passing `medium`. "
                        "Unset it follows the same four steps as --model, "
                        "reading `model_reasoning_effort` from your "
                        "config.toml; with nothing to read, nothing is sent "
                        "and the server applies that model's own default.")
    p.add_argument("--inherit-config", action="store_true",
                   help="load the user's config.toml: their MCP servers, "
                        "plugins, agent roles and hooks. Off by default — a "
                        "fresh run is isolated, and a resumed one keeps "
                        "whatever its thread recorded. Auth is unaffected "
                        "either way, coming from auth.json.")
    tier = p.add_mutually_exclusive_group()
    tier.add_argument("--priority", dest="priority", action="store_true", default=None,
                   help="force service_tier=\"priority\" — the tier Codex "
                        "labels \"Fast mode\" and its config.toml spells "
                        "\"fast\"; both names are advertised and both were "
                        "measured to run clean. Only needed to override: "
                        "unset, an isolated run already takes whatever "
                        "service_tier your config.toml sets, and a resumed one "
                        "carries forward what its thread recorded.")
    tier.add_argument("--no-priority", dest="priority", action="store_false",
                   help="send no service_tier at all, and record that choice "
                        "so later turns on the thread do not re-add Fast "
                        "mode. That "
                        "is not the same as forcing the standard tier — "
                        "omitting the key leaves the server's own default, and "
                        "a run under --inherit-config can still pick the tier "
                        "up from your config.toml. Refused alongside "
                        "--priority.")
    p.add_argument("--schema",
                   help="path to a JSON Schema file handed to Codex. "
                        "`result --run` then returns the parsed object as "
                        "`json` and fails loudly if the final message is not "
                        "valid JSON; `result --group` does not parse, so "
                        "collect a schema batch member by member.")
    p.add_argument("--timeout", type=float,
                   help="give the run this many seconds, then SIGINT its process "
                        "group and record state=timed_out — a state of its own, "
                        "so a deadline is never mistaken for a failure you "
                        "should not retry. "
                        "No default: no flag, no deadline. The thread is "
                        "resumable across it only if a thread id was recorded "
                        "before the deadline; without one there is no "
                        "conversation to continue. If Codex does not exit on "
                        "the SIGINT the signal ladder escalates.")
    if kind in ("start", "resume"):
        p.add_argument("--image", action="append",
                       help="attach an image file to the prompt. Repeatable.")
        p.add_argument("--prompt-file",
                       help="read the prompt from this file instead of the "
                            "positional argument")
    if kind in ("start", "batch"):
        p.add_argument("--cwd",
                       help="directory the run works in (default: the project "
                            "root)")
        p.add_argument("--add-dir", action="append",
                       help="extra writable root beyond --cwd. Repeatable. "
                            "Codex offers it on `exec` only, so it cannot be "
                            "added to a resumed run later.")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="cli_codex.py",
        formatter_class=HidesSuppressedCommands,
        description="Drive the OpenAI Codex CLI as a managed subagent.",
        epilog=OUTPUT_CONTRACT)
    ap.subparser_map = {}
    # An explicit metavar, because argparse builds the default one from every
    # registered name including the suppressed one.
    sub = ap.add_subparsers(
        dest="cmd", required=True,
        metavar="{start,resume,status,log,show,stop,result,batch,"
                "models,doctor}",
        help="the whole command surface. Each takes its own --help, which is "
             "where every flag, its default and what it refuses are stated.")

    p = sub.add_parser("start", formatter_class=HidesSuppressedCommands,
                       help="a fresh thread, backgrounded — when you want the work done rather than judged",
                       epilog=RUN_RETURN_EPILOG)
    add_common(p); add_run_options(p, kind="start")
    p.add_argument("prompt", nargs="?",
                   help="the prompt. May instead come from --prompt-file, or "
                        "from stdin when this is `-` or omitted and stdin is "
                        "not a terminal.")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser(
        "resume", formatter_class=HidesSuppressedCommands,
        help="another turn on a thread, keeping what it already worked out",
        epilog=RUN_RETURN_EPILOG)
    add_common(p); add_run_options(p, kind="resume")
    p.add_argument("--last", action="store_true",
                   help="pick the thread to continue instead of naming one. "
                        "Candidates are registry runs that recorded a thread "
                        "id: exactly one live run wins, none falls back to the "
                        "newest and says so, two or more is ambiguous and is "
                        "refused with the candidates listed. Threads started "
                        "outside this skill are never picked; name one to "
                        "resume it.")
    p.add_argument("--force", action="store_true",
                   help="start a turn on a thread the concurrency check "
                        "objected to — one that already has a live turn, or one "
                        "whose metadata could not be read, which is the same "
                        "refusal for the opposite reason.")
    p.add_argument("rest", nargs="*", metavar="[REF] PROMPT",
                   help="run id / thread id / thread name, then the prompt; "
                        "with --last, just the prompt. A ref this registry has "
                        "never seen — a thread id or name from the Codex TUI — "
                        "is passed through to Codex, but its original sandbox "
                        "was never recorded and there is nothing to re-assert, "
                        "so it is refused without an explicit --sandbox. A run "
                        "whose thread_id is still null has no conversation yet "
                        "and is refused too — wait for `status` to backfill it.")
    p.set_defaults(func=cmd_resume, cwd=None, add_dir=None, ref=None, prompt=None)
    ap.subparser_map["resume"] = p

    p = sub.add_parser(
        "status", formatter_class=HidesSuppressedCommands,
        help="is it alive, how far along, what it last said — registry state, not the event stream",
        description="State, never output. The default listing also carries this "
                    "project's `groups` and gives every row its `group` (the "
                    "full row, with `worktree`, is behind --run, --thread and "
                    "--group), which is how a session that did not start a "
                    "batch finds it: the group name is the one thing about a "
                    "batch nobody can re-derive.",
        epilog=STATUS_EPILOG)
    add_common(p)
    p.add_argument("--run", metavar="REF",
                   help="one run: a run id, a thread id, or a run-id prefix "
                        "(newest wins)")
    p.add_argument("--thread", metavar="THREAD_ID",
                   help="every run on one thread")
    p.add_argument("--group", help="report on one batch group's members only")
    p.add_argument("--all", action="store_true",
                   help="every run in the registry. Without this, and without "
                        "--run, --thread or --group, the listing keeps every "
                        "non-terminal run plus the 20 newest — so it can exceed "
                        "20 rows when older runs are still live — and reports "
                        "how many it withheld as runs_truncated.")
    p.add_argument("--follow", action="store_true",
                   help="requires --group: plain text rather than the one "
                        "JSON object `status --group` returns — a "
                        "`run <id> <prev> -> <state>` line per member state "
                        "change, with ` exit=N` appended when the state is not "
                        "`completed` and an exit code was recorded, then one "
                        "terminal `group.<state> group=<name> done=N failed=N` "
                        "line, then exit. A group with no resolvable member is "
                        "one `group.empty group=<name>` line instead, carrying "
                        "neither tally. Both closing lines append ` unstarted=N` "
                        "and ` unreadable=N` when either is non-zero. A pure "
                        "view — it holds no state, so a follower that dies loses "
                        "nothing and `status --group` answers the same question "
                        "at any time.")
    p.add_argument("--follow-timeout", type=float,
                   help="stop following after this many seconds and print "
                        "group.still-running instead of a terminal group line. "
                        "No default: the follow ends only when the group does. "
                        "Refused without --follow.")
    add_heartbeat(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser(
        "log", formatter_class=HidesSuppressedCommands,
        help="filtered events from a byte cursor — the whole log, or only what is new")
    add_common(p)
    target = p.add_mutually_exclusive_group()
    target.add_argument("--run", metavar="REF",
                        help="a run id, a thread id, or a run-id prefix (newest "
                             "wins). Omitted, the project's single live run is "
                             "used; with none live the newest terminal one, and "
                             "with two or more live it is refused rather than "
                             "guessed.")
    target.add_argument("--group", metavar="NAME",
                        help="every member of one batch group, interleaved as "
                             "each writes. A first line maps index to run id "
                             "(`group.members group=<name> 0=<run_id>[:label] "
                             "…`), and every event line is prefixed "
                             "`[<index>:<label>]`, or `[<index>]` for a member "
                             "with no label. Under --follow the stream ends on "
                             "the group's own terminal line, the same one "
                             "`status --group --follow` ends on; without it, one "
                             "pass over every member's whole log ending on the "
                             "group's line as it stands, which for a live group "
                             "is `group.running`. --since is refused here: a "
                             "cursor is a byte offset into one file and every "
                             "member has its own.")
    p.add_argument("--since", type=int, default=None,
                   help="resume from the byte offset a previous call printed as "
                        "`# cursor=<n>`. Omitted, the whole log. Only "
                        "complete lines are consumed, so nothing is duplicated "
                        "or skipped however often you poll.")
    p.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL,
                   help="how much of each event to print (default: compact). "
                        "All four carry the lifecycle, the agent's own messages "
                        "in full, every command line with its exit code and "
                        "output size, changed paths, errors, searches, MCP "
                        "calls and usage; they differ only in what rides "
                        "along. compact: nothing further. normal: a "
                        f"{FAIL_HEAD_BYTES}B head and {FAIL_TAIL_BYTES}B tail "
                        "of output for commands that exited non-zero, plus "
                        "todo lists. full: the same head/tail excerpt for every "
                        f"command whatever its exit code ({FULL_ITEM_BYTES}B "
                        "of excerpt, before the marker naming what was left "
                        "out), and reasoning items, which no lower level "
                        "shows. raw: the events verbatim. The split is on exit "
                        "code rather than size, which is a proxy and not a "
                        "verdict — a command that exits non-zero because one "
                        "file argument was missing brings its output along too.")
    p.add_argument("--follow", action="store_true",
                   help="print events as they arrive, then one terminal line "
                        "(run.completed / run.failed / run.interrupted / "
                        "run.timed_out / run.orphaned, with the exit code) "
                        "before exiting. There is a line for every terminal "
                        "state on purpose: a follower that only printed "
                        "progress would go silent through a crash, and silence "
                        "is indistinguishable from still working.")
    p.add_argument("--follow-timeout", type=float,
                   help="stop following after this many seconds and print "
                        "run.still-running instead of a terminal line, so a "
                        "watcher cannot hang on a wedged run. Shapes nothing "
                        "without --follow.")
    add_heartbeat(p)
    p.set_defaults(func=cmd_log)

    p = sub.add_parser(
        "show", formatter_class=HidesSuppressedCommands,
        help="one item's output, when the summary looks wrong",
        description="Returns exactly one item's full aggregated_output (or a "
                    "file_change's whole change list) and nothing else's. This "
                    "is the only path by which complete command output reaches "
                    "a caller's context, and it is always one explicit request "
                    "at a time.")
    add_common(p)
    p.add_argument("--run", required=True, metavar="REF",
                   help="required: item ids restart at item_0 in every run's "
                        "event stream, so two runs on one thread each have an "
                        "item_0 meaning different things and an item id alone "
                        "identifies nothing")
    p.add_argument("--item", required=True, metavar="ITEM_ID",
                   help="the item to fetch, as printed by `log` (item_0, "
                        "item_1, …). An unknown id is refused with up to 60 of "
                        "the run's completed items listed.")
    p.add_argument("--max-bytes", type=int, default=SHOW_MAX_BYTES,
                   help=f"cap on command output returned (default: "
                        f"{SHOW_MAX_BYTES}); a file_change's list is not capped. "
                        "Truncation is reported with the true size and how to "
                        "raise the cap, never silent.")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser(
        "stop", formatter_class=HidesSuppressedCommands,
        help="interrupt a run, a group, or everything, by process group")
    add_common(p)
    p.add_argument("--run", action="append", metavar="REF",
                   help="a run to interrupt. Repeatable. No default target: one "
                        "of --run, --group or --all is required.")
    p.add_argument("--group",
                   help="interrupt every live member of a batch group")
    p.add_argument("--all", action="store_true",
                   help="interrupt every run in this project's registry that "
                        "is still doing something — every non-terminal one, "
                        "plus an orphaned run whose Codex is still writing")
    p.add_argument("--grace", type=float, default=5.0,
                   help="seconds to wait after SIGINT before SIGTERM, then 3s "
                        "before SIGKILL (default: 5.0). Signals go to the run's "
                        "recorded process group, never to a matched process "
                        "name, so one run's stop cannot reach another's — "
                        "matching `codex exec` by name would reach every Codex "
                        "on the machine, including another person's. The ladder "
                        "starts at SIGINT because that lets Codex flush its "
                        "rollout: a stopped run stays resumable and the resumed "
                        "turn still knows what the interrupted one finished. "
                        "That is the whole of mid-turn steering — there is no "
                        "channel into a running turn, so redirecting one is "
                        "stop then resume. A process group isolates signals and "
                        "nothing else: two runs in one directory still edit the "
                        "same files.")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser(
        "result", formatter_class=HidesSuppressedCommands,
        help="the run's message and usage — final once it ends, partial while it runs")
    add_common(p)
    p.add_argument("--run", metavar="REF",
                   help="one run's whole message — final once the run ends, "
                        "and whatever it has said so far while it is live. No "
                        "default target: one of --run or --group is required.")
    p.add_argument("--group",
                   help="collect a batch group: every member that started, "
                        "capped per run, with usage, files_changed and "
                        "`overlaps` — the paths more than one member was "
                        "observed writing. Members that never started are "
                        "listed separately under `unstarted` rather than "
                        "silently shortening the list.")
    p.set_defaults(func=cmd_result)

    p = sub.add_parser(
        "batch", formatter_class=HidesSuppressedCommands,
        help="several runs as one name you can watch, collect and stop together",
        description="A group is the set of runs one `batch start` created, "
                    "addressable afterwards as one thing — by `status --group`, "
                    "`result --group`, `stop --group`, `batch clean --group` "
                    "and `batch start --resume-from`. It outlives the session "
                    "that started it. The name is single-use per project.")
    bsub = p.add_subparsers(dest="batch_cmd", required=True)
    b = bsub.add_parser("start", help="start N runs as one addressable group",
                        formatter_class=HidesSuppressedCommands,
                        epilog=BATCH_START_EPILOG)
    add_common(b); add_run_options(b, kind="batch")
    b.add_argument("--group", required=True,
                   help="name for this group. Single-use per project until "
                        "`batch clean` releases it: reusing a live name would "
                        "make membership and start order ambiguous, and "
                        "--resume-from pairs positionally against exactly that "
                        "list.")
    b.add_argument("--task", action="append",
                   help="a prompt. Repeatable, and ordered before any "
                        "--tasks-file entries. kind=start on its own; under "
                        "--resume-from each becomes the resume of the member it "
                        "pairs with.")
    b.add_argument("--tasks-file",
                   help="JSONL, one task object per line, for long or "
                        "heterogeneous tasks; see the epilog for how these "
                        "interact with the group-level options. Fields: "
                        + ", ".join(TASK_FIELDS))
    b.add_argument("--force", action="store_true",
                   help="allow a resume task to start a second turn on a thread "
                        "that already has a live one")
    b.add_argument("--worktree", action="store_true",
                   help="give each writing member its own git checkout instead "
                        "of the caller's tree. Off by default: members share "
                        "the tree, so their work is in it as they do it. Reach "
                        "for this when two or more members can touch the same "
                        "files — the cost is that results stay in the "
                        "checkouts until you collect them, and that a checkout "
                        "holds only what git tracks. Per member, not per "
                        "batch: a resume, a read-only member and one with "
                        "its own cwd stay in the caller's tree whatever this "
                        "says.")
    b.add_argument("--base",
                   help="commit or ref the worktrees are cut from (default "
                        "HEAD). Refused without --worktree, which is the only "
                        "thing it shapes. A base older than HEAD can be "
                        "missing the project's AGENTS.md, which reaches a "
                        "worktree run only from a base where the file exists.")
    b.add_argument("--resume-from", metavar="GROUP",
                   help="continue an earlier group: task i resumes member i of "
                        "that group, in its start order, keeping its thread and "
                        "the directory it already lives in — including that "
                        "group's worktrees, which are preserved rather than "
                        "reissued, so a phase 1 that was never isolated stays "
                        "un-isolated. One task per started member, unless a "
                        "task names its own target with kind/resume, which "
                        "wins over its positional counterpart.")
    b.set_defaults(func=cmd_batch_start)

    b = bsub.add_parser("clean", formatter_class=HidesSuppressedCommands,
                        help="remove a group's worktrees, and release its name when nothing is left")
    add_common(b)
    b.add_argument("--group", required=True,
                   help="the group to clean up. The name is released only when "
                        "nothing is left behind. Refused while a member is live, "
                        "and a worktree another live run is working inside is "
                        "kept; both say which `stop` ends them. Also refused "
                        "while a member's meta.json will not parse or a group "
                        "derived from this one still needs the worktrees, and a "
                        "worktree git will not discard uncommitted changes from "
                        "is kept.")
    b.add_argument("--force", action="store_true",
                   help="lift every refusal at once, not only the one you "
                        "hit, including a manifest that will not parse — except "
                        "that a worktree whose run is live, or whose meta.json "
                        "will not parse, is always kept. The result says what "
                        "it overrode. "
                        "Where a worktree held uncommitted changes, that work "
                        "had no other copy.")
    b.set_defaults(func=cmd_batch_clean)

    p = sub.add_parser(
        "models", formatter_class=HidesSuppressedCommands,
        help="which models and efforts exist here, before you name one",
        description="This install's model catalog, read live from `codex debug "
                    "models` and cached once per process. Each model carries "
                    "its own `efforts` and its own `default_effort` — they are "
                    "not a shared ladder every model climbs the same way, which "
                    "is why no list of them is written down anywhere here. "
                    "`start`, `resume` and `batch start` check a passed --model "
                    "or --effort against this before spawning. When it cannot "
                    "be read the check is skipped rather than failing closed, "
                    "and `doctor` reports models_catalog as null with a "
                    "warning saying why.")
    add_common(p)
    p.set_defaults(func=cmd_models)

    p = sub.add_parser(
        "doctor", formatter_class=HidesSuppressedCommands,
        help="why is Codex not behaving — env, auth, sandbox, paths",
        description="Exits 0 when healthy and 2 when there is a blocker, so it "
                    "is usable in a conditional. Blockers stop a run working at "
                    "all: no codex on PATH, no authentication, a missing "
                    "CODEX_HOME, an unwritable runs dir, Python below 3.10. "
                    "The warnings are things that work but are worth "
                    "knowing: a "
                    "config.toml set to danger-full-access, a project "
                    "AGENTS.md. Check auth "
                    "before anything else — an unauthenticated run fails in "
                    "ways that look like other problems. `codex_home` is "
                    "printed resolved, with `codex_home_from_env` saying "
                    "whether it was overridden; an override moves sessions, "
                    "config.toml and auth.json with it, so ~/.codex is then "
                    "someone else's state or nothing.")
    add_common(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("__supervise", help=argparse.SUPPRESS)
    p.add_argument("--run-dir", required=True,
                   help="the run directory to supervise. Not a command a caller "
                        "runs: this process re-execs itself with it to become "
                        "the detached supervisor for a run it just claimed.")
    p.set_defaults(func=lambda a: sys.exit(supervise(Path(a.run_dir))))

    return ap


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("CODEX_HOME"):
        # The supervisor and codex run in other directories, so a relative value is pinned to what it meant here.
        os.environ["CODEX_HOME"] = str(codex_home())
    ap = build_parser()
    # `resume` is the only subcommand with two optional positionals
    # (`[REF] PROMPT`). Plain argparse binds them in groups split by any option
    # in between, so `resume <ref> --sandbox read-only "prompt"` loses the
    # prompt. parse_intermixed_args handles exactly that, but it cannot run on a
    # parser that owns subparsers — so dispatch to the subparser itself.
    if raw[:1] == ["resume"]:
        args = ap.subparser_map["resume"].parse_intermixed_args(raw[1:])
    else:
        args = ap.parse_args(raw)
    try:
        args.func(args)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
    except KeyboardInterrupt:
        fail("interrupted")
    except Exception as e:
        fail(f"internal error: {e}")


if __name__ == "__main__":
    main()
