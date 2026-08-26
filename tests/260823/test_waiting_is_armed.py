"""Seam 3 — the waiting doctrine reaches a single run, and never advises a
watcher that stops before the run does.

Seams 1 and 2 are about *where a fact lives*. This one is about *who reads it*,
which is the defect this round exists for: the doctrine was correct and sat
under `## Collecting a batch`, so a lone `start` had no reason to read it and
the observed behaviour was a delegation nobody ever came back to.

Both checks below are on text a machine can adjudicate, which is the bar for
putting a rule here rather than in prose. The judgement they cannot make — is
the idiom convincing, does the reason let a reader re-derive it — stays a
reading job, and the e2e scenarios are where it is actually answered.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import REPO, SKILL_MD

#: Every document that carries waiting guidance for this skill.
#:
#: The wiki is in here because the same wrong sentence was in three places at
#: once — SKILL.md, `Orchestration.md` and `CLI-Reference.md` — and a check that
#: only read the skill package would have called the round finished with two of
#: them still standing.
DOCS = [SKILL_MD] + sorted((REPO / "docs" / "wiki").rglob("*.md"))

_MONITOR = re.compile(r"\bMonitor\b")
_PERSISTENT = re.compile(r"\bpersistent\b", re.I)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def sections(text):
    """(heading, body) pairs, split on markdown headings.

    A section rather than a paragraph, because the paragraph that *rejects*
    Monitor for a job sits next to the one that accepts it for another, and a
    paragraph-scoped rule makes the rejection restate the caveat it exists to
    keep you away from. A section is also the unit a reader actually arrives in.
    The preamble before the first heading comes back as `""`.
    """
    heading, body, out = "", [], []
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            out.append((heading, "\n".join(body)))
            heading, body = m.group(2), []
        else:
            body.append(line)
    out.append((heading, "\n".join(body)))
    return out


class MonitorIsNeverAdvisedAtItsDefaultLifetime(unittest.TestCase):
    """A Monitor left at its default stops watching after five minutes.

    Codex runs go past five minutes routinely, so a paragraph that reaches for
    Monitor without saying `persistent: true` is prescribing a watcher that
    quits mid-run. Measured this round: the expiry does announce itself
    (`[Monitor timed out — re-arm if needed.]`), so the failure is not silence —
    it is an interruption a reader will take for an ending unless the paragraph
    that sent them there already told them the window exists.
    """

    def test_every_section_that_names_monitor_names_persistent(self):
        for doc in DOCS:
            for heading, body in sections(doc.read_text()):
                if not _MONITOR.search(body):
                    continue
                with self.subTest(doc=doc.name, section=heading or "(preamble)"):
                    self.assertRegex(
                        body, _PERSISTENT,
                        f"{doc.name} reaches for the Monitor tool under "
                        f"{heading!r} without `persistent`, so it is describing "
                        f"a watcher that stops after five minutes on a run that "
                        f"will not")


class TheOneTurnRuleCoversEveryWayOfArming(unittest.TestCase):
    """C7 — the exception said "run the follow in the foreground" and named
    only the follower.

    Two measured sessions found the two holes it left. One armed a background
    follower, then filled the wait with parallel work and ended the turn on a
    promise; the other armed a Monitor and did the same. Both had read the
    exception and neither was covered by it: it addressed the instrument rather
    than the property that makes arming useless, which is that this turn is the
    last one.
    """

    def section(self):
        for heading, body in sections(SKILL_MD.read_text()):
            if "wait" in heading.lower():
                return body
        self.fail("no waiting section in SKILL.md")

    def test_the_exception_covers_monitor_as_well_as_the_follower(self):
        body = self.section()
        para = [b for b in body.split("\n\n") if "only turn" in b]
        self.assertEqual(len(para), 1, "the one-turn rule is not one paragraph")
        self.assertRegex(para[0], _MONITOR,
                         "a session that armed a Monitor read this paragraph "
                         "and ended the turn on a promise; naming only the "
                         "follower is what left it uncovered")

    def test_it_says_what_to_do_with_the_turn_that_is_left(self):
        """The other hole: knowing to block does not say *when*, and a session
        that blocked first had nothing to fill the turn with afterwards."""
        para = [b for b in self.section().split("\n\n") if "only turn" in b][0]
        self.assertRegex(para, r"parallel work")
        self.assertRegex(para, r"\blast\b")


class TheWaitingDoctrineIsNotScopedToBatch(unittest.TestCase):
    """Waiting guidance filed under a batch heading is guidance a single run
    never reads.

    `--follow` is the marker because it is the only thing in this skill that
    waits — every mention of it is either the instruction or the exception to
    it. A heading that narrows those to batches is the exact shape of this
    round's defect, and the one part of it a machine can see.
    """

    def test_no_heading_narrows_waiting_guidance_to_a_batch(self):
        for heading, body in sections(SKILL_MD.read_text()):
            if "--follow" not in body:
                continue
            with self.subTest(heading=heading or "(preamble)"):
                self.assertNotRegex(
                    heading, re.compile(r"batch", re.I),
                    f"SKILL.md files waiting guidance under {heading!r}. A "
                    f"lone `start` is the case that most needs it and the one "
                    f"with no reason to read a section named for batches")


if __name__ == "__main__":
    unittest.main()
