"""What this tool prints, stated once and stated correctly.

Three files claim the output contract — SKILL.md, `codex_bridge.py`'s own module
docstring, and docs/wiki/CLI-Reference.md — and all three said the same wrong
thing: *"every subcommand prints one line of JSON, except `log`"*. There are two
exceptions. `status --group --follow` streams plain text too (`group.empty`,
`run <id> <prev> -> <state>`, `group.<state> …`), and has since the batch
subsystem landed.

Nobody noticed because a claim about output is only checked by reading output,
and none of the three copies is close enough to the code to be read alongside
it — including the docstring sitting directly above the module that violates it.

So this pins the behaviour first and the prose against it: a caller who trusts
the contract and pipes `status --group --follow` into a JSON parser gets a crash
this test now prevents.
"""

from __future__ import annotations

import json
import re
import unittest

from helpers import BRIDGE, REPO, SKILL_MD, BridgeCase

# `.*?\.(?=\s|$)` and not `[^.]*\.`: every statement of this contract contains
# `group.<state>`, whose period is not a sentence end. A pattern that stopped at
# the first period captured only the prefix, so the half of the sentence naming
# the second exception was never inspected — the check would have passed with
# anything at all after that point.
CLAIM_RE = re.compile(r"[^.]*one line of JSON.*?\.(?=\s|$)", re.IGNORECASE)


def contract_claims(text):
    """Every sentence in `text` that asserts the one-JSON-line contract.

    Whitespace is flattened first: the claim is a prose sentence, and in
    `codex_bridge.py` it is wrapped across two lines of a docstring, so a
    line-sensitive pattern reads that copy as absent — which is the same as not
    checking it.
    """
    return CLAIM_RE.findall(" ".join(text.split()))


class FollowingAGroupPrintsText(BridgeCase):
    """The second exception, exercised rather than described."""

    def _finished_group(self, name="g"):
        out = self.bridge("batch", "start", "--group", name,
                          "--sandbox", "read-only", "--task", "a", "--task", "b")
        self.assertEqual(out["spawned"], 2, out)
        for row in self.bridge("status", "--group", name)["runs"]:
            self.wait_terminal(row["run_id"])
        return name

    def test_status_group_follow_does_not_emit_json(self):
        name = self._finished_group()
        p = self.bridge_raw("status", "--group", name, "--follow")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
        self.assertTrue(lines, f"--follow printed nothing: {p.stdout!r}")
        for ln in lines:
            with self.subTest(line=ln):
                with self.assertRaises(ValueError, msg=(
                        f"{ln!r} parsed as JSON, so the plain-text stream this "
                        "test exists to pin is no longer plain text — the "
                        "contract sentences need updating with it")):
                    json.loads(ln)

    def test_the_terminal_line_names_the_group_and_its_tally(self):
        """What a caller reads instead of JSON has to carry the same answer."""
        name = self._finished_group()
        p = self.bridge_raw("status", "--group", name, "--follow")
        last = [ln for ln in p.stdout.splitlines() if ln.strip()][-1]
        self.assertRegex(last, rf"^group\.\w+ group={name} done=\d+ failed=\d+")


class TheContractSentencesAreTrue(unittest.TestCase):
    """Each copy of the claim must name both exceptions, or it is still wrong."""

    # The wiki is not part of the skill — Claude never loads it — but it is what
    # someone reads to decide whether to adopt this, and it carried the same
    # wrong sentence. `test_suite_integrity.py` already checks docs/wiki, so
    # holding this one claim true there costs nothing new.
    SOURCES = {
        "SKILL.md": SKILL_MD,
        "codex_bridge.py": BRIDGE,
        "docs/wiki/CLI-Reference.md": REPO / "docs" / "wiki" / "CLI-Reference.md",
        "docs/wiki/Architecture.md": REPO / "docs" / "wiki" / "Architecture.md",
    }

    def test_each_source_states_the_contract_exactly_once(self):
        for label, path in self.SOURCES.items():
            with self.subTest(source=label):
                self.assertEqual(
                    len(contract_claims(path.read_text())), 1,
                    f"{label} should assert the output contract once; a second "
                    "copy is a second thing to keep true")

    def test_every_statement_of_the_contract_names_both_exceptions(self):
        for label, path in self.SOURCES.items():
            claim = contract_claims(path.read_text())[0]
            for exception in ("log", "status --group --follow"):
                with self.subTest(source=label, exception=exception):
                    self.assertIn(
                        exception, claim,
                        f"{label} states the contract without naming "
                        f"`{exception}`, which also streams plain text")


if __name__ == "__main__":
    unittest.main()
