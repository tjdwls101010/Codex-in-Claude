"""B20 and B18 — the two rows the suite never touched.

B20 is "the gotchas a caller cannot derive live in SKILL.md and references/".
No test read those files, so nothing checked that what they say matches what the
CLI does. Four separate mismatches leaked out through that gap in one audit: a
flag the skill instructs you to use that appears in no command table, a flag
documented only in a reference nobody reads first, an equivalence between two
spellings that is never stated, and a citation that resolves nowhere.

Prose cannot be tested for being right. It can be tested for being *consistent
with the thing it describes*, and that is where all four of those lived.

B18 is "polling must not raise an approval prompt". The skill declares
`allowed-tools` so that a caller checking on a run every few seconds is
pre-approved once rather than prompted every time; if the declared pattern stops
matching the commands the docs tell you to run, background work dies by a
thousand prompts. Reverting the trap that caused it (R21) would not be caught by
any other test here.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

from helpers import BRIDGE, REPO

SKILL_DIR = BRIDGE.parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = sorted((SKILL_DIR / "references").glob("*.md"))
DOCS = [SKILL_MD, *REFERENCES]

sys.path.insert(0, str(BRIDGE.parent))
import codex_bridge  # noqa: E402


def cli_surface():
    """{subcommand: {flags}} as argparse actually has it, plus the global flags.

    Read off the parser rather than a hand-kept list, because a hand-kept list
    is a second place for the docs to disagree with.
    """
    parser = codex_bridge.build_parser()
    surface, globals_ = {}, set()
    for action in parser._actions:
        globals_.update(action.option_strings)
        if not hasattr(action, "choices") or not isinstance(action.choices, dict):
            continue
        for name, sub in action.choices.items():
            flags = set()
            nested = {}
            for a in sub._actions:
                flags.update(a.option_strings)
                if hasattr(a, "choices") and isinstance(a.choices, dict):
                    for sname, ssub in a.choices.items():
                        nested[f"{name} {sname}"] = {
                            f for sa in ssub._actions for f in sa.option_strings}
            surface[name] = flags
            surface.update(nested)
    return surface, globals_


# `$CODEX <sub> …` in a code block, and the same commands written inline in
# prose. Both forms have to be read: the mismatch that motivated this check was
# an instruction in a sentence, and a check that only read code blocks would
# have walked straight past it.
COMMAND_RE = re.compile(r"\$CODEX\s+([a-z]+(?:\s+[a-z]+)?)((?:\s+[^\n`|]*)?)")
INLINE_RE = re.compile(r"`([^`\n]+)`")
FLAG_RE = re.compile(r"(--[a-z][a-z0-9-]*)")


def _split(phrase: str, surface):
    """The longest leading run of words that names a subcommand."""
    words = phrase.split()
    for n in (2, 1):
        if len(words) >= n and " ".join(words[:n]) in surface:
            return " ".join(words[:n]), " ".join(words[n:])
    return None, ""


def documented_commands():
    """(doc, subcommand, flag) for every flag the docs show being passed."""
    surface, _ = cli_surface()
    out = []
    for doc in DOCS:
        text = doc.read_text()
        for m in COMMAND_RE.finditer(text):
            phrase, rest = m.group(1).strip(), m.group(2)
            sub = phrase if phrase in surface else phrase.split()[0]
            for flag in FLAG_RE.findall(rest):
                out.append((doc, sub, flag))
        for m in INLINE_RE.finditer(text):
            sub, rest = _split(m.group(1), surface)
            if not sub:
                continue
            for flag in FLAG_RE.findall(rest):
                out.append((doc, sub, flag))
    return out


class DocumentedFlagsExist(unittest.TestCase):
    """Every flag the skill tells you to pass must be a flag the CLI takes."""

    def test_the_extraction_found_commands_to_check(self):
        self.assertGreater(len(documented_commands()), 20,
                           "the command regex stopped matching the docs, so "
                           "this check is passing vacuously")

    def test_every_documented_flag_is_real(self):
        surface, globals_ = cli_surface()
        for doc, sub, flag in documented_commands():
            with self.subTest(doc=doc.name, sub=sub, flag=flag):
                self.assertIn(sub, surface, f"{doc.name} shows `$CODEX {sub}`")
                self.assertIn(
                    flag, surface[sub] | globals_,
                    f"{doc.name} tells the caller to pass `{flag}` to "
                    f"`{sub}`, which does not accept it")


class DocumentedFlagsAreFindable(unittest.TestCase):
    """A flag SKILL.md instructs you to use has to be listed in SKILL.md.

    The failure this closes is not "undocumented" — it is documented, in a
    reference file — but a caller reading the instruction has no way to learn
    the flag's syntax without already knowing which of four references to open.
    """

    def test_every_flag_skill_md_instructs_is_also_named_in_its_tables(self):
        surface, globals_ = cli_surface()
        text = SKILL_MD.read_text()
        # The command table and the options paragraph are where a reader looks
        # a flag up; everywhere else is where they are told to use one.
        tables = "\n".join(ln for ln in text.splitlines()
                           if ln.startswith("|") or " options:" in ln)
        instructed = {flag for doc, _sub, flag in documented_commands()
                      if doc == SKILL_MD}
        for flag in sorted(instructed):
            with self.subTest(flag=flag):
                self.assertIn(
                    flag, tables,
                    f"SKILL.md tells the caller to use `{flag}` but never lists "
                    f"it, so there is nowhere in this file to learn its syntax")


class CitationsResolve(unittest.TestCase):
    """`(V-31)` style citations are this project's way of saying "this claim was
    measured, and here is where". One that resolves nowhere is a claim wearing
    evidence it does not have."""

    CITATION_RE = re.compile(r"\((V-\d+|D\d+|R\d+|B\d+|F\d+)\)")

    def corpus(self):
        return {p: p.read_text() for p in REPO.rglob("*.md")
                if ".codex-runs" not in p.parts and "node_modules" not in p.parts}

    def test_every_citation_in_the_skill_resolves_somewhere(self):
        corpus = self.corpus()
        for doc in DOCS:
            for m in self.CITATION_RE.finditer(doc.read_text()):
                tag = m.group(1)
                with self.subTest(doc=doc.name, tag=tag):
                    elsewhere = [p.relative_to(REPO).as_posix()
                                 for p, t in corpus.items()
                                 if p != doc and tag in t]
                    self.assertTrue(
                        elsewhere,
                        f"{doc.name} cites {tag}, which appears nowhere else in "
                        f"the repository — the citation points at nothing")


class PollingIsPreApproved(unittest.TestCase):
    """B18. `allowed-tools` is what makes repeated polling free of prompts."""

    def allowed_patterns(self):
        text = SKILL_MD.read_text()
        front = text.split("---")[1]
        return re.findall(r"-\s*(Bash\(.*\))", front)

    def test_the_skill_declares_allowed_tools(self):
        self.assertTrue(self.allowed_patterns(),
                        "no allowed-tools entry; every bridge call prompts")

    def test_the_pattern_covers_the_bridge_and_ends_in_a_wildcard(self):
        """A pattern pinned to one subcommand would pre-approve `start` and
        prompt on every `status` that follows it — which is the polling loop."""
        for pattern in self.allowed_patterns():
            with self.subTest(pattern=pattern):
                self.assertIn("codex_bridge.py", pattern)
                self.assertTrue(
                    pattern.rstrip(")").rstrip().endswith("*"),
                    "the pattern must end in a wildcard, or each distinct "
                    "argument list is a separate approval")

    def test_the_documented_invocation_matches_the_pattern(self):
        """The docs abbreviate the bridge call as `$CODEX`. Whatever `$CODEX` is
        defined as has to be the same string the pattern approves."""
        text = SKILL_MD.read_text()
        m = re.search(r"\$CODEX[^\n]*?is\s+shorthand\s+for[^\n]*", text) \
            or re.search(r"`?\$CODEX`?\s*=\s*([^\n]*)", text)
        self.assertIsNotNone(
            m, "SKILL.md uses $CODEX without ever saying what it stands for")
        self.assertIn("codex_bridge.py", m.group(0))


if __name__ == "__main__":
    unittest.main()
