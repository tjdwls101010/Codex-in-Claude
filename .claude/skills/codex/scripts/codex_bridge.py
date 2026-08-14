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

from _codex import (  # noqa: E402
    codex_version, model_catalog, review_argv,
    SANDBOX_MODES, query_threads, state_db_path, supervise,
)
from _events import (  # noqa: E402
    CursorOutOfRange, DEFAULT_LEVEL, LEVELS, find_item, format_events, read_events,
    scan_progress, strip_wrapper,
)
from _batch import (  # noqa: E402
    TASK_FIELDS, cmd_batch_clean, cmd_batch_start, cmd_result_group, follow_group,
    group_snapshot, list_groups, resolve_group, unstarted_members,
    vanished_members,
)
from _worktree import registered as worktrees_registered  # noqa: E402
from _registry import (  # noqa: E402
    ACTIVE_STATES, TERMINAL_STATES, find_run, iter_runs, meta_unreadable,
    read_meta, reap, resolve_project, resolve_runs_dir, still_writing,
    unreadable_runs, update_meta_if,
)
from _run import (  # noqa: E402
    WRITING_SANDBOXES, create_run, ordered_by_waiting, resolve_implicit_run,
    run_row,
)
from _util import (  # noqa: E402
    clip, codex_home, emit, fail, git_toplevel, is_within, now_iso, pid_alive,
)

# `show --item` default cap. A silently truncated blob is worse than a loud one,
# so truncation is always announced along with how much was withheld.
SHOW_MAX_BYTES = 20000

# `status --include-external` caps each thread's title. Codex stores the whole
# prompt there, preamble included, and this listing returns up to fifty of them.
# Measured on one project with sixteen external threads: the listing went
# 19,293 B to 16,399 B, so the titles were about 2.9 KB of it. The rest is
# structural — roughly 830 B per thread, mostly `sandbox_policy` and
# `rollout_path` — which at the fifty-thread limit is around 40 KB, and is
# the larger half of this cost rather than the part capped here.
EXTERNAL_TITLE_CAP = 200


# --------------------------------------------------------------------------
# start / resume / review — all three build a run the same way, in `_run.py`
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
        if candidates:
            _, base, resolved_from = resolve_implicit_run(candidates)
            thread_ref = base["thread_id"]
        else:
            # Nothing in the registry: fall back to Codex's own thread list for
            # this directory, which is what lets Claude pick up a session the
            # user started in the Codex TUI.
            rows = query_threads(cwd_filter=str(project), limit=1)
            if not rows:
                fail("no previous run in this project's registry and no Codex thread "
                     "recorded for this directory", project=str(project))
            thread_ref = rows[0]["id"]
            resolved_from = "Codex's own thread list (no registry entry)"
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


def cmd_review(args):
    review_args = review_argv(uncommitted=args.uncommitted, base=args.base,
                              commit=args.commit, title=args.title,
                              prompt=args.prompt, fail=fail)
    emit(create_run(args, kind="review", review_args=review_args))


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


