"""Refusals several commands share: competing selectors, a run that cannot be resolved, a follower-only flag without a follower."""

from __future__ import annotations

from core.registry import meta_unreadable, unreadable_runs
from util import fail


def refuse_competing_selectors(args, command, *selectors):
    """Two selectors name different things, and honouring one would silently drop the other. Which flags compete is per command (`status --all` lifts a cap; `stop --all` is a selector), so each caller names its set."""
    given = {name: getattr(args, name.lstrip("-").replace("-", "_"), None) for name in selectors}
    given = {k: v for k, v in given.items() if v}
    if len(given) > 1:
        names = " and ".join(sorted(given))
        fail(f"{names} select different runs; pass one",
             **{k.lstrip("-").replace("-", "_"): v for k, v in given.items()})


def refuse_unresolved_run(ref, run_dir, meta, runs_dir):
    """"Cannot read that run" and "no such run" are different answers: the first still has an event stream on disk."""
    if meta:
        return
    if run_dir is not None and meta_unreadable(run_dir):
        fail(f"run {ref} has a meta.json that will not parse, so its state is unknown; its event stream may still be readable",
             run_id=run_dir.name, run_dir=str(run_dir), events=str(run_dir / "events.jsonl"))
    fail(f"no such run: {ref}", runs_dir=str(runs_dir))


def refuse_unusable_follow_options(args):
    """`--follow-timeout` and `--heartbeat` only mean something to a follower, at a positive number of seconds; accepted otherwise they would read as obeyed."""
    for flag in ("--follow-timeout", "--heartbeat"):
        value = getattr(args, flag[2:].replace("-", "_"), None)
        if value is None:
            continue
        if not args.follow:
            fail(f"{flag} requires --follow")
        if value <= 0:
            fail(f"{flag} must be a positive number of seconds", **{flag[2:].replace("-", "_"): value})


def note_unreadable(out: dict, runs_dir):
    """Name runs whose meta.json will not parse, so a listing they are missing from does not look complete."""
    bad = unreadable_runs(runs_dir)
    if bad:
        out["runs_unreadable"] = len(bad)
        out["unreadable"] = bad
    return out
