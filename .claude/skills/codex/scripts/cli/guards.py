"""Refusals several commands share: competing selectors, a run that cannot be resolved, a follower-only flag without a follower."""

from __future__ import annotations

from codex.registry.runs import unreadable_runs
from codex.util import fail


def refuse_competing_selectors(args, command, *selectors):
    """Two selectors name different things, and honouring one would silently drop the other. Which flags compete is per command (`status --all` lifts a cap; `stop --all` is a selector), so each caller names its set."""
    given = {name: getattr(args, name.lstrip("-").replace("-", "_"), None) for name in selectors}
    given = {k: v for k, v in given.items() if v}
    if len(given) > 1:
        names = " and ".join(sorted(given))
        fail(f"{names} select different runs; pass one",
             **{k.lstrip("-").replace("-", "_"): v for k, v in given.items()})


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
