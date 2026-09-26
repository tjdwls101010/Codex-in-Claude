"""CODEX_HOME and the few top-level values this skill reads from the user's config.toml."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

# An isolated run (`--ignore-user-config`) loses the whole file, so these three are put back from it: the skill has no defaults of its own and respects the user's. `sandbox_mode` is never read from here — the sandbox is the invariant this skill owns and re-asserts every turn.
USER_DEFAULT_KEYS = ("model", "model_reasoning_effort", "service_tier")


def codex_home() -> Path:
    """CODEX_HOME when set, resolved — sessions, config and auth all move with it — else ~/.codex."""
    v = os.environ.get("CODEX_HOME")
    return Path(v).expanduser().resolve() if v else Path.home() / ".codex"


def config_scalars(keys, path=None):
    """Named top-level string values from config.toml; `{}` when the file cannot be read or does not parse.

    Only top-level keys count: `model` under `[profiles.work]` is a different setting, and Codex applies the top-level one unless a profile is selected, which this skill never does. A value that is not a string is not one of these settings and is left out.
    """
    path = Path(path) if path else codex_home() / "config.toml"
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if k in keys and isinstance(v, str)}


def user_defaults():
    """`{model, effort, service_tier}` from the user's config.toml, read fresh on every call."""
    raw = config_scalars(USER_DEFAULT_KEYS)
    return {"model": raw.get("model"), "effort": raw.get("model_reasoning_effort"),
            "service_tier": raw.get("service_tier")}
