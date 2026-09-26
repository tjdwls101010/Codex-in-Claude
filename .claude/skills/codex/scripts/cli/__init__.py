"""The command-line surface: parse, dispatch, and answer in the output contract — one line of JSON per command, success or failure, except the streaming `log` and `status --group --follow`."""

from __future__ import annotations

import os
import sys

from cli.parser import build_parser
from codex.codex_cli.config import codex_home
from codex.errors import Refusal
from codex.util import emit


def render(out):
    """A handler's answer: a dict is one line of JSON, a `(dict, exit code)` pair the same with that code, and anything else is text to stream, piece by piece, each carrying its own newlines."""
    if isinstance(out, tuple):
        emit(*out)
    if isinstance(out, dict):
        emit(out)
    for piece in out:
        sys.stdout.write(piece)
        sys.stdout.flush()


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
        out = args.func(args)
        if out is not None:
            render(out)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
    except Refusal as e:
        emit({"error": e.error, **e.fields}, code=1)
    except KeyboardInterrupt:
        emit({"error": "interrupted"}, code=1)
    except Exception as e:
        emit({"error": f"internal error: {e}"}, code=1)
