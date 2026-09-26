"""The codex skill's one package. `cli.py` beside it is the command surface; everything a command does lives here.

    runs/        feature: start, resume, stop, and the run engine every one of them and every batch member goes through
    batch/       feature: batch start and batch clean — a batch is N runs, so it builds members with runs/, the one import between features
    observe/     feature: status, log, show, result, for a run and for a group
    doctor.py    feature: doctor and models
    codex_cli/   system: the formats the Codex CLI owns — argv, CODEX_HOME and config.toml, the model catalog, the event stream
    git/         system: repository questions and worktrees, asked of the git CLI
    registry/    store: <project>/.codex-runs — run records, group manifests, locks
    errors.py    shared: Refusal, the one way a command says no
    util.py      shared: time, text, paths, process liveness, the entrypoint's path

Imports run from features to systems and stores to shared helpers, never back; tests/test_structure.py holds the tree to that.
"""
