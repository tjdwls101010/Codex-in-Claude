"""What the git CLI says about a repository: its top level, its identity, a commit, and what a checkout cut from it would lack."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from codex.util import nfc

# How much of one ignored directory `_covered_by` walks before giving up and reporting it as missing, which is the safe side to err on.
WALK_CAP = 500


def run_git(cwd, *args, timeout=60):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=timeout)


def git_toplevel(path: Path):
    try:
        r = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return Path(nfc(r.stdout.strip())).resolve()
    except Exception:
        pass
    return None


def resolve_project(explicit=None) -> Path:
    """The project a command works on: the git top level of `explicit`, or of the current directory, else that directory itself."""
    base = Path(explicit).expanduser().resolve() if explicit else Path.cwd().resolve()
    return git_toplevel(base) or base


def resolve_base(cwd: Path, ref=None):
    """The full sha a worktree will be cut from (`ref`, else HEAD), or None. A sha rather than a name, because the preamble states it and a name could move."""
    r = run_git(cwd, "rev-parse", "--verify", f"{ref or 'HEAD'}^{{commit}}")
    return r.stdout.strip() if r.returncode == 0 else None


def repo_identity(cwd: Path):
    """`(repository, top level)` for a directory, or `(None, None)`.

    The repository is `--git-common-dir`, which every worktree of one repository shares and no two repositories (or a submodule and its parent) do; the per-worktree top level is what a path is made relative to.
    """
    r = run_git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir", "--show-toplevel")
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
        if (cwd / name).exists() and run_git(cwd, "cat-file", "-e", f"{base}:{name}").returncode != 0:
            missing.append(name)
    return missing


def ignored_entries(cwd: Path, base=None, skip=(), limit=20):
    """What git ignores in the caller's tree — so no checkout has it — at the shallowest ignored level; returns `(entries[:limit], how many more)`.

    `skip` drops path prefixes (the registry ignores itself). `base` drops what a checkout cut from it does have. `-z` because porcelain otherwise C-quotes non-ASCII paths.
    """
    p = run_git(cwd, "status", "--porcelain", "-z", "--ignored=matching", "--untracked-files=normal")
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
    p = run_git(cwd, "ls-tree", "-r", "-z", "--name-only", base)
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
    r = run_git(cwd, "status", "--porcelain")
    if r.returncode != 0:
        return None
    return len([ln for ln in r.stdout.splitlines() if ln.strip()])


def is_dirty(target: Path) -> bool:
    r = run_git(target, "status", "--porcelain")
    return r.returncode == 0 and bool(r.stdout.strip())
