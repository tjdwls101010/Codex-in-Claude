"""Primitives with no knowledge of runs, events or Codex: time, text, paths, process liveness, and where the entrypoint is."""

from __future__ import annotations

import errno
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# The entrypoint a detached supervisor re-executes and `doctor` reports.
ENTRY = Path(__file__).resolve().parent.parent / "cli.py"


def now_iso() -> str:
    """UTC with millisecond precision: run ids carry a one-second stamp, so `started_at` is what orders runs started in the same second."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def nfc(s):
    """APFS hands back NFD for non-ASCII filenames while argv and JSON carry NFC, so every path that becomes a string is normalised."""
    # 성진: folding to NFC assumes a normalisation-insensitive filesystem such as APFS; change the comparison if a supported filesystem can hold NFC and NFD names as two files.
    return unicodedata.normalize("NFC", s) if isinstance(s, str) else s


def clip(s: str, n: int) -> str:
    """Collapse to one line and cap, saying how much was dropped."""
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s.replace("\n", " ").replace("\r", " ")).strip()
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n} chars)"


def pid_alive(pid, pgid=None) -> bool:
    """Whether process `pid` exists, and, given the process group it was recorded in, is still that process: an exited process's pid goes to a later one, which sits in another group."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError as e:
        # EPERM means it exists and belongs to someone else.
        if e.errno != errno.EPERM:
            return False
    except Exception:
        return False
    if not pgid:
        return True
    try:
        return os.getpgid(int(pid)) == int(pgid)
    except ProcessLookupError:
        return False
    except Exception:
        # Unknown is not "someone else's": a live run taken for dead would be recorded orphaned.
        return True


def is_within(path, parent) -> bool:
    """Whether `path` is `parent` or lives inside it, compared in NFC."""
    if not path:
        return False
    try:
        p, q = Path(nfc(str(path))), Path(nfc(str(parent)))
        return p == q or q in p.parents
    except Exception:
        return False
