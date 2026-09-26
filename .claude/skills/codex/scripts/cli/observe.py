"""Argument checks for `status`, `log` and `result` before they reach `codex.observe`: a selector pair that names two things, and a follower-only flag without a follower."""

from __future__ import annotations

from cli.guards import refuse_competing_selectors, refuse_unusable_follow_options
from codex.errors import Refusal
from codex.observe import log, result, status


def cmd_status(args):
    refuse_competing_selectors(args, "status", "--run", "--thread", "--group")
    if args.follow and not args.group:
        raise Refusal("--follow requires --group; to follow one run use `log --run <id> --follow`", run=args.run)
    refuse_unusable_follow_options(args)
    return status.status(args)


def cmd_log(args):
    refuse_unusable_follow_options(args)
    if args.group and args.since is not None:
        raise Refusal("--since takes one run's cursor and a group has one per member; use `log --run <id> --since <n>`", group=args.group)
    return log.log(args)


def cmd_result(args):
    refuse_competing_selectors(args, "result", "--run", "--group")
    if not (args.run or args.group):
        raise Refusal("result needs --run <id> or --group <name>")
    return result.result(args)