def cmd_status(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    # `--run` and `--group` are two different questions and the branches below
    # answer whichever comes first, so passing both silently drops one of them
    # — including the case where the dropped one is the `--group` that would
    # have made `--follow` mean something. Found by a `review` member reading
    # the commit that added the check below, which is the kind of hole a fix
    # leaves when it guards a symptom instead of the precedence underneath it.
    refuse_competing_selectors(args, "status", "--run", "--group")
    # `--follow` only ever meant "--group --follow": the other branches emit a
    # snapshot and exit. Accepting it silently is the shape of mistake R13 was
    # about — the tool hands back an answer the caller reads as "I waited for
    # this", and everything they conclude from that instant's state is then
    # correctly reasoned from a false premise.
    if args.follow and not args.group:
        fail("--follow needs --group; a group is what has an end to wait for. "
             "To watch one run, use `log --run <id> --follow`, which streams its "
             "events and ends on the run's terminal line.",
             run=args.run, interval=args.interval)
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
            rows.append(run_row(rd, m, project))

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
    known = {r["thread_id"] for r in rows}

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

    # Groups are listed even when no run in the (truncated) view belongs to one:
    # discovering that this project has batches at all is the step that makes
    # `status --group` and `--resume-from` reachable.
    out = {"project": str(project), "runs_dir": str(runs_dir), "runs": display_rows,
           "threads": by_thread, "running": running, "done": done, "failed": failed,
           "total_runs": total_runs, "runs_truncated": runs_truncated,
           "groups": list_groups(runs_dir)}
    note_unreadable(out, runs_dir)
    if args.include_external:
        # `title` is whatever Codex stored, which is the whole prompt — and for
        # a thread this skill started, that includes the preamble verbatim on
        # every row. What a caller needs in order to pick a thread is the
        # opening, so this is capped for the same reason `result --group` caps
        # a member's message, and `clip` says how much it dropped. The numbers
        # are on EXTERNAL_TITLE_CAP above; the cap is the smaller half of the
        # cost, which is worth knowing before reaching for it again.
        out["external_threads"] = [{**t, "title": clip(t.get("title") or "",
                                                       EXTERNAL_TITLE_CAP)}
                                   for t in query_threads(cwd_filter=str(project))
                                   if t.get("id") not in known]
        out["external_note"] = (
            "Codex threads for this cwd with no registry entry — started outside this "
            "skill. Resumable by id, but their original sandbox was never recorded "
            "here, so pass --sandbox explicitly rather than inheriting a default.")
    emit(out)


# --------------------------------------------------------------------------
# log / show
# --------------------------------------------------------------------------

def cmd_log(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
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
    cursor = args.since

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
    deadline = time.time() + args.follow_timeout if args.follow_timeout else None
    while True:
        cursor = dump(cursor)
        sys.stdout.flush()
        m = reap(rd, read_meta(rd) or {})
        st = m.get("state")
        # A terminal line means the run stopped moving — that is the contract
        # `--follow` is paired with Monitor on. A run whose supervisor died is
        # terminal while its codex keeps emitting events, so printing it here
        # ends the stream in the middle of the stream.
        if st in TERMINAL_STATES and not still_writing(m):
            cursor = dump(cursor)
            sys.stdout.write(f"run.{st} run={m.get('run_id')} exit={m.get('exit_code')}\n")
            sys.stdout.write(f"# cursor={cursor} run={run_id}\n")
            sys.stdout.flush()
            return
        if deadline and time.time() > deadline:
            sys.stdout.write(f"run.still-running run={m.get('run_id')} state={st}\n")
            sys.stdout.write(f"# cursor={cursor} run={run_id}\n")
            sys.stdout.flush()
            return
        time.sleep(args.interval)


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
    review_zero = meta.get("kind") == "review" and usage is not None and not any(usage.values())
    out = {"run_id": meta["run_id"], "thread_id": meta.get("thread_id") or info["thread_id"],
           "state": meta.get("state"), "exit_code": meta.get("exit_code"),
           "message": message, "usage": None if review_zero else usage,
           # F8: same clipped `turn.failed` error as `run_row`, so `result`
           # doesn't force a second `log` call to learn why a run failed.
           "turn_failed": (clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400)
                          if info["turn_failed"] else None),
           "files_changed": info["files_changed"], "commands": info["commands"]}
    if review_zero:
        out["usage_note"] = "review runs report zero usage; unavailable, not free"
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
                 run_id=meta["run_id"], parse_error=str(e),
                 message_preview=clip(message, 400))
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
    cfg_sandbox = cfg_approval = None
    if cfg.exists():
        try:
            txt = cfg.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'(?m)^\s*sandbox_mode\s*=\s*"?([\w-]+)"?', txt)
            cfg_sandbox = m.group(1) if m else None
            m = re.search(r'(?m)^\s*approval_policy\s*=\s*"?([\w-]+)"?', txt)
            cfg_approval = m.group(1) if m else None
        except Exception as e:
            warnings.append(f"could not read config.toml: {e}")
    report["config_sandbox_mode"] = cfg_sandbox
    report["config_approval_policy"] = cfg_approval
    if cfg_sandbox == "danger-full-access":
        warnings.append(
            'config.toml sets sandbox_mode = "danger-full-access". `codex exec resume` '
            "and `codex exec review` have no -s flag and fall back to this value, which "
            "is how a read-only thread becomes fully privileged on its second turn. "
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
        by_id = {m.get("run_id"): m for m in live}
        for i, m in enumerate(live):
            group = [m] + [o for j, o in enumerate(live) if j != i
                           and (is_within(o.get("cwd"), m.get("cwd"))
                                or is_within(m.get("cwd"), o.get("cwd")))
                           # A `--as-ready` member inherits its predecessor's
                           # directory and sits non-terminal beside it, which is
                           # exactly the shape this looks for — and is the one
                           # pair that cannot be writing at once. Same exclusion
                           # `concurrent_writers` makes at creation time; the two
                           # have already drifted once (R20).
                           and not ordered_by_waiting(m, o, by_id)]
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

    db = state_db_path()
    report["thread_db"] = str(db) if db else None
    report["thread_db_readable"] = bool(query_threads(limit=1)) if db else False
    if db and not report["thread_db_readable"]:
        warnings.append(
            f"{db} exists but no threads could be read. The filename is "
            "version-stamped, so a Codex upgrade may have changed its schema; "
            "`--include-external` and a registry-less `--last` degrade, nothing else.")

    report["blockers"] = blockers
    report["warnings"] = warnings
    report["ok"] = not blockers
    emit(report, code=0 if not blockers else 2)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

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
                        "`status`. A resumed run keeps its thread's unless this "
                        "replaces it.")
    p.add_argument("--sandbox", choices=SANDBOX_MODES,
                   help="what the run may do to the filesystem (default: "
                        "workspace-write). Recorded, and re-asserted on every "
                        "later turn of this thread.")
    p.add_argument("--model",
                   help="model slug, checked against this Codex install before "
                        "the run spawns. `models` prints the catalog. No "
                        "default: Codex picks its own.")
    p.add_argument("--effort",
                   help="reasoning effort. Valid values differ per model — "
                        "`models` prints each model's, with its default. "
                        "Omitting this sends nothing at all, which is not the "
                        "same as naming a level.")
    p.add_argument("--inherit-config", action="store_true",
                   help="load the user's config.toml: their MCP servers, "
                        "plugins, agent roles and hooks. Off by default. Auth "
                        "is unaffected either way, coming from auth.json.")
    p.add_argument("--isolate", action="store_true",
                   help="ignore the user's config.toml. Already the default for "
                        "a fresh run; pass it to override the inherited setting "
                        "of a thread being resumed.")
    p.add_argument("--priority", dest="priority", action="store_true", default=None,
                   help="re-inject service_tier=\"priority\", which ignoring the "
                        "user's config would otherwise drop. Defaults to on "
                        "exactly when the run is isolated.")
    p.add_argument("--no-priority", dest="priority", action="store_false",
                   help="do not re-inject service_tier")
    p.add_argument("--schema",
                   help="path to a JSON Schema file handed to Codex. `result` "
                        "then returns the parsed object as `json`, and fails "
                        "loudly if the final message is not valid JSON.")
    p.add_argument("--config", action="append", metavar="k=v",
                   help="extra `-c k=v` passed through to Codex. Repeatable. "
                        "The four keys this wrapper records and re-asserts — "
                        "model, model_reasoning_effort, sandbox_mode, "
                        "service_tier — are refused here; use their own flags.")
    p.add_argument("--foreground", action="store_true",
                   help="block until the turn ends instead of backgrounding it. "
                        "Refused on `batch start`.")
    p.add_argument("--timeout", type=float,
                   help="give the run this many seconds, then SIGINT its process "
                        "group and record state=timed_out. Works in background "
                        "and foreground. No default: no flag, no deadline.")
    p.add_argument("--no-preamble", action="store_true",
                   help="drop the paragraph this wrapper prepends to the prompt "
                        "— that nobody is watching the turn, and that the final "
                        "message is what the caller receives. `result` depends "
                        "on the second half of that.")
    if kind in ("start", "resume"):
        p.add_argument("--image", action="append",
                       help="attach an image file to the prompt. Repeatable.")
        p.add_argument("--prompt-file",
                       help="read the prompt from this file instead of the "
                            "positional argument")
    if kind == "start":
        p.add_argument("--cwd",
                       help="directory the run works in (default: the project "
                            "root)")
        p.add_argument("--add-dir", action="append",
                       help="extra writable root beyond --cwd. Repeatable. "
                            "Codex offers it on `exec` only, so it cannot be "
                            "added to a resumed or review run later.")


