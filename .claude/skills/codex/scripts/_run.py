"""Building a run, and describing one.

One function does the first job — `create_run` — and everything about a run's
identity is decided inside it: which directory it runs in, which settings it
carries, whether it gets its own worktree, and what prompt Codex actually
receives. `start`, `resume`, `review` and every batch member funnel through it,
which is what keeps a batch member and a hand-typed `start` from drifting apart.

`run_row` does the second: the one-line summary that `status` prints, for a
single run and for a group member alike.

This module is deliberately below the batch layer in the import order.
`_batch.py` needs both of these; putting them here rather than in the CLI
entrypoint is what lets the batch subsystem live in one file without importing
the entrypoint back.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from _codex import THREAD_ID_WAIT, apply_preamble, build_argv, spawn_supervised, supervise
from _events import scan_progress
from _registry import (
    TERMINAL_STATES, claim_run_dir, ensure_runs_dir, iter_runs, read_meta, reap,
    resolve_project, resolve_runs_dir, write_meta,
)
from _util import clip, fail, git_toplevel, is_within, now_iso

WRITING_SANDBOXES = ("workspace-write", "danger-full-access")


def concurrent_writers(runs_dir, cwd, exclude_run_id=None):
    """Other live runs that can write to this same directory.

    Compared on each run's recorded `cwd`, never on its git top level: every
    worktree of one repository shares a top level, so that comparison would
    warn about the very isolation that makes the situation safe.

    Reported, never refused (D17). Concurrency here is sometimes exactly what
    the caller wants — but it is never something they can see, and a session
    that cannot see it will not go looking. Measured: an e2e session continued
    three writing threads with three `resume` calls into one directory and
    escaped damage only because the three edits landed in three different
    files. `resume` has no worktree option, so nothing but this could have
    told it.
    """
    out = []
    for rd, m in iter_runs(runs_dir):
        if m.get("run_id") == exclude_run_id:
            continue
        if m.get("sandbox") not in WRITING_SANDBOXES:
            continue
        if not (is_within(m.get("cwd"), cwd) or is_within(cwd, m.get("cwd"))):
            continue
        # Reaped before being judged alive, like every other place that turns
        # registry state into a liveness claim. meta.json says `running` until
        # something notices the supervisor died, so trusting it as written
        # names dead runs as live writers — and a warning that cries wolf is
        # one the caller learns to skip past, which costs more than not having
        # it. Reaped only for the few candidates that already matched the
        # directory and the sandbox, so this is not a registry-wide write.
        m = reap(rd, m)
        if m.get("state") in TERMINAL_STATES:
            continue
        out.append({"run_id": m.get("run_id"), "state": m.get("state"),
                    "sandbox": m.get("sandbox"), "group": m.get("group")})
    return out
from _worktree import (
    add as worktree_add, uncommitted_count as worktree_uncommitted,
)

# Advisory only. `idle_seconds` is always reported alongside it, so this number
# never decides anything by itself: one long `command_execution` is legitimately
# silent, which is why silence alone is not failure — silence plus no
# in-progress item is.
STALL_SECONDS = 300


def read_prompt(args) -> str:
    if getattr(args, "prompt_file", None):
        try:
            return Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as e:
            fail(f"cannot read prompt file: {e}")
    p = getattr(args, "prompt", None)
    if p == "-" or p is None:
        if not sys.stdin.isatty():
            data = sys.stdin.read()
            if data.strip():
                return data
        if p is None:
            return ""
    return p or ""


def resolve_implicit_run(candidates):
    """D27: pick a run nobody named, without silently crossing into another
    run's identity.

    `candidates` must be oldest-first (`iter_runs` order). Reaping first means
    the decision is made on live state, not a meta.json a dead supervisor never
    updated. Exactly one non-terminal run is unambiguous. Zero non-terminal
    runs falls back to the newest run, and the caller must echo which one it
    picked. Two or more is exactly the F4 reproduction — a read-only caller
    silently inheriting another run's label and sandbox — so it fails loud
    with the candidate list instead of guessing.
    """
    reaped = [(rd, reap(rd, m)) for rd, m in candidates]
    non_terminal = [(rd, m) for rd, m in reaped if m.get("state") not in TERMINAL_STATES]
    if len(non_terminal) == 1:
        rd, m = non_terminal[0]
        return rd, m, "the only non-terminal run"
    if len(non_terminal) >= 2:
        fail("multiple non-terminal runs; an implicit target is ambiguous — "
             "pass an explicit run id, thread id, or thread name",
             candidates=[{"run_id": m.get("run_id"), "label": m.get("label"),
                          "state": m.get("state"), "sandbox": m.get("sandbox"),
                          "thread_id": m.get("thread_id")} for rd, m in non_terminal])
    if not reaped:
        return None, None, None
    rd, m = reaped[-1]
    return rd, m, "the newest run (no non-terminal runs)"


def refuse_concurrent_turn(runs_dir, thread_id, force):
    """F4 reproduced two turns run concurrently on one thread: rc 0, no
    warning. A resumed run shares its parent's process group with nothing —
    two live turns on the same thread would race on the same rollout file —
    so a live turn on the target thread is refused unless the caller opts in
    with --force."""
    if not thread_id or force:
        return
    live = [reap(rd, m) for rd, m in iter_runs(runs_dir) if m.get("thread_id") == thread_id]
    live = [m for m in live if m.get("state") not in TERMINAL_STATES]
    if live:
        fail("thread already has a live turn; pass --force to run a second turn "
             "concurrently", thread_id=thread_id,
             live_runs=[{"run_id": m.get("run_id"), "state": m.get("state")}
                        for m in live])


def create_run(args, *, kind: str, base=None, review_args=None, thread_ref=None,
               group=None, batch=None, worktree_base=None):
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))

    cwd = (Path(args.cwd).expanduser().resolve() if getattr(args, "cwd", None)
           else (Path(base["cwd"]) if base else project))
    if not cwd.is_dir():
        fail(f"cwd does not exist: {cwd}")

    prompt = read_prompt(args)
    if kind != "review" and not prompt.strip():
        fail("a prompt is required (positional, --prompt-file, or stdin via '-')")

    if kind == "resume" and not thread_ref:
        # `build_argv` omits the ref when there is none, producing a bare
        # `codex exec resume` that fails asynchronously — after this command
        # has already reported a run started. A run whose Codex process died
        # before emitting `thread.started` has a run id and a terminal state
        # but no conversation, and that is the usual way to get here.
        fail("nothing to resume: that run never recorded a thread id, so there "
             "is no conversation to continue",
             run_id=(base or {}).get("run_id"), state=(base or {}).get("state"))

    isolated = base["isolated"] if base else True
    if getattr(args, "inherit_config", False):
        isolated = False
    if getattr(args, "isolate", False):
        isolated = True

    sandbox = args.sandbox or (base["sandbox"] if base else "workspace-write")
    if getattr(args, "priority", None) is not None:
        priority = args.priority
    elif base and isolated == base["isolated"]:
        # Isolation state unchanged from the parent: inherit its priority like
        # every other recorded setting.
        priority = base.get("priority")
    else:
        # No base, or --inherit-config/--isolate just flipped isolation: priority
        # is only re-injected to undo what isolation removed, so it follows the
        # new isolation state rather than carrying over the parent's value.
        priority = isolated

    try:
        run_id, run_dir = claim_run_dir(
            runs_dir, args.label or (base.get("label") if base else None))
    except FileExistsError as e:
        fail(str(e), runs_dir=str(runs_dir))

    meta = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "thread_id": base.get("thread_id") if base else None,
        "parent_run_id": base.get("run_id") if base else None,
        "kind": kind,
        "label": args.label or (base.get("label") if base else None),
        "prompt_preview": clip(prompt, 300),
        "cwd": str(cwd),
        "project": str(project),
        "sandbox": sandbox,
        "model": args.model or (base.get("model") if base else None),
        "effort": args.effort or (base.get("effort") if base else None),
        "isolated": isolated,
        "priority": priority,
        "schema_path": (str(Path(args.schema).expanduser().resolve())
                        if getattr(args, "schema", None)
                        else (base.get("schema_path") if base else None)),
        "images": [str(Path(i).expanduser().resolve())
                   for i in (getattr(args, "image", None) or [])],
        "add_dirs": [str(Path(d).expanduser().resolve())
                     for d in (getattr(args, "add_dir", None) or [])],
        "extra_config": (list(args.config) if getattr(args, "config", None)
                         else (base.get("extra_config") if base else [])) or [],
        # Only where Codex's own guard does not apply. The wrapper does not
        # silently disable a Codex safety default just to keep its own argv
        # uniform.
        "skip_git_repo_check": git_toplevel(cwd) is None,
        "preamble": not args.no_preamble,
        "claude_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"),
        "foreground": bool(getattr(args, "foreground", False)),
        "timeout_seconds": getattr(args, "timeout", None),
        # The manifest is the authority on membership and order; this copy lets
        # a single run say which group it belongs to without one, so `status`
        # can still answer that after a manifest is lost or hand-deleted.
        "group": group,
        "worktree": None,       # filled in below, once nothing can still refuse
        "started_at": now_iso(),
        "ended_at": None, "exit_code": None, "state": "starting",
        "codex_pid": None, "supervisor_pid": None, "pgid": None,
    }

    if base and args.sandbox and args.sandbox != base["sandbox"]:
        # A sandbox change is never silent, in either direction.
        meta["sandbox_changed_from"] = base["sandbox"]

    if meta["schema_path"] and not Path(meta["schema_path"]).exists():
        fail(f"schema file not found: {meta['schema_path']}")
    for img in meta["images"]:
        if not Path(img).exists():
            fail(f"image not found: {img}")

    # Cut the worktree last, after every check that can still refuse this run.
    # It cannot be cut before `claim_run_dir` — it lives at `<run_dir>/wt`, and
    # the run id naming that directory does not exist until then — but cutting
    # it any earlier than here leaks. A member rejected afterwards never gets a
    # meta.json and so never gets a run_id, and `batch clean` resolves
    # worktrees through the manifest's run ids: the worktree would survive
    # every documented removal path while `batch clean` reported the group
    # fully cleaned.
    wt_info = None
    if worktree_base:
        source, wt = cwd, run_dir / "wt"
        ok, err = worktree_add(source, wt, worktree_base)
        if not ok:
            fail(f"could not create the worktree for this member: {err}",
                 base=worktree_base, path=str(wt))
        cwd = wt
        wt_info = {"path": str(wt), "base": worktree_base,
                   "uncommitted_in_caller_tree": worktree_uncommitted(source),
                   "source": str(source)}
        meta["cwd"] = str(cwd)
        meta["worktree"] = wt_info

    if batch and wt_info:
        batch = {**batch, "worktree": wt_info["path"], "base": wt_info["base"],
                 "uncommitted": wt_info["uncommitted_in_caller_tree"]}
    send = (apply_preamble(prompt, meta["preamble"], batch=batch)
            if prompt.strip() else None)
    meta["argv"] = build_argv(meta, kind=kind, prompt=send,
                              thread_ref=thread_ref, review_args=review_args)
    write_meta(run_dir, meta)

    if meta["foreground"]:
        supervise(run_dir, timeout=getattr(args, "timeout", None))
        m = read_meta(run_dir) or {}
        info = scan_progress(run_dir / "events.jsonl")
        return {"run_id": run_id, "thread_id": m.get("thread_id"),
                "state": m.get("state"), "exit_code": m.get("exit_code"),
                "events": str(run_dir / "events.jsonl"), "project": str(project),
                "cwd": str(cwd), "sandbox": sandbox, "isolated": isolated,
                "last_agent_message": info["last_agent_message"],
                "usage": info["usage"]}

    spawn_supervised(run_dir)
    # Hand back a usable handle as soon as the thread id exists, and never block
    # the caller past that window.
    deadline = time.time() + THREAD_ID_WAIT
    thread_id = None
    while time.time() < deadline:
        m = read_meta(run_dir) or {}
        thread_id = m.get("thread_id")
        if thread_id or m.get("state") in TERMINAL_STATES:
            break
        time.sleep(0.05)
    m = read_meta(run_dir) or {}
    out = {"run_id": run_id, "thread_id": thread_id,
           "state": m.get("state", "starting"),
           "events": str(run_dir / "events.jsonl"), "project": str(project),
           "cwd": str(cwd), "sandbox": sandbox, "isolated": isolated}
    if group:
        out["group"] = group
    if wt_info:
        out["worktree"] = wt_info
    if "sandbox_changed_from" in meta:
        out["sandbox_changed_from"] = meta["sandbox_changed_from"]
    if sandbox in WRITING_SANDBOXES and not wt_info:
        others = concurrent_writers(runs_dir, cwd, exclude_run_id=run_id)
        if others:
            out["concurrent_writers"] = others
            out["concurrent_writers_note"] = (
                f"{len(others)} other live run(s) can write to {cwd}. None of you "
                "can tell another agent's change from your own. `batch start` "
                "assigns a worktree per writing member — including when "
                "continuing an earlier group with --resume-from, which is the "
                "only isolated way to resume several writers at once.")
    return out


def run_row(run_dir: Path, meta: dict, project: Path):
    meta = reap(run_dir, meta)
    events_path = run_dir / "events.jsonl"
    info = scan_progress(events_path)
    now = time.time()

    elapsed = None
    try:
        t0 = datetime.fromisoformat(meta["started_at"].replace("Z", "+00:00")).timestamp()
        elapsed = int(now - t0)
    except Exception:
        pass
    idle = None
    if events_path.exists() and events_path.stat().st_size > 0:
        idle = int(now - events_path.stat().st_mtime)

    state = meta.get("state")
    if state == "running" and idle is not None and idle >= STALL_SECONDS:
        state = "stalled"

    stderr_tail = None
    sp = run_dir / "stderr.log"
    if sp.exists() and sp.stat().st_size:
        txt = sp.read_text(encoding="utf-8", errors="replace")
        # Codex always writes `Reading additional input from stdin...` here when
        # stdin is not a TTY. It is normal output, not failure; surfacing it as
        # an error would train the reader to ignore this field entirely.
        txt = "\n".join(l for l in txt.splitlines()
                        if l.strip() and "Reading additional input from stdin" not in l)
        stderr_tail = txt[-800:] or None

    # Measured: review runs report all-zero usage even after real work. Zero
    # would be a wrong number; null is a true one.
    usage = info["usage"]
    review_zero = meta.get("kind") == "review" and usage is not None and not any(usage.values())

    row = {
        "run_id": meta.get("run_id"),
        "thread_id": meta.get("thread_id") or info["thread_id"],
        "parent_run_id": meta.get("parent_run_id"), "kind": meta.get("kind"),
        "label": meta.get("label"), "state": state,
        "codex_pid": meta.get("codex_pid"), "pgid": meta.get("pgid"),
        "started_at": meta.get("started_at"), "ended_at": meta.get("ended_at"),
        "elapsed_seconds": elapsed, "idle_seconds": idle,
        "exit_code": meta.get("exit_code"), "sandbox": meta.get("sandbox"),
        "model": meta.get("model"), "effort": meta.get("effort"),
        "isolated": meta.get("isolated"),
        "cwd": meta.get("cwd"),
        "usage": None if review_zero else usage,
        "turns_completed": info["turns_completed"], "commands": info["commands"],
        "files_changed": info["files_changed"], "config_error_events": info["errors"],
        "in_progress_item": info["in_progress_item"],
        "last_agent_message": clip(info["last_agent_message"] or "", 400) or None,
        # F8: `turn.failed` was parsed by _events.py and never surfaced, so a
        # failed run showed `message: null` and the reason needed a second
        # `log` call. Clipped like the neighbouring `turn.failed` log line.
        "turn_failed": (clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400)
                        if info["turn_failed"] else None),
        "events": str(events_path),
    }
    if meta.get("group"):
        # A run's group is the one fact a later session cannot re-derive.
        # `create_run` records it here precisely so `status` can answer it, and
        # for a while `status` did not: a session recovering a batch it did not
        # start saw N unrelated runs, concluded they were individual `start`s,
        # and had no group name to give `--resume-from`. Measured in an e2e
        # session, which then reasoned correctly from that false premise and
        # continued three writers into one shared directory.
        row["group"] = meta["group"]
    if meta.get("worktree"):
        row["worktree"] = meta["worktree"]["path"]
    if review_zero:
        row["usage_note"] = "review runs report zero usage; unavailable, not free"
    if meta.get("sandbox_changed_from"):
        row["sandbox_changed_from"] = meta["sandbox_changed_from"]
    if stderr_tail:
        row["stderr_tail"] = stderr_tail
    if meta.get("error"):
        row["error"] = meta["error"]
    return row


