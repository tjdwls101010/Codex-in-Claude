"""Seam 4 — every `.md` pointer inside the skill package resolves, and none leaves it.

Two failures, one check. A pointer at a file that does not exist sends the reader
nowhere; a pointer at a file *outside* the package sends a plugin install nowhere,
because only the package ships. Both read as working when the author tests them
from a git clone, which is why this exists — the four that were live when this
round started (`_events.py`, `_run.py`, `_worktree.py`, `event-stream.md`) were
all written by someone with the whole repository on disk.

Markdown links are the obvious form and the least common one here. The pointers
that broke were inline code spans in prose and paths in Python comments, so all
three shapes are scanned.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import SKILL_DIR, skill_docs

#: `[text](path.md)`, `` `references/foo.md` ``, and bare `foo.md` in a comment
#: or string. The three ways a path is written in this package.
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+\.md)[^)]*\)")
SPAN_RE = re.compile(r"`([^`\n]*?[\w/.-]+\.md)`")
# The lookbehind rejects `-` as well as word characters: `event-stream.md` would
# otherwise also match starting at `stream.md`, reporting a missing file whose
# name nobody wrote.
BARE_RE = re.compile(r"(?<![\w/`(\[-])((?:\.{0,2}/)?[\w][\w./-]*\.md)")


def scan(text: str):
    """Every markdown path the text points at, however it is written."""
    out = set()
    for pattern in (LINK_RE, SPAN_RE, BARE_RE):
        for m in pattern.finditer(text):
            path = m.group(1).strip().split("#", 1)[0]
            if path:
                out.add(path)
    return out


#: Names of files that belong to the wider world, not to a path on disk.
#:
#: `AGENTS.md` and `CLAUDE.md` are the project's own, named as a subject rather
#: than linked; `SKILL.md` is this file. A pointer at `harness-spec.md` is the
#: shape this seam exists to catch and is deliberately not exempt.
NOT_A_PATH = {"AGENTS.md", "CLAUDE.md", "SKILL.md", "README.md", "config.md"}


def package_files():
    """Every file the skill package ships, as the caller would reach them."""
    return {p.relative_to(SKILL_DIR).as_posix()
            for p in SKILL_DIR.rglob("*") if p.is_file()}


class EveryPointerResolvesInsideThePackage(unittest.TestCase):

    def sources(self):
        return [*skill_docs(), *sorted((SKILL_DIR / "scripts").glob("*.py"))]

    def test_the_scan_reads_the_whole_package(self):
        self.assertGreater(len(self.sources()), 5)

    def test_every_pointer_names_a_file_that_ships(self):
        shipped = package_files()
        for source in self.sources():
            rel = source.relative_to(SKILL_DIR).as_posix()
            for pointer in sorted(scan(source.read_text())):
                if Path(pointer).name in NOT_A_PATH:
                    continue
                with self.subTest(source=rel, pointer=pointer):
                    resolved = (source.parent / pointer).resolve()
                    self.assertTrue(
                        resolved.is_file(),
                        f"{rel} points at {pointer}, which does not exist")
                    try:
                        inside = resolved.relative_to(SKILL_DIR).as_posix()
                    except ValueError:
                        self.fail(
                            f"{rel} points at {pointer}, which is outside the "
                            f"skill package — a plugin install ships the "
                            f"package and nothing else, so this resolves for "
                            f"the author and for nobody else")
                    self.assertIn(inside, shipped)


if __name__ == "__main__":
    unittest.main()
