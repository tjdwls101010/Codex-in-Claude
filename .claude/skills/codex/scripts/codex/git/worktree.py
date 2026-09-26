"""git worktrees: cutting one per writing batch member, and removing it after.

A checkout is detached at `<run_dir>/wt`, under a registry whose `.gitignore` is `*`, so the caller's `git status` stays clean while it holds changes. It holds tracked files at the base commit and nothing else: none of the caller's uncommitted or ignored work. Results stay in it as uncommitted changes, which is the state `git worktree remove` refuses to discard unless forced.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from codex.git.repo import run_git


def add(source: Path, target: Path, base: str):
    """Cut a detached worktree at `target` from `base`. Returns (ok, error)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    r = run_git(source, "worktree", "add", "--detach", str(target), base)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[:400]
    return True, None


def remove(source: Path, target: Path, force: bool = False, owned: bool = False):
    """Remove a worktree. Returns (ok, error).

    Unforced, git's own refusal of a dirty tree is what keeps uncollected results. Forced is `-f -f`: one `--force` does not lift the `initializing` lock a killed `git worktree add` leaves.
    """
    args = ["worktree", "remove"]
    if force:
        args += ["--force", "--force"]
    r = run_git(source, *args, str(target))
    if r.returncode == 0:
        return True, None
    if force and owned and not (target / ".git").exists():
        # A `git worktree add` killed before it wrote the checkout's .git file leaves a directory git refuses to validate as a working tree. `owned` is the caller's word that `target` is a checkout this skill cut for one run; only then is it unlocked, deleted and pruned instead.
        run_git(source, "worktree", "unlock", str(target))
        shutil.rmtree(target, ignore_errors=True)
        prune(source)
        listed = run_git(source, "worktree", "list", "--porcelain")
        still = [ln[len("worktree "):] for ln in listed.stdout.splitlines() if ln.startswith("worktree ")]
        if not target.exists() and listed.returncode == 0 and str(target) not in still:
            return True, None
    return False, (r.stderr or r.stdout).strip()[:400]


def prune(source: Path):
    """Drop git's entries for worktrees whose directory is gone; a stale one makes a later `git worktree add` refuse the path."""
    run_git(source, "worktree", "prune")


def registered(source: Path):
    """Worktree paths git knows about, excluding the main tree."""
    r = run_git(source, "worktree", "list", "--porcelain")
    if r.returncode != 0:
        return []
    paths = [ln.split(" ", 1)[1].strip() for ln in r.stdout.splitlines() if ln.startswith("worktree ")]
    return [Path(p) for p in paths[1:]]
