"""The git CLI: repository questions and the worktrees a batch cuts. A git behaviour change lands here, and what leaves is paths, shas, counts and `(ok, error)` pairs, never git's own output."""

from codex.git.repo import (
    git_toplevel, ignored_entries, is_dirty, missing_at_base, repo_identity, resolve_base, resolve_project,
    uncommitted_count,
)
from codex.git.worktree import (
    add as worktree_add, prune as worktree_prune, registered as worktrees_registered, remove as worktree_remove,
)

__all__ = [
    "git_toplevel", "resolve_project", "resolve_base", "repo_identity", "missing_at_base", "ignored_entries",
    "uncommitted_count", "is_dirty", "worktree_add", "worktree_remove", "worktree_prune", "worktrees_registered",
]
