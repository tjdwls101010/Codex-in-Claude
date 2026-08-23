"""Seam 1 — each fact the rewrite moved out of prose is in the surface that owns it.

The rewrite's premise is that a fact stated in `--help` cannot drift from the code
that emits it, while the same fact stated in SKILL.md can. That premise buys
nothing unless the fact actually arrives: a sentence deleted from prose and never
added to help is a fact that simply left.

This reads the real `--help` text out of a subprocess rather than the parser's
`help=` attributes. Those are not the same string — argparse rewraps, and it is
the rewrapped text a caller reads — so a check against the attribute can pass on
a help string no caller ever sees in that form.

The propositions below are the ones the rewrite plan moved, each with the
correction Codex made to it during review. They are matched loosely (a few
required substrings per proposition) because the wording is meant to stay
editable; what is pinned is that the claim is there and in the right place.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest

from helpers import BRIDGE, BridgeCase

#: (command path, [substrings that must all appear in that command's --help])
#:
#: The command path is what a caller types after the bridge, so `""` is the
#: top-level help.
FACTS = {
    "doctor exit codes and the two categories": (
        "doctor", ["exit", "0", "2", "blocker", "warning"]),
    "thread_db_readable is about rows, not schema": (
        "doctor", ["thread_db_readable", "no thread"]),
    "models reports each model's efforts and its default": (
        "models", ["efforts", "default_effort"]),
    "the models catalog comes from codex debug models": (
        "models", ["codex debug models"]),
    "log --follow names timed_out among the terminal lines": (
        "log", ["run.timed_out"]),
    "a timed-out run is resumable only if a thread id was recorded": (
        "start", ["timed_out", "thread id"]),
    "an unregistered thread needs an explicit --sandbox": (
        "resume", ["--sandbox", "never recorded"]),
    "batch start returns after the spawns, not after the turns": (
        "batch start", ["spawn", "15", "does not wait"]),
    "which members qualify for a worktree": (
        "batch start", ["worktree", "two or more", "read-only", "review"]),
    "the output contract and both of its exceptions": (
        "", ["one line of JSON", "log", "status --group --follow"]),
}

#: Every state a caller can read off `status`, written out deliberately.
#:
#: A set imported from `_registry` would be the same constant compared against
#: itself — true however wrong the constant is. This list is the specification;
#: `TheStateVocabularyIsReal` below checks the runtime actually produces the
#: states in it, so the two halves can disagree.
RUN_STATES = ["starting", "waiting", "running", "stalled",
              "completed", "failed", "interrupted", "orphaned", "timed_out"]
GROUP_STATES = ["running", "completed", "partial"]


def help_text(command: str) -> str:
    """The real rendered help for one command path."""
    argv = [sys.executable, str(BRIDGE), *command.split(), "--help"]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise AssertionError(f"`{' '.join(argv[2:])}` exited {p.returncode}: "
                             f"{p.stderr or p.stdout}")
    return " ".join(p.stdout.split())


class HelpCarriesTheMigratedFacts(unittest.TestCase):

    def test_each_fact_appears_in_the_help_that_owns_it(self):
        for name, (command, needles) in FACTS.items():
            text = help_text(command)
            for needle in needles:
                with self.subTest(fact=name, command=command or "(top level)",
                                  needle=needle):
                    self.assertIn(
                        needle, text,
                        f"`{command or ''} --help` does not state {name!r}; the "
                        f"rewrite removed that sentence from prose on the "
                        f"understanding it would live here instead")


class TheStateVocabularyIsStated(unittest.TestCase):
    """`status`'s epilog is where a caller learns what the words mean.

    A state name printed with no gloss is a word the caller has to guess at, and
    the two that get guessed wrong are `stalled` (a display state, not a stored
    one — nothing is killed) and `orphaned` (the supervisor is gone, not Codex).
    """

    def test_the_epilog_names_every_run_state(self):
        text = help_text("status")
        for state in RUN_STATES:
            with self.subTest(state=state):
                self.assertIn(state, text)

    def test_the_epilog_names_every_group_state(self):
        text = help_text("status")
        self.assertIn("group_state", text)
        for state in GROUP_STATES:
            with self.subTest(group_state=state):
                self.assertIn(state, text)

    def test_the_epilog_glosses_the_two_misread_states(self):
        text = help_text("status")
        self.assertRegex(text, r"stalled[^.]*(no events|nothing is|advisory)")
        self.assertRegex(text, r"orphaned[^.]*supervisor")


class TheStateVocabularyIsReal(BridgeCase):
    """The list above is a specification; this drives the CLI until it says
    those words back.

    Comparing `RUN_STATES` against a constant in `_registry` would be the same
    list twice — true no matter how wrong it is, and it would keep passing after
    a state stopped being reachable. So each of these comes out of a run that
    was actually put into that state against the fake `codex`.

    Four of the nine are left to the rounds that already own them: `waiting` and
    `orphaned` need a batch predecessor and a killed supervisor respectively
    (tests/260813), and `stalled` needs a clock past its threshold
    (tests/260813/test_turn_clock.py). Reproducing them here would be a second
    copy of a fixture rather than a second check.

    `starting` is the fifth, and for a different reason: it is the state written
    between the fork and the supervisor's first report, so a test that waited to
    observe it would be racing the thing it is observing. It stays in the
    vocabulary because `status` can genuinely hand it back.
    """

    OBSERVED_HERE = {"running", "completed", "interrupted",
                     "timed_out", "failed"}

    def test_the_states_this_round_can_reach_are_reachable(self):
        seen = set()

        done = self.bridge("start", "--sandbox", "read-only", "hello")
        seen.add(done["state"])
        self.wait_terminal(done["run_id"])
        seen.add(self.meta(done["run_id"])["state"])

        self.env["FAKE_CODEX_EXIT"] = "3"
        bad = self.bridge("start", "--sandbox", "read-only", "boom")
        self.wait_terminal(bad["run_id"])
        seen.add(self.meta(bad["run_id"])["state"])
        del self.env["FAKE_CODEX_EXIT"]

        self.env["FAKE_CODEX_HANG"] = "30"
        slow = self.bridge("start", "--sandbox", "read-only", "wait")
        seen.add(self.bridge("status", "--run", slow["run_id"])["runs"][0]["state"])
        self.bridge("stop", "--run", slow["run_id"])
        self.wait_terminal(slow["run_id"])
        seen.add(self.meta(slow["run_id"])["state"])

        timed = self.bridge("start", "--sandbox", "read-only",
                            "--timeout", "1", "wait")
        self.wait_terminal(timed["run_id"])
        seen.add(self.meta(timed["run_id"])["state"])
        del self.env["FAKE_CODEX_HANG"]

        self.assertEqual(
            self.OBSERVED_HERE - seen, set(),
            f"these states are in the vocabulary this file pins and in "
            f"`status --help`, but driving the CLI into them produced "
            f"{sorted(seen)} instead")
        self.assertEqual(
            seen - set(RUN_STATES), set(),
            "the CLI reported a state neither this file nor `status --help` "
            "names, so a caller reading either would not know what it means")

    def test_a_group_reports_the_group_vocabulary(self):
        self.bridge("batch", "start", "--group", "g", "--sandbox", "read-only",
                    "--task", "a", "--task", "b")
        for row in self.bridge("status", "--group", "g")["runs"]:
            self.wait_terminal(row["run_id"])
        state = self.bridge("status", "--group", "g")["group_state"]
        self.assertIn(state, GROUP_STATES)


if __name__ == "__main__":
    unittest.main()
