"""The run registry, the one store this skill keeps: `<main checkout>/.codex-runs/<run_id>/`, one per repository whichever of its checkouts a command runs from. The caller hands the root in: this store does not ask git.

    .codex-runs/
    ├── .gitignore            # `*`, so the registry never lands in the user's history
    ├── .groups/<name>.json   # batch manifests
    ├── .locks/               # per-thread turn locks
    └── <run_id>/
        ├── meta.json         # the run's settings and lifecycle
        ├── events.jsonl      # `codex exec --json` stdout
        ├── stderr.log
        └── last-message.txt  # from -o

`codex exec resume` inherits no per-invocation setting from the thread it continues, so this registry is the only place a run's intended sandbox, model and effort exist at all.

Locks, atomic writes, staging names, run-id claims and the compare-and-set on `state` stay behind this interface: a caller asks for a run, the live runs, a published run or a recorded outcome, and gets them consistent.
"""

from codex.registry.groups import (
    claim_group, group_gaps, group_manifest, group_path, group_runs, group_unreadable, group_view,
    list_groups, member_run_ids, owned_run_ids, record_members, release_group, valid_group_name,
)
from codex.registry.runs import (
    TERMINAL_STATES, ensure_runs_dir, find_run, is_live, iter_runs, live_runs, meta_unreadable,
    publish_run, read_meta, reap, record_if_active, resolve_runs_dir, run, still_writing, unreadable_runs, update_meta,
    write_meta,
)

__all__ = [
    # where the registry is
    "resolve_runs_dir", "ensure_runs_dir",
    # reading runs
    "iter_runs", "find_run", "run", "live_runs", "unreadable_runs", "meta_unreadable", "read_meta",
    # liveness
    "is_live", "still_writing", "reap", "TERMINAL_STATES",
    # writing runs
    "publish_run", "write_meta", "update_meta", "record_if_active",
    # groups
    "valid_group_name", "claim_group", "record_members", "group_manifest", "group_view", "group_runs", "group_gaps",
    "owned_run_ids", "member_run_ids", "list_groups", "group_path", "group_unreadable",
    "release_group",
]
