"""Formats the Codex CLI owns: its argv, CODEX_HOME and config.toml, the model catalog, `codex login status`, the event stream and stderr. A Codex upgrade lands here, and what leaves is in the skill's own terms: nothing outside reads a raw event, a config key or a line Codex prints."""

from codex.codex_cli.argv import SANDBOX_MODES, WRITING_SANDBOXES, apply_preamble, build_argv
from codex.codex_cli.catalog import check_model_effort, codex_version, model_catalog
from codex.codex_cli.config import codex_home, config_summary, pin_codex_home, user_defaults
from codex.codex_cli.events import (
    DEFAULT_LEVEL, FAIL_HEAD_BYTES, FULL_ITEM_BYTES, LEVELS, CursorOutOfRange, changed_paths, event_lines, find_item,
    first_thread_id, item_ids, scan_progress, stderr_tail,
)
from codex.codex_cli.login import login_status

__all__ = [
    # argv
    "SANDBOX_MODES", "WRITING_SANDBOXES", "build_argv", "apply_preamble",
    # CODEX_HOME and config.toml
    "codex_home", "pin_codex_home", "user_defaults", "config_summary",
    # the model catalog
    "model_catalog", "check_model_effort", "codex_version",
    # login
    "login_status",
    # the event stream and stderr
    "LEVELS", "DEFAULT_LEVEL", "FAIL_HEAD_BYTES", "FULL_ITEM_BYTES", "CursorOutOfRange", "event_lines",
    "first_thread_id", "scan_progress", "find_item", "item_ids", "changed_paths", "stderr_tail",
]
