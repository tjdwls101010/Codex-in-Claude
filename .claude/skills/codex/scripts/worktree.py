"""git worktrees: cutting one per writing batch member, and removing it after.

A checkout is detached at `<run_dir>/wt`, under a registry whose `.gitignore` is `*`, so the caller's `git status` stays clean while it holds changes. It holds tracked files at the base commit and nothing else: none of the caller's uncommitted or ignored work. Results stay in it as uncommitted changes, which is the state `git worktree remove` refuses to discard unless forced.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# How much of one ignored directory `_covered_by` walks before giving up and reporting it as missing, which is the safe side to err on.
WALK_CAP = 500


def _git(cwd, *args, timeout=60):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout)


def resolve_base(cwd: Path, ref=None):
    """The full sha a worktree will be cut from (`ref`, else HEAD), or None. A sha rather than a name, because the preamble states it and a name could move."""
    r = _git(cwd, "rev-parse", "--verify", f"{ref or 'HEAD'}^{{commit}}")
    return r.stdout.strip() if r.returncode == 0 else None


def repo_identity(cwd: Path):
    """`(repository, top level)` for a directory, or `(None, None)`.

    The repository is `--git-common-dir`, which every worktree of one repository shares and no two repositories (or a submodule and its parent) do; the per-worktree top level is what a path is made relative to.
    """
    r = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir", "--show-toplevel")
    if r.returncode != 0:
        return None, None
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None, None
    return lines[0], Path(lines[1])


def missing_at_base(cwd: Path, base: str, names=("AGENTS.md", "CLAUDE.md")):
    """Instruction files in the caller's tree but not at `base`: a run in a checkout cut from there starts without them, and neither side can notice."""
    missing = []
    for name in names:
        if (cwd / name).exists() and _git(cwd, "cat-file", "-e", f"{base}:{name}").returncode != 0:
            missing.append(name)
    return missing


def ignored_entries(cwd: Path, base=None, skip=(), limit=20):
    """What git ignores in the caller's tree — so no checkout has it — at the shallowest ignored level; returns `(entries[:limit], how many more)`.

    `skip` drops path prefixes (the registry ignores itself). `base` drops what a checkout cut from it does have. `-z` because porcelain otherwise C-quotes non-ASCII paths.
    """
    p = _git(cwd, "status", "--porcelain", "-z", "--ignored=matching", "--untracked-files=normal")
    if p.returncode != 0:
        return [], 0
    found = [rec[3:] for rec in p.stdout.split("\0")
             if rec.startswith("!! ") and not any(rec[3:].startswith(s) for s in skip)]
    if base:
        tracked = _tree_paths(cwd, base)
        found = [f for f in found if not _covered_by(cwd, tracked, f)]
    return found[:limit], max(0, len(found) - limit)


def _tree_paths(cwd: Path, base: str):
    """Every path the base commit tracks, from one `git ls-tree`."""
    p = _git(cwd, "ls-tree", "-r", "-z", "--name-only", base)
    if p.returncode != 0:
        return set()
    return {x for x in p.stdout.split("\0") if x}


def _covered_by(cwd: Path, tracked, entry: str):
    """Whether a checkout at that base has all of this entry. A collapsed ignored directory counts only if everything under it was tracked."""
    if not entry.endswith("/"):
        return entry in tracked
    seen = 0
    for dirpath, _dirs, files in os.walk(cwd / entry.rstrip("/")):
        for name in files:
            if os.path.relpath(os.path.join(dirpath, name), cwd) not in tracked:
                return False
            seen += 1
            if seen > WALK_CAP:
                return False
    return seen > 0


def uncommitted_count(cwd: Path):
    """Files that differ from HEAD in the caller's tree, or None if git would not say — never 0 for unknown, since the preamble states the number to Codex as fact."""
    r = _git(cwd, "status", "--porcelain")
    if r.returncode != 0:
        return None
    return len([ln for ln in r.stdout.splitlines() if ln.strip()])


def add(source: Path, target: Path, base: str):
    """Cut a detached worktree at `target` from `base`. Returns (ok, error)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    r = _git(source, "worktree", "add", "--detach", str(target), base)
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
    r = _git(source, *args, str(target))
    if r.returncode == 0:
        return True, None
    if force and owned and not (target / ".git").exists():
        # A `git worktree add` killed before it wrote the checkout's .git file leaves a directory git refuses to validate as a working tree. `owned` is the caller's word that `target` is a checkout this skill cut for one run; only then is it unlocked, deleted and pruned instead.
        _git(source, "worktree", "unlock", str(target))
        shutil.rmtree(target, ignore_errors=True)
        prune(source)
        listed = _git(source, "worktree", "list", "--porcelain")
        still = [ln[len("worktree "):] for ln in listed.stdout.splitlines() if ln.startswith("worktree ")]
        if not target.exists() and listed.returncode == 0 and str(target) not in still:
            return True, None
    return False, (r.stderr or r.stdout).strip()[:400]


def prune(source: Path):
    """Drop git's entries for worktrees whose directory is gone; a stale one makes a later `git worktree add` refuse the path."""
    _git(source, "worktree", "prune")


def is_dirty(target: Path) -> bool:
    r = _git(target, "status", "--porcelain")
    return r.returncode == 0 and bool(r.stdout.strip())


def registered(source: Path):
    """Worktree paths git knows about, excluding the main tree."""
    r = _git(source, "worktree", "list", "--porcelain")
    if r.returncode != 0:
        return []
    paths = [ln.split(" ", 1)[1].strip() for ln in r.stdout.splitlines() if ln.startswith("worktree ")]
    return [Path(p) for p in paths[1:]]
