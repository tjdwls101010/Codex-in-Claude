"""T1 — model and effort validation: the catalog lookup, and everything it must
never block.

`check_model_effort` refuses only a `--model`/`--effort` the caller just typed,
checked against a catalog fetched fresh from `codex debug models`. Two things
have to hold at once for that to be worth doing: the check has to be exact
per-model (fake-big takes `ultra`, fake-small does not — a static allowlist
gets this wrong), and it has to fail OPEN — the three ways the lookup itself
can break (empty stdout, non-zero exit, unparseable JSON) must leave `start`
exactly as capable as it was before this check existed.
"""

from __future__ import annotations

import json
import unittest

from helpers import BridgeTestCase


def started_run_dirs(project):
    runs = project / ".codex-runs"
    return [p for p in runs.iterdir() if p.is_dir()] if runs.is_dir() else []


class Models(BridgeTestCase):

    def test_prints_one_line_and_never_leaks_base_instructions(self):
        """The shim deliberately puts a 4096-char `base_instructions` in each
        model precisely so a passthrough of the raw catalog is caught here —
        `model_catalog` is supposed to whitelist fields, not forward `**m`."""
        p = self.bridge_raw("models")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 1,
                         f"expected exactly one line of JSON, got: {p.stdout!r}")
        self.assertNotIn("base_instructions", p.stdout)
        self.assertNotIn("x" * 500, p.stdout)
        self.assertNotIn("y" * 500, p.stdout)
        out = json.loads(lines[0])
        self.assertEqual({m["slug"] for m in out["models"]}, {"fake-big", "fake-small"})


class LookupFailuresFailOpen(BridgeTestCase):
    """FAKE_CODEX_MODELS = "", "!fail", "!garbage" are the three ways
    `codex debug models` can break, per the shim's own docstring. Each must
    leave `start` working: a validation that goes fail-closed on its own
    breakage is worse than no validation at all."""

    def start_despite_broken_catalog(self, **env):
        out = self.start("hello", env_extra=env)
        self.assertTrue((self.project / ".codex-runs" / out["run_id"]).is_dir(),
                        "start must still create a run when the catalog lookup "
                        "itself is broken")
        self.wait_for_state(out["run_id"])

    def test_empty_stdout(self):
        self.start_despite_broken_catalog(FAKE_CODEX_MODELS="")

    def test_nonzero_exit(self):
        self.start_despite_broken_catalog(FAKE_CODEX_MODELS="!fail")

    def test_unparseable_output(self):
        self.start_despite_broken_catalog(FAKE_CODEX_MODELS="!garbage")


class MalformedCatalogStillFailsOpen(BridgeTestCase):
    """Valid JSON of the wrong shape is a separate failure mode from the three
    above, and a worse one: those break the subprocess or the parse, while this
    one breaks the shaping loop after both have succeeded.

    Found by review, reproduced live. The `or []` guard only rescues a missing
    or null field — a truthy scalar passes straight through it into `for lv in
    5`, and the TypeError escaped `model_catalog` entirely to become
    `internal error` from the CLI's top-level handler, with no run spawned. A
    batch was worse still: one bad entry blocked every member.
    """

    def catalog_with(self, levels):
        return json.dumps({"models": [
            {"slug": "fake-big", "default_reasoning_level": "low",
             "supported_reasoning_levels": levels},
        ]})

    def assert_start_survives(self, levels):
        # `--model` is not decoration. The catalog is only consulted when the
        # caller named a model or an effort, so a bare `start` never reaches the
        # shaping loop and would pass this test with the bug fully present.
        out = self.start("hello", "--model", "fake-big", env_extra={
            "FAKE_CODEX_MODELS": self.catalog_with(levels)})
        self.assertTrue((self.project / ".codex-runs" / out["run_id"]).is_dir())
        self.wait_for_state(out["run_id"])

    def test_a_scalar_where_a_list_belongs(self):
        self.assert_start_survives(5)

    def test_a_string_degrades_to_no_efforts_rather_than_crashing(self):
        """Not a second copy of the case above — a string IS iterable, so it
        never raised. It yields characters, none of them dicts, so the model
        arrives with an empty effort list and `check_model_effort` has nothing
        to compare against. Asserted because "no efforts known" must read as
        "cannot check", never as "nothing is valid"."""
        out = self.bridge("models", env_extra={
            "FAKE_CODEX_MODELS": self.catalog_with("high")})
        self.assertEqual(out["models"][0]["efforts"], [])
        self.bridge("start", "--model", "fake-big", "--effort", "anything", "go",
                    env_extra={"FAKE_CODEX_MODELS": self.catalog_with("high")})

    def test_a_batch_is_not_blocked_by_one_malformed_entry(self):
        tf = self.tmp / "tasks.jsonl"
        tf.write_text(json.dumps({"prompt": "a", "model": "fake-big"}) + "\n")
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file",
                          str(tf),
                          env_extra={"FAKE_CODEX_MODELS": self.catalog_with(5)})
        self.assertEqual(len(out["runs"]), 1,
                         "one malformed catalog entry must not block the group")


