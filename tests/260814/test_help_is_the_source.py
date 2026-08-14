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
import re
import unittest

from helpers import SKILL_MD

import codex_bridge  # noqa: E402

TABLE_ROW_RE = re.compile(r"^\|\s*`([a-z][a-z ]*)`\s*\|")


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


def runnable_subcommands(parser, path=""):
    """Every command path a caller can actually invoke.

    Leaves only: `batch` alone is not one of them, because its own subparsers
    are `required=True`, so `batch` with nothing after it is a usage error
    rather than a command.
    """
    nested = [a for a in parser._actions
              if isinstance(getattr(a, "choices", None), dict) and a.choices]
    if not nested:
        return {path}
    out = set()
    for action in nested:
        hidden = {c.dest for c in getattr(action, "_choices_actions", [])
                  if c.help is argparse.SUPPRESS}
        for name, sub in action.choices.items():
            if name not in hidden:
                out |= runnable_subcommands(sub, f"{path} {name}".strip())
    return out


class TheCommandTableIsTheWholeSurface(unittest.TestCase):
    """SKILL.md keeps a map of what exists; `--help` owns everything below it.

    The map earns its ~370 tokens by saving a call: a model that does not know
    `batch` exists never thinks to ask `--help` about it. But it is still a
    hand-kept copy of what the parser knows, and that is the arrangement that
    let seven flags drift. So the copy stays and the drift does not.
    """

    def table_commands(self):
        return {m.group(1).strip()
                for m in map(TABLE_ROW_RE.match, SKILL_MD.read_text().splitlines())
                if m}

    def test_the_table_lists_every_runnable_command_and_no_others(self):
        self.assertEqual(
            self.table_commands(),
            runnable_subcommands(codex_bridge.build_parser()),
            "SKILL.md's command table and the CLI's actual commands have "
            "diverged; the table is what tells a caller a command exists at all")


DEFAULT_RE = re.compile(r"default:\s*([A-Za-z0-9_.\-]+)")


def _comparable(stated, real):
    """(matches, ) for a stated default against argparse's, or None to skip.

    Skipping is the common case and it is deliberate. Most defaults in this CLI
    are resolved past argparse — `--sandbox`'s `workspace-write` and `--cwd`'s
    project root are decided in `create_run`, so argparse holds `None` and there
    is nothing here to compare. A check that guessed at those would fail on
    correct help text, which is worse than not checking them.
    """
    if real is None or isinstance(real, bool):
        return None
    if isinstance(real, (int, float)):
        try:
            return float(stated) == float(real)
        except ValueError:
            return None                      # prose, not a number
    if isinstance(real, str):
        return stated == real
    return None


class AStatedDefaultIsTheRealDefault(unittest.TestCase):
    """Presence is not truth, and this is the part of truth a machine can check.

    That a `help=` string exists says nothing about whether it is right, and a
    wrong one ships more confidently than none at all now that it is the only
    copy. Most of what a help string claims — what the flag does, how it
    interacts with another — can only be checked by reading it against the code.
    A stated default is the exception: argparse is holding the real one.
    """

    def comparable_defaults(self):
        out = []
        actual = {}
        for action in _walk_actions(codex_bridge.build_parser()):
            for opt in action.option_strings or [action.dest]:
                actual[opt] = action.default
        for cmd, name, help_ in option_surface(codex_bridge.build_parser()):
            m = DEFAULT_RE.search(help_ or "")
            if not m:
                continue
            stated, real = m.group(1), actual.get(name)
            verdict = _comparable(stated, real)
            if verdict is not None:
                out.append((cmd, name, stated, real, verdict))
        return out

    def test_the_scan_found_defaults_it_can_check(self):
        self.assertGreater(
            len(self.comparable_defaults()), 3,
            "no help string states a default argparse also holds, so this "
            "check is passing without looking at anything")

    def test_each_stated_default_matches_the_parser(self):
        for cmd, name, stated, real, matches in self.comparable_defaults():
            with self.subTest(cmd=cmd, flag=name):
                self.assertTrue(
                    matches,
                    f"`{cmd} {name}` --help says the default is {stated!r}, "
                    f"but argparse's is {real!r}")


def _walk_actions(parser):
    for action in parser._actions:
        if isinstance(getattr(action, "choices", None), dict) and action.choices:
            for sub in action.choices.values():
                yield from _walk_actions(sub)
        else:
            yield action


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
