"""Groups: `<runs_dir>/.groups/<name>.json`, the set of runs one `batch start` created, addressed afterwards as one thing.

The manifest is a file rather than a query over the registry: claiming it is the atomic claim on the name, it records start order (which `--resume-from` pairs against and which run ids cannot recover — same-second, same-label starts are the normal case), and reading a group does not walk the whole registry on every follower tick.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import uuid
from pathlib import Path

from codex.catalog import check_model_effort, model_catalog
from codex.config import user_defaults
from codex.events import read_events
from core import settings
from core.observe import progress, turn_failed_excerpt
from core.registry import (
    find_run, is_live, iter_runs, meta_unreadable, reap, still_writing, write_json_atomic,
)
from core.runs import WRITING_SANDBOXES, create_run
from util import BridgeError, clip, fail, failures_raise, git_toplevel, is_within, nfc, now_iso
from worktree import (
    ignored_entries as worktree_ignored_entries, is_dirty as worktree_dirty,
    missing_at_base as worktree_missing_at_base, prune as worktree_prune,
    remove as worktree_remove, repo_identity, resolve_base as worktree_base_sha,
    uncommitted_count as worktree_uncommitted,
)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

TASK_FIELDS = ("prompt", "kind", "label", "model", "effort", "sandbox", "schema", "image", "cwd", "resume")
# Types are checked too: a wrong-typed value would otherwise surface as a Python error inside `create_run`, after earlier members spawned.
TASK_FIELD_TYPES = {"prompt": str, "kind": str, "label": str, "model": str, "effort": str, "sandbox": str,
                    "schema": str, "cwd": str, "resume": str, "image": list}

# Per member, in bytes, in `result --group`; `result --run` returns the whole message.
GROUP_MESSAGE_CAP = 4000


# -- the manifest -------------------------------------------------------------

def groups_dir(runs_dir: Path) -> Path:
    return runs_dir / ".groups"


def group_path(runs_dir: Path, name: str) -> Path:
    return groups_dir(runs_dir) / f"{name}.json"


def valid_name(name: str) -> bool:
    """A group name becomes a filename, so no separator and no leading dot."""
    return bool(NAME_RE.match(name or ""))


def read_group(runs_dir: Path, name: str):
    try:
        return json.loads(group_path(runs_dir, name).read_text(encoding="utf-8"))
    except Exception:
        return None


def group_unreadable(runs_dir: Path, name: str) -> bool:
    """Present but will not parse, as distinct from absent. Membership survives it (each run records its group); start order does not."""
    return group_path(runs_dir, name).is_file() and read_group(runs_dir, name) is None


def list_groups(runs_dir: Path):
    d = groups_dir(runs_dir)
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def claim_group(runs_dir: Path, name: str, derived_from=None, requested=0) -> dict:
    """Take the name before anything spawns; FileExistsError if it is taken.

    `os.link` publishes a manifest that is already complete, so no reader sees the name without its content. `requested` is written now because a batch killed partway would otherwise be indistinguishable from one that asked for fewer tasks. `epoch` identifies this claim, so a writer notices if the name was released and claimed again underneath it.
    """
    d = groups_dir(runs_dir)
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"group": name, "created_at": now_iso(), "epoch": uuid.uuid4().hex,
                "derived_from": derived_from, "requested": requested, "members": []}
    path = group_path(runs_dir, name)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return manifest


def write_members(runs_dir: Path, name: str, members: list, epoch=None) -> dict:
    """Record the member list so far, after every member: a spawned member must be reachable through its group from the instant it exists."""
    manifest = read_group(runs_dir, name) or {"group": name, "created_at": now_iso(), "derived_from": None}
    if epoch is not None and manifest.get("epoch") != epoch:
        fail(f"group {name!r} was released and re-claimed while this batch was "
             f"still starting; its manifest is no longer this batch's",
             spawned=[m.get("run_id") for m in members if m.get("run_id")])
    manifest["members"] = members
    write_json_atomic(group_path(runs_dir, name), manifest)
    return manifest


def member_run_ids(runs_dir: Path, name: str):
    """Run ids in start order, skipping slots that never spawned; `[]` for an unreadable manifest, None for an absent one."""
    g = read_group(runs_dir, name)
    if not g:
        return [] if group_unreadable(runs_dir, name) else None
    return [m["run_id"] for m in g.get("members", []) if m.get("run_id")]


def owned_run_ids(runs_dir: Path, name: str):
    """Every run that says it belongs to this group, manifest order first, then runs only the registry knows — the manifest lags a member that was killed between claiming its directory and being recorded."""
    ids = member_run_ids(runs_dir, name)
    if ids is None:
        return None
    seen = set(ids)
    return ids + [m["run_id"] for _rd, m in iter_runs(runs_dir)
                  if m.get("group") == name and m.get("run_id") and m["run_id"] not in seen]


def derived_groups(runs_dir: Path, name: str):
    """Groups whose `--resume-from` was this one; their members work in this group's worktrees."""
    return [g for g in list_groups(runs_dir) if (read_group(runs_dir, g) or {}).get("derived_from") == name]


