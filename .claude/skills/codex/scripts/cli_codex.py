#!/usr/bin/env python3
"""Drive the OpenAI Codex CLI as a managed subagent. Entrypoint and the supervisor's re-exec target; Python 3.10+, standard library only.

    cli/       the command-line surface: flags, help, handlers, output
    core/      this skill's state and lifecycle: registry, settings, runs, supervisor, observation, groups
    codex/     formats the Codex CLI owns: argv, CODEX_HOME and config.toml, model catalog, event stream
    worktree.py  git worktree adapter
    util.py      primitives
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli import main  # noqa: E402

if __name__ == "__main__":
    main()
