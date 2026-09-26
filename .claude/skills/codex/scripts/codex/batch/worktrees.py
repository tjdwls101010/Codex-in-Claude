"""Isolation for a batch: which members get a git checkout of their own, cut from which commit, and what the caller should know about the checkouts and about members sharing a tree."""

from __future__ import annotations

from codex.batch.tasks import task_args
from codex.codex_cli.argv import WRITING_SANDBOXES
from codex.errors import Refusal
from codex.git.repo import (
    git_toplevel, ignored_entries as worktree_ignored_entries, missing_at_base as worktree_missing_at_base,
    resolve_base as worktree_base_sha, uncommitted_count as worktree_uncommitted,
)
from codex.registry.runs import find_run
from codex.runs import settings


def wants_worktree(item, args):
    """Whether `--worktree` would isolate this member: a fresh writer with no cwd of its own. A read-only member would see none of the caller's uncommitted work in a checkout; a resume keeps its thread's directory."""
    if item["kind"] == "resume" or item.get("cwd") or getattr(args, "cwd", None):
        return False
    return (item.get("sandbox") or args.sandbox or "workspace-write") in WRITING_SANDBOXES


def why_not_isolated(item, args):
    """Why `--worktree` would pass this member over, in the caller's words, or None."""
    if item["kind"] == "resume":
        return "a resumed thread keeps the directory it already lives in"
    if item.get("cwd") or getattr(args, "cwd", None):
        return "a member with a cwd of its own was told where to go"
    return None


def writers_by_directory(tasks, args, project, runs_dir):
    """Members that will write, grouped by the directory they will write in, resolved as `create_run` will resolve them."""
    dirs = {}
    for i, item in enumerate(tasks):
        parent = None
        if item["kind"] == "resume" and item.get("resume"):
            _rd, parent = find_run(runs_dir, item["resume"])
        ns = task_args(args, item)
        r = settings.resolve(sandbox=ns.sandbox, cwd=getattr(ns, "cwd", None), base=parent)
        if r["sandbox"] in WRITING_SANDBOXES:
            dirs.setdefault(str(r["cwd"] or project), []).append(i)
    return dirs


def sharing_note(shared, reasons):
    """Who is about to write into one directory, and — only where it would work — the remedy."""
    parts = "; ".join(f"{len(idx)} members write to {d} and share it" for d, idx in shared.items())
    tail = (" `--worktree` gives each its own checkout instead; `result --group` "
            "then reports which paths more than one wrote."
            if not reasons else
            " `--worktree` does not separate all of them: " + "; ".join(reasons) + ".")
    return (parts + ", so each one's changes are in that tree as it makes them "
            "— and none of them can tell another's edit from its own." + tail)


def plan_worktrees(tasks, args, project, runs_dir):
    """Which members get a checkout, cut from which commit, and a note when members will share a tree. Returns `(eligible indices, base sha, note)`.

    Isolation is opt-in: without `--worktree` members share the caller's tree as a fan-out of Claude's own subagents does, and the note says so only when two or more writers share a directory.
    """
    eligible = {i for i, t in enumerate(tasks) if wants_worktree(t, args)}
    shared = {d: idx for d, idx in writers_by_directory(tasks, args, project, runs_dir).items() if len(idx) > 1}

    def reasons_for(indices):
        out = []
        for i in indices:
            r = why_not_isolated(tasks[i], args)
            if r and r not in out:
                out.append(r)
        return out

    if not getattr(args, "worktree", False):
        if not shared:
            return set(), None, None
        return set(), None, sharing_note(shared, reasons_for(i for idx in shared.values() for i in idx))
    if not eligible:
        why = reasons_for(range(len(tasks)))
        if not why:
            return set(), None, "no member writes to the tree, so there is nothing to isolate"
        note = "no worktree is cut: " + "; ".join(why) + "."
        return set(), None, note + (" " + sharing_note(shared, why) if shared else "")
    if git_toplevel(project) is None:
        return set(), None, (f"{project} is not a git repository, so worktrees "
                             "are unavailable; members share the caller's tree")
    ref = getattr(args, "base", None)
    base = worktree_base_sha(project, ref)
    if not base and ref:
        # A typo'd --base is the caller's mistake; degrading to a shared tree would give them the one outcome they asked to avoid.
        raise Refusal(f"--base {ref!r} does not resolve to a commit in {project}")
    if not base:
        return set(), None, ("this repository has no HEAD yet (nothing is "
                             "committed), so there is no commit to cut a "
                             "worktree from; members share the caller's tree")
    return eligible, base, None


def worktree_report(project, runs_dir, base, count):
    """What the caller cannot see from anywhere else about the checkouts just cut: their base, the uncommitted and ignored work they lack, and instructions missing at the base."""
    out = {"count": count, "base": base,
           "uncommitted_files_in_caller_tree": worktree_uncommitted(project),
           "note": "each writing member has its own checkout at "
                   "<run_dir>/wt. Their changes are not in your tree; "
                   "`result --group` reports which paths more than one wrote. "
                   "`batch clean --group` removes them once you have collected."}
    try:
        own = runs_dir.relative_to(project).as_posix() + "/"
    except ValueError:
        own = None
    ignored, more = worktree_ignored_entries(project, base=base, skip=[own] if own else [])
    if ignored:
        out["missing_ignored"] = ignored
        if more:
            out["missing_ignored_truncated"] = more
    missing = worktree_missing_at_base(project, base)
    if missing:
        out["missing_at_base"] = missing
        out["missing_note"] = (f"{', '.join(missing)} exists in your tree but not at the base "
                               f"these worktrees were cut from, so these runs start without "
                               f"the project instructions a HEAD-based run would have had.")
    return out
