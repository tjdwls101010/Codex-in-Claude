"""git worktrees: cutting one per writing batch member, and removing it after.

Why a worktree at all: two `workspace-write` runs in one directory edit each
other's files mid-edit, and neither Codex can tell that from its own change. A
worktree gives each writer a private checkout of the same repository at the same
commit, so the collision surfaces later as a merge rather than sooner as
corruption.

Three properties of this design were measured before it was built (see
`harness-spec.md` V-13/V-14/V-15) and each one carries weight here:

  * The worktree lives under `.codex-runs/<run_id>/wt`, whose `.gitignore` is
    `*`, and the main tree's `git status --porcelain` stays empty even while the
    worktree holds modified and untracked files. The isolation is not paid for
    with noise in the caller's tree.
  * `git worktree remove` refuses a worktree with uncommitted changes on its
    own. `batch clean`'s promise not to discard uncollected results is therefore
    git's behaviour, not a check this module reimplements — and reimplementing
    it would be strictly worse, since git's notion of dirty is the correct one.
  * A freshly cut detached worktree has zero lines of `git diff HEAD`. That is
    the whole reason worktrees are assigned per member rather than per batch: a
    `read-only` reviewer put in one would be reviewing nothing, because the
    uncommitted work it exists to look at lives only in the caller's tree.

Detached rather than on a branch: nothing to name, nothing to collide, and the
result stays as uncommitted changes in the worktree — which is exactly the state
that makes `git worktree remove` protect it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(cwd, *args, timeout=60):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True, timeout=timeout)


def resolve_base(cwd: Path, ref=None):
    """The commit a worktree will be cut from: `ref` if given, else HEAD.

    Resolved to a full sha rather than passed through as a name, because the
    preamble states it to Codex and a symbolic ref would move under it.
    """
    r = _git(cwd, "rev-parse", "--verify", f"{ref or 'HEAD'}^{{commit}}")
    return r.stdout.strip() if r.returncode == 0 else None


def repo_identity(cwd: Path):
    """`(repository, top level)` for a directory, or `(None, None)`.

    The repository is `--git-common-dir`, which every worktree of one
    repository shares and no two repositories do. That is the property that
    makes it the right key for comparing paths across runs: three worktrees of
    one repo are the same repository, and two unrelated checkouts that both
    contain an `output.txt` are not.

    The top level is what a path is made relative to, and it is per-worktree —
    so the same tracked file reduces to the same repo-relative path no matter
    which worktree, or which subdirectory of one, a run was started in.
    """
    r = _git(cwd, "rev-parse", "--path-format=absolute",
             "--git-common-dir", "--show-toplevel")
    if r.returncode != 0:
        return None, None
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None, None
    return lines[0], Path(lines[1])


def missing_at_base(cwd: Path, base: str, names=("AGENTS.md", "CLAUDE.md")):
    """Instruction files that exist in the caller's tree but not at `base`.

    V-14 measured that `AGENTS.md` does reach a run whose cwd is a worktree —
    but only when the worktree was cut from a ref where the file exists. A
    `--base` older than the commit that introduced it produces a run with no
    project instructions at all, and nothing about that is visible from either
    side: the caller sees a normal batch, and Codex cannot miss a file it was
    never told about. Cheap to check, and it is the only way the gap ever
    surfaces.
    """
    missing = []
    for name in names:
        if not (cwd / name).exists():
            continue
        if _git(cwd, "cat-file", "-e", f"{base}:{name}").returncode != 0:
            missing.append(name)
    return missing


def uncommitted_count(cwd: Path) -> int:
    """Files that differ from HEAD in the caller's tree, tracked or not.

    Reported, never acted on (D17): the preamble tells Codex the count so it
    knows its worktree is not what the caller is looking at, and `batch start`
    tells the caller the same thing. Neither refuses.
    """
    r = _git(cwd, "status", "--porcelain")
    if r.returncode != 0:
        return 0
    return len([ln for ln in r.stdout.splitlines() if ln.strip()])


def add(source: Path, target: Path, base: str):
    """Cut a detached worktree at `target` from `base`. Returns (ok, error)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    r = _git(source, "worktree", "add", "--detach", str(target), base)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[:400]
    return True, None


def remove(source: Path, target: Path, force: bool = False):
    """Remove a worktree. Returns (ok, error).

    Not forced by default, so git's own refusal of a dirty worktree is what
    stops `batch clean` from discarding work nobody collected (D06).

    Forced means *forced*, which git spells `-f -f`. A single `--force` covers a
    dirty tree but not a locked one, and `git worktree add` holds a lock reading
    `initializing` for the duration of the checkout — so a `batch start` killed
    inside `git worktree add` leaves a worktree that stays locked forever and
    that `--force` then refuses, while `batch clean` reports having lifted every
    protection. Measured: `cannot remove a locked working tree, lock reason:
    initializing / use 'remove -f -f' to override or unlock first`.
    """
    args = ["worktree", "remove"]
    if force:
        args += ["--force", "--force"]
    r = _git(source, *args, str(target))
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[:400]
    return True, None


def prune(source: Path):
    """Drop administrative entries for worktrees whose directory is gone.

    A run directory deleted by hand leaves git still listing its worktree, and
    that stale entry is what later makes `git worktree add` refuse a path it
    considers already registered.
    """
    _git(source, "worktree", "prune")


def is_dirty(target: Path) -> bool:
    r = _git(target, "status", "--porcelain")
    return r.returncode == 0 and bool(r.stdout.strip())


def registered(source: Path):
    """Worktree paths git currently knows about, excluding the main tree."""
    r = _git(source, "worktree", "list", "--porcelain")
    if r.returncode != 0:
        return []
    paths = [ln.split(" ", 1)[1].strip()
             for ln in r.stdout.splitlines() if ln.startswith("worktree ")]
    return [Path(p) for p in paths[1:]]   # the first entry is the main tree
