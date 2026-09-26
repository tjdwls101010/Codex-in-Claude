"""Building a run: `start`, `resume` and every batch member go through `create_run`, so they cannot drift apart.

Four stages, ordered around the thread's turn lock: everything that can still refuse a run happens before the lock (and costs nothing); publishing the run happens inside it, together with the check that the thread is free; everything slow — cutting a worktree — happens after it, and only once the run is published, so a checkout always belongs to a run something can find.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from codex.codex_cli.argv import SANDBOX_MODES, WRITING_SANDBOXES, apply_preamble, build_argv
from codex.codex_cli.catalog import check_model_effort, model_catalog
from codex.codex_cli.config import user_defaults
from codex.codex_cli.events import first_thread_id
from codex.errors import Refusal
from codex.git.repo import git_toplevel, resolve_project, uncommitted_count as worktree_uncommitted
from codex.git.worktree import add as worktree_add
from codex.registry.locks import thread_turn_lock
from codex.registry.runs import (
    TERMINAL_STATES, claim_run_dir, ensure_runs_dir, is_live, iter_runs, read_meta, reap,
    resolve_runs_dir, still_writing, unreadable_runs, write_meta,
)
from codex.runs import settings
from codex.runs.supervisor import THREAD_ID_WAIT, spawn_supervised
from codex.util import clip, is_within, now_iso


def concurrent_writers(runs_dir, cwd, exclude_run_id=None):
    """Other live runs that can write in or around this directory — reported, never refused.

    Compared on each run's recorded cwd in both directions, never on the git top level, which every worktree of a repository shares.
    """
    out = []
    for rd, m in iter_runs(runs_dir):
        if m.get("run_id") == exclude_run_id or m.get("sandbox") not in WRITING_SANDBOXES:
            continue
        if not (is_within(m.get("cwd"), cwd) or is_within(cwd, m.get("cwd"))):
            continue
        m = reap(rd, m)
        if not is_live(m):
            continue
        out.append({"run_id": m.get("run_id"), "state": m.get("state"),
                    "sandbox": m.get("sandbox"), "group": m.get("group"),
                    **({"codex_still_running": True} if still_writing(m) else {})})
    return out


def read_prompt(args) -> str:
    if getattr(args, "prompt_file", None):
        try:
            return Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as e:
            raise Refusal(f"cannot read prompt file: {e}")
    p = getattr(args, "prompt", None)
    if p == "-" or p is None:
        if not sys.stdin.isatty():
            data = sys.stdin.read()
            if data.strip():
                return data
        if p is None:
            return ""
    return p or ""


def thread_of_unreadable(run_dir):
    """The thread a run with an unparseable meta.json was on, recovered from its event stream (a separate file), or None."""
    try:
        return first_thread_id(run_dir / "events.jsonl")
    except Exception:
        return None


def refuse_concurrent_turn(runs_dir, thread_id, force):
    """Refuse a second live turn on one thread — two turns would append to one rollout file — unless `--force`. Called only inside `thread_turn_lock`.

    Matched on `resume_ref` as well as `thread_id`, because a resume of a ref this registry has never seen publishes before the real id is known. A run whose meta.json will not parse blocks only when its thread cannot be shown to be another one: unknown is not free.
    """
    if not thread_id or force:
        return
    live = [reap(rd, m) for rd, m in iter_runs(runs_dir)
            if thread_id in (m.get("thread_id"), m.get("resume_ref"))]
    live = [{"run_id": m.get("run_id"), "state": m.get("state"),
             **({"codex_still_running": True} if still_writing(m) else {})}
            for m in live if is_live(m)]
    if live:
        raise Refusal("thread already has a live turn; wait for it, or pass --force to run a second turn at once", thread_id=thread_id, live_runs=live)
    blind = [name for name in unreadable_runs(runs_dir)
             if thread_of_unreadable(runs_dir / name) in (None, thread_id)]
    if blind:
        raise Refusal("cannot tell whether this thread is free: the runs in `unreadable_runs` have a meta.json that will not parse and may be on this thread; repair or remove them, or pass --force",
                      thread_id=thread_id,
                      unreadable_runs=[{"run_id": name, "run_dir": str(runs_dir / name)} for name in blind])


def resolve_settings(args, *, kind, base, project, thread_ref):
    """Stage 1 — what this run will be. Nothing here writes or claims anything, so a refusal costs nothing."""
    cwd = (Path(args.cwd).expanduser().resolve() if getattr(args, "cwd", None)
           else (Path(base["cwd"]) if base else project))
    if not cwd.is_dir():
        raise Refusal(f"cwd does not exist: {cwd}")

    prompt = read_prompt(args)
    if not prompt.strip():
        raise Refusal("a prompt is required (positional, --prompt-file, or stdin via '-')")

    # Checked here rather than once the run is published: a refusal after the claim would leave a run directory with no meta.json, which no listing shows.
    schema_path = (str(Path(args.schema).expanduser().resolve()) if getattr(args, "schema", None)
                   else (base.get("schema_path") if base else None))
    if schema_path and not Path(schema_path).exists():
        raise Refusal(f"schema file not found: {schema_path}")
    images = [str(Path(i).expanduser().resolve()) for i in (getattr(args, "image", None) or [])]
    for img in images:
        if not Path(img).exists():
            raise Refusal(f"image not found: {img}")

    if kind == "resume" and not thread_ref:
        # A bare `codex exec resume` would fail after this command already reported a run started.
        raise Refusal("nothing to resume: that run has no thread id; `status --run` shows why",
                      run_id=(base or {}).get("run_id"), state=(base or {}).get("state"))

    r = settings.resolve(sandbox=args.sandbox, model=args.model, effort=args.effort,
                         priority=getattr(args, "priority", None),
                         inherit_config=getattr(args, "inherit_config", False),
                         base=base, user=user_defaults())
    adopted = r["adopted"]
    # Guarded because the catalog lookup is a subprocess on the path of every run.
    if adopted["model"] or adopted["effort"]:
        check_model_effort(adopted["model"], adopted["effort"], catalog=model_catalog(),
                           model_source=adopted["model_source"], effort_source=adopted["effort_source"])

    return {"cwd": cwd, "prompt": prompt, "isolated": r["isolated"],
            "sandbox": r["sandbox"], "model": r["model"], "effort": r["effort"],
            "service_tier": r["service_tier"], "schema_path": schema_path, "images": images}


def publish_run(args, s, *, kind, base, project, runs_dir, thread_ref, group):
    """Stage 2 — under the thread's turn lock, check the thread is free, claim a run directory and publish meta.json. Returns `(run_id, run_dir, meta)`."""
    with thread_turn_lock(runs_dir, thread_ref):
        refuse_concurrent_turn(runs_dir, thread_ref, getattr(args, "force", False))
        # A thread this registry never recorded has no sandbox to re-assert, and inventing a write policy cannot be undone. Skipped when a run is unreadable: "never recorded" is a claim about the whole registry.
        if (kind == "resume" and base is None and not getattr(args, "sandbox", None)
                and not unreadable_runs(runs_dir)):
            raise Refusal(f"thread {thread_ref} is not in this registry, so its sandbox was never recorded; pass --sandbox, which is recorded from then on",
                          thread=thread_ref, sandbox=sorted(SANDBOX_MODES))
        try:
            run_id, run_dir = claim_run_dir(runs_dir, args.label or (base.get("label") if base else None))
        except FileExistsError as e:
            raise Refusal(str(e), runs_dir=str(runs_dir))

        meta = {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "thread_id": base.get("thread_id") if base else None,
            "parent_run_id": base.get("run_id") if base else None,
            "kind": kind,
            "label": args.label or (base.get("label") if base else None),
            "prompt_preview": clip(s["prompt"], 300),
            "cwd": str(s["cwd"]),
            "project": str(project),
            "sandbox": s["sandbox"],
            "model": s["model"],
            "effort": s["effort"],
            "isolated": s["isolated"],
            "service_tier": s["service_tier"],
            "schema_path": s["schema_path"],
            "images": s["images"],
            "add_dirs": [str(Path(d).expanduser().resolve()) for d in (getattr(args, "add_dir", None) or [])],
            # Only where Codex's own guard does not apply.
            "skip_git_repo_check": git_toplevel(s["cwd"]) is None,
            "claude_session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"),
            "timeout_seconds": getattr(args, "timeout", None),
            # The manifest is the authority on membership and order; this copy lets a run say which group it belongs to without one.
            "group": group,
            "worktree": None,
            "started_at": now_iso(),
            "codex_started_at": None,
            "ended_at": None, "exit_code": None, "state": "starting",
            "codex_pid": None, "supervisor_pid": None, "pgid": None,
            # What the run was launched against, even when that is not (yet) a thread id.
            "resume_ref": thread_ref,
            # Who is building this run, so `reap` can ask it rather than guess from a clock while a worktree is cut.
            "creator_pid": os.getpid(),
        }
        if base and args.sandbox and args.sandbox != base["sandbox"]:
            meta["sandbox_changed_from"] = base["sandbox"]
        write_meta(run_dir, meta)
    return run_id, run_dir, meta


