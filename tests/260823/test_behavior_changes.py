"""Seam 6 — the six places where honest help would have had to be a warning.

The rewrite's rule is that the tool says what the tool knows. Six help strings
could not be written honestly without becoming a caveat about the tool's own
behaviour — "this flag exists but is refused", "the last one you passed wins",
"this option surface includes something you must not call". A caveat in help is
a design defect wearing documentation, so the behaviour changed instead and the
caveat went away.

Each change is one test, driven through the real CLI, because a refusal that
exists in the source and not in the process is not a refusal.

A seventh followed later, from the same rule read the other way round. Help that
names what a flag costs is only honest if the cost is visible afterwards, and
`status` reported every other setting the run was pinned to except this one.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from helpers import BRIDGE, BridgeCase


def top_level_help():
    p = subprocess.run([sys.executable, str(BRIDGE), "--help"],
                       capture_output=True, text=True, timeout=60)
    return p.stdout


class TheSuperviseTargetIsHidden(unittest.TestCase):
    """1. `__supervise` is how this process re-execs itself. Listing it as a
    command invites calling it, and it is also what stops SKILL.md deferring to
    `--help` for the command list: a table that says "these are your commands"
    cannot be replaced by a listing that includes one that is not."""

    def test_the_listing_does_not_advertise_it(self):
        self.assertNotIn("__supervise", top_level_help())

    def test_it_still_runs_when_named(self):
        """Hidden, not removed — the supervisor spawns itself by that name."""
        p = subprocess.run([sys.executable, str(BRIDGE), "__supervise"],
                           capture_output=True, text=True, timeout=60)
        self.assertIn("--run-dir", p.stderr,
                      "`__supervise` stopped being reachable, which breaks "
                      "every run rather than only its documentation")


class BatchStartHasNoForegroundFlag(BridgeCase):
    """2. `--foreground` was accepted by the parser and then refused by the
    command, so its help string had to say "Refused on `batch start`" — an
    option surface documenting a hole in itself. Removing the argument makes the
    refusal argparse's, and the help honest by having nothing to say."""

    def test_the_flag_is_not_in_the_help(self):
        p = subprocess.run(
            [sys.executable, str(BRIDGE), "batch", "start", "--help"],
            capture_output=True, text=True, timeout=60)
        self.assertNotIn("--foreground", p.stdout)

    def test_passing_it_is_a_usage_error(self):
        p = self.bridge_raw("batch", "start", "--group", "g", "--task", "a",
                            "--foreground")
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertIn("unrecognized arguments", p.stderr)

    def test_start_still_takes_it(self):
        p = subprocess.run([sys.executable, str(BRIDGE), "start", "--help"],
                           capture_output=True, text=True, timeout=60)
        self.assertIn("--foreground", p.stdout)


class StatusRefusesSelectorsThatContradict(BridgeCase):
    """3. `status` took combinations where one selector silently won. A caller
    who passed both got an answer about something they did not ask about, and no
    help string can warn about that without describing a bug."""

    def setUp(self):
        super().setUp()
        # Real targets, because "no such run" also exits non-zero: a refusal
        # test against `--run x` passes whether or not the conflict is checked.
        self.bridge("batch", "start", "--group", "g", "--sandbox", "read-only",
                    "--task", "a")
        row = self.bridge("status", "--group", "g")["runs"][0]
        self.run_id, self.thread_id = row["run_id"], row["thread_id"]

    def refused(self, *args, naming):
        p = self.bridge_raw("status", *args)
        self.assertNotEqual(
            p.returncode, 0,
            f"`status {' '.join(args)}` was accepted: {p.stdout}")
        text = p.stdout + p.stderr
        for flag in naming:
            self.assertIn(
                flag, text,
                f"`status {' '.join(args)}` failed, but not for the reason "
                f"this test is about — the message does not mention {flag}:\n"
                f"{text}")

    def test_a_run_and_a_thread_cannot_both_be_named(self):
        self.refused("--run", self.run_id, "--thread", self.thread_id,
                     naming=("--run", "--thread"))

    def test_a_run_and_a_group_cannot_both_be_named(self):
        self.refused("--run", self.run_id, "--group", "g",
                     naming=("--run", "--group"))

    def test_a_thread_and_a_group_cannot_both_be_named(self):
        self.refused("--thread", self.thread_id, "--group", "g",
                     naming=("--thread", "--group"))

    def test_external_threads_cannot_be_asked_for_within_a_group(self):
        """`--include-external` lists threads with no registry entry; a group is
        a registry construct. The combination has no members by definition."""
        self.refused("--group", "g", "--include-external",
                     naming=("--include-external", "--group"))

    def test_follow_options_without_follow_are_refused(self):
        self.refused("--group", "g", "--follow-timeout", "2",
                     naming=("--follow-timeout", "--follow"))
        self.refused("--group", "g", "--follow-timeout", "5",
                     naming=("--follow-timeout", "--follow"))

    def test_each_selector_alone_still_works(self):
        for args in (("--run", self.run_id), ("--thread", self.thread_id),
                     ("--group", "g"), ("--include-external",)):
            with self.subTest(args=args):
                self.bridge("status", *args)


