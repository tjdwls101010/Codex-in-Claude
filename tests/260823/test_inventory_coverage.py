"""Seam 3 — the inventory covers every block, and every owner it names is real.

A rewrite loses facts silently. The only defence is a list that was complete
before the rewriting started, so this is two checks with the same subject:

  * the inventory's block ids and hashes are exactly the extractor's, which makes
    "everything was classified" a machine's verdict rather than a claim; and
  * every `owner_anchor` an (a) or (b) row names resolves to a real destination —
    a heading that exists in the new SKILL.md, an argument that command's parser
    actually takes and explains, an epilog or description that is not empty.

The second half is the one that keeps mattering after the rewrite lands. A row
saying a fact moved to `help:start --timeout` is a promise; a flag renamed later
breaks the promise, and nothing else in the suite is looking at the inventory.

The duplicate check at the bottom is deliberately exact rather than fuzzy. An
n-gram similarity score would flag two paragraphs that share a subject and
disagree about it, which is a judgement, not a defect. Two byte-identical blocks
of twenty words or more is not a judgement: one of them is a copy.
"""

from __future__ import annotations

import argparse
import re
import sys
import unittest
from collections import Counter

from blocks import REPO, digest, is_prose, normalize, original_blocks, split_blocks
from helpers import BRIDGE, SKILL_MD, skill_docs

sys.path.insert(0, str(BRIDGE.parent))
import codex_bridge  # noqa: E402

INVENTORY = REPO / "docs" / "plan" / "skill-rewrite-inventory.md"
ROW_RE = re.compile(r"^\|\s*`([\w-]+)`\s*\|\s*`([0-9a-f]+)`\s*\|\s*([abcd+]+)\s*"
                    r"\|\s*([^|]*?)\s*\|")


def inventory_rows():
    """(block_id, hash, class, [anchors]) for every row of the table."""
    out = []
    for line in INVENTORY.read_text().splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        anchors = [a.strip() for a in m.group(4).split("|") if a.strip()
                   and a.strip() != "—"]
        out.append((m.group(1), m.group(2), m.group(3), anchors))
    return out


def headings(text: str) -> Counter:
    """GitHub-style anchors for every heading, so a `SKILL.md#…` row resolves."""
    out = Counter()
    for line in text.splitlines():
        m = re.match(r"^#{1,6}\s+(.*?)\s*$", line)
        if not m:
            continue
        slug = re.sub(r"[^\w\- ]", "", m.group(1).lower()).strip().replace(" ", "-")
        out[slug] += 1
    return out


def split_help_anchor(body: str):
    """`batch start --as-ready` → ("batch start", "--as-ready").

    The command half is one or two words and the argument half is everything
    left, which can itself contain a space (`resume [REF] PROMPT`). Splitting on
    the longest command path that actually exists is what tells the two apart.
    """
    if body.startswith("(top level)"):
        return "", body[len("(top level)"):].strip()
    words = body.split()
    for n in (2, 1):
        if parser_for(" ".join(words[:n])) is not None:
            return " ".join(words[:n]), " ".join(words[n:])
    return body, ""


def parser_for(path: str):
    """The subparser a command path names, or None."""
    parser = codex_bridge.build_parser()
    for word in path.split():
        nested = [a for a in parser._actions
                  if isinstance(getattr(a, "choices", None), dict) and a.choices]
        found = None
        for action in nested:
            if word in action.choices:
                found = action.choices[word]
                break
        if found is None:
            return None
        parser = found
    return parser


class TheInventoryCoversEveryBlock(unittest.TestCase):

    def test_the_extractor_still_finds_the_old_skill(self):
        """The blocks come out of a commit. A bad ref yields zero rows and every
        check below then passes by comparing nothing to nothing."""
        self.assertGreater(len(original_blocks()), 150)

    def test_the_ids_and_hashes_match_the_extractor_exactly(self):
        expected = {bid: digest(text) for bid, _, text in original_blocks()}
        listed = {bid: h for bid, h, _, _ in inventory_rows()}
        self.assertEqual(
            listed, expected,
            "the inventory and the extractor disagree about which blocks exist "
            "or what they say — a block the inventory does not list is a block "
            "nobody decided the fate of")

    def test_every_row_carries_a_class_the_scheme_defines(self):
        for bid, _, cls, _ in inventory_rows():
            with self.subTest(block=bid):
                self.assertIn(cls, {"a", "b", "c", "d", "a+b"})

    def test_a_kept_row_names_an_owner_and_a_dropped_row_does_not(self):
        for bid, _, cls, anchors in inventory_rows():
            with self.subTest(block=bid, cls=cls):
                if cls in ("a", "b", "a+b"):
                    self.assertTrue(anchors, f"{bid} is kept but named no owner")
                else:
                    self.assertFalse(
                        anchors, f"{bid} is dropped but names an owner")


