"""git worktrees: cutting one per writing batch member, and removing it after.

Why a worktree at all: two `workspace-write` runs in one directory edit each
other's files mid-edit, and neither Codex can tell that from its own change. A
worktree gives each writer a private checkout of the same repository at the same
commit, so the collision surfaces later as a merge rather than sooner as
corruption.

Three properties of this design were measured before it was built, and each
one carries weight here:

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
    `read-only` member put in one would see nothing, because the uncommitted
    work it was started to look at lives only in the caller's tree.

Detached rather than on a branch: nothing to name, nothing to collide, and the
result stays as uncommitted changes in the worktree — which is exactly the state
that makes `git worktree remove` protect it.
"""

from __future__ import annotations

import os
import shutil
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


def ignored_entries(cwd: Path, base=None, skip=(), limit=20):
    """What git ignores in the caller's tree, at the shallowest ignored level.

    A worktree is `git worktree add` output: tracked files at the base commit,
    and nothing else. So every one of these is absent from a checkout — the
    canonical interpreter, provider caches, fixture directories, whatever this
    repository deliberately keeps out of git. V-27 reproduced it directly, and
    the consequence is worse than a missing file: a run that rebuilds its own
    cache gets live data and reports every comparison against the recorded
    baseline as a regression, which reads as a finding rather than as a
    setup problem.

    `--ignored=matching` collapses a wholly-ignored directory to one entry, so
    a `node_modules` does not arrive as fifty thousand lines. The cap is for
    what that still does not collapse — a rule matching many siblings — and the
    caller is told a count rather than handed a truncated list to reason from.

    `skip` drops paths under a prefix: the run registry gitignores itself, and
    a checkout not having this tool's own bookkeeping is neither news nor a
    thing the caller can act on. `base` drops a path the checkout does have —
    a `--base` older than the commit that stopped tracking something puts that
    something back in every worktree, and this field is a claim about what is
    absent.

    `-z` rather than plain porcelain: without it git C-quotes any path with a
    non-ASCII character, a tab, a quote or a backslash, so the field would hand
    back an encoded token where the caller expects a path — and this repository
    has Korean paths in its own test fixtures.
    """
    p = _git(cwd, "status", "--porcelain", "-z", "--ignored=matching",
             "--untracked-files=normal")
    if p.returncode != 0:
        return [], 0
    found = [rec[3:] for rec in p.stdout.split("\0")
             if rec.startswith("!! ")
             and not any(rec[3:].startswith(s) for s in skip)]
    if base:
        tracked = _tree_paths(cwd, base)
        found = [f for f in found if not _covered_by(cwd, tracked, f)]
    return found[:limit], max(0, len(found) - limit)


#: How much of one ignored directory this will walk before giving up on
#: deciding and simply reporting it. A false positive here names something the
#: checkouts do have; a false negative hides something they do not, which is
#: the answer the field exists to give — so the cap fails towards reporting.
WALK_CAP = 500


def _tree_paths(cwd: Path, base: str):
    """Every path the base commit tracks, from one `git ls-tree`.

    One process rather than one per entry: `base` is supplied for every
    isolated batch now, and a repository whose ignore rules match a thousand
    siblings would otherwise spend a thousand forks here before the 20-entry
    cap is even applied.
    """
    p = _git(cwd, "ls-tree", "-r", "-z", "--name-only", base)
    if p.returncode != 0:
        return set()
    return {x for x in p.stdout.split("\0") if x}


def _covered_by(cwd: Path, tracked, entry: str):
    """Whether a checkout at that base already has all of this entry.

    A file is simple. A directory is not: `--ignored=matching` collapses a
    wholly-ignored directory to one entry, and a base that tracked a single
    file under it makes "does the base know this path" answer yes for the whole
    collapsed tree — dropping a `.venv/` whose hundred other files really are
    absent. So a directory is only covered when everything now under it was
    tracked then.
    """
    if not entry.endswith("/"):
        return entry in tracked
    root = entry.rstrip("/")
    seen = 0
    for dirpath, _dirs, files in os.walk(cwd / root):
        for name in files:
            rel = os.path.relpath(os.path.join(dirpath, name), cwd)
            if rel not in tracked:
                return False
            seen += 1
            if seen > WALK_CAP:
                return False
    return seen > 0


def uncommitted_count(cwd: Path):
    """Files that differ from HEAD in the caller's tree, tracked or not, or
    `None` if git would not say.

    Reported, never acted on (D17): the preamble tells Codex the count so it
    knows its worktree is not what the caller is looking at, and `batch start`
    tells the caller the same thing. Neither refuses.

    `None` rather than 0 on failure, matching `resolve_base` and `repo_identity`
    above. Answering 0 here is not a conservative default — it is the preamble
    stating to Codex, as fact, that the caller's tree is clean. A corrupt
    `.git/index` makes `status` exit 128 while `rev-parse` and `worktree add`
    both still succeed, so this branch sits behind operations that just worked.
    """
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
    if r.returncode == 0:
        return True, None
    if force:
        # A `git worktree add` killed before it wrote the checkout's .git file leaves a directory git refuses to validate as a working tree; forced, it is unlocked, deleted and pruned instead.
        _git(source, "worktree", "unlock", str(target))
        shutil.rmtree(target, ignore_errors=True)
        prune(source)
        if not target.exists() and target not in registered(source):
            return True, None
    return False, (r.stderr or r.stdout).strip()[:400]


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
