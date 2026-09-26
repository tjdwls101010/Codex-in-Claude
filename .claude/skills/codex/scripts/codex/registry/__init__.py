"""The run registry, the one store this skill keeps: `<project>/.codex-runs/<run_id>/`.

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
"""
