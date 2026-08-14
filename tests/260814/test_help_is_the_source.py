"""The CLI's own signature is the source of truth for its option surface.

Every flag this tool takes is a fact about it, and that fact currently lives in
up to three places: the argparse call, SKILL.md's option paragraph, and
docs/wiki/CLI-Reference.md. Only the first one cannot be wrong. The other two
drifted — seven flags (`--isolate`, `--prompt-file`, `--priority`, `--thread`,
`--grace`, `--title`, `--interval`) reached the CLI without ever reaching the
skill's markdown, and `--as-ready` reached the markdown without reaching the
wiki's flag reference.

`test_docs_match_the_cli.py` in the 260813 round already checks the direction
that catches a documented flag the CLI does not accept. It cannot catch this
one, because a flag nobody documented is a flag it never looks at. The check
that closes it has to start from the parser, not from the prose.
"""

from __future__ import annotations

import argparse
import unittest

from helpers import SKILL_MD  # noqa: F401  (imported for sys.path side effect)

import codex_bridge  # noqa: E402


def option_surface(parser, path=""):
    """(command path, argument, help) for everything a caller can pass.

    Walks the parser rather than a hand-kept list, for the same reason
    `cli_surface()` does in the 260813 round: a hand-kept list is one more place
    for this to disagree with itself.

    Subcommands registered with `help=argparse.SUPPRESS` are skipped whole.
    `__supervise` is a re-exec target this process spawns for itself, not part of
    the surface a caller reads, and requiring help on it would be requiring
    documentation nobody can reach.
    """
    out = []
    for action in parser._actions:
        if isinstance(getattr(action, "choices", None), dict) and action.choices:
            hidden = {c.dest for c in getattr(action, "_choices_actions", [])
                      if c.help is argparse.SUPPRESS}
            for name, sub in action.choices.items():
                if name in hidden:
                    continue
                out.extend(option_surface(sub, f"{path} {name}".strip()))
            continue
        name = action.option_strings[0] if action.option_strings else action.dest
        out.append((path or "(top level)", name, action.help))
    return out


class EveryFlagExplainsItself(unittest.TestCase):
    """A flag with no `help=` is a flag whose only explanation is prose.

    That is the arrangement this round is undoing. `--help` is re-read from the
    signature on every invocation and cannot fall behind the code; a paragraph
    describing the same flag is a copy, and every copy of this surface in this
    repository has already drifted at least once.
    """

    def test_the_walk_found_the_whole_surface(self):
        """A walk that silently stops finding arguments passes vacuously."""
        surface = option_surface(codex_bridge.build_parser())
        self.assertGreater(len(surface), 60,
                           "the parser walk stopped matching, so the check "
                           "below is passing without looking at anything")

    def test_every_argument_carries_a_help_string(self):
        undocumented = [(cmd, name) for cmd, name, help_ in
                        option_surface(codex_bridge.build_parser())
                        if not help_]
        self.assertEqual(
            undocumented, [],
            f"{len(undocumented)} argument(s) have no `help=`, so a caller "
            f"running `--help` learns only that they exist:\n  " +
            "\n  ".join(f"{cmd} {name}" for cmd, name in undocumented))


if __name__ == "__main__":
    unittest.main()
