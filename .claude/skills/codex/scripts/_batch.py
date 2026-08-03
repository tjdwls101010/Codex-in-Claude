"""Groups: `<project>/.codex-runs/.groups/<name>.json`.

A group is a set of runs started by one `batch start` and thereafter addressed
as one thing — `status --group`, `result --group`, `stop --group`. The manifest
is a small file rather than a derived query, and each of the three reasons is
load-bearing:

  * **Uniqueness is free.** Creating the file with `O_EXCL` is the atomic claim
    on the name, so a second `batch start --group p1` fails on the filesystem
    rather than on a check that could race.
  * **Membership order is recorded, not re-derived.** `--resume-from` pairs the
    previous group's members with this group's tasks positionally, and a run id
    carries only a one-second stamp — batch start makes same-second, same-label
    starts the normal case (audit F15), so ordering by id or timestamp would be
    a coin flip exactly when it matters most.
  * **Reading a group does not walk the whole registry.** `status --group
    --follow` polls once a second; resolving membership through `iter_runs`
    would re-read every meta.json in the project on every tick.

`iter_runs` skips dot-directories, so `.groups/` is invisible to it and cannot
be mistaken for a run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

from _events import read_events, scan_progress
from _registry import (
    TERMINAL_STATES, ensure_runs_dir, find_run, iter_runs, read_meta, reap,
    resolve_project, resolve_runs_dir, unreadable_runs,
)
from _codex import review_argv
from _run import (
    WRITING_SANDBOXES, create_run, refuse_concurrent_turn, run_row,
)
from _util import (
    BridgeError, clip, emit, fail, failures_raise, git_toplevel, is_within, nfc,
    now_iso,
)
from _worktree import (
    is_dirty as worktree_dirty, missing_at_base as worktree_missing_at_base,
    prune as worktree_prune, remove as worktree_remove, repo_identity,
    resolve_base as worktree_base_sha, uncommitted_count as worktree_uncommitted,
)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def groups_dir(runs_dir: Path) -> Path:
    return runs_dir / ".groups"


def group_path(runs_dir: Path, name: str) -> Path:
    return groups_dir(runs_dir) / f"{name}.json"


def valid_name(name: str) -> bool:
    """A group name becomes a filename, so it may not contain a separator or
    start with a dot. Rejecting up front beats discovering it as a traversal."""
    return bool(NAME_RE.match(name or ""))


def read_group(runs_dir: Path, name: str):
    try:
        return json.loads(group_path(runs_dir, name).read_text(encoding="utf-8"))
    except Exception:
        return None


def list_groups(runs_dir: Path):
    d = groups_dir(runs_dir)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _tmp_path(path: Path) -> Path:
    """A tmp name no other writer can be using. Same discipline as `write_meta`
    (F1): a fixed name lets two writers truncate each other's file and lets a
    reader see the result."""
    return path.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")


def _write_atomic(path: Path, manifest: dict):
    tmp = _tmp_path(path)
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def claim_group(runs_dir: Path, name: str, derived_from=None, requested=0) -> dict:
    """Take the name, atomically, before any run is spawned.

    Raises FileExistsError if the name is taken. Claiming first means a
    duplicate name costs nothing — no Codex process has started yet.

    `requested` is written here, before the first spawn, because it is the one
    fact that cannot be recovered afterwards. `members` grows as the loop
    reaches each task, so a `batch start` killed partway through leaves a
    manifest that is internally consistent and wrong: asked for three, given
    two, and indistinguishable from a group that only ever asked for two. That
    reports `completed` — the same lie R12 exists to prevent, arriving by a
    different road. A manifest written before v0.2.1 has no `requested`, and
    falls back to counting only the slots it does have.

    The claim is `os.link`, not `O_CREAT|O_EXCL` on the destination, and the
    difference is not cosmetic. `O_EXCL` creates the file empty and fills it
    afterwards, so a crash — or merely a concurrent reader arriving in that
    window — sees a name that exists with no parsable content behind it, which
    `read_group` cannot distinguish from a corrupt manifest. `link` publishes a
    file that is already complete, and fails if the name is taken, so the name
    and its content appear in the same instant.
    """
    d = groups_dir(runs_dir)
    d.mkdir(parents=True, exist_ok=True)
    manifest = {"group": name, "created_at": now_iso(),
                "derived_from": derived_from, "requested": requested, "members": []}
    path = group_path(runs_dir, name)
    tmp = _tmp_path(path)
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.link(tmp, path)   # raises FileExistsError if the name is taken
    finally:
        tmp.unlink(missing_ok=True)
    return manifest


def write_members(runs_dir: Path, name: str, members: list) -> dict:
    """Record the member list so far, in start order.

    Called after **every** member rather than once at the end. Writing once was
    the natural shape — `batch start` is the only writer and knows the full list
    by the time it finishes — but it left a window with teeth: a batch killed
    partway through had already spawned live Codex processes whose manifest
    still said `members: []`, so `status/stop/result --group` could not see them
    and nothing could stop them through the group. Rewriting a file of a few
    hundred bytes N times is not a cost worth trading that for.
    """
    path = group_path(runs_dir, name)
    manifest = read_group(runs_dir, name) or {"group": name, "created_at": now_iso(),
                                              "derived_from": None}
    manifest["members"] = members
    _write_atomic(path, manifest)
    return manifest


def member_run_ids(runs_dir: Path, name: str):
    """Run ids in start order, skipping members that never spawned."""
    g = read_group(runs_dir, name)
    if not g:
        return None
    return [m["run_id"] for m in g.get("members", []) if m.get("run_id")]


def owned_run_ids(runs_dir: Path, name: str):
    """Every run that says it belongs to this group, manifest first.

    The manifest is `batch start`'s record and it lags what is already on disk:
    `create_run` mints the run id, cuts the worktree and writes `meta.json`
    before it returns, and only then does the spawn loop learn the id and put it
    in the manifest. A batch killed inside that window — up to THREAD_ID_WAIT
    wide — leaves a full checkout whose slot has no run id, and anything that
    resolves membership through `member_run_ids` alone can never reach it.

    So membership is asked of the registry as well: a run records its own group
    at the moment its directory is claimed. This is R10 again, and for the same
    reason — a run's own record cannot go stale the way a manifest entry that
    was never written cannot be recovered. Manifest order comes first because
    `--resume-from` pairs positionally against it; registry-only members are
    appended, since by definition nothing ever recorded an order for them.
    """
    ids = member_run_ids(runs_dir, name)
    if ids is None:
        return None
    seen = set(ids)
    extra = [m["run_id"] for _rd, m in iter_runs(runs_dir)
             if m.get("group") == name and m.get("run_id")
             and m["run_id"] not in seen]
    return ids + extra


def derived_groups(runs_dir: Path, name: str):
    """Groups whose `--resume-from` was this one. `batch clean` needs them:
    a phase-2 member resumes into its phase-1 predecessor's worktree, so
    removing phase 1's worktrees pulls the ground out from under phase 2."""
    return [g for g in list_groups(runs_dir)
            if (read_group(runs_dir, g) or {}).get("derived_from") == name]


