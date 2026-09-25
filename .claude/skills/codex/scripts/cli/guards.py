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
        fail(f"{names} are different questions; pass one. "
             f"`{command}` acts on whichever it sees first, which is not "
             f"necessarily the one you meant.",
             **{k.lstrip("-").replace("-", "_"): v for k, v in given.items()})


def refuse_unresolved_run(ref, run_dir, meta, runs_dir):
    """"Cannot read that run" and "no such run" are different answers: the first still has an event stream on disk."""
    if meta:
        return
    if run_dir is not None and meta_unreadable(run_dir):
        fail(f"run {ref} exists but its meta.json will not parse, so nothing "
             f"can be said about its state. Its event stream is a separate "
             f"file and may still be readable.",
             run_id=run_dir.name, run_dir=str(run_dir), events=str(run_dir / "events.jsonl"))
    fail(f"no such run: {ref}", runs_dir=str(runs_dir))


def refuse_unusable_heartbeat(args):
    """`--heartbeat` only means something to a follower, at a positive interval; accepted otherwise it would read as obeyed."""
    beat = getattr(args, "heartbeat", None)
    if beat is None:
        return
    if not args.follow:
        fail("--heartbeat is a line a follower prints while it follows, and "
             "there is no --follow here, so nothing would print it.")
    if beat <= 0:
        fail("--heartbeat is an interval in seconds and has to be positive; "
             "omitting it is how a follower stays quiet.", heartbeat=beat)


def note_unreadable(out: dict, runs_dir):
    """Name runs whose meta.json will not parse, so a listing they are missing from does not look complete."""
    bad = unreadable_runs(runs_dir)
    if bad:
        out["runs_unreadable"] = len(bad)
        out["unreadable"] = bad
    return out
