"""Seam 5 — the help audit has a finish line a machine can see.

"Audit the help text" is not a completable task on its own: there is no state of
the tree that says every string was looked at. So the audit produces a manifest —
one row per argument a caller can pass, each marked `keep`, `change` or `remove` —
and this test holds the manifest and the parser to the same shape.

That makes an unaudited flag impossible rather than unlikely. Add an argument
without a manifest row and this fails; delete an argument whose row says `keep`
and this fails too. Neither is caught by anything else here: the 260814 round
checks every argument *has* a `help=`, which a wrong one also has.

What this cannot check is whether a `keep` verdict was right. That was Codex
review 4's job, and its findings are the `change` rows.
"""

from __future__ import annotations

import argparse
import re
import sys
import unittest

from blocks import REPO
from helpers import BRIDGE

sys.path.insert(0, str(BRIDGE.parent))
import codex_bridge  # noqa: E402

MANIFEST = REPO / ".claude" / "plans" / "260823" / "help-audit-manifest.md"
ROW_RE = re.compile(r"^\|\s*`([^`]*)`\s*\|\s*`([^`]+)`\s*\|\s*(keep|change|remove)\s*\|")


def manifest_rows():
    """{(command, argument): verdict} for every audited argument."""
    out = {}
    for line in MANIFEST.read_text().splitlines():
        m = ROW_RE.match(line)
        if m:
            out[(m.group(1), m.group(2))] = m.group(3)
    return out


def public_surface(parser, path=""):
    """Every (command, argument) a caller can pass, hidden commands skipped.

    `__supervise` is a re-exec target this process spawns for itself. It is not
    part of what a caller reads, and this round hides it from the top-level
    listing for exactly that reason — so auditing its arguments would be
    auditing something with no reader.
    """
    out = set()
    for action in parser._actions:
        if isinstance(getattr(action, "choices", None), dict) and action.choices:
            hidden = {c.dest for c in getattr(action, "_choices_actions", [])
                      if c.help is argparse.SUPPRESS}
            for name, sub in action.choices.items():
                if name not in hidden:
                    out |= public_surface(sub, f"{path} {name}".strip())
            continue
        if action.help is argparse.SUPPRESS:
            continue
        name = action.option_strings[0] if action.option_strings else action.dest
        out.add((path, name))
    return out


class EveryArgumentWasAudited(unittest.TestCase):

    def test_the_walk_found_the_whole_surface(self):
        self.assertGreater(len(public_surface(codex_bridge.build_parser())), 60,
                           "the parser walk stopped matching, so the "
                           "comparison below is between two empty sets")

    def test_the_manifest_and_the_parser_describe_the_same_arguments(self):
        rows = manifest_rows()
        surviving = {k for k, v in rows.items() if v != "remove"}
        real = public_surface(codex_bridge.build_parser())
        self.assertEqual(
            surviving - real, set(),
            "the manifest keeps arguments the parser does not have — either a "
            "flag was deleted without its row being marked `remove`, or a row "
            "names it wrongly")
        self.assertEqual(
            real - surviving, set(),
            "these arguments reach a caller with nobody having read their help "
            "text; the audit is not finished")

    def test_the_removals_actually_left(self):
        """A `remove` row is a claim about the tree, not a plan."""
        real = public_surface(codex_bridge.build_parser())
        for (command, arg), verdict in manifest_rows().items():
            if verdict == "remove":
                with self.subTest(command=command, arg=arg):
                    self.assertNotIn((command, arg), real)

    def test_the_audit_changed_something(self):
        """A manifest of nothing but `keep` is an audit that was not run."""
        verdicts = set(manifest_rows().values())
        self.assertTrue(
            {"change", "remove"} & verdicts,
            "every row says `keep`, which is what a manifest written without "
            "reading the help text looks like")


if __name__ == "__main__":
    unittest.main()