class EveryOwnerAnchorResolves(unittest.TestCase):

    def anchors(self):
        return [(bid, a) for bid, _, _, anchors in inventory_rows()
                for a in anchors]

    def test_the_table_named_owners_to_check(self):
        self.assertGreater(len(self.anchors()), 100)

    def test_every_skill_md_anchor_is_a_heading_that_exists_once(self):
        found = headings(SKILL_MD.read_text())
        for bid, anchor in self.anchors():
            if not anchor.startswith("SKILL.md#"):
                continue
            slug = anchor.split("#", 1)[1]
            with self.subTest(block=bid, anchor=anchor):
                self.assertEqual(
                    found[slug], 1,
                    f"{bid} says its content lives under {anchor}, which "
                    f"appears {found[slug]} times in SKILL.md")

    def test_every_help_anchor_names_an_argument_that_explains_itself(self):
        for bid, anchor in self.anchors():
            if not anchor.startswith("help:"):
                continue
            command, arg = split_help_anchor(anchor[len("help:"):])
            with self.subTest(block=bid, anchor=anchor):
                parser = parser_for(command)
                self.assertIsNotNone(parser, f"{anchor} names no such command")
                match = [a for a in parser._actions
                         if arg in a.option_strings
                         or arg == a.dest or arg == (a.metavar or "")]
                self.assertTrue(match, f"{anchor} names an argument "
                                       f"`{command}` does not take")
                self.assertTrue(match[0].help,
                                f"{anchor} names an argument with no help=")

    def test_every_epilog_and_description_anchor_is_non_empty(self):
        for bid, anchor in self.anchors():
            kind, _, command = anchor.partition(":")
            if kind not in ("epilog", "desc"):
                continue
            command = "" if command == "(top level)" else command
            with self.subTest(block=bid, anchor=anchor):
                parser = parser_for(command)
                self.assertIsNotNone(parser, f"{anchor} names no such command")
                text = parser.epilog if kind == "epilog" else parser.description
                self.assertTrue(
                    text and text.strip(),
                    f"{bid} moved its content into `{command or 'the top level'}`'s "
                    f"{kind}, which is empty")

    def test_only_anchor_kinds_the_checks_above_understand_are_used(self):
        for bid, anchor in self.anchors():
            with self.subTest(block=bid, anchor=anchor):
                self.assertTrue(
                    anchor.startswith(("SKILL.md#", "help:", "epilog:", "desc:")),
                    f"{bid} names {anchor!r}, a destination shape nothing "
                    f"verifies — an unverifiable anchor is a promise with no "
                    f"one holding it")


class NoBlockIsWrittenTwice(unittest.TestCase):
    """Exact duplicates only. Two paragraphs about one subject are a judgement
    call; the same twenty words twice is a copy, and this round removed six of
    them between SKILL.md and `orchestration.md`."""

    MIN_WORDS = 20

    def substantial_blocks(self):
        out = []
        for doc in skill_docs():
            for block in split_blocks(doc.read_text()):
                if is_prose(block) and len(normalize(block).split()) >= self.MIN_WORDS:
                    out.append((doc.name, block))
        return out

    def test_there_are_blocks_long_enough_to_check(self):
        self.assertGreater(len(self.substantial_blocks()), 10)

    def test_no_two_blocks_are_byte_identical(self):
        seen = {}
        for name, block in self.substantial_blocks():
            h = digest(block)
            if h in seen:
                self.fail(f"{seen[h]} and {name} carry the same block "
                          f"verbatim:\n  {normalize(block)[:160]}…")
            seen[h] = name


if __name__ == "__main__":
    unittest.main()