def resolve_group(runs_dir: Path, name: str):
    """Members as (run_dir, meta) in start order; refuses an unknown or unreadable group. Slots that never spawned are `unstarted_members`."""
    if group_unreadable(runs_dir, name):
        fail(f"group {name!r} has a manifest that will not parse, so its "
             f"membership and start order cannot be read from it",
             manifest=str(group_path(runs_dir, name)),
             members_recorded_by_runs=owned_run_ids(runs_dir, name),
             remedy=f"`batch clean --group {name} --force` removes their "
                    f"worktrees and releases the name")
    ids = member_run_ids(runs_dir, name)
    if ids is None:
        fail(f"no such group: {name}", runs_dir=str(runs_dir), known_groups=list_groups(runs_dir))
    out = []
    for rid in ids:
        rd, m = find_run(runs_dir, rid)
        if m:
            out.append((rd, m))
    return out


def unstarted_members(runs_dir: Path, name: str):
    """Slots that never became runs, including tasks a killed `batch start` never reached, so no group view answers as if fewer were asked for."""
    g = read_group(runs_dir, name) or {}
    members = g.get("members", [])
    never = [{"index": m.get("index"), "label": m.get("label"), "kind": m.get("kind"), "error": m.get("error")}
             for m in members if not m.get("run_id")]
    for i in range(len(members), g.get("requested") or 0):
        never.append({"index": i, "label": None, "kind": None,
                      "error": "batch start recorded no run for this task"})
    return never


def vanished_members(runs_dir: Path, name: str):
    """Members the manifest names that no longer resolve — a directory removed by hand, or one whose meta.json will not parse, which still holds its work."""
    gone = []
    for m in (read_group(runs_dir, name) or {}).get("members", []):
        rid = m.get("run_id")
        if not rid:
            continue
        rd, meta = find_run(runs_dir, rid)
        if meta:
            continue
        present = rd is not None and meta_unreadable(rd)
        gone.append({"index": m.get("index"), "label": m.get("label"), "run_id": rid,
                     "error": ("its meta.json will not parse; the run directory "
                               "is still there and may still hold results"
                               if present else "its run directory is no longer in the registry")})
    return gone


# -- tasks --------------------------------------------------------------------

def load_tasks(args):
    """The ordered task list: `--task` prompts first (as typed), then `--tasks-file` entries, each validated so a broken file costs nothing."""
    tasks = [{"prompt": p, "kind": "start"} for p in (args.task or [])]
    if args.tasks_file:
        try:
            raw = Path(args.tasks_file).read_text(encoding="utf-8")
        except OSError as e:
            fail(f"cannot read tasks file: {e}")
        for n, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if line and not line.startswith("#"):
                tasks.append(_task_from_line(n, line, args))
    if not tasks:
        fail("batch start needs at least one --task or a --tasks-file")
    return tasks