def build_parser():
    ap = argparse.ArgumentParser(prog="codex_bridge.py",
                                 description="Drive the OpenAI Codex CLI as a managed subagent.")
    ap.subparser_map = {}
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="hand work to a fresh thread — when you want the change made")
    add_common(p); add_run_options(p, kind="start")
    p.add_argument("prompt", nargs="?",
                   help="the prompt. May instead come from --prompt-file, or "
                        "from stdin when this is `-` or omitted.")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("resume", help="another turn on a thread, keeping what it already worked out")
    add_common(p); add_run_options(p, kind="resume")
    p.add_argument("--last", action="store_true",
                   help="pick the thread to continue instead of naming one: the "
                        "single live run if there is exactly one, else the "
                        "newest. Two or more live runs are ambiguous and are "
                        "refused with the candidates listed.")
    p.add_argument("--force", action="store_true",
                   help="allow a second turn on a thread that already has one running")
    p.add_argument("rest", nargs="*", metavar="[REF] PROMPT",
                   help="run id / thread id / thread name, then the prompt; "
                        "with --last, just the prompt")
    p.set_defaults(func=cmd_resume, cwd=None, add_dir=None, ref=None, prompt=None)
    ap.subparser_map["resume"] = p

    p = sub.add_parser("review", help="read-only findings on a diff — a verdict you act on, not a change")
    add_common(p); add_run_options(p, kind="review")
    p.add_argument("--uncommitted", action="store_true",
                   help="review the working tree's uncommitted changes")
    p.add_argument("--base", metavar="REF",
                   help="review the diff against this ref")
    p.add_argument("--commit", metavar="SHA",
                   help="review one commit")
    p.add_argument("--title",
                   help="title for the review; only valid with --commit")
    p.add_argument("--cwd",
                   help="directory to review in (default: the project root)")
    p.add_argument("prompt", nargs="?",
                   help="free-form review instruction. Exactly one of "
                        "--uncommitted, --base, --commit or this is required — "
                        "the Codex CLI rejects combinations.")
    p.set_defaults(func=cmd_review, image=None, add_dir=None, prompt_file=None)

    p = sub.add_parser("status", help="is it alive and how far along — state, not output")
    add_common(p)
    p.add_argument("--run", metavar="REF",
                   help="one run: a run id, a thread id, or a run-id prefix "
                        "(newest wins)")
    p.add_argument("--thread", metavar="THREAD_ID",
                   help="every run on one thread")
    p.add_argument("--group", help="report on one batch group's members only")
    p.add_argument("--all", action="store_true",
                   help="every run in the registry. Without this, and without "
                        "--run or --group, the listing keeps every non-terminal "
                        "run plus a tail of recent ones, caps at 20 rows, and "
                        "reports how many it withheld as runs_truncated.")
    p.add_argument("--include-external", action="store_true",
                   help="also list Codex threads for this directory that have no "
                        "registry entry — ones started outside this skill. Their "
                        "original sandbox was never recorded, so resuming one "
                        "needs an explicit --sandbox.")
    p.add_argument("--follow", action="store_true",
                   help="with --group: print each member state change, then a "
                        "terminal group line, then exit. Pair with Monitor; the "
                        "Bash tool's 600s ceiling cannot be crossed by blocking.")
    p.add_argument("--interval", type=float, default=1.0,
                   help="seconds between polls while following (default: 1.0)")
    p.add_argument("--follow-timeout", type=float,
                   help="stop following after this many seconds and print "
                        "group.still-running. No default: the follow ends only "
                        "when the group does.")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("log", help="what it is doing right now — events since a cursor")
    add_common(p)
    p.add_argument("--run", metavar="REF",
                   help="a run id, a thread id, or a run-id prefix (newest "
                        "wins). Omitted, this project's only live run is used.")
    p.add_argument("--since", type=int, default=0,
                   help="resume from the byte offset a previous call printed as "
                        "`# cursor=<n>` (default: 0, the whole log). Only "
                        "complete lines are consumed, so nothing is duplicated "
                        "or skipped however often you poll.")
    p.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL,
                   help="how much of each event to print (default: compact). "
                        "compact: lifecycle, the agent's own messages in full, "
                        "each command line with its exit code and output size, "
                        "changed paths, errors, usage — and no command output. "
                        "normal: adds output for commands that exited non-zero. "
                        "full: adds capped output for every item. "
                        "raw: the events verbatim.")
    p.add_argument("--follow", action="store_true",
                   help="print events as they arrive, then one terminal line "
                        "(run.completed / run.failed / run.interrupted / "
                        "run.orphaned, with the exit code) before exiting")
    p.add_argument("--interval", type=float, default=1.0,
                   help="seconds between polls while following (default: 1.0)")
    p.add_argument("--follow-timeout", type=float,
                   help="stop following after this many seconds and print "
                        "run.still-running instead of a terminal line")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("show", help="one item's full output, when the summary looks wrong")
    add_common(p)
    p.add_argument("--run", required=True, metavar="REF",
                   help="required: item ids restart at item_0 on every "
                        "invocation, so an item id alone identifies nothing")
    p.add_argument("--item", required=True, metavar="ITEM_ID",
                   help="the item to fetch, as printed by `log` (item_0, "
                        "item_1, …). An unknown id is refused with the run's "
                        "available items listed.")
    p.add_argument("--max-bytes", type=int, default=SHOW_MAX_BYTES,
                   help=f"cap on the output returned (default: {SHOW_MAX_BYTES}). "
                        "Truncation is reported, never silent.")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stop", help="interrupt a run, a group, or everything, by process group")
    add_common(p)
    p.add_argument("--run", action="append", metavar="REF",
                   help="a run to interrupt. Repeatable. No default target: one "
                        "of --run, --group or --all is required.")
    p.add_argument("--group",
                   help="interrupt every member of a batch group, including one "
                        "still waiting on its predecessor under --as-ready")
    p.add_argument("--all", action="store_true",
                   help="interrupt every non-terminal run in this project's "
                        "registry")
    p.add_argument("--grace", type=float, default=5.0,
                   help="seconds to wait after SIGINT before SIGTERM, then 3s "
                        "before SIGKILL (default: 5.0). Signals go to the run's "
                        "recorded process group, never to a matched process "
                        "name, so one run's stop cannot reach another's.")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("result", help="what it concluded — final message, usage, parsed schema JSON")
    add_common(p)
    p.add_argument("--run", metavar="REF",
                   help="one run's full final message. No default target: one of "
                        "--run or --group is required.")
    p.add_argument("--group", help="collect every member of a batch group, capped "
                                   "per run, plus the paths more than one wrote")
    p.set_defaults(func=cmd_result)

    p = sub.add_parser("batch", help="several runs as one name you can watch, collect and stop together")
    bsub = p.add_subparsers(dest="batch_cmd", required=True)
    b = bsub.add_parser("start", help="start N runs as one addressable group")
    add_common(b); add_run_options(b, kind="start")
    b.add_argument("--group", required=True,
                   help="name for this group. Single-use per project: reusing one "
                        "would make membership and start order ambiguous, and "
                        "--resume-from pairs positionally against exactly that list.")
    b.add_argument("--task", action="append",
                   help="a prompt. Repeatable. Always kind=start.")
    b.add_argument("--tasks-file",
                   help="JSONL, one task object per line, for long or "
                        "heterogeneous tasks. Fields: " + ", ".join(TASK_FIELDS))
    b.add_argument("--force", action="store_true",
                   help="allow a resume task to start a second turn on a thread "
                        "that already has a live one")
    b.add_argument("--worktree", action="store_true",
                   help="give every writing member its own git worktree even if "
                        "there is only one of them")
    b.add_argument("--no-worktree", action="store_true",
                   help="never assign worktrees; every member shares the "
                        "caller's tree")
    b.add_argument("--base",
                   help="commit or ref the worktrees are cut from (default HEAD)")
    b.add_argument("--resume-from", metavar="GROUP",
                   help="continue an earlier group: task i resumes member i of "
                        "that group, in its start order, keeping its thread and "
                        "its working directory. One task per started member.")
    b.add_argument("--as-ready", action="store_true",
                   help="with --resume-from: start each member as soon as the "
                        "member it continues reaches a terminal state, instead "
                        "of refusing until every one of them has. Any terminal "
                        "state releases, including a failure. --timeout still "
                        "bounds only the Codex turn, never the wait; "
                        "`stop --group` ends a wait.")
    b.set_defaults(func=cmd_batch_start)

    b = bsub.add_parser("clean", help="remove a finished group's worktrees")
    add_common(b)
    b.add_argument("--group", required=True,
                   help="the group to clean up. Removing its worktrees is also "
                        "what releases the name for reuse.")
    b.add_argument("--force", action="store_true",
                   help="remove worktrees that still hold uncommitted changes, "
                        "and ignore live members and dependent groups. This "
                        "discards work nothing else has a copy of.")
    b.set_defaults(func=cmd_batch_clean)

    p = sub.add_parser("models", help="which models and efforts exist here, before you name one")
    add_common(p)
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("doctor", help="why is Codex not behaving — env, auth, sandbox, paths")
    add_common(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("__supervise", help=argparse.SUPPRESS)
    p.add_argument("--run-dir", required=True)
    p.set_defaults(func=lambda a: sys.exit(supervise(Path(a.run_dir))))

    return ap


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
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
