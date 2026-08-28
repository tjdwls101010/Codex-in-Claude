"""`review` is gone from the command surface, and its removal is announced once.

The seam is the CLI surface — what a caller types and what comes back — not the
bridge's internals. A check that `review_argv` no longer exists would pass on a
rename and say nothing about whether anyone can still reach the command, which
is the only question the removal was about.

Three things have to hold. The command must not be listed, so nobody is routed
to it; typing it must fail rather than doing something else; and a `kind:
review` line in a tasks file — the one place the command's name was data rather
than argv — must be refused with the migration attached. That last one is why
this file exists at all: `kind` already had an allow-set, so dropping `review`
from it would refuse the line either way. What is pinned here is that the
refusal says where the command went, for the one release where somebody still
has such a file on disk.
"""

from __future__ import annotations

import re
import unittest

from helpers import BridgeCase, help_text


class ReviewIsNotOnTheSurface(BridgeCase):

    def test_top_level_help_does_not_list_review(self):
        """The command listing is what a caller reads to learn what exists."""
        out = help_text()
        listing = re.search(r"\{([a-z,_]+)\}", out)
        self.assertIsNotNone(listing, f"no subcommand listing in:\n{out}")
        self.assertNotIn("review", listing.group(1).split(","))

    def test_typing_review_is_a_usage_error(self):
        """Not a silent alias for something else, and not a traceback."""
        p = self.bridge_raw("review", "--uncommitted")
        self.assertEqual(p.returncode, 2, f"stdout={p.stdout}\nstderr={p.stderr}")
        self.assertIn("invalid choice", p.stderr)
        self.assertNotIn("Traceback", p.stderr)

    def test_review_help_is_a_usage_error_too(self):
        """`review --help` is how a caller checks whether a command is still
        there; it must not print a help page for a command that is gone."""
        p = self.bridge_raw("review", "--help")
        self.assertEqual(p.returncode, 2, f"stdout={p.stdout}\nstderr={p.stderr}")
        self.assertNotIn("diff selector", p.stdout)


class TasksFilesSayWhereItWent(BridgeCase):

    def test_kind_review_is_refused_with_the_migration(self):
        tf = self.tasks_file({"kind": "review", "prompt": "look at this"})
        r = self.bridge("batch", "start", "--group", "g", "--tasks-file", str(tf),
                        expect_rc=1)
        msg = r.get("error", "") + str(r)
        self.assertIn("start", msg)
        self.assertIn("resume", msg)
        # The release it went in, and what replaces it. A refusal that only says
        # the value is invalid leaves the reader to guess whether they mistyped.
        self.assertIn("0.7.0", msg)
        self.assertIn("read-only", msg)

    def test_a_review_object_is_an_unknown_field(self):
        """The nested object went with the command. It was validated against its
        own field list, so an unvalidated leftover would be a silent no-op."""
        tf = self.tasks_file(
            {"prompt": "p", "review": {"uncommitted": True}})
        r = self.bridge("batch", "start", "--group", "g", "--tasks-file", str(tf),
                        expect_rc=1)
        self.assertIn("unknown field", r.get("error", ""))
        self.assertIn("review", r.get("error", ""))


if __name__ == "__main__":
    unittest.main()