def _task_from_line(n, line, args):
    try:
        item = json.loads(line)
    except json.JSONDecodeError as e:
        fail(f"tasks file line {n} is not valid JSON: {e}", line=clip(line, 200))
    if not isinstance(item, dict):
        fail(f"tasks file line {n} is not a JSON object", line=clip(line, 200))
    unknown = set(item) - set(TASK_FIELDS)
    if unknown:
        # A silently ignored field is a member that quietly used the group default.
        fail(f"tasks file line {n} has unknown field(s): {sorted(unknown)}", known_fields=list(TASK_FIELDS))
    for field, want in TASK_FIELD_TYPES.items():
        if field in item and not isinstance(item[field], want):
            fail(f"tasks file line {n}: {field!r} must be {want.__name__}, got {type(item[field]).__name__}",
                 line=clip(line, 200))
    if any(not isinstance(i, str) for i in item.get("image") or []):
        fail(f"tasks file line {n}: 'image' must be a list of paths", line=clip(line, 200))
    item.setdefault("kind", "start")
    if item["kind"] not in ("start", "resume"):
        fail(f"tasks file line {n}: kind must be start or resume"
             + ("; `review` was removed in 0.7.0 — use kind 'start' "
                "with sandbox 'read-only' and say what to look at in "
                "the prompt" if item["kind"] == "review" else ""),
             got=item["kind"])
    # Under --resume-from the target comes from the pairing, so an unnamed resume is normal there.
    if item["kind"] == "resume" and not item.get("resume") and not getattr(args, "resume_from", None):
        fail(f"tasks file line {n}: kind 'resume' needs a 'resume' field naming a run id or thread id")
    return item


def task_args(base_args, item):
    """A member's options: the group's as defaults, the task's own fields over them."""
    ns = argparse.Namespace(**vars(base_args))
    ns.prompt = item.get("prompt")
    ns.prompt_file = None
    for field in ("label", "model", "effort", "sandbox", "cwd"):
        if item.get(field) is not None:
            setattr(ns, field, item[field])
    if item.get("schema") is not None:
        ns.schema = item["schema"]
    ns.image = item.get("image") or []
    ns.add_dir = getattr(base_args, "add_dir", None) or []
    return ns


def check_task_settings(tasks, args, runs_dir):
    """Refuse a model or effort any task would adopt, before the group name is claimed and with one catalog lookup, rather than at the eighth member with seven already running."""
    user = user_defaults()
    adopted = []
    for n, item in enumerate(tasks, 1):
        ns = task_args(args, item)
        base = find_run(runs_dir, item["resume"])[1] if item["kind"] == "resume" else None
        adopted.append((n, settings.resolve(
            sandbox=ns.sandbox, model=ns.model, effort=ns.effort, priority=getattr(ns, "priority", None),
            inherit_config=getattr(ns, "inherit_config", False), base=base, user=user)["adopted"]))
    if not any(a["model"] or a["effort"] for _n, a in adopted):
        return
    catalog = model_catalog()
    for n, a in adopted:
        if a["model"] or a["effort"]:
            check_model_effort(a["model"], a["effort"], catalog=catalog,
                               fail=lambda msg, _n=n, **extra: fail(f"task {_n}: {msg}", **extra),
                               model_source=a["model_source"], effort_source=a["effort_source"])


# -- continuing a group ---------------------------------------------------------

