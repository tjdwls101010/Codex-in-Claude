"""Cleaning a group: removing its worktrees and releasing its name, never taking live work with them."""

from __future__ import annotations

import shlex
from pathlib import Path

from codex.errors import Refusal
from codex.git.repo import is_dirty as worktree_dirty
from codex.git.worktree import prune as worktree_prune, remove as worktree_remove
from codex.registry.groups import (
    derived_groups, group_path, group_unreadable, list_groups, member_run_ids, owned_run_ids, read_group,
)
from codex.registry.runs import find_run, is_live, iter_runs, meta_unreadable, reap, still_writing
from codex.util import is_within


def stop_commands(runs, runs_dir, explicit_registry=False):
    """The `stop` calls that end these runs: the group's when the run is one of its recorded members, else the run's own. A registry the caller named is named in the command too."""
    where = f" --runs-dir {shlex.quote(str(runs_dir))}" if explicit_registry else ""
    out = []
    for m in runs:
        g = m.get("group")
        cmd = (f"stop --group {g}" if g and m["run_id"] in (member_run_ids(runs_dir, g) or [])
               else f"stop --run {m['run_id']}") + where
        if cmd not in out:
            out.append(cmd)
    return out


def clean_group(project, runs_dir, name, *, force, explicit_registry):
    """Remove a group's worktrees and release its name when nothing is left behind.

    Live work is never removed, `--force` or not: a live member refuses the call, and a worktree another live run is working in (or a member whose state cannot be read) is kept. `force` lifts the rest — an unreadable manifest or member, a derived group, git's refusal of a dirty tree — and the reply says what it overrode.
    """
    lost_manifest = read_group(runs_dir, name) is None and group_unreadable(runs_dir, name)
    if read_group(runs_dir, name) is None and not lost_manifest:
        raise Refusal(f"no such group in this project: {name}", known_groups=list_groups(runs_dir)[:20])
    live, unknown = _member_liveness(runs_dir, name)
    if live:
        raise Refusal(f"group {name!r} still has running members; stop them with the command in `stop`, then clean again",
                      running=live, stop=stop_commands(live, runs_dir, explicit_registry))
    overrode = _check_liftable_guards(runs_dir, name, force=force, lost_manifest=lost_manifest, unknown=unknown)
    removed, kept = _remove_worktrees(project, runs_dir, name, force=force,
                                      explicit_registry=explicit_registry, overrode=overrode)

    released = not kept and not unknown
    if released:
        group_path(runs_dir, name).unlink(missing_ok=True)
        note = None
    elif unknown or any(k.get("stop") for k in kept):
        note = ("the name stays reserved until nothing is left: "
                + (f"{', '.join(m['run_id'] for m in unknown)} will not parse (repair or remove those run directories); " if unknown else "")
                + "kept[].reason says why each worktree is kept, and kept[].stop ends a live run")
    else:
        note = "the name stays reserved until nothing is left: kept[].reason says why git kept each worktree; collect uncommitted changes, or pass --force to discard them"
    out = {"group": name, "name_released": released}
    if overrode:
        out["forced_past"] = overrode
        out["forced_note"] = "--force overrode everything in forced_past, not only the refusal you hit; discarded changes are not recoverable"
    out.update(note=note, removed=removed, kept=kept)
    return out


def _member_liveness(runs_dir, name):
    """`(live members, members whose meta.json will not parse)` — unknown is kept apart from dead."""
    live, unknown = [], []
    for rid in owned_run_ids(runs_dir, name) or []:
        rd, meta = find_run(runs_dir, rid)
        if not meta:
            if rd is not None and meta_unreadable(rd):
                unknown.append({"run_id": rid, "state": "unreadable",
                                "reason": "its meta.json will not parse, so whether "
                                          "it is still running cannot be determined"})
            continue
        meta = reap(rd, meta)
        if is_live(meta):
            live.append({"run_id": rid, "state": meta.get("state"), "group": meta.get("group"),
                         **({"codex_still_running": True} if still_writing(meta) else {})})
    return live, unknown


def _check_liftable_guards(runs_dir, name, *, force, lost_manifest, unknown):
    """The refusals `--force` lifts, in check order; returns what was overridden, since one flag lifts all of them and the caller usually meant one."""
    children = derived_groups(runs_dir, name)
    guards = [
        ("unreadable_manifest", lost_manifest,
         f"group {name!r} has a manifest that will not parse; its members are listed in `members_recorded_by_runs`, and --force cleans them",
         lambda: {"manifest": str(group_path(runs_dir, name)),
                  "members_recorded_by_runs": owned_run_ids(runs_dir, name)},
         str(group_path(runs_dir, name))),
        ("unreadable_members", bool(unknown),
         f"group {name!r} has members whose meta.json will not parse, so whether they run is unknown; --force cleans the others and keeps those worktrees",
         lambda: {"running": unknown}, unknown),
        # `--resume-from` puts phase 2 in phase 1's worktrees. One hop only, which is why the removal asks the registry again.
        ("derived_groups", bool(children),
         f"group {name!r} was continued by another group (--resume-from), whose members work in these worktrees; --force lifts this refusal, but a worktree a live run still works in is kept",
         lambda: {"derived_groups": children}, children),
    ]
    overrode = {}
    for key, tripped, message, detail, forced_value in guards:
        if tripped:
            if not force:
                raise Refusal(message, **detail())
            overrode[key] = forced_value
    return overrode


def _remove_worktrees(project, runs_dir, name, *, force, explicit_registry, overrode):
    removed, kept = [], []
    worktree_prune(project)
    for rid in owned_run_ids(runs_dir, name) or []:
        rd, meta = find_run(runs_dir, rid)
        if rd is None:
            continue
        wt = (meta or {}).get("worktree")
        # A member's checkout is always `<run_dir>/wt`, which recovers one whose path was never recorded.
        path = Path(wt["path"]) if wt else rd / "wt"
        if not path.exists():
            continue
        if meta is None:
            kept.append({"run_id": rid, "path": str(path),
                         "reason": "its run's meta.json will not parse, so whether it runs is unknown; repair or remove the run directory to release this worktree",
                         "run_dir": str(rd)})
            continue
        # Who lives here is asked of the registry, not the group graph, which forgets an intermediate group once it is cleaned.
        occupants = [m for _rd, m in iter_runs(runs_dir)
                     if is_live(m) and m.get("run_id") != rid and is_within(m.get("cwd"), path)]
        if occupants:
            kept.append({"run_id": rid, "path": str(path),
                         "reason": "another run is still working in this worktree",
                         "occupied_by": [m["run_id"] for m in occupants],
                         "stop": stop_commands(occupants, runs_dir, explicit_registry)})
            continue
        dirty = worktree_dirty(path)
        # The repository the checkout was cut from: recorded with the worktree, or — when `git worktree add` never returned — the cwd the run was published with.
        source = Path((wt or {}).get("source") or meta.get("cwd") or project)
        ok, err = worktree_remove(source, path, force=force, owned=path == rd / "wt")
        if ok and dirty and force:
            overrode.setdefault("discarded_uncommitted", []).append(str(path))
        (removed if ok else kept).append({"run_id": rid, "path": str(path),
                                          **({} if ok else {"reason": err, "dirty": dirty})})
    return removed, kept
