"""Cross-process locks on registry files, and the atomic JSON write every registry file goes through."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import uuid
from pathlib import Path

from codex.util import nfc


@contextlib.contextmanager
def flock(lock: Path):
    """Hold an exclusive lock on `lock` for the body.

    Failing to take the lock degrades to unlocked access, so a registry on a filesystem that cannot lock still works; an error raised by the body is the body's and propagates.
    """
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        fh = lock.open("a+")
    except OSError:
        yield
        return
    try:
        with contextlib.suppress(OSError):
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        with contextlib.suppress(Exception):
            fh.close()


def thread_turn_lock(runs_dir: Path, thread_ref):
    """Serialise "is this thread free?" with publishing the run that answers it, across processes.

    Without it two resumes a fraction of a second apart both see an idle thread and start two turns on one rollout file. Held only across check-and-publish, never across the turn.
    """
    if not thread_ref:
        return contextlib.nullcontext()
    return flock(runs_dir / ".locks" / (nfc(str(thread_ref)).replace("/", "_") + ".lock"))


def meta_lock(run_dir: Path):
    """Serialise read-modify-write on one meta.json. The lock file is separate because locking the file being replaced would lock an inode that is no longer current."""
    return flock(run_dir / ".meta.lock")


def write_json_atomic(path: Path, obj):
    """A reader sees the old file or the new one, never half of one. The staging name is unique per writer: a shared one lets two writers truncate each other."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()
