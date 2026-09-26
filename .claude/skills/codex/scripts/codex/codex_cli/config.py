"""CODEX_HOME and the few top-level values this skill reads from the user's config.toml."""

from __future__ import annotations

import os
import re
from pathlib import Path

# An isolated run (`--ignore-user-config`) loses the whole file, so these three are put back from it: the skill has no defaults of its own and respects the user's. `sandbox_mode` is never read from here — the sandbox is the invariant this skill owns and re-asserts every turn.
USER_DEFAULT_KEYS = ("model", "model_reasoning_effort", "service_tier")

# 성진: a regex over top-level `key = scalar` lines, not a TOML parser, because tomllib needs Python 3.11 and the floor is 3.10. Quoted keys, escapes, inline tables and multi-line values are not read. Replace with tomllib when the floor moves to 3.11.
_SCALAR_RE = re.compile(r"""^([A-Za-z_][\w-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s#]+))""")


def codex_home() -> Path:
    """CODEX_HOME when set, resolved — sessions, config and auth all move with it — else ~/.codex."""
    v = os.environ.get("CODEX_HOME")
    return Path(v).expanduser().resolve() if v else Path.home() / ".codex"


def config_scalars(keys, path=None):
    """Named top-level scalars from config.toml, as strings; `{}` when the file cannot be read.

    The scan stops at the first `[table]` header: `model` under `[profiles.work]` is a different setting, and Codex applies the top-level one unless a profile is selected, which this skill never does.
    """
    path = Path(path) if path else codex_home() / "config.toml"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            break
        m = _SCALAR_RE.match(s)
        if m and m.group(1) in keys:
            out[m.group(1)] = next(g for g in m.groups()[1:] if g is not None)
    return out


def user_defaults():
    """`{model, effort, service_tier}` from the user's config.toml, read fresh on every call."""
    raw = config_scalars(USER_DEFAULT_KEYS)
    return {"model": raw.get("model"), "effort": raw.get("model_reasoning_effort"),
            "service_tier": raw.get("service_tier")}
