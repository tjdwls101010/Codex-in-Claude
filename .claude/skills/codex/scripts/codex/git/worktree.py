"""git worktrees: cutting one per writing batch member, and removing it after.

A checkout is detached at `<run_dir>/wt`, under a registry whose `.gitignore` is `*`, so the caller's `git status` stays clean while it holds changes. It holds tracked files at the base commit and nothing else: none of the caller's uncommitted or ignored work. Results stay in it as uncommitted changes, which is the state `git worktree remove` refuses to discard unless forced.
"""

from __future__ import annotations

import os
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
    if force and owned and _unfinished(source, target):
        # A `git worktree add` killed partway leaves a directory git refuses to validate as a working tree. `owned` is the caller's word that `target` is a checkout this skill cut for one run; only then is it unlocked, deleted and pruned instead.
        run_git(source, "worktree", "unlock", str(target))
        shutil.rmtree(target, ignore_errors=True)
        prune(source)
        listed = run_git(source, "worktree", "list", "--porcelain")
        still = [os.path.realpath(ln[len("worktree "):]) for ln in listed.stdout.splitlines() if ln.startswith("worktree ")]
        if not target.exists() and listed.returncode == 0 and os.path.realpath(target) not in still:
            return True, None
    return False, (r.stderr or r.stdout).strip()[:400]


def _unfinished(source: Path, target: Path) -> bool:
    """Whether `target` is a checkout `git worktree add` never finished, asked of git rather than judged from the .git file, whose content a finished checkout can also have in forms this cannot judge (a relative path, a file it may not read).

    Unfinished: it has no .git file, or git still holds it under the `initializing` lock that command takes for the whole add and releases at its end. A checkout git has no record of is not judged unfinished even when its .git names a directory that is gone: a kill inside git's own cleanup of a failed add leaves that, but so does a finished checkout whose record was pruned, and only the first may be deleted by hand."""
    if not (target / ".git").exists():
        return True
    r = run_git(source, "worktree", "list", "--porcelain")
    if r.returncode != 0:
        return False
    # git records a checkout by its physical path, which a symlinked registry spells differently.
    here = os.path.realpath(target)
    # 성진: a git that translates its messages writes the lock reason in its own language; the fallback then never applies and the checkout is kept, the safe side. Match the translations too if that is ever seen.
    for record in r.stdout.split("\n\n"):
        lines = record.splitlines()
        if lines and lines[0].startswith("worktree ") and os.path.realpath(lines[0][len("worktree "):]) == here:
            return "locked initializing" in lines
    return False


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
