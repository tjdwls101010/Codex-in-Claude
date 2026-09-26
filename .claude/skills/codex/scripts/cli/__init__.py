"""The command-line surface: parse, dispatch, and answer in the output contract — one line of JSON per command, success or failure, except the streaming `log` and `status --group --follow`."""

from __future__ import annotations

import os
import sys

from cli.parser import build_parser
from codex.codex_cli.config import codex_home
from util import fail


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("CODEX_HOME"):
        # The supervisor and codex run in other directories, so a relative value is pinned to what it meant here.
        os.environ["CODEX_HOME"] = str(codex_home())
    ap = build_parser()
    # `resume [REF] PROMPT` has two optional positionals; plain parsing would drop the prompt when an option sits between them, and parse_intermixed_args cannot run on a parser that owns subparsers.
    if raw[:1] == ["resume"]:
        args = ap.subparser_map["resume"].parse_intermixed_args(raw[1:])
    else:
        args = ap.parse_args(raw)
    try:
        args.func(args)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
    except KeyboardInterrupt:
        fail("interrupted")
    except Exception as e:
        fail(f"internal error: {e}")
