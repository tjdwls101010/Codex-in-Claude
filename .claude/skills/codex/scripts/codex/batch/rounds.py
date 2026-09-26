"""A next round: `batch start --resume-from` pairs task i with member i of an earlier group, or refuses the whole batch before anything is claimed."""

from __future__ import annotations

from codex.errors import Refusal
from codex.registry.groups import group_path, group_unreadable, list_groups, owned_run_ids, read_group
from codex.registry.runs import find_run, is_live, meta_unreadable, reap


def pair_with_previous(tasks, runs_dir, previous: str, *, force=False):
    """Turn task i into the resume of member i of `previous`, in start order, or refuse the whole batch before anything is claimed. A task naming its own target keeps it. Returns `(tasks, previous member ids)`."""
    manifest = read_group(runs_dir, previous)
    if manifest is None:
        if group_unreadable(runs_dir, previous):
            # Only the manifest records slots; inferring an order would land tasks on other tasks' threads.
            raise Refusal(f"group {previous!r} has a manifest that will not parse, and only the manifest records the start order --resume-from pairs by",
                          manifest=str(group_path(runs_dir, previous)),
                          members_recorded_by_runs=owned_run_ids(runs_dir, previous))
        raise Refusal(f"no such group to resume from: {previous}", known_groups=list_groups(runs_dir)[:20])
    prior = [m for m in manifest.get("members") or [] if m.get("run_id")]
    if not prior:
        raise Refusal(f"group {previous!r} has no members that started, so there is nothing to resume")
    threadless = [m["run_id"] for m in prior if not (find_run(runs_dir, m["run_id"])[1] or {}).get("thread_id")]
    if threadless:
        raise Refusal(f"{len(threadless)} member(s) of {previous!r} have no thread id, so there is nothing to continue for them; `status --run` shows why. --resume-from needs every started member, so start that work fresh",
                      members=threadless)
    if len(tasks) != len(prior):
        raise Refusal(f"--resume-from pairs task i with member i, but {previous!r} has {len(prior)} started member(s) and this batch has {len(tasks)} task(s)",
                      previous_members=[m["run_id"] for m in prior])
    # Checked for the whole group up front: per member, the refusal would come after earlier tasks had already resumed.
    live = []
    for m in prior:
        rd, meta = find_run(runs_dir, m["run_id"])
        if meta is None:
            if rd is not None and meta_unreadable(rd):
                live.append({"run_id": m["run_id"], "state": "unreadable",
                             "reason": "its meta.json will not parse, so whether "
                                       "its turn has finished cannot be determined"})
            continue
        reaped = reap(rd, meta)
        if is_live(reaped):
            live.append({"run_id": m["run_id"], "state": reaped.get("state")})
    if live and not force:
        raise Refusal(f"group {previous!r} still has members running; wait for them, or pass --force to continue them mid-turn", running=live)

    paired = []
    for slot, (task, prev) in enumerate(zip(tasks, prior)):
        kind, named = task["kind"], task.get("resume")
        if kind != "resume" and named:
            raise Refusal(f"task {slot} names a `resume` target but has kind {kind!r}; set kind 'resume' to keep the target, or drop `resume` to pair it with {prev['run_id']}", arguments=True)
        paired.append(task if named else {**task, "kind": "resume", "resume": prev["run_id"]})
    return paired, [m["run_id"] for m in prior]
