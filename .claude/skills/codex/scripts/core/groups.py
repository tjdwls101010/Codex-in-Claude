"""Collecting a group: what each member concluded and which paths more than one member wrote."""

from __future__ import annotations

from pathlib import Path

from codex.codex_cli.events import read_events
from codex.git.repo import repo_identity
from codex.registry.runs import still_writing
from codex.util import nfc
from core.observe import progress, turn_failed_excerpt


# Per member, in bytes, in `result --group`; `result --run` returns the whole message.
GROUP_MESSAGE_CAP = 4000


# -- collecting a group ----------------------------------------------------------

def changed_paths(events_path: Path, root=None):
    """Paths a run wrote, as `(repository, repo-relative path)` pairs.

    Codex reports absolute paths and every checkout has its own prefix, so paths are made relative to the repository's top level; the repository (`--git-common-dir`) stays in the key so two repositories' `output.txt` are two files. A path outside any repository stays absolute.
    """
    repo, top = repo_identity(Path(root)) if root else (None, None)
    paths = set()
    for ev in read_events(events_path, 0)[0]:
        item = ev.get("item") or {}
        if item.get("type") != "file_change":
            continue
        for ch in item.get("changes") or []:
            p = ch.get("path") if isinstance(ch, dict) else ch
            if not p:
                continue
            p = Path(nfc(str(p)))
            if top:
                try:
                    paths.add((repo, str(p.relative_to(Path(nfc(str(top)))))))
                    continue
                except ValueError:
                    pass
            paths.add((None, str(p)))
    return paths


def member_result(rd, meta):
    """One member's row in `result --group`: its message capped in bytes (cut and counted in the same unit), plus usage and liveness."""
    info = progress(rd, meta)
    msg_path = rd / "last-message.txt"
    message = (msg_path.read_text(encoding="utf-8") if msg_path.exists() else info["last_agent_message"]) or ""
    raw = message.encode("utf-8", "replace")
    truncated = len(raw) > GROUP_MESSAGE_CAP
    row = {"run_id": meta["run_id"], "label": meta.get("label"),
           "state": meta.get("state"), "exit_code": meta.get("exit_code"),
           # "ignore": a byte cut mid-character would otherwise add U+FFFD, which is larger and reads as corruption.
           "message": raw[:GROUP_MESSAGE_CAP].decode("utf-8", "ignore") if truncated else message,
           "message_bytes": len(raw), "message_truncated": truncated,
           "usage": info["usage"], "files_changed": info["files_changed"],
           "turn_failed": turn_failed_excerpt(info)}
    if info["unparsed_events"]:
        row["unparsed_events"] = info["unparsed_events"]
    if still_writing(meta):
        row["codex_still_running"] = True
    if meta.get("worktree"):
        row["worktree"] = meta["worktree"]
    return row, info


def overlaps(per_run_paths):
    """Paths more than one run wrote, reported by path alone. Keyed by run, never by worktree, so a phase-2 member does not overlap its own predecessor."""
    counts = {}
    for rid, paths in per_run_paths.items():
        for key in paths:
            counts.setdefault(key, []).append(rid)
    return {path: rids for (_repo, path), rids in sorted(counts.items()) if len(rids) > 1}
