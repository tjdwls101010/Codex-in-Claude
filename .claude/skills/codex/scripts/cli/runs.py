"""Argument checks for `resume` and `stop` before they reach `codex.runs`: splitting `[REF] PROMPT`, and a selector that must be exactly one."""

from __future__ import annotations

from cli.guards import refuse_competing_selectors
from codex.errors import Refusal
from codex.runs import commands


def cmd_resume(args):
    # `[REF] PROMPT` is two optional positionals argparse cannot tell apart; with --last everything positional is the prompt.
    rest = list(args.rest)
    args.ref = None if args.last else (rest.pop(0) if rest else None)
    if len(rest) > 1:
        raise Refusal("too many positional arguments: resume takes [REF] PROMPT",
                      expected="resume <ref> <prompt>  |  resume --last <prompt>", got=list(args.rest))
    args.prompt = rest[0] if rest else None
    if not args.last and not args.ref:
        raise Refusal("resume needs a run id, thread id, thread name, or --last")
    return commands.resume(args)


def cmd_stop(args):
    refuse_competing_selectors(args, "stop", "--run", "--group", "--all")
    if not (args.run or args.group or args.all):
        raise Refusal("stop needs --run <id> (repeatable), --group <name>, or --all")
    return commands.stop(args)
