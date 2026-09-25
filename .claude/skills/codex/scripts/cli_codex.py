#!/usr/bin/env python3
"""Drive the OpenAI Codex CLI as a managed subagent. Entrypoint and the supervisor's re-exec target; Python 3.10+, standard library only.

    cli/       the command-line surface: flags, help, handlers, output
    core/      this skill's state and lifecycle: registry, settings, runs, supervisor, observation, groups
    codex/     formats the Codex CLI owns: argv, CODEX_HOME and config.toml, model catalog, event stream
    worktree.py  git worktree adapter
    util.py      primitives
"""

# Python puts this file's directory first on sys.path, which is what makes the packages beside it importable from any cwd and through a symlinked install.
from cli import main

if __name__ == "__main__":
    main()
