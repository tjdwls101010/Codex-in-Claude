"""Seam 2 — a fact the tool states is not stated again in prose.

Seam 1 says the fact arrived in `--help`. This says it left the prose. They are
separate tests on purpose: the migration passes through a state where both are
true, and one test covering both would go green only at the very end and tell you
nothing about which half is missing.

Two copies of a fact is not a redundancy, it is a fork. `--help` is regenerated
from the code on every call; the paragraph is not, so the paragraph is the copy
that goes wrong — and it goes wrong silently, because nothing reads the two
side by side. This round found the shape already happening: `orchestration.md`
described a `concurrent_writers_note` that pointed at `orchestration.md`, and
`harness-spec.md` counted eight gotchas against a SKILL.md that had fourteen.
"""

from __future__ import annotations

import re
import unittest

from helpers import skill_docs
from test_help_owns_its_facts import FACTS, RUN_STATES, help_text

#: Phrases that would mean the prose is carrying a fact `--help` now owns.
#:
#: Each is deliberately narrow. "worktree" appearing in SKILL.md is fine and
#: expected — the caller has to know worktrees exist to decide anything. What is
#: not fine is SKILL.md restating *the eligibility rule*, because that rule is a
#: property of `batch start`'s own code and changes with it.
RESTATEMENTS = {
    "the option surface as a table": (
        re.compile(r"^\|\s*`(start|resume|review|status|log|show|stop|result|"
                   r"doctor|models|batch[a-z ]*)`\s*\|", re.M),
        "a command table in prose is a second copy of `--help`'s own listing"),
    "the worktree eligibility rule": (
        re.compile(r"two or more .{0,40}(members|writers).{0,40}worktree", re.I),
        "which members qualify is `batch start`'s rule, stated in its epilog"),
    "the tasks-file field list": (
        re.compile(r"`?(prompt|kind)`?,\s*`?(kind|label|prompt)`?,\s*`?\w+`?,"
                   r"\s*`?\w+`?,\s*`?\w+`?", re.I),
        "the per-item fields are generated from the validator's own tuple"),
    "the filter levels enumerated": (
        re.compile(r"`?compact`?[^.\n]{0,30}`?normal`?[^.\n]{0,30}`?full`?"
                   r"[^.\n]{0,30}`?raw`?", re.I),
        "what each --level includes is `log --help`'s to state"),
    "the doctor blocker list": (
        re.compile(r"blockers?\b[^.\n]{0,80}\bwarnings?\b", re.I),
        "the two categories and their members belong to `doctor`'s description"),
    "the --resume-from pairing rules": (
        re.compile(r"one task per (started )?member", re.I),
        "each pairing rule is a refusal that names the caller's own case"),
    "the projected_cost sample story": (
        re.compile(r"\b6 (under )?of 11\b", re.I),
        "the sample narrative leaves the output entirely"),
    # This round's addition. The waiting section has to argue *from* the return
    # contract — arm it now, because nothing will tell you later — and the
    # nearest wrong turn is to restate the contract on the way, which puts the
    # copy in the document that cannot regenerate it.
    "when a start returns": (
        re.compile(r"returns? (as soon as|immediately|right away|the moment)"
                   r"|does not wait for the turn", re.I),
        "when a run hands back its handle is `start --help`'s to state"),
    # C6's addition. The format is now in `--follow`'s own help, and a
    # document that spells the template again is the copy that survives a
    # change to `follow_group`'s f-string.
    "the group follower's line format": (
        re.compile(r"run <id> <prev>|group\.<state>|`group\.\w+ group=", re.I),
        "what `status --group --follow` prints is that flag's help"),
    "the thread_id: null gotcha": (
        re.compile(r"thread[_ ]id\b[^.\n]{0,40}\bnull\b", re.I),
        "that a null thread id is a normal return is the same epilog's"),
}


class ProseDoesNotRestateWhatHelpOwns(unittest.TestCase):

    def test_no_document_carries_a_restatement(self):
        for doc in skill_docs():
            text = doc.read_text()
            for name, (pattern, why) in RESTATEMENTS.items():
                with self.subTest(doc=doc.name, restated=name):
                    self.assertIsNone(
                        pattern.search(text),
                        f"{doc.name} still carries {name}: {why}")

    def test_the_state_vocabulary_is_not_enumerated_in_prose(self):
        """Naming one state to make a point is fine; listing the set is the
        copy. Four or more of the nine in one document is the listing."""
        for doc in skill_docs():
            named = {s for s in RUN_STATES if re.search(rf"\b{s}\b",
                                                        doc.read_text())}
            with self.subTest(doc=doc.name):
                self.assertLess(
                    len(named), 4,
                    f"{doc.name} names {sorted(named)} — that is the state "
                    f"vocabulary, which `status --help` now glosses")


class TheMigratedFactsAreGoneFromProse(unittest.TestCase):
    """The other direction of seam 1, phrase by phrase.

    A needle seam 1 requires in `--help` must not also be sitting in a
    paragraph. Short and ambiguous needles are skipped — `log` and `0` appear in
    prose for a hundred honest reasons — so this checks the distinctive ones.
    """

    DISTINCTIVE = re.compile(r"^(--|[a-z_]+\.[a-z_]+|.{12,})$")

    def test_no_distinctive_migrated_phrase_survives_in_prose(self):
        checked = 0
        for name, (command, needles) in FACTS.items():
            for needle in needles:
                if not self.DISTINCTIVE.match(needle):
                    continue
                checked += 1
                for doc in skill_docs():
                    with self.subTest(fact=name, needle=needle, doc=doc.name):
                        # assertFalse rather than assertNotIn: the latter puts
                        # the entire document in the failure message.
                        self.assertFalse(
                            needle in doc.read_text(),
                            f"{doc.name} repeats {needle!r}, which "
                            f"`{command or ''} --help` now states")
        self.assertGreater(checked, 5,
                           "the distinctiveness filter rejected almost every "
                           "needle, so this check is looking at nothing")


if __name__ == "__main__":
    unittest.main()
