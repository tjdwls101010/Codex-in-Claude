"""`codex login status`: whether this install can authenticate, read from how that command exits and what it prints."""

from __future__ import annotations

import re
import shutil
import subprocess

# `codex login status` also fails when it cannot load config at all; calling that "not authenticated" would send the caller to `codex login`, which fails the same way.
CONFIG_FAILURE = re.compile(r"(?i)error loading config|config\.toml|permission denied|invalid|parse")


def login_status():
    """`{ok, cause, detail}`. `cause` is `authenticated`; `unauthenticated`; `environment` — the command could not run at all, an environment or config problem that `codex login` would hit the same way; or `unavailable` — no codex, or it would not answer, with `ok` None. `detail` is what it printed, at most 400 characters, or why it could not be asked."""
    exe = shutil.which("codex")
    if not exe:
        return {"ok": None, "cause": "unavailable", "detail": "`codex` is not on PATH"}
    try:
        r = subprocess.run([exe, "login", "status"], capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
    except Exception as e:
        return {"ok": None, "cause": "unavailable", "detail": str(e)}
    detail = (r.stdout or r.stderr).strip()[:400]
    if r.returncode == 0:
        return {"ok": True, "cause": "authenticated", "detail": detail}
    return {"ok": False, "cause": "environment" if CONFIG_FAILURE.search(detail) else "unauthenticated", "detail": detail}