def cut_worktree(run_dir: Path, meta: dict, source: Path, worktree_base: str):
    """Stage 3 — the run's own checkout at `<run_dir>/wt`, recorded in meta.json at once so `batch clean` can find it. Returns `(cwd, wt_info)`."""
    wt = run_dir / "wt"
    ok, err = worktree_add(source, wt, worktree_base)
    if not ok:
        raise Refusal(f"could not create the worktree for this member: {err}", base=worktree_base, path=str(wt))
    wt_info = {"path": str(wt), "base": worktree_base,
               "uncommitted_in_caller_tree": worktree_uncommitted(source), "source": str(source)}
    meta["cwd"] = str(wt)
    meta["worktree"] = wt_info
    write_meta(run_dir, meta)
    return wt, wt_info


def create_run(args, *, kind: str, base=None, thread_ref=None, group=None, batch=None, worktree_base=None):
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))

    s = resolve_settings(args, kind=kind, base=base, project=project, thread_ref=thread_ref)
    run_id, run_dir, meta = publish_run(args, s, kind=kind, base=base, project=project, runs_dir=runs_dir,
                                        thread_ref=thread_ref, group=group)
    cwd, wt_info = s["cwd"], None
    if worktree_base:
        cwd, wt_info = cut_worktree(run_dir, meta, s["cwd"], worktree_base)

    # Stage 4 — the argv, the last thing written before anything runs; then a handle back.
    if batch and wt_info:
        batch = {**batch, "worktree": wt_info["path"], "base": wt_info["base"],
                 "uncommitted": wt_info["uncommitted_in_caller_tree"]}
    send = apply_preamble(s["prompt"], batch=batch) if s["prompt"].strip() else None
    meta["argv"] = build_argv(meta, kind=kind, prompt=send, thread_ref=thread_ref)
    write_meta(run_dir, meta)

    spawn_supervised(run_dir)
    deadline = time.time() + THREAD_ID_WAIT
    thread_id = None
    while time.time() < deadline:
        m = read_meta(run_dir) or {}
        thread_id = m.get("thread_id")
        if thread_id or m.get("state") in TERMINAL_STATES:
            break
        time.sleep(0.05)
    m = read_meta(run_dir) or {}
    out = {"run_id": run_id, "thread_id": thread_id, "state": m.get("state", "starting"),
           "events": str(run_dir / "events.jsonl"), "project": str(project),
           "cwd": str(cwd), "sandbox": s["sandbox"], "isolated": s["isolated"]}
    if group:
        out["group"] = group
    if wt_info:
        out["worktree"] = wt_info
    if "sandbox_changed_from" in meta:
        out["sandbox_changed_from"] = meta["sandbox_changed_from"]
    if s["sandbox"] in WRITING_SANDBOXES and not wt_info:
        others = concurrent_writers(runs_dir, cwd, exclude_run_id=run_id)
        if others:
            out["concurrent_writers"] = others
            out["concurrent_writers_note"] = (
                f"{len(others)} other live run(s) can write in {cwd}, and none of you can tell another's change from your own. "
                "Only a fresh `batch start --worktree` member gets a checkout of its own; a resumed thread keeps its directory.")
    return out
