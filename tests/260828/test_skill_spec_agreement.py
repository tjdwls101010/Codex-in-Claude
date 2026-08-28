"""The numbers SKILL.md quotes are the numbers `harness-spec.md` measured.

This is a drift check, not a fact check. It cannot tell you whether four rounds
really ran or whether three findings really were reachable; what it can tell you
is that the two files still say the same thing, which is the failure this
repository has actually had — the spec once counted "eight gotchas" against a
SKILL.md that had fourteen.

The reason it is worth a test at all: the stopping-rule sentences in SKILL.md are
a claim moved out of an audit record and into an instrument that is read on every
delegation. A moved sentence is an unverified new assertion, and nothing else in
the suite reads `harness-spec.md`.

Both directions of drift are caught. Change the spec and the paragraph goes
stale; rewrite the paragraph with a rounder number and the spec disagrees. The
guard tests below exist because the interesting way for a check like this to fail
is to find nothing on one side and compare two empty sets.
"""

from __future__ import annotations

import re
import unittest

from helpers import SKILL_MD, SPEC_MD

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
         "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
         "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
         "twenty": 20}

#: Each measured quantity, as the regex that finds it in `harness-spec.md`. The
#: pattern anchors on the surrounding claim rather than on the number alone, so
#: a stray "three" elsewhere in a 700-line spec cannot stand in for the one this
#: is about.
SPEC_CLAIMS = {
    "adversarial rounds": re.compile(
        r"(\w+) adversarial rounds ran[^.]*?none came back at zero", re.I),
    "defects found": re.compile(
        r"(\w+) defects were found and fixed across those rounds", re.I),
    "reachable in ordinary use": re.compile(
        r"Reachable in ordinary single-session use\s*[—-]\s*(\w+)", re.I),
}


def number(token: str):
    token = token.strip().lower().replace(",", "")
    if token.isdigit():
        return int(token)
    return WORDS.get(token)


def spec_numbers():
    text = SPEC_MD.read_text(encoding="utf-8")
    out = {}
    for name, pattern in SPEC_CLAIMS.items():
        m = pattern.search(text)
        out[name] = number(m.group(1)) if m else None
    return out


def stopping_rule_paragraph():
    """The one paragraph in SKILL.md that carries the moved claim.

    Found by its own subject matter rather than by line number: the file is
    edited far more often than this check is, and a paragraph that has moved is
    not a paragraph that has drifted.
    """
    paras = [p for p in SKILL_MD.read_text(encoding="utf-8").split("\n\n")
             if "stopping rule" in p]
    return paras


class TheSpecStillStatesWhatIsBeingCheckedAgainst(unittest.TestCase):
    """Guards. Without these, a spec rewrite turns this file into a check that
    passes by finding nothing on both sides."""

    def test_every_measured_quantity_is_still_in_the_spec(self):
        for name, value in spec_numbers().items():
            with self.subTest(claim=name):
                self.assertIsNotNone(
                    value,
                    f"harness-spec.md no longer states {name!r} in a form this "
                    f"check can read — the claim moved, was reworded, or was "
                    f"dropped, and SKILL.md is now quoting nothing")

    def test_skill_md_carries_the_paragraph_exactly_once(self):
        paras = stopping_rule_paragraph()
        self.assertEqual(
            len(paras), 1,
            f"expected one paragraph naming the stopping rule, found "
            f"{len(paras)}")


class TheNumbersAgree(unittest.TestCase):

    def test_each_measured_number_appears_in_the_paragraph(self):
        para = stopping_rule_paragraph()[0]
        found = {number(t) for t in re.findall(r"[A-Za-z]+|\d+", para)}
        found.discard(None)
        for name, value in spec_numbers().items():
            with self.subTest(claim=name):
                self.assertIn(
                    value, found,
                    f"SKILL.md's stopping-rule paragraph does not carry the "
                    f"{name} the spec measured ({value})")


if __name__ == "__main__":
    unittest.main()