# --------------------------------------------------------------------------
# the batch subcommands, and the group views `status` and `result` grow for one
# --------------------------------------------------------------------------
TASK_FIELDS = ("prompt", "kind", "label", "model", "effort", "sandbox", "schema",
               "image", "cwd", "resume", "review")

# Checking the field *names* is not enough. A value of the wrong type reaches
# argv composition unexamined and surfaces as a Python error from deep inside
# `create_run` — `{"prompt": 123}` becomes `AttributeError: 'int' object has no
# attribute 'strip'`. The batch's own D11 net catches that now, but only after
# the earlier members have already spawned; a tasks file this broken should
# cost nothing, and the way to make it cost nothing is to read it fully before
# starting anything.
REVIEW_FIELDS = ("uncommitted", "base", "commit", "title")

TASK_FIELD_TYPES = {"prompt": str, "kind": str, "label": str, "model": str,
                    "effort": str, "sandbox": str, "schema": str, "cwd": str,
                    "resume": str, "image": list, "review": dict}


def load_tasks(args):
    """Build the ordered task list from `--task` and `--tasks-file`.

    Both may be given; `--task` entries come first, because that is the order
    they were typed in and `--resume-from` pairs positionally. A `--task` is
    always `kind: start` — it is a bare prompt with nowhere to say otherwise.
    """
    tasks = [{"prompt": p, "kind": "start"} for p in (args.task or [])]
    if args.tasks_file:
        try:
            raw = Path(args.tasks_file).read_text(encoding="utf-8")
        except OSError as e:
            fail(f"cannot read tasks file: {e}")
        for n, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                fail(f"tasks file line {n} is not valid JSON: {e}", line=clip(line, 200))
            if not isinstance(item, dict):
                fail(f"tasks file line {n} is not a JSON object", line=clip(line, 200))
            unknown = set(item) - set(TASK_FIELDS)
            if unknown:
                # Loud, because the failure mode of a silently ignored field is
                # a run that quietly used the group default instead.
                fail(f"tasks file line {n} has unknown field(s): {sorted(unknown)}",
                     known_fields=list(TASK_FIELDS))
            for field, want in TASK_FIELD_TYPES.items():
                if field in item and not isinstance(item[field], want):
                    fail(f"tasks file line {n}: {field!r} must be "
                         f"{want.__name__}, got {type(item[field]).__name__}",
                         line=clip(line, 200))
            if any(not isinstance(i, str) for i in item.get("image") or []):
                fail(f"tasks file line {n}: 'image' must be a list of paths",
                     line=clip(line, 200))
            # The same rule one level down. `review` is the only nested object
            # a task has, and typing `titel` into it was silently a no-op while
            # typing it at the top level was a loud refusal.
            unknown_review = set(item.get("review") or {}) - set(REVIEW_FIELDS)
            if unknown_review:
                fail(f"tasks file line {n} has unknown 'review' field(s): "
                     f"{sorted(unknown_review)}", known_fields=list(REVIEW_FIELDS))
            item.setdefault("kind", "start")
            if item["kind"] not in ("start", "resume", "review"):
                fail(f"tasks file line {n}: kind must be start, resume or review",
                     got=item["kind"])
            if (item["kind"] == "resume" and not item.get("resume")
                    and not getattr(args, "resume_from", None)):
                # --resume-from supplies the target positionally, so under it
                # an unnamed resume is the normal form rather than an omission.
                fail(f"tasks file line {n}: kind 'resume' needs a 'resume' field "
                     f"naming a run id or thread id")
            tasks.append(item)
    if not tasks:
        fail("batch start needs at least one --task or a --tasks-file")
    return tasks


