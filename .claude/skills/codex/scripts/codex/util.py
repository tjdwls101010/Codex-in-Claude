"""Primitives with no knowledge of runs, events or Codex: time, text, paths, process liveness, and where the entrypoint is and how it is called again."""

from __future__ import annotations

import errno
import os
import re
import shlex
import sys
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
    # 성진: pid and group together can still be reused by one later process in a group led by a reused pid; record the process's start time if that is ever observed.
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


def invocation(*words):
    """This CLI called again the way SKILL.md calls it: `uv run "<this file, as the caller named it>" <words>`. The path is not resolved, so a symlinked install keeps the path its pre-approval matches."""
    path = os.path.abspath(sys.argv[0])
    # Double quotes are what the pre-approval pattern has; a path they cannot hold safely gets shell quoting instead.
    quoted = shlex.quote(path) if any(c in path for c in '"$`\\') else f'"{path}"'
    return " ".join(["uv run", quoted, *(shlex.quote(str(w)) for w in words)])


def with_next(out: dict, after: str, *words, project=None, runs_dir=None) -> dict:
    """`out` with `next` right after its key `after`: this CLI called again with `words`, to run in the background, written out whole so it matches the pre-approval. A registry the caller named — `project`, `runs_dir` as typed — is named in it too."""
    where = []
    if project:
        where += ["--project", os.path.abspath(os.path.expanduser(project))]
    if runs_dir:
        where += ["--runs-dir", os.path.abspath(os.path.expanduser(runs_dir))]
    items = list(out.items())
    at = next((i + 1 for i, (k, _v) in enumerate(items) if k == after), 1)
    return dict(items[:at] + [("next", {"command": invocation(*words, *where), "run_in_background": True})] + items[at:])
