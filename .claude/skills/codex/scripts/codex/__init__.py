"""The codex skill's one package. `cli.py` beside it is the command surface; everything a command does lives here.

    runs/        feature: start, resume, stop, and the run engine every one of them and every batch member goes through
    batch/       feature: batch and clean — a batch is N runs, so it builds members with runs/, the one import between features
    observe/     feature: status, log, result — for a run, and status and result for a group
    doctor.py    feature: doctor and models
    codex_cli/   system: the formats the Codex CLI owns — argv, CODEX_HOME and config.toml, the model catalog, login, the event stream and stderr
    git/         system: repository questions and worktrees, asked of the git CLI
    registry/    store: <project>/.codex-runs — run records, group manifests, locks
    errors.py    shared: Refusal, the one way a command says no
    util.py      shared: time, text, paths, process liveness, the entrypoint's path and how this CLI is called again

Each unit is used through its interface alone — a subpackage's `__all__`, a module's names without a leading underscore — by cli.py, by other units and by tests, so what is behind it can change without touching them. Imports run from features to systems and stores to shared helpers, never back; tests/test_structure.py holds the tree to both.
"""