def task_args(base_args, item):
    """A per-task argv namespace: the group-level options as defaults, the
    task's own fields overriding them.

    Group options are defaults rather than constraints on purpose — a batch is
    usually "the same thing N ways", and the exceptions are exactly what the
    per-item fields exist to express.
    """
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


def projected_cost(runs_dir: Path, n_runs: int):
    """What N runs are likely to cost, computed from this project's own history
    rather than a constant.

    D37. A baked-in number rots: the isolation overhead measured at design time
    moved 2.92x -> 1.09x within two weeks (R8), so any constant written here
    would be wrong by the time anyone read it. The median input_tokens over
    recent isolated, completed runs is the same measurement taken fresh.

    It was called a *floor* until this was measured against the registry it is
    computed from: 6 of 11 real runs came in **below** it. Of course they did —
    a median is exceeded by half its samples by construction, and the word
    invited a caller to read "at least this much" from a number that is under
    the truth as often as over it. A misleading name is a false premise the
    caller then reasons correctly from, which is R19 in a different place.

    Reported, not enforced (D10): the caller decides whether N runs is worth
    it, and this only makes the decision informed instead of blind.
    """
    samples = []
    for _rd, m in reversed(list(iter_runs(runs_dir))):
        if m.get("state") != "completed" or not m.get("isolated"):
            continue
        tokens = (m.get("usage") or {}).get("input_tokens")
        if tokens:
            samples.append(int(tokens))
        if len(samples) >= 10:
            break
    if len(samples) < 3:
        return {"runs": n_runs, "input_median_per_run": None,
                "input_median_total": None, "samples": len(samples),
                "note": "not enough completed isolated runs in this project to "
                        "measure a median yet (need 3)"}
    samples.sort()
    per_run = samples[len(samples) // 2]
    return {"runs": n_runs, "input_median_per_run": per_run,
            "input_median_total": per_run * n_runs, "samples": len(samples),
            "note": "median input tokens of this project's recent isolated runs, "
                    "times N. About half of real runs come in under it and half "
                    "over — measured 6 under of 11 — and a resume grows from "
                    "there. It is a scale, not a bound: re-measure rather than "
                    "budgeting from it."}


def wants_worktree(item, args):
    """Whether this member would be isolated if the batch turns isolation on.

    D35 assigns per member, not per batch, and each exclusion has its own
    reason rather than a shared one:

      * **`read-only`** has nothing to isolate — it cannot write.
      * **`kind: review`** is excluded even though its sandbox defaults to
        `workspace-write`, and this is the exclusion that matters most. A
        freshly cut worktree has zero lines of `git diff HEAD` (measured,
        V-15), so a reviewer inside one reviews nothing: the uncommitted work
        it was started to look at exists only in the caller's tree.
      * **an explicit `cwd`** was a decision the caller already made, and an
        inferred default does not overrule a stated one.
      * **`kind: resume`** continues a thread whose directory is inherited from
        its parent run; `--cwd` is not even accepted on resume, so a new
        worktree here would be a directory the thread has never seen.
    """
    if item["kind"] in ("review", "resume"):
        return False
    if item.get("cwd") or getattr(args, "cwd", None):
        return False
    sandbox = item.get("sandbox") or args.sandbox or "workspace-write"
    return sandbox in WRITING_SANDBOXES


def plan_worktrees(tasks, args, project):
    """Decide isolation for the batch, then report why in the same breath.

    Returns `(eligible_indices, base_sha, note)`. The threshold is two writing
    members because one writer has nobody to collide with, and isolating it
    would only put its results somewhere the caller has to go and fetch.
    """
    eligible = {i for i, t in enumerate(tasks) if wants_worktree(t, args)}
    if getattr(args, "no_worktree", False):
        return set(), None, "worktrees disabled by --no-worktree"
    forced = getattr(args, "worktree", False)
    if not eligible:
        return set(), None, ("no member writes to the tree, so there is nothing "
                             "to isolate" if forced else None)
    if len(eligible) < 2 and not forced:
        return set(), None, ("only one member writes to the tree; a lone writer "
                             "has nobody to collide with. Pass --worktree to "
                             "isolate it anyway.")
    if git_toplevel(project) is None:
        return set(), None, (f"{project} is not a git repository, so worktrees "
                             "are unavailable; members share the caller's tree")
    ref = getattr(args, "base", None)
    base = worktree_base_sha(project, ref)
    if not base and ref:
        # An unresolvable --base was typed by the caller, so it is a mistake to
        # report rather than a condition to degrade around. Silently sharing the
        # caller's tree instead would answer a typo with the one outcome the
        # flag was used to avoid.
        fail(f"--base {ref!r} does not resolve to a commit in {project}")
    if not base:
        return set(), None, ("this repository has no HEAD yet (nothing is "
                             "committed), so there is no commit to cut a "
                             "worktree from; members share the caller's tree")
    return eligible, base, None


def pair_with_previous(tasks, runs_dir, previous: str, *, force=False):
    """Turn each task into a resume of the corresponding member of `previous`.

    The pairing is positional against the manifest's member list, and that is
    the whole reason the manifest records start order (D36). The alternative —
    ordering by run id or timestamp — is a coin flip precisely here: a batch
    starts its members within the same second and usually under the same label,
    which audit F15 recorded as the normal case rather than the unlucky one.

    A task that already names what it resumes keeps it. Explicit beats inferred,
    the same rule that governs a per-item `cwd`.
    """
    manifest = read_group(runs_dir, previous)
    if manifest is None:
        fail(f"no such group to resume from: {previous}",
             known_groups=list_groups(runs_dir)[:20])
    started = [m for m in manifest.get("members") or [] if m.get("run_id")]
    if not started:
        fail(f"group {previous!r} has no members that started, so there is "
             f"nothing to resume")
    # A run id is not a thread. A member whose Codex process died before
    # emitting `thread.started` — an early crash, a failed login — has a run
    # directory and a terminal state but no thread, and `codex exec resume`
    # with nothing to resume is not an error Codex reports back here: it
    # produces a ref-less argv that fails asynchronously, long after this
    # command has already told the caller it spawned fine.
    threadless = [m["run_id"] for m in started
                  if not (find_run(runs_dir, m["run_id"])[1] or {}).get("thread_id")]
    if threadless:
        fail(f"{len(threadless)} member(s) of {previous!r} never recorded a "
             f"thread id, so there is no conversation to continue for them — "
             f"they failed before Codex started one",
             members=threadless)
    prior = started
    if len(tasks) != len(prior):
        # Loud, because the failure mode of pairing a short list is a phase-2
        # task silently landing on the wrong phase-1 thread — every member
        # after the mismatch continues work it was not written for.
        fail(f"--resume-from pairs one task to one member in order, but "
             f"{previous!r} has {len(prior)} started member(s) and this batch "
             f"has {len(tasks)} task(s)",
             previous_members=[m["run_id"] for m in prior])
    # Checked for the whole group before a single member starts, rather than
    # left to `refuse_concurrent_turn` per member. Per member it would still
    # refuse — but only after the earlier tasks had already resumed, leaving a
    # phase 2 that is half started against a phase 1 that is half finished.
    live = []
    for m in prior:
        rd, meta = find_run(runs_dir, m["run_id"])
        if meta and reap(rd, meta).get("state") not in TERMINAL_STATES:
            live.append({"run_id": m["run_id"], "state": meta.get("state")})
    if live and not force:
        fail(f"group {previous!r} still has members running; resuming a thread "
             f"mid-turn would run two turns on it at once", running=live)

    paired = []
    for slot, (task, prev) in enumerate(zip(tasks, prior)):
        kind, named = task["kind"], task.get("resume")
        if kind == "review":
            # Rewriting it would turn a read-only review into a full agentic
            # turn on someone else's thread, which is a larger authority than
            # the caller asked for and is invisible in the output.
            fail(f"task {slot} is a review, but every task in a --resume-from "
                 f"batch continues one member of {previous!r}; a review cannot "
                 f"be that continuation")
        if kind != "resume" and named:
            # Neither reading is safe to pick silently: honouring `resume`
            # leaves this member's phase-1 counterpart unresumed while the
            # output still claims it was paired, and ignoring it discards a
            # target the caller wrote down.
            fail(f"task {slot} names a thread to resume but its kind is "
                 f"{kind!r}; under --resume-from, set kind to 'resume' to keep "
                 f"that target or drop the 'resume' field to be paired with "
                 f"{prev['run_id']}")
        if named:
            paired.append(task)
            continue
        paired.append({**task, "kind": "resume", "resume": prev["run_id"]})
    return paired, [m["run_id"] for m in prior]


def cmd_batch_start(args):
    if not valid_name(args.group):
        fail("group name must be alphanumeric with . _ - and no path separators",
             got=args.group)
    if getattr(args, "worktree", False) and getattr(args, "no_worktree", False):
        # Checked here, above `claim_group`, and not where the flags are used.
        # Silently letting one win would hand isolation — or its absence — to a
        # caller who asked for both and cannot tell which they got; refusing
        # after the name was claimed would burn that name on a typo, against
        # the whole point of claiming before anything is spawned.
        fail("--worktree and --no-worktree contradict each other; pass one")
    project = resolve_project(args.project)
    runs_dir = ensure_runs_dir(resolve_runs_dir(project, args.runs_dir))
    tasks = load_tasks(args)

    previous = getattr(args, "resume_from", None)
    if previous:
        tasks, paired_with = pair_with_previous(
            tasks, runs_dir, previous, force=getattr(args, "force", False))

    # Claim the name before spawning anything. D36: a reused group name would
    # make "the members of p1" ambiguous, and --resume-from pairs positionally
    # against exactly that list. Failing here costs nothing — no Codex process
    # has started yet.
    try:
        claim_group(runs_dir, args.group, derived_from=previous, requested=len(tasks))
    except FileExistsError:
        existing = read_group(runs_dir, args.group) or {}
        fail(f"group {args.group!r} already exists in this project; group names "
             f"are single-use so that membership and start order stay unambiguous. "
             f"`batch clean --group {args.group}` releases the name once its "
             f"worktrees are gone — which is also how a name is reclaimed from a "
             f"batch whose members all failed to spawn, since the claim happens "
             f"before the first one is tried",
             created_at=existing.get("created_at"),
             members=len(existing.get("members") or []))

    isolated_idx, wt_base, wt_note = plan_worktrees(tasks, args, project)
    batch_ctx = {"n": len(tasks), "group": args.group}

    members, results = [], []
    for index, item in enumerate(tasks):
        entry = {"index": index, "kind": item["kind"],
                 "label": item.get("label") or args.label}
        # The slot goes in before the spawn, not after it. `spawn_task` cuts the
        # member's worktree and claims its run directory before it returns, and
        # recording the slot afterwards left that whole window unaccounted: a
        # batch killed inside it leaves a checkout belonging to no member of any
        # group, which `batch clean --group` will therefore never remove. Two
        # writes of a few hundred bytes per member is the price of the manifest
        # never trailing what is already on disk.
        members.append(entry)
        write_members(runs_dir, args.group, members)
        try:
            with failures_raise():
                out = spawn_task(task_args(args, item), item, group=args.group,
                                 runs_dir=runs_dir, project=project,
                                 batch=batch_ctx,
                                 worktree_base=wt_base if index in isolated_idx
                                 else None)
        except Exception as e:
            # D11: one member failing to spawn does not take the batch with it.
            # The failure is recorded in place so the caller sees which slot is
            # missing rather than a shorter list than it asked for.
            #
            # `Exception`, not `BridgeError`: a BridgeError is a refusal this
            # code anticipated, but the failures that actually cost a batch are
            # the ones it did not — a bad value in a tasks file reaching
            # `prompt.strip()` as an AttributeError, an OSError from a full
            # disk. Letting those escape aborts the batch *after* members are
            # already running, which is the one outcome D11 exists to prevent.
            entry["error"] = e.msg if isinstance(e, BridgeError) else str(e)
            entry.update(e.extra if isinstance(e, BridgeError)
                         else {"error_type": type(e).__name__})
            results.append(entry)
            write_members(runs_dir, args.group, members)
            continue
        entry["run_id"] = out["run_id"]
        entry["thread_id"] = out.get("thread_id")
        entry["cwd"] = out.get("cwd")
        entry["sandbox"] = out.get("sandbox")
        if out.get("worktree"):
            entry["worktree"] = out["worktree"]["path"]
        results.append({**entry, "state": out.get("state")})
        # After every member, not once at the end: see write_members. A member
        # that has spawned is a live process, and it must be reachable through
        # the group from the instant it exists.
        write_members(runs_dir, args.group, members)
    spawned = [m for m in members if m.get("run_id")]
    isolated = [m for m in members if m.get("worktree")]
    out = {"group": args.group, "runs": results,
           "spawned": len(spawned), "requested": len(tasks),
           "projected_cost": projected_cost(runs_dir, len(spawned)),
           "manifest": str(group_path(runs_dir, args.group))}
    if previous:
        # Phase 2 works in phase 1's worktrees — it inherits each thread's cwd
        # rather than being given a new one. That is also why `batch clean` now
        # refuses to clean phase 1: the manifest records this link.
        out["resumed_from"] = {"group": previous, "members": paired_with}
    if isolated:
        # D17: a dirty caller tree is stated, never refused. The number is what
        # tells the caller their uncommitted work is not in what these runs see
        # — and the same fact goes to Codex itself in the preamble.
        out["worktrees"] = {
            "count": len(isolated), "base": wt_base,
            "uncommitted_files_in_caller_tree": worktree_uncommitted(project),
            "note": "each writing member has its own checkout at "
                    "<run_dir>/wt. Their changes are not in your tree; "
                    "`result --group` reports which paths more than one wrote. "
                    "`batch clean --group` removes them once you have collected."}
        missing = worktree_missing_at_base(project, wt_base)
        if missing:
            # V-14: project instructions reach a worktree run, but only from a
            # base where the file exists. A --base older than the commit that
            # added AGENTS.md produces runs with no project guidance, and
            # neither side can notice on its own.
            out["worktrees"]["missing_at_base"] = missing
            out["worktrees"]["missing_note"] = (
                f"{', '.join(missing)} exists in your tree but not at the base "
                f"these worktrees were cut from, so these runs start without "
                f"the project instructions a HEAD-based run would have had.")
    elif wt_note:
        out["worktrees"] = {"count": 0, "note": wt_note}
    emit(out)


def spawn_task(ns, item, *, group, runs_dir, project, batch=None,
               worktree_base=None):
    """Start one member. Mirrors cmd_start/cmd_resume/cmd_review's dispatch,
    minus their argv parsing, which `task_args` has already done."""
    kind = item["kind"]
    if kind == "start":
        return create_run(ns, kind="start", group=group, batch=batch,
                          worktree_base=worktree_base)
    if kind == "resume":
        rd, base = find_run(runs_dir, item["resume"])
        if not base:
            # Not in the registry: it may still be a real Codex thread started
            # outside this skill, so pass the ref through rather than refusing.
            return create_run(ns, kind="resume", thread_ref=item["resume"],
                              group=group, batch=batch)
        refuse_concurrent_turn(runs_dir, base.get("thread_id"),
                               getattr(ns, "force", False))
        return create_run(ns, kind="resume", base=base,
                          thread_ref=base.get("thread_id"), group=group,
                          batch=batch)
    review = item.get("review") or {}
    review_args = review_argv(uncommitted=review.get("uncommitted"),
                              base=review.get("base"), commit=review.get("commit"),
                              title=review.get("title"),
                              prompt=item.get("prompt"), fail=fail)
    return create_run(ns, kind="review", review_args=review_args, group=group,
                      batch=batch)


def cmd_batch_clean(args):
    """Remove a finished group's worktrees and release its name.

    There is no automatic cleanup and no hook (D06, D23): a worktree holds the
    only copy of what a run produced, and nothing should delete that on a
    schedule the caller did not choose.

    Four things stop a clean without `--force`, and only the first two are
    checks this code performs. The other two are git's own refusal, and a fact
    about groups that outlive each other.
    """
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    manifest = read_group(runs_dir, args.group)
    if manifest is None:
        fail(f"no such group in this project: {args.group}",
             known_groups=list_groups(runs_dir)[:20])

    live, removed, kept = [], [], []
    for rid in owned_run_ids(runs_dir, args.group) or []:
        rd, meta = find_run(runs_dir, rid)
        if not meta:
            # A run whose meta.json will not parse is not thereby dead. Skipping
            # it here left it out of the live-member guard while the removal
            # loop below still found its worktree by convention, so a run last
            # recorded `running` had its only copy of its work deleted without
            # `--force` ever being passed. Unknown is not terminal: refuse, and
            # make the caller say --force if they mean it.
            if rd is not None and (rd / "meta.json").exists():
                live.append({"run_id": rid, "state": "unreadable",
                             "reason": "its meta.json will not parse, so whether "
                                       "it is still running cannot be determined"})
            continue
        meta = reap(rd, meta)
        if meta.get("state") not in TERMINAL_STATES:
            live.append({"run_id": rid, "state": meta.get("state")})

    # 1. A live member is still writing into the very directory being removed.
    if live and not args.force:
        fail(f"group {args.group!r} still has running members; stop them first "
             f"or pass --force", running=live)
    # One flag lifts all three protections, and a caller usually reaches for it
    # to get past one of them. What it actually overrode therefore has to be in
    # the result, not only in --help: the caller who forced past a dependent
    # group needs to see that a running member's directory went with it.
    overrode = {}
    if args.force and live:
        overrode["running_members"] = live

    # 2. A group that another group resumed into. `--resume-from` puts phase 2
    #    in phase 1's worktrees, so cleaning phase 1 pulls the tree out from
    #    under runs that are still using it. Free to detect thanks to the
    #    manifest's `derived_from`.
    children = derived_groups(runs_dir, args.group)
    if children and not args.force:
        fail(f"group {args.group!r} was resumed by another group, whose members "
             f"are working in these worktrees", derived_groups=children)
    if args.force and children:
        overrode["derived_groups"] = children

    worktree_prune(project)
    for rid in owned_run_ids(runs_dir, args.group) or []:
        rd, meta = find_run(runs_dir, rid)
        if rd is None:
            continue
        wt = (meta or {}).get("worktree")
        # `git worktree add` and the `write_meta` that records its path cannot
        # be one operation, so there is a window — now milliseconds rather than
        # the fifteen seconds it used to be — where the checkout exists and
        # `meta["worktree"]` is still null. The path is not a guess: a member's
        # worktree is always `<run_dir>/wt` (`create_run`), so the convention is
        # the recovery. Without it that checkout is removable by nothing.
        path = Path(wt["path"]) if wt else rd / "wt"
        if not path.exists():
            continue
        # 3. Uncommitted changes in the worktree, i.e. results nobody collected.
        #    Not implemented here: `git worktree remove` refuses a dirty tree by
        #    itself (measured, V-13), and git's definition of dirty is the
        #    correct one. Its refusal is reported as the reason.
        # Who is actually living here, asked of the registry rather than of the
        # group graph. The `derived_from` check above is a better error message
        # when the chain is intact, but it is only one hop and it evaporates the
        # moment an intermediate manifest is cleaned: p1 -> p2 -> p3, clean p2,
        # and p1 looks unreferenced while p3 is still running in p1's worktree.
        # A run's own recorded cwd cannot go stale that way.
        occupants = [m for _rd, m in iter_runs(runs_dir)
                     if m.get("state") not in TERMINAL_STATES
                     and m.get("run_id") != rid
                     and is_within(m.get("cwd"), path)]
        if occupants and not args.force:
            kept.append({"run_id": rid, "path": str(path),
                         "reason": "another run is still working in this "
                                   "worktree",
                         "occupied_by": [m["run_id"] for m in occupants]})
            continue
        if occupants:
            overrode.setdefault("removed_under_live_runs", []).extend(
                m["run_id"] for m in occupants)
        dirty = worktree_dirty(path)
        ok, err = worktree_remove(project, path, force=args.force)
        if ok and dirty and args.force:
            overrode.setdefault("discarded_uncommitted", []).append(str(path))
        (removed if ok else kept).append(
            {"run_id": rid, "path": str(path),
             **({} if ok else {"reason": err, "dirty": dirty})})

    # The name is released only when nothing was left behind, so a caller who
    # sees `cleaned: true` can reuse the name and one who does not still has a
    # group to address the leftovers by. This is also the only way to reclaim a
    # name from a `batch start` that died before it recorded any member.
    released = not kept
    if released:
        group_path(runs_dir, args.group).unlink(missing_ok=True)
    out = {"group": args.group, "removed": removed, "kept": kept,
           "name_released": released,
           "note": None if released else
           "these worktrees hold uncommitted changes — collect them, or pass "
           "--force to discard. The group name stays claimed until they are gone."}
    if overrode:
        out["forced_past"] = overrode
        out["forced_note"] = (
            "--force lifted every protection at once, not only the one you were "
            "after. What it overrode is listed above; none of it is recoverable "
            "from here.")
    emit(out)


def resolve_group(runs_dir: Path, name: str):
    """Group members as (run_dir, meta), in start order. Fails if the group is
    unknown. Members that never spawned have no run id to resolve, so they are
    not here — `unstarted_members` is how the rest of the group views learn
    they exist."""
    ids = member_run_ids(runs_dir, name)
    if ids is None:
        fail(f"no such group: {name}", runs_dir=str(runs_dir),
             known_groups=list_groups(runs_dir))
    out = []
    for rid in ids:
        rd, m = find_run(runs_dir, rid)
        if m:
            out.append((rd, m))
    return out


def unstarted_members(runs_dir: Path, name: str):
    """Manifest slots that never became runs, with the reason each one didn't.

    Kept as a first-class part of every group view. The alternative — letting
    them exist only in `batch start`'s reply — means the information is gone
    the moment that one line of JSON scrolls past, and every later question
    about the group answers as if the caller had asked for fewer things."""
    g = read_group(runs_dir, name) or {}
    members = g.get("members", [])
    never = [{"index": m.get("index"), "label": m.get("label"),
              "kind": m.get("kind"), "error": m.get("error")}
             for m in members if not m.get("run_id")]
    # Slots the manifest never got to record at all, because `batch start` was
    # killed before it reached them. Without this the group looks like it asked
    # for however many it managed to start.
    #
    # The wording claims only what this view knows. A slot with no run id may
    # still have got as far as a run directory and a worktree — the manifest
    # lags `create_run` by up to THREAD_ID_WAIT — and `batch clean` finds those
    # through the registry (`owned_run_ids`). This view deliberately does not:
    # it is the one a caller polls once a second, and walking the registry per
    # tick is the cost this module's docstring exists to refuse.
    for i in range(len(members), g.get("requested") or 0):
        never.append({"index": i, "label": None, "kind": None,
                      "error": "batch start recorded no run for this task"})
    return never


def vanished_members(runs_dir: Path, name: str):
    """Members the manifest names whose run directory is no longer there.

    A third category, and the only one nothing in this codebase creates:
    `batch clean` removes worktrees and never run directories. It takes a hand
    edit or an outside process. But a member that is neither resolvable nor
    `unstarted` falls out of every count silently, and a group quietly
    reporting `completed` with one fewer member than it had is the same failure
    as the one `unstarted` exists to prevent — so it is named rather than
    dropped."""
    g = read_group(runs_dir, name) or {}
    gone = []
    for m in g.get("members", []):
        rid = m.get("run_id")
        if not rid:
            continue
        rd, meta = find_run(runs_dir, rid)
        if meta:
            continue
        # Two different things reach here and they need different words. A
        # directory that is gone was removed by hand or by something outside
        # this skill. A directory that is present with an unparseable meta.json
        # still holds its event stream and possibly its worktree — telling the
        # caller it is "no longer in the registry" would send them away from
        # work that is still on disk, while the same payload's `unreadable`
        # field says the opposite.
        present = rd is not None and (rd / "meta.json").exists()
        gone.append({"index": m.get("index"), "label": m.get("label"),
                     "run_id": rid,
                     "error": ("its meta.json will not parse; the run directory "
                               "is still there and may still hold results"
                               if present else
                               "its run directory is no longer in the registry")})
    return gone


def group_snapshot(rows, unstarted=0):
    """The one place group state is derived, so `status --group` and
    `--follow`'s exit line can never disagree about whether a group is done.

    `unstarted` is the count of manifest members that never got a run id. They
    have to be counted here rather than only in `batch start`'s own reply,
    because every later view of the group resolves membership through run ids
    and would otherwise be blind to them — a batch asked for three and given
    one would report `completed`, which is the group-level form of the failure
    a terminal `--follow` line exists to prevent.
    """
    running = [r["run_id"] for r in rows if r["state"] in ("running", "starting", "stalled")]
    done = [r["run_id"] for r in rows if r["state"] == "completed"]
    failed = [r["run_id"] for r in rows
              if r["state"] in ("failed", "interrupted", "orphaned", "timed_out")]
    if running:
        state = "running"
    elif failed or unstarted or not rows:
        # `partial` covers "a member failed", "the user stopped it" and "a member
        # timed out" alike. It means "this group did not all succeed", not
        # "Codex broke" — worth stating, because a --follow exit line saying
        # `group.partial` after a deliberate `stop --group` otherwise reads as
        # an error.
        state = "partial"
    else:
        state = "completed"
    return running, done, failed, state


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
    deadline = time.time() + args.follow_timeout if args.follow_timeout else None
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
        if deadline and time.time() >= deadline:
            sys.stdout.write(f"group.still-running group={args.group} "
                             f"running={len(running)} done={len(done)} "
                             f"failed={len(failed)}\n")
            sys.stdout.flush()
            return
        time.sleep(args.interval)


GROUP_MESSAGE_CAP = 4000


def changed_paths(events_path: Path, root=None):
    """Paths a run wrote, as `(repository, repo-relative path)` pairs.

    Codex reports absolute paths, and comparing them as written makes
    `overlaps` blind under worktree isolation: three members editing the same
    `src/parser.py` in three worktrees produce three distinct strings that
    intersect to nothing, so the field reported a clean run in exactly the
    situation it exists to warn about. Reproduced against the real CLI.

    Making them relative to each run's own cwd fixes that case and breaks two
    others, which is why the key is a pair rather than a string:

      * Two members in **different repositories** — a per-task `cwd` is allowed
        and disables worktree assignment — that each write an `output.txt`
        would share the relative path and be reported as colliding on a file
        neither of them touched.
      * Two members with **nested roots** in one repository, one started in a
        subdirectory of the other, that both write the same file would produce
        different relative paths and miss a real collision — the same silent
        miss, reached from the other side.

    `--git-common-dir` is what every worktree of one repository shares and no
    two repositories do, and the per-worktree top level is what makes the same
    tracked file reduce to the same repo-relative path from anywhere inside it.
    Outside a repository there is nothing to be relative to, so the path stays
    absolute and only ever matches itself.
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
                    pass    # outside the repo entirely; keep it absolute
            paths.add((None, str(p)))
    return paths


def cmd_result_group(args, project, runs_dir):
    members = resolve_group(runs_dir, args.group)
    results, per_run_paths, totals = [], {}, {"input_tokens": 0, "output_tokens": 0}

    for rd, meta in members:
        meta = reap(rd, meta)
        info = scan_progress(rd / "events.jsonl")
        msg_path = rd / "last-message.txt"
        message = (msg_path.read_text(encoding="utf-8") if msg_path.exists()
                   else info["last_agent_message"]) or ""
        # Cut and measure in the same unit. Slicing characters while reporting
        # bytes made a 3,000-character Korean message — 9,000 bytes, nothing
        # actually removed — report `message_truncated: true`, which is exactly
        # the guess D07's cap exists to replace with a fact.
        raw = message.encode("utf-8", "replace")
        truncated = len(raw) > GROUP_MESSAGE_CAP
        row = {"run_id": meta["run_id"], "label": meta.get("label"),
               "state": meta.get("state"), "exit_code": meta.get("exit_code"),
               # D07: capped per run, with the real size stated. Whether to pull
               # the full text is then a decision the caller makes, not a guess
               # — `result --run <id>` returns it whole.
               # "ignore", not "replace": a byte cut lands mid-character often
               # in any non-ASCII text, and U+FFFD would both re-encode larger
               # than the byte it replaced — pushing the payload back over the
               # cap — and read as corruption in prose that is merely cut short.
               "message": (raw[:GROUP_MESSAGE_CAP].decode("utf-8", "ignore")
                           if truncated else message),
               "message_bytes": len(raw),
               "message_truncated": truncated,
               "usage": info["usage"], "files_changed": info["files_changed"],
               "turn_failed": (clip(json.dumps(info["turn_failed"], ensure_ascii=False), 400)
                               if info["turn_failed"] else None)}
        if meta.get("worktree"):
            row["worktree"] = meta["worktree"]
        results.append(row)
        # Keyed by run, never by worktree: with --resume-from a phase-2 member
        # inherits its predecessor's worktree, so a worktree-keyed set would
        # report every member as overlapping with its own past self.
        per_run_paths[meta["run_id"]] = changed_paths(
            rd / "events.jsonl", (meta.get("worktree") or {}).get("path") or meta.get("cwd"))
        for key in totals:
            totals[key] += int((info["usage"] or {}).get(key) or 0)

    # D30: the intersection only. A full path list per run inverts the context
    # discipline this skill exists for, and `log` already prints file_change
    # paths for anyone who wants them. What is genuinely un-derivable, and what
    # a synthesis step needs first, is which paths two runs both touched.
    counts = {}
    for rid, paths in per_run_paths.items():
        for key in paths:
            counts.setdefault(key, []).append(rid)
    # Keyed on (repository, path) but reported by path alone: two members can
    # only appear together under a key when they were in the same repository,
    # so the repository half has done its work by the time this is rendered and
    # printing it would only be noise.
    overlaps = {path: rids for (_repo, path), rids in sorted(counts.items())
                if len(rids) > 1}

    never = unstarted_members(runs_dir, args.group)
    gone = vanished_members(runs_dir, args.group)
    running, done, failed, gstate = group_snapshot(
        [{"run_id": r["run_id"], "state": r["state"]} for r in results],
        len(never) + len(gone))
    out = {"group": args.group, "project": str(project), "results": results,
           "overlaps": overlaps, "totals": totals, "group_state": gstate,
           "done": done, "failed": failed, "running": running,
           "unstarted": never + gone,
           "overlaps_note": ("paths written by more than one member. Under worktree "
                             "isolation this is a merge conflict ahead, not damage "
                             "already done.") if overlaps else None}
    emit(out)


