"""Batch command handlers and group views (moving to cli/)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from codex.events import FOLLOW_INTERVAL, format_events, read_events
from core.groups import (
    changed_paths, check_task_settings, claim_group, clean_group, group_path, load_tasks,
    member_result, overlaps, pair_with_previous, plan_worktrees, read_group, resolve_group,
    spawn_members, unstarted_members, valid_name, vanished_members, worktree_report,
)
from core.observe import group_snapshot, run_row
from core.registry import ensure_runs_dir, read_meta, reap, resolve_project, resolve_runs_dir, unreadable_runs
from util import emit, fail


def cmd_batch_start(args):
    if not valid_name(args.group):
        fail("group name must be alphanumeric with . _ - and no path separators", got=args.group)
    if getattr(args, "base", None) and not getattr(args, "worktree", False):
        # Refused before the claim, so a typo does not burn the name.
        fail("--base only shapes the worktrees --worktree cuts, and there is no "
             "--worktree here, so nothing would use it. Members share the "
             "caller's tree, which is whatever is checked out in it now.",
             base=args.base)
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))
    tasks = load_tasks(args)
    previous = getattr(args, "resume_from", None)
    if previous:
        tasks, paired_with = pair_with_previous(tasks, runs_dir, previous, force=getattr(args, "force", False))
    check_task_settings(tasks, args, runs_dir)

    # Claimed before anything spawns, so a duplicate name costs nothing.
    try:
        epoch = claim_group(runs_dir, args.group, derived_from=previous, requested=len(tasks))["epoch"]
    except FileExistsError:
        existing = read_group(runs_dir, args.group) or {}
        fail(f"group {args.group!r} already exists in this project; group names "
             f"are single-use so that membership and start order stay unambiguous. "
             f"`batch clean --group {args.group}` releases the name once its "
             f"worktrees are gone — which is also how a name is reclaimed from a "
             f"batch whose members all failed to spawn, since the claim happens "
             f"before the first one is tried",
             created_at=existing.get("created_at"), members=len(existing.get("members") or []))

    isolated, base, note = plan_worktrees(tasks, args, project, runs_dir)
    members, results = spawn_members(args, tasks, runs_dir=runs_dir, epoch=epoch, isolated=isolated, base=base)
    out = {"group": args.group, "runs": results,
           "spawned": len([m for m in members if m.get("run_id")]), "requested": len(tasks),
           "manifest": str(group_path(runs_dir, args.group))}
    if previous:
        out["resumed_from"] = {"group": previous, "members": paired_with}
    cut = [m for m in members if m.get("worktree")]
    if cut:
        out["worktrees"] = worktree_report(project, runs_dir, base, len(cut))
    elif note:
        out["worktrees"] = {"count": 0, "note": note}
    emit(out)


def cmd_batch_clean(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    emit(clean_group(project, runs_dir, args.group, force=args.force,
                     explicit_registry=bool(args.project or args.runs_dir)))


def follow_group(args, project, runs_dir):
    """Print one line per member state change, then a terminal line, then exit.

    Deliberately symmetrical with `log --follow`, so pairing it with the Monitor
    tool needs nothing new learned — and pairing is the intended use, because
    the Bash tool's 600-second ceiling cannot be crossed by blocking.

    A terminal line is always printed, including on --follow-timeout. Without
    one, a group that is quietly still working and a group whose follower died
    look identical, which is the failure B21 exists to prevent.

    This holds no state: if the follower dies, nothing is lost, because
    `status --group` re-derives everything from the registry. Do not cache
    group state here.
    """
    members = resolve_group(runs_dir, args.group)
    never = unstarted_members(runs_dir, args.group) + vanished_members(runs_dir, args.group)
    # The other two `status` branches report this; the one a caller actually
    # polls did not, so a group whose only member had a corrupt meta.json
    # printed `group.empty` — indistinguishable from a group that never started
    # anything, while the member's run directory and worktree were still there.
    bad = len(unreadable_runs(runs_dir))
    tail = ((f" unstarted={len(never)}" if never else "")
            + (f" unreadable={bad}" if bad else ""))
    if not members:
        sys.stdout.write(f"group.empty group={args.group}" + tail + "\n")
        sys.stdout.flush()
        return
    seen = {}
    started = time.time()
    beat_at = started
    deadline = started + args.follow_timeout if args.follow_timeout else None
    while True:
        rows = []
        for rd, m in members:
            m = read_meta(rd) or m
            row = run_row(rd, m, project)
            rows.append(row)
            prev = seen.get(row["run_id"])
            if prev != row["state"]:
                line = f"run {row['run_id']} {prev or '-'} -> {row['state']}"
                if row.get("exit_code") is not None and row["state"] != "completed":
                    line += f" exit={row['exit_code']}"
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
                seen[row["run_id"]] = row["state"]
        running, done, failed, gstate = group_snapshot(rows, len(never))
        if not running:
            sys.stdout.write(f"group.{gstate} group={args.group} "
                             f"done={len(done)} failed={len(failed)}" + tail + "\n")
            sys.stdout.flush()
            return
        now = time.time()
        if deadline and now >= deadline:
            sys.stdout.write(f"group.still-running group={args.group} "
                             f"running={len(running)} done={len(done)} "
                             f"failed={len(failed)}\n")
            sys.stdout.flush()
            return
        beat, beat_at = heartbeat_due(beat_at, getattr(args, "heartbeat", None), now)
        if beat:
            sys.stdout.write(f"still-running elapsed={int(now - started)} "
                             f"running={len(running)}\n")
            sys.stdout.flush()
        time.sleep(FOLLOW_INTERVAL)


def heartbeat_due(last, every, now):
    """Whether a follower owes a beat, and when the next one is measured from.

    Opt-in on both followers, because the line separates a *busy* run from a
    *dead follower* and only a watcher woken per event can tell the difference
    in the first place. A run that is genuinely wedged already announces itself:
    `run_row` derives `stalled` after 300 idle seconds, so `status --group
    --follow` prints `running -> stalled` on its own.
    """
    if not every or now - last < every:
        return False, last
    return True, now


def follow_group_log(args, project, runs_dir):
    """What `log --run --follow` gives one run, for every member of a group.

    A group had no equivalent, so wanting mid-run signal from three members
    meant arming three followers — and a field report wrote its own polling
    loop instead, got the format wrong, and came within one step of reporting a
    false completion. The single-run follower's contract is kept exactly: every
    line prefixed with the member it came from, the group's own terminal line
    at the end, and nothing held in memory that `status --group` could not
    re-derive after the follower dies.

    Cursors are per member because the files are: each has its own byte offset
    into its own stream, which is why `--since` is refused rather than given
    some collapsed meaning.
    """
    members = resolve_group(runs_dir, args.group)
    never = (unstarted_members(runs_dir, args.group)
             + vanished_members(runs_dir, args.group))
    bad = len(unreadable_runs(runs_dir))
    tail = ((f" unstarted={len(never)}" if never else "")
            + (f" unreadable={bad}" if bad else ""))
    if not members:
        sys.stdout.write(f"group.empty group={args.group}" + tail + "\n")
        sys.stdout.flush()
        return

    labels = {m.get("run_id"): m.get("label")
              for m in (read_group(runs_dir, args.group) or {}).get("members", [])}
    prefixes, cursors = [], []
    header = []
    for i, (_rd, m) in enumerate(members):
        rid = m.get("run_id")
        label = labels.get(rid) or m.get("label")
        # Short enough to read down the left margin at a glance, and the header
        # is what leads back from an index to a `stop --run`. Putting the run id
        # in every line instead cost 24 characters of every line to answer a
        # question asked once.
        # Flattened, because this is a line-oriented protocol and the label is
        # caller text. A label holding a newline splits both the header and
        # every prefix into extra physical lines, and one shaped like
        # `x\ngroup.completed group=g done=2 failed=0` puts a forged terminal
        # line into the stream a watcher is armed on.
        label = " ".join(label.split()) if label else label
        prefixes.append(f"[{i}:{label}] " if label else f"[{i}] ")
        header.append(f"{i}={rid}" + (f":{label}" if label else ""))
        cursors.append(0)
    sys.stdout.write(f"group.members group={args.group} " + " ".join(header) + "\n")
    sys.stdout.flush()

    def drain():
        for i, (rd, m) in enumerate(members):
            events, cursors[i] = read_events(rd / "events.jsonl", cursors[i])
            rel_to = Path(m.get("cwd") or project)
            for entry in format_events(events, args.level, rel_to):
                # Every physical line, not only the first of a multi-line
                # entry. Two members' messages can land adjacent in an
                # interleaved stream, so a continuation line without a prefix
                # belongs to whichever member the reader last saw — which is
                # not always the one that wrote it.
                for line in entry.split("\n"):
                    sys.stdout.write(prefixes[i] + line + "\n")
        sys.stdout.flush()

    started = time.time()
    beat_at = started
    deadline = started + args.follow_timeout if args.follow_timeout else None
    while True:
        drain()
        rows = [run_row(rd, read_meta(rd) or m, project) for rd, m in members]
        running, done, failed, gstate = group_snapshot(rows, len(never))
        if not running or not args.follow:
            # Drained once more after the state was read, not before: an event
            # written between the last read and the terminal check would
            # otherwise be lost on exactly the runs that just finished.
            drain()
            sys.stdout.write(f"group.{gstate} group={args.group} "
                             f"done={len(done)} failed={len(failed)}" + tail + "\n")
            sys.stdout.flush()
            return
        now = time.time()
        if deadline and now >= deadline:
            sys.stdout.write(f"group.still-running group={args.group} "
                             f"running={len(running)} done={len(done)} "
                             f"failed={len(failed)}\n")
            sys.stdout.flush()
            return
        beat, beat_at = heartbeat_due(beat_at, args.heartbeat, now)
        if beat:
            sys.stdout.write(f"still-running elapsed={int(now - started)} "
                             f"running={len(running)}\n")
            sys.stdout.flush()
        time.sleep(FOLLOW_INTERVAL)


def cmd_result_group(args, project, runs_dir):
    members = resolve_group(runs_dir, args.group)
    results, per_run_paths, totals = [], {}, {"input_tokens": 0, "output_tokens": 0}
    for rd, meta in members:
        meta = reap(rd, meta)
        row, info = member_result(rd, meta)
        results.append(row)
        per_run_paths[meta["run_id"]] = changed_paths(
            rd / "events.jsonl", (meta.get("worktree") or {}).get("path") or meta.get("cwd"))
        for key in totals:
            totals[key] += int((info["usage"] or {}).get(key) or 0)
    found = overlaps(per_run_paths)
    never = unstarted_members(runs_dir, args.group) + vanished_members(runs_dir, args.group)
    running, done, failed, gstate = group_snapshot(results, len(never))
    emit({"group": args.group, "project": str(project), "results": results,
          "overlaps": found, "totals": totals, "group_state": gstate,
          "done": done, "failed": failed, "running": running, "unstarted": never,
          "overlaps_note": ("paths written by more than one member. Under worktree "
                            "isolation this is a merge conflict ahead, not damage "
                            "already done.") if found else None})
