#!/usr/bin/env python3
"""Drive the OpenAI Codex CLI as a managed subagent.

Python 3.10+, standard library only. Every subcommand prints exactly one line of
JSON on stdout, except `log`, which prints compact text plus a trailing
`# cursor=<n>` line — JSON framing per event would itself be a meaningful
fraction of the context the filter exists to save.

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
    TERMINAL_STATES, find_run, iter_runs, read_meta, reap, resolve_project,
    resolve_runs_dir, unreadable_runs, update_meta_if,
)
from _run import (  # noqa: E402
    WRITING_SANDBOXES, create_run, refuse_concurrent_turn, resolve_implicit_run,
    run_row,
)
from _util import (  # noqa: E402
    clip, codex_home, emit, fail, git_toplevel, now_iso, pid_alive,
)

# `show --item` default cap. A silently truncated blob is worse than a loud one,
# so truncation is always announced along with how much was withheld.
SHOW_MAX_BYTES = 20000


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

    # F4's second reproduction: two turns run concurrently on one thread, rc 0,
    # no warning. Refuse a second live turn on the same thread unless the
    # caller explicitly opts in.
    refuse_concurrent_turn(runs_dir, thread_ref, args.force)

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
    chosen = [n for n, v in (("--uncommitted", args.uncommitted), ("--base", args.base),
                             ("--commit", args.commit), ("prompt", args.prompt)) if v]
    if len(chosen) != 1:
        fail("review takes exactly one of --uncommitted, --base <ref>, --commit <sha>, "
             "or a prompt; the Codex CLI rejects combinations", given=chosen)
    if args.title and not args.commit:
        fail("--title is only valid with --commit")

    if args.uncommitted:
        review_args = ["--uncommitted"]
    elif args.base:
        review_args = ["--base", args.base]
    elif args.commit:
        review_args = ["--commit", args.commit]
        if args.title:
            review_args += ["--title", args.title]
    else:
        review_args = []
    emit(create_run(args, kind="review", review_args=review_args))


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

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
    rows = []
    if args.run:
        rd, m = find_run(runs_dir, args.run)
        if not m:
            fail(f"no such run: {args.run}", runs_dir=str(runs_dir))
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
    running = [r["run_id"] for r in rows if r["state"] in ("running", "stalled")]
    done = [r["run_id"] for r in rows if r["state"] == "completed"]
    failed = [r["run_id"] for r in rows
              if r["state"] in ("failed", "interrupted", "orphaned", "timed_out")]
    known = {r["thread_id"] for r in rows}

    display_rows = rows
    runs_truncated = 0
    if not args.run and not args.all and total_runs > 20:
        tail = rows[-20:]
        # Truncate the display list only — a non-terminal row must survive
        # truncation no matter how old, or `running` above and `runs` below
        # would disagree about which runs are still alive.
        kept_live = [r for r in rows[:-20] if r["state"] not in TERMINAL_STATES]
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
        out["external_threads"] = [t for t in query_threads(cwd_filter=str(project))
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
        if not meta:
            fail(f"no such run: {args.run}", runs_dir=str(runs_dir))
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
        if st in TERMINAL_STATES:
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
    if not meta:
        fail(f"no such run: {args.run}", runs_dir=str(runs_dir))

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
    m = update_meta_if(run_dir, ("running", "starting", "stalled"),
                       state="interrupted", ended_at=now_iso())
    result["state"] = m.get("state")
    result["thread_id"] = m.get("thread_id")
    return result


def cmd_stop(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if args.run:
        targets = []
        for ref in args.run:
            rd, m = find_run(runs_dir, ref)
            if not m:
                fail(f"no such run: {ref}", runs_dir=str(runs_dir))
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
            if m.get("state") in ("running", "starting", "stalled"):
                targets.append((rd, m))
    elif args.all:
        targets = []
        for rd, m in iter_runs(runs_dir):
            m = reap(rd, m)
            if m.get("state") in ("running", "starting", "stalled"):
                targets.append((rd, m))
    else:
        fail("stop needs --run <id> (repeatable), --group <name>, or --all")
    emit({"stopped": [signal_run(rd, m, grace=args.grace) for rd, m in targets],
          "claude_session_id": session})


# --------------------------------------------------------------------------
# result
# --------------------------------------------------------------------------

def cmd_result(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    if args.group:
        return cmd_result_group(args, project, runs_dir)
    if not args.run:
        fail("result needs --run <id> or --group <name>")
    rd, meta = find_run(runs_dir, args.run)
    if not meta:
        fail(f"no such run: {args.run}", runs_dir=str(runs_dir))
    meta = reap(rd, meta)
    info = scan_progress(rd / "events.jsonl")

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
    if meta.get("state") not in TERMINAL_STATES:
        out["note"] = f"run is still {meta.get('state')}; this is a partial result"

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
                blockers.append("`codex login status` exited non-zero — not authenticated")
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
        by_cwd = {}
        for rd, m in iter_runs(runs_dir):
            # Reaped, like `concurrent_writers`. meta.json says `running` until
            # something notices the supervisor died, so grouping on it as
            # written names dead runs as live writers — and this is the report
            # a caller consults precisely when they suspect something is stuck,
            # which is exactly when stale state is most likely.
            m = reap(rd, m)
            if m.get("state") in TERMINAL_STATES:
                continue
            by_cwd.setdefault(m.get("cwd"), []).append(m)
        for cwd, ms in sorted(by_cwd.items(), key=lambda kv: str(kv[0])):
            writers = [m for m in ms if m.get("sandbox") in WRITING_SANDBOXES]
            if len(ms) > 1 and writers:
                warnings.append(
                    f"{len(ms)} live runs share {cwd}, {len(writers)} of which can "
                    f"write to it: {', '.join(m.get('run_id') for m in ms)}. None of "
                    f"them can tell another agent's change from its own. Runs in "
                    f"their own worktrees are exempt and will not appear here.")

        live_wt = [p for p in worktrees_registered(project) if p.exists()]
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
    p.add_argument("--runs-dir")
    p.add_argument("--project")


def add_run_options(p, *, kind):
    p.add_argument("--label")
    p.add_argument("--sandbox", choices=SANDBOX_MODES)
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--inherit-config", action="store_true")
    p.add_argument("--isolate", action="store_true")
    p.add_argument("--priority", dest="priority", action="store_true", default=None)
    p.add_argument("--no-priority", dest="priority", action="store_false")
    p.add_argument("--schema")
    p.add_argument("--config", action="append", metavar="k=v")
    p.add_argument("--foreground", action="store_true")
    p.add_argument("--timeout", type=float,
                   help="give the run this many seconds, then SIGINT its process "
                        "group and record state=timed_out. Works in background "
                        "and foreground. No default: no flag, no deadline.")
    p.add_argument("--no-preamble", action="store_true")
    if kind in ("start", "resume"):
        p.add_argument("--image", action="append")
        p.add_argument("--prompt-file")
    if kind == "start":
        p.add_argument("--cwd")
        p.add_argument("--add-dir", action="append")


def build_parser():
    ap = argparse.ArgumentParser(prog="codex_bridge.py",
                                 description="Drive the OpenAI Codex CLI as a managed subagent.")
    ap.subparser_map = {}
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="start a new Codex thread")
    add_common(p); add_run_options(p, kind="start")
    p.add_argument("prompt", nargs="?")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("resume", help="continue an existing Codex thread")
    add_common(p); add_run_options(p, kind="resume")
    p.add_argument("--last", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="allow a second turn on a thread that already has one running")
    p.add_argument("rest", nargs="*", metavar="[REF] PROMPT",
                   help="run id / thread id / thread name, then the prompt; "
                        "with --last, just the prompt")
    p.set_defaults(func=cmd_resume, cwd=None, add_dir=None, ref=None, prompt=None)
    ap.subparser_map["resume"] = p

    p = sub.add_parser("review", help="run `codex exec review`")
    add_common(p); add_run_options(p, kind="review")
    p.add_argument("--uncommitted", action="store_true")
    p.add_argument("--base")
    p.add_argument("--commit")
    p.add_argument("--title")
    p.add_argument("--cwd")
    p.add_argument("prompt", nargs="?")
    p.set_defaults(func=cmd_review, image=None, add_dir=None, prompt_file=None)

    p = sub.add_parser("status", help="list runs with state, idle time and usage")
    add_common(p)
    p.add_argument("--run")
    p.add_argument("--thread")
    p.add_argument("--group", help="report on one batch group's members only")
    p.add_argument("--all", action="store_true")
    p.add_argument("--include-external", action="store_true")
    p.add_argument("--follow", action="store_true",
                   help="with --group: print each member state change, then a "
                        "terminal group line, then exit. Pair with Monitor; the "
                        "Bash tool's 600s ceiling cannot be crossed by blocking.")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--follow-timeout", type=float)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("log", help="filtered, incremental event log")
    add_common(p)
    p.add_argument("--run")
    p.add_argument("--since", type=int, default=0)
    p.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL)
    p.add_argument("--follow", action="store_true")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--follow-timeout", type=float)
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("show", help="full output of one event item")
    add_common(p)
    p.add_argument("--run", required=True)
    p.add_argument("--item", required=True)
    p.add_argument("--max-bytes", type=int, default=SHOW_MAX_BYTES)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stop", help="interrupt a run by process group")
    add_common(p)
    p.add_argument("--run", action="append")
    p.add_argument("--group")
    p.add_argument("--all", action="store_true")
    p.add_argument("--grace", type=float, default=5.0)
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("result", help="final message, usage, and schema JSON")
    add_common(p)
    p.add_argument("--run")
    p.add_argument("--group", help="collect every member of a batch group, capped "
                                   "per run, plus the paths more than one wrote")
    p.set_defaults(func=cmd_result)

    p = sub.add_parser("batch", help="start and manage a group of runs")
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
    b.set_defaults(func=cmd_batch_start)

    b = bsub.add_parser("clean", help="remove a finished group's worktrees")
    add_common(b)
    b.add_argument("--group", required=True)
    b.add_argument("--force", action="store_true",
                   help="remove worktrees that still hold uncommitted changes, "
                        "and ignore live members and dependent groups. This "
                        "discards work nothing else has a copy of.")
    b.set_defaults(func=cmd_batch_clean)

    p = sub.add_parser("doctor", help="diagnose the Codex environment")
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
