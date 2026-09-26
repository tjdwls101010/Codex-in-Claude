"""Primitives with no knowledge of runs, events or Codex: time, text, paths, JSON output, process liveness."""

from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# The entrypoint a detached supervisor re-executes and `doctor` reports.
ENTRY = Path(__file__).resolve().parent.parent / "cli_codex.py"


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


def emit(obj, code: int = 0):
    """Print one line of JSON and exit. The whole CLI answers this way."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    sys.exit(code)


class BridgeError(Exception):
    """A `fail()` raised instead of emitted. See `failures_raise`."""

    def __init__(self, msg: str, extra: dict):
        super().__init__(msg)
        self.msg = msg
        self.extra = extra


_FAIL_RAISES = False


@contextlib.contextmanager
def failures_raise():
    """Inside this block `fail()` raises `BridgeError` instead of printing and exiting.

    `batch start` needs it: one member failing to spawn must neither take the others with it nor print a second line of JSON. Reentrant.
    """
    global _FAIL_RAISES
    prev = _FAIL_RAISES
    _FAIL_RAISES = True
    try:
        yield
    finally:
        _FAIL_RAISES = prev


def fail(msg: str, **extra):
    """Errors are JSON on stdout too, so the caller parses one shape whatever happened."""
    if _FAIL_RAISES:
        raise BridgeError(msg, extra)
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


def is_within(path, parent) -> bool:
    """Whether `path` is `parent` or lives inside it, compared in NFC."""
    if not path:
        return False
    try:
        p, q = Path(nfc(str(path))), Path(nfc(str(parent)))
        return p == q or q in p.parents
    except Exception:
        return False
