"""Collecting a group: what each member concluded and which paths more than one member wrote."""

from __future__ import annotations

from pathlib import Path

from codex.codex_cli.events import read_events
from codex.git.repo import repo_identity
from codex.observe.rows import progress, turn_failed_excerpt
from codex.registry.runs import still_writing
from codex.util import nfc

# Per member, in bytes, in `result --group`; `result --run` returns the whole message.
GROUP_MESSAGE_CAP = 4000


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


def final_message(run_dir, info, errors="replace"):
    """What a run concluded: its `-o` file decoded as UTF-8 (a byte that is not, handled by `errors`), else the last agent message in its event stream (a live run's answer so far), else nothing."""
    msg_path = run_dir / "last-message.txt"
    if msg_path.exists():
        return msg_path.read_bytes().decode("utf-8", errors)
    return info["last_agent_message"] or ""


def member_result(rd, meta):
    """One member of `result --group`: its row and the part of its message that is shown, capped in bytes (cut and counted in the same unit). Returns `(row, info, shown)`."""
    info = progress(rd, meta)
    message = final_message(rd, info)
    raw = message.encode("utf-8")
    truncated = len(raw) > GROUP_MESSAGE_CAP
    # "ignore": a byte cut mid-character would otherwise add U+FFFD, which is larger and reads as corruption.
    shown = raw[:GROUP_MESSAGE_CAP].decode("utf-8", "ignore") if truncated else message
    row = {"run_id": meta["run_id"], "label": meta.get("label"),
           "state": meta.get("state"), "exit_code": meta.get("exit_code"),
           "message_bytes": len(raw), "shown_bytes": len(shown.encode("utf-8")), "message_truncated": truncated,
           "files_changed": info["files_changed"], "usage": info["usage"],
           "turn_failed": turn_failed_excerpt(info)}
    if info["unparsed_events"]:
        row["unparsed_events"] = info["unparsed_events"]
    if meta.get("worktree"):
        row["worktree"] = meta["worktree"]
    if still_writing(meta):
        row["codex_still_running"] = True
    return row, info, shown


def overlaps(per_run_paths):
    """Paths more than one run wrote, reported by path alone. Keyed by run, never by worktree, so a phase-2 member does not overlap its own predecessor."""
    counts = {}
    for rid, paths in per_run_paths.items():
        for key in paths:
            counts.setdefault(key, []).append(rid)
    return {path: rids for (_repo, path), rids in sorted(counts.items()) if len(rids) > 1}
