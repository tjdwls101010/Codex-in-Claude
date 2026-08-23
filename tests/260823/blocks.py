"""One mechanical definition of "a prose block", shared by the inventory and its test.

The rewrite's safety net is a claim about coverage: every block of the old skill
was looked at and assigned an owner. That claim is only checkable if "block" has
a definition a machine applies the same way twice — hence this file rather than a
paragraph describing the intent.

The old text is read out of git rather than the worktree, because the rewrite
deletes it. `ORIGIN` is the commit that still holds it.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

#: The commit whose tree still carries the pre-rewrite skill package.
ORIGIN = "2357bd3"

#: The files the inventory covers, relative to the repo root.
SOURCES = [
    ".claude/skills/codex/SKILL.md",
    ".claude/skills/codex/references/environment.md",
    ".claude/skills/codex/references/event-stream.md",
    ".claude/skills/codex/references/orchestration.md",
    ".claude/skills/codex/references/troubleshooting.md",
]

_FENCE = re.compile(r"^\s*```")
_HEADING_ONLY = re.compile(r"#{1,6} .*")


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 3)
    return text[end + 5:] if end != -1 else text


def normalize(block: str) -> str:
    """Whitespace-insensitive form. Re-wrapping a paragraph is not a new block."""
    return " ".join(block.split())


def digest(block: str) -> str:
    return hashlib.sha256(normalize(block).encode("utf-8")).hexdigest()[:12]


def split_blocks(text: str) -> list[str]:
    """Blank-line-separated runs, with fenced code kept whole.

    A fence's own body contains blank lines (the JSONL samples do), so splitting
    on blank lines alone would shatter one example into several blocks and make
    the count depend on the example's contents.
    """
    blocks, current, in_fence = [], [], False
    for line in strip_frontmatter(text).splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            current.append(line)
            continue
        if not line.strip() and not in_fence:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def original(path: str) -> str:
    """The pre-rewrite text of one source, out of git."""
    return subprocess.run(
        ["git", "-C", str(REPO), "show", f"{ORIGIN}:{path}"],
        capture_output=True, text=True, check=True).stdout


def is_prose(block: str) -> bool:
    """A block that carries a claim, as opposed to structure.

    A line that is only a heading names a section without asserting anything, so
    there is nothing to own or to move. Excluding them keeps the inventory about
    claims; including them would pad the coverage count with 50 rows that all say
    the same nothing.
    """
    return not _HEADING_ONLY.fullmatch(block)


def original_blocks() -> list[tuple[str, str, str]]:
    """(block_id, source, text) for every prose block the rewrite is replacing."""
    out = []
    for path in SOURCES:
        stem = Path(path).stem.replace("-", "")
        n = 0
        for block in split_blocks(original(path)):
            if not is_prose(block):
                continue
            n += 1
            out.append((f"{stem}-{n:02d}", path, block))
    return out