class UnknownEffort(BridgeTestCase):

    def test_with_no_model_is_checked_against_the_union_of_every_model(self):
        out = self.bridge("start", "--effort", "bogus", "go", expect_rc=1)
        self.assertIn("bogus", out["error"])
        self.assertEqual(set(out["valid_efforts"]),
                         {"low", "medium", "high", "xhigh", "ultra"})
        self.assertEqual(started_run_dirs(self.project), [])

    def test_with_a_model_is_checked_against_that_models_own_list_only(self):
        out = self.bridge("start", "--model", "fake-small", "--effort",
                          "nonexistent", "go", expect_rc=1)
        self.assertIn("fake-small", out["error"])
        self.assertEqual(set(out["valid_efforts"]), {"low", "medium", "high"})


class UnknownModel(BridgeTestCase):

    def test_is_refused_and_lists_the_known_slugs(self):
        out = self.bridge("start", "--model", "no-such-model", "go", expect_rc=1)
        self.assertIn("no-such-model", out["error"])
        self.assertEqual(set(out["known_models"]), {"fake-big", "fake-small"})
        self.assertEqual(started_run_dirs(self.project), [])


class EffortValidityIsPerModel(BridgeTestCase):
    """The single most important case here: fake-big and fake-small do not
    agree on whether `ultra` is valid, which is exactly the case a static
    allowlist (one list, not keyed by model) gets wrong."""

    def test_ultra_is_accepted_for_fake_big_and_refused_for_fake_small(self):
        accepted = self.bridge("start", "--model", "fake-big", "--effort",
                               "ultra", "go")
        self.wait_for_state(accepted["run_id"])
        before = {p.name for p in started_run_dirs(self.project)}

        out = self.bridge("start", "--model", "fake-small", "--effort", "ultra",
                          "go", expect_rc=1)
        self.assertIn("fake-small", out["error"])
        self.assertIn("ultra", out["error"])
        self.assertNotIn("ultra", out["valid_efforts"])

        after = {p.name for p in started_run_dirs(self.project)}
        self.assertEqual(before, after,
                         "the refused call must not have claimed a run directory")


class ResumeDoesNotRecheckInheritedSettings(BridgeTestCase):
    """B3: a resumed run must never silently change its sandbox — or its
    effort. `check_model_effort` only ever looks at what THIS call passed, so
    a model retired or an effort dropped upstream between turns must not turn
    every resume of an existing thread into a refusal."""

    def test_survives_a_catalog_that_no_longer_offers_the_recorded_effort(self):
        first = self.bridge("start", "--model", "fake-big", "--effort", "low", "seed")
        self.wait_for_state(first["run_id"])

        shrunk_catalog = json.dumps({"models": [
            {"slug": "fake-big", "display_name": "Fake Big",
             "default_reasoning_level": "medium",
             "supported_reasoning_levels": [{"effort": "medium"}, {"effort": "high"}]},
        ]})
        out = self.bridge("resume", first["run_id"], "continue",
                          env_extra={"FAKE_CODEX_MODELS": shrunk_catalog})
        self.wait_for_state(out["run_id"])

        st = self.bridge("status", "--run", out["run_id"])
        self.assertEqual(st["runs"][0]["effort"], "low",
                         "the recorded effort carries over unchanged; it was "
                         "never re-checked against the shrunk catalog")


class BatchValidatesBeforeSpawning(BridgeTestCase):

    def write_tasks(self, *objs):
        f = self.tmp / "tasks.jsonl"
        f.write_text("\n".join(json.dumps(o) for o in objs) + "\n")
        return str(f)

    def test_a_bad_effort_in_one_task_spawns_zero_runs(self):
        tf = self.write_tasks({"prompt": "a"}, {"prompt": "b", "effort": "bogus"})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf,
                          expect_rc=1)
        self.assertIn("task 2", out["error"])
        self.assertEqual(started_run_dirs(self.project), [],
                         "one bad task must cost zero spawned runs")


class DoctorReportsModelCatalogHealth(BridgeTestCase):

    def test_a_count_when_the_catalog_reads_fine(self):
        rep = self.bridge("doctor")
        self.assertEqual(rep["models_catalog"], 2)

    def test_null_with_a_warning_when_the_lookup_fails(self):
        rep = self.bridge("doctor", env_extra={"FAKE_CODEX_MODELS": "!fail"})
        self.assertIsNone(rep["models_catalog"])
        self.assertTrue(any("codex debug models" in w for w in rep["warnings"]))


if __name__ == "__main__":
    unittest.main()