class ResumingAnUnknownThreadNeedsASandbox(BridgeCase):
    """4. `codex exec resume` has no `-s`, so this wrapper re-asserts the
    sandbox from what it recorded. A thread it never started has no record, and
    the fallback was `workspace-write` — a write policy invented for a thread
    whose own policy nobody knows. Now it is a refusal that names the flag."""

    def test_an_unregistered_thread_is_refused_without_a_sandbox(self):
        p = self.bridge_raw("resume", "019f0000-0000-7000-0000-0000000000ff",
                            "carry on")
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("--sandbox", p.stdout + p.stderr)

    def test_the_same_thread_is_accepted_with_one(self):
        out = self.bridge("resume", "--sandbox", "read-only",
                          "019f0000-0000-7000-0000-0000000000ff", "carry on")
        self.assertEqual(out["sandbox"], "read-only")

    def test_a_run_this_skill_started_still_needs_nothing(self):
        started = self.bridge("start", "--sandbox", "read-only", "hello")
        self.wait_terminal(started["run_id"])
        out = self.bridge("resume", started["run_id"], "again")
        self.assertEqual(out["sandbox"], "read-only",
                         "a resumed run stopped inheriting its thread's "
                         "recorded sandbox, which is the protection itself")


class ContradictoryPriorityFlagsAreRefused(BridgeCase):
    """5. `--priority` and `--no-priority` share a dest, so the last one on the
    line won silently. Whether a run pays for the priority tier is a cost the
    caller cannot see afterwards, and argparse's answer to "both" was a coin
    toss they were never told about."""

    def test_both_together_are_refused(self):
        p = self.bridge_raw("start", "--sandbox", "read-only",
                            "--priority", "--no-priority", "hi")
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("--no-priority", p.stdout + p.stderr)

    def test_either_alone_is_accepted(self):
        for flag in ("--priority", "--no-priority"):
            with self.subTest(flag=flag):
                self.bridge("start", "--sandbox", "read-only", flag, "hi")


class ProjectedCostStatesNoSampleStory(BridgeCase):
    """6. `projected_cost.note` carried "measured 6 under of 11" — a fact about
    eleven runs in one project on one afternoon, printed to every caller
    forever. What survives is what the number is: a median, so a scale."""

    def note(self):
        for _ in range(4):
            r = self.bridge("start", "--sandbox", "read-only", "warm")
            self.wait_terminal(r["run_id"])
        out = self.bridge("batch", "start", "--group", "g",
                          "--sandbox", "read-only", "--task", "a", "--task", "b")
        return (out.get("projected_cost") or {}).get("note") or ""

    def test_the_sample_narrative_is_gone(self):
        self.assertNotIn("of 11", self.note())

    def test_it_still_says_what_the_number_is(self):
        note = self.note()
        self.assertIn("median", note)
        self.assertRegex(note, r"scale, not a bound")


class StatusReportsTheTierTheRunIsPayingFor(BridgeCase):
    """7. `run_row` reported `sandbox`, `model`, `effort` and `isolated` and
    stopped one short of `priority`, so the one recorded setting that costs
    money was the one nothing read back. A caller could pass `--priority`, be
    charged the faster tier for every turn on that thread, and find no surface
    that would say so.

    The row is checked against the argv the fake `codex` was actually handed,
    not against `meta.json`, which is where the row reads from: a claim compared
    with its own source agrees with itself however wrong both are.
    """

    def setUp(self):
        super().setUp()
        self.argv_log = self.tmp / "argv.jsonl"
        self.env["FAKE_CODEX_ARGV_LOG"] = str(self.argv_log)

    def injected_tier(self):
        """Did the last invocation really carry the tier?

        The exact value, not a `service_tier=` prefix: the prefix is also what
        a typo'd tier looks like, and Codex answers one of those with a warning
        and the standard tier rather than an error.
        """
        lines = [json.loads(l) for l in
                 self.argv_log.read_text().splitlines() if l.strip()]
        return 'service_tier="priority"' in lines[-1]["argv"]

    def row(self, run_id):
        return self.bridge("status", "--run", run_id)["runs"][0]

    def test_a_run_on_the_faster_tier_says_so(self):
        r = self.bridge("start", "--sandbox", "read-only",
                        "--inherit-config", "--priority", "hi")
        self.wait_terminal(r["run_id"])
        self.assertTrue(self.injected_tier(),
                        "fixture check: this run was supposed to be pinned to "
                        "the tier and argv says it was not")
        self.assertIs(
            self.row(r["run_id"]).get("priority"), True,
            "the run was handed the faster tier and `status` does not report "
            "it, so the caller pays for it with no surface saying so")

    def test_a_run_that_opted_out_says_that_too(self):
        r = self.bridge("start", "--sandbox", "read-only", "--no-priority", "hi")
        self.wait_terminal(r["run_id"])
        self.assertFalse(self.injected_tier(),
                         "fixture check: --no-priority still injected the tier")
        self.assertIs(
            self.row(r["run_id"]).get("priority"), False,
            "`--no-priority` is a recorded choice a resume carries forward; a "
            "row that omits it cannot be told from one that never chose")


if __name__ == "__main__":
    unittest.main()