def pair_with_previous(tasks, runs_dir, previous: str, *, force=False):
    """Turn task i into the resume of member i of `previous`, in start order, or refuse the whole batch before anything is claimed. A task naming its own target keeps it. Returns `(tasks, previous member ids)`."""
    manifest = read_group(runs_dir, previous)
    if manifest is None:
        if group_unreadable(runs_dir, previous):
            # Only the manifest records slots; inferring an order would land tasks on other tasks' threads.
            fail(f"group {previous!r} has a manifest that will not parse, and "
                 f"--resume-from pairs task to member by position, which only "
                 f"the manifest records",
                 manifest=str(group_path(runs_dir, previous)),
                 members_recorded_by_runs=owned_run_ids(runs_dir, previous))
        fail(f"no such group to resume from: {previous}", known_groups=list_groups(runs_dir)[:20])
    prior = [m for m in manifest.get("members") or [] if m.get("run_id")]
    if not prior:
        fail(f"group {previous!r} has no members that started, so there is nothing to resume")
    threadless = [m["run_id"] for m in prior if not (find_run(runs_dir, m["run_id"])[1] or {}).get("thread_id")]
    if threadless:
        fail(f"{len(threadless)} member(s) of {previous!r} never recorded a "
             f"thread id, so there is no conversation to continue for them — "
             f"they failed before Codex started one, and their `stderr.log` "
             f"records why. This refuses the whole batch rather than those "
             f"slots: --resume-from pairs one task to every started member, so "
             f"work for a threadless slot has to be started fresh, in a batch "
             f"of its own",
             members=threadless)
    if len(tasks) != len(prior):
        fail(f"--resume-from pairs one task to one member in order, but "
             f"{previous!r} has {len(prior)} started member(s) and this batch "
             f"has {len(tasks)} task(s)",
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
        fail(f"group {previous!r} still has members running; resuming a thread "
             f"mid-turn would run two turns on it at once", running=live)

    paired = []
    for slot, (task, prev) in enumerate(zip(tasks, prior)):
        kind, named = task["kind"], task.get("resume")
        if kind != "resume" and named:
            fail(f"task {slot} names a thread to resume but its kind is "
                 f"{kind!r}; under --resume-from, set kind to 'resume' to keep "
                 f"that target or drop the 'resume' field to be paired with "
                 f"{prev['run_id']}")
        paired.append(task if named else {**task, "kind": "resume", "resume": prev["run_id"]})
    return paired, [m["run_id"] for m in prior]


# -- worktrees for a batch ------------------------------------------------------

def wants_worktree(item, args):
    """Whether `--worktree` would isolate this member: a fresh writer with no cwd of its own. A read-only member would see none of the caller's uncommitted work in a checkout; a resume keeps its thread's directory."""
    if item["kind"] == "resume" or item.get("cwd") or getattr(args, "cwd", None):
        return False
    return (item.get("sandbox") or args.sandbox or "workspace-write") in WRITING_SANDBOXES


def why_not_isolated(item, args):
    """Why `--worktree` would pass this member over, in the caller's words, or None."""
    if item["kind"] == "resume":
        return "a resumed thread keeps the directory it already lives in"
    if item.get("cwd") or getattr(args, "cwd", None):
        return "a member with a cwd of its own was told where to go"
    return None


def writers_by_directory(tasks, args, project, runs_dir):
    """Members that will write, grouped by the directory they will write in, resolved as `create_run` will resolve them."""
    dirs = {}
    for i, item in enumerate(tasks):
        parent = None
        if item["kind"] == "resume" and item.get("resume"):
            _rd, parent = find_run(runs_dir, item["resume"])
        ns = task_args(args, item)
        r = settings.resolve(sandbox=ns.sandbox, cwd=getattr(ns, "cwd", None), base=parent)
        if r["sandbox"] in WRITING_SANDBOXES:
            dirs.setdefault(str(r["cwd"] or project), []).append(i)
    return dirs


def sharing_note(shared, reasons):
    """Who is about to write into one directory, and — only where it would work — the remedy."""
    parts = "; ".join(f"{len(idx)} members write to {d} and share it" for d, idx in shared.items())
    tail = (" `--worktree` gives each its own checkout instead; `result --group` "
            "then reports which paths more than one wrote."
            if not reasons else
            " `--worktree` does not separate all of them: " + "; ".join(reasons) + ".")
    return (parts + ", so each one's changes are in that tree as it makes them "
            "— and none of them can tell another's edit from its own." + tail)


def plan_worktrees(tasks, args, project, runs_dir):
    """Which members get a checkout, cut from which commit, and a note when members will share a tree. Returns `(eligible indices, base sha, note)`.

    Isolation is opt-in: without `--worktree` members share the caller's tree as a fan-out of Claude's own subagents does, and the note says so only when two or more writers share a directory.
    """
    eligible = {i for i, t in enumerate(tasks) if wants_worktree(t, args)}
    shared = {d: idx for d, idx in writers_by_directory(tasks, args, project, runs_dir).items() if len(idx) > 1}

    def reasons_for(indices):
        out = []
        for i in indices:
            r = why_not_isolated(tasks[i], args)
            if r and r not in out:
                out.append(r)
        return out

    if not getattr(args, "worktree", False):
        if not shared:
            return set(), None, None
        return set(), None, sharing_note(shared, reasons_for(i for idx in shared.values() for i in idx))
    if not eligible:
        why = reasons_for(range(len(tasks)))
        if not why:
            return set(), None, "no member writes to the tree, so there is nothing to isolate"
        note = "no worktree is cut: " + "; ".join(why) + "."
        return set(), None, note + (" " + sharing_note(shared, why) if shared else "")
    if git_toplevel(project) is None:
        return set(), None, (f"{project} is not a git repository, so worktrees "
                             "are unavailable; members share the caller's tree")
    ref = getattr(args, "base", None)
    base = worktree_base_sha(project, ref)
    if not base and ref:
        # A typo'd --base is the caller's mistake; degrading to a shared tree would give them the one outcome they asked to avoid.
        fail(f"--base {ref!r} does not resolve to a commit in {project}")
    if not base:
        return set(), None, ("this repository has no HEAD yet (nothing is "
                             "committed), so there is no commit to cut a "
                             "worktree from; members share the caller's tree")
    return eligible, base, None


def worktree_report(project, runs_dir, base, count):
    """What the caller cannot see from anywhere else about the checkouts just cut: their base, the uncommitted and ignored work they lack, and instructions missing at the base."""
    out = {"count": count, "base": base,
           "uncommitted_files_in_caller_tree": worktree_uncommitted(project),
           "note": "each writing member has its own checkout at "
                   "<run_dir>/wt. Their changes are not in your tree; "
                   "`result --group` reports which paths more than one wrote. "
                   "`batch clean --group` removes them once you have collected."}
    try:
        own = runs_dir.relative_to(project).as_posix() + "/"
    except ValueError:
        own = None
    ignored, more = worktree_ignored_entries(project, base=base, skip=[own] if own else [])
    if ignored:
        out["missing_ignored"] = ignored
        if more:
            out["missing_ignored_truncated"] = more
    missing = worktree_missing_at_base(project, base)
    if missing:
        out["missing_at_base"] = missing
        out["missing_note"] = (f"{', '.join(missing)} exists in your tree but not at the base "
                               f"these worktrees were cut from, so these runs start without "
                               f"the project instructions a HEAD-based run would have had.")
    return out


# -- spawning -------------------------------------------------------------------

def spawn_task(ns, item, *, group, runs_dir, batch=None, worktree_base=None):
    """Start one member, as `start` or `resume` would. A resume target outside the registry is passed through: it may be a thread started elsewhere."""
    if item["kind"] == "resume":
        _rd, base = find_run(runs_dir, item["resume"])
        if not base:
            return create_run(ns, kind="resume", thread_ref=item["resume"], group=group, batch=batch)
        return create_run(ns, kind="resume", base=base, thread_ref=base.get("thread_id"), group=group, batch=batch)
    return create_run(ns, kind="start", group=group, batch=batch, worktree_base=worktree_base)


def spawn_members(args, tasks, *, runs_dir, epoch, isolated, base):
    """Spawn every task in order. A member that fails keeps its slot with the error, and the others still start. Returns `(manifest members, reply rows)`."""
    batch_ctx = {"n": len(tasks), "group": args.group}
    members, results = [], []
    for index, item in enumerate(tasks):
        entry = {"index": index, "kind": item["kind"], "label": item.get("label") or args.label}
        # The slot is recorded before the spawn, so a checkout cut by a batch killed mid-spawn still belongs to the group.
        members.append(entry)
        write_members(runs_dir, args.group, members, epoch=epoch)
        try:
            with failures_raise():
                out = spawn_task(task_args(args, item), item, group=args.group, runs_dir=runs_dir, batch=batch_ctx,
                                 worktree_base=base if index in isolated else None)
        except Exception as e:
            # Any exception, not only an anticipated refusal: escaping would abort the batch with members already running.
            entry["error"] = e.msg if isinstance(e, BridgeError) else str(e)
            entry.update(e.extra if isinstance(e, BridgeError) else {"error_type": type(e).__name__})
            results.append(entry)
            write_members(runs_dir, args.group, members, epoch=epoch)
            continue
        entry.update(run_id=out["run_id"], thread_id=out.get("thread_id"), cwd=out.get("cwd"),
                     sandbox=out.get("sandbox"))
        if out.get("worktree"):
            entry["worktree"] = out["worktree"]["path"]
        results.append({**entry, "state": out.get("state")})
        write_members(runs_dir, args.group, members, epoch=epoch)
    return members, results


# -- cleaning a group -------------------------------------------------------------

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
        fail(f"no such group in this project: {name}", known_groups=list_groups(runs_dir)[:20])
    live, unknown = _member_liveness(runs_dir, name)
    if live:
        fail(f"group {name!r} still has running members; stop them first",
             running=live, stop=stop_commands(live, runs_dir, explicit_registry))
    overrode = _check_liftable_guards(runs_dir, name, force=force, lost_manifest=lost_manifest, unknown=unknown)
    removed, kept = _remove_worktrees(project, runs_dir, name, force=force,
                                      explicit_registry=explicit_registry, overrode=overrode)

    released = not kept and not unknown
    if released:
        group_path(runs_dir, name).unlink(missing_ok=True)
        note = None
    elif unknown or any(k.get("stop") for k in kept):
        note = ("some members are live or cannot be read"
                + (f" ({', '.join(m['run_id'] for m in unknown)} will not parse; "
                   f"repair or remove those run directories)" if unknown else "")
                + "; kept[].reason says which worktree is held and kept[].stop "
                "how to end a live run. The group name stays claimed until "
                "nothing is left.")
    else:
        note = ("these worktrees hold uncommitted changes — collect them, or "
                "pass --force to discard. The group name stays claimed until "
                "they are gone.")
    out = {"group": name, "removed": removed, "kept": kept, "name_released": released, "note": note}
    if overrode:
        out["forced_past"] = overrode
        out["forced_note"] = ("--force lifted every protection at once, not only the one you were "
                              "after. What it overrode is listed above; none of it is recoverable "
                              "from here.")
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
         f"group {name!r} has a manifest that will not parse, so what it "
         f"was and what order it ran in cannot be read. Its members are still "
         f"recoverable from the registry; pass --force to remove their "
         f"worktrees and release the name",
         lambda: {"manifest": str(group_path(runs_dir, name)),
                  "members_recorded_by_runs": owned_run_ids(runs_dir, name)},
         str(group_path(runs_dir, name))),
        ("unreadable_members", bool(unknown),
         f"group {name!r} has members whose meta.json will not parse, so "
         f"whether they are still running cannot be determined; pass --force "
         f"to clean anyway",
         lambda: {"running": unknown}, unknown),
        # `--resume-from` puts phase 2 in phase 1's worktrees. One hop only, which is why the removal asks the registry again.
        ("derived_groups", bool(children),
         f"group {name!r} was resumed by another group, whose members are "
         f"working in these worktrees",
         lambda: {"derived_groups": children}, children),
    ]
    overrode = {}
    for key, tripped, message, detail, forced_value in guards:
        if tripped:
            if not force:
                fail(message, **detail())
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
                         "reason": "its meta.json will not parse, so whether it "
                                   "is still running cannot be determined; "
                                   "repair or remove the run directory to "
                                   "release this worktree",
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
