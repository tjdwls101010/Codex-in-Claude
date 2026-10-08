"""Formats the Codex CLI owns: its argv, CODEX_HOME and config.toml, its version and model catalog, `codex login status`, the event stream and stderr. A Codex upgrade lands here, and what leaves is in the skill's own terms: nothing outside reads a raw event, a config key or a line Codex prints."""

from codex.codex_cli.argv import SANDBOX_MODES, WRITING_SANDBOXES, apply_preamble, build_argv, read_only_blocker
from codex.codex_cli.catalog import (
    ISOLATION_FLOOR_TEXT, check_model_effort, codex_support, codex_version, model_catalog, refuse_without_isolation,
    support_for,
)
from codex.codex_cli.config import codex_home, config_summary, pin_codex_home, user_defaults
from codex.codex_cli.events import (
    FAIL_HEAD_BYTES, changed_paths, event_lines, first_thread_id, scan_progress, stderr_tail,
)
from codex.codex_cli.login import login_status

__all__ = [
    # argv
    "SANDBOX_MODES", "WRITING_SANDBOXES", "build_argv", "apply_preamble", "read_only_blocker",
    # CODEX_HOME and config.toml
    "codex_home", "pin_codex_home", "user_defaults", "config_summary",
    # the version and what it can run, the model catalog
    "model_catalog", "check_model_effort", "codex_version", "support_for", "codex_support", "refuse_without_isolation",
    "ISOLATION_FLOOR_TEXT",
    # login
    "login_status",
    # the event stream and stderr
    "FAIL_HEAD_BYTES", "event_lines", "first_thread_id", "scan_progress", "changed_paths", "stderr_tail",
]
