"""Primitives shared by every module in the bridge.

Nothing here knows about runs, events, or Codex — it is the bottom of the
dependency graph and imports nothing from its siblings.
"""

from __future__ import annotations

import errno
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    """Millisecond precision, deliberately.

    Run ids carry a one-second stamp because they are read by humans, so two
    runs started in the same second are indistinguishable by id — and "newest
    wins" would then be decided by the random suffix. `started_at` is what
    actually orders runs, so it needs finer resolution than the id does.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nfc(s):
    """Normalise to NFC.

    APFS hands back NFD for non-ASCII filenames while argv and JSON carry NFC,
    so a Korean path compares unequal to itself unless both sides are
    normalised. Applied at every boundary where a path becomes a string.
    """
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s


def clip(s: str, n: int) -> str:
    """Collapse to one line and cap, saying how much was dropped."""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s.replace("\n", " ").replace("\r", " ")).strip()
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n} chars)"


def emit(obj, code: int = 0):
    """Print one line of JSON and exit. The whole CLI answers this way."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    sys.exit(code)


def fail(msg: str, **extra):
    """Errors are JSON too — the caller parses stdout either way, and a plain
    text error would force it to branch on whether parsing worked."""
    emit({"error": msg, **extra}, code=1)


def pid_alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError as e:
        # EPERM means it exists and belongs to someone else.
        return e.errno == errno.EPERM
    except Exception:
        return False


def codex_home() -> Path:
    """Never hardcode ~/.codex: CODEX_HOME is overridden on some machines and
    then sessions, config and auth all live somewhere else entirely."""
    v = os.environ.get("CODEX_HOME")
    return Path(v).expanduser() if v else Path.home() / ".codex"


def git_toplevel(path: Path):
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(nfc(r.stdout.strip())).resolve()
    except Exception:
        pass
    return None
