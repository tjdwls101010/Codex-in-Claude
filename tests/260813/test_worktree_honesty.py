"""D2 — the worktree preamble must not assert a count it never read.

`uncommitted_count` returns 0 when `git status --porcelain` fails, so "I could
not count" and "there are none" leave by the same door. That number is stated to
Codex as fact in the worktree preamble, and handed to the caller as
`uncommitted_files_in_caller_tree`.

The preamble exists to correct a confident falsehood — Codex otherwise assumes
it is looking at the caller's tree — so a preamble that manufactures one is the
worst possible place for this. The precondition is not exotic: a corrupt
`.git/index` makes `status` exit 128 while `rev-parse` and `worktree add` both
still succeed, so the batch gets far enough to write the sentence.
"""

from __future__ import annotations

import unittest

from helpers import BridgeCase


class UncommittedCount(BridgeCase):

    def start_batch(self):
        # Two members, because a lone writer is given no worktree — it has
        # nobody to collide with — and the preamble under test is the worktree
        # one.
        tasks = self.tasks_file("do the thing", "do the other thing")
        return self.bridge("batch", "start", "--group", "g", "--tasks-file", tasks)

    def preamble(self):
        """The prompt the bridge actually handed to `codex`."""
        invocations = self.invocations()
        self.assertTrue(invocations, "the bridge never invoked codex")
        argv = invocations[0]["argv"]
        return "\n".join(a for a in argv if "Working tree:" in a)

    def break_git_status(self):
        """`status` fails; `rev-parse` and `worktree add` keep working."""
        (self.project / ".git" / "index").write_bytes(b"\xde\xad\xbe\xef" * 8)
        self.assertNotEqual(
            self.git("status", "--porcelain").returncode, 0,
            "this test needs a tree git cannot count")

    def test_a_countable_tree_reports_the_count(self):
        (self.project / "dirty.txt").write_text("uncommitted\n")
        out = self.start_batch()
        self.assertEqual(out["worktrees"]["uncommitted_files_in_caller_tree"], 1)
        self.assertIn("1", self.preamble())

    def test_an_uncountable_tree_reports_unknown_rather_than_zero(self):
        self.break_git_status()
        out = self.start_batch()
        self.assertIsNone(
            out["worktrees"]["uncommitted_files_in_caller_tree"],
            "a count that could not be read must not be reported as a number")

    def test_the_preamble_does_not_tell_codex_a_number_it_never_read(self):
        self.break_git_status()
        self.start_batch()
        text = self.preamble()
        self.assertTrue(text, "no worktree preamble reached codex")
        self.assertNotIn(
            "0 uncommitted", text,
            "the preamble states as fact a count git refused to give")
        self.assertIn("could not", text)


if __name__ == "__main__":
    unittest.main()
