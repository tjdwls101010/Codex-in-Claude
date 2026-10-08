"""The model catalog: read from `codex debug models`, trimmed to what a caller chooses from, used to refuse a model or effort before anything spawns — and never a reason a run cannot start.
"""

from __future__ import annotations

import json
import unittest

from support.harness import BridgeCase, LEGACY_INHERITED, engine


class Models(BridgeCase):

    def test_each_model_carries_its_own_efforts_and_nothing_bulky(self):
        p = self.bridge_raw("models")
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("base_instructions", p.stdout)
        models = {m["slug"]: m for m in json.loads(p.stdout)["models"]}
        self.assertEqual(models["fake-small"]["efforts"], ["low", "medium", "high"])
        self.assertEqual(models["fake-big"]["default_effort"], "low")

    def test_an_unreadable_catalog_is_an_error_with_exit_1(self):
        out = self.bridge("models", rc=1, env={"FAKE_CODEX_MODELS": "!fail"})
        self.assertIsNone(out["models"])


class ChecksBeforeSpawning(BridgeCase):

    def test_an_unknown_model_or_effort_is_refused_and_costs_nothing(self):
        for args, message in ((("--model", "gpt-nope"), "unknown model"),
                              (("--model", "fake-small", "--effort", "ultra"), "does not accept effort"),
                              (("--effort", "maximal"), "unknown effort")):
            with self.subTest(args=args):
                # A value the command line names is the command line's to change: exit 2.
                self.assertIn(message, self.bridge("start", *args, "x", rc=2)["error"])
        self.assertEqual(self.run_dirs(), [])

    def test_a_refused_value_says_it_came_from_the_config(self):
        # The command line was right and the config is what must change, so these stay 1.
        (self.codex_home / "config.toml").write_text('model = "retired-model"\n')
        refused = self.bridge("start", "x", rc=1)
        self.assertIn("retired-model", refused["error"])
        self.assertIn("config.toml", refused["error"])
        (self.codex_home / "config.toml").write_text('model_reasoning_effort = "ultra"\n')
        refused = self.bridge("start", "--model", "fake-small", "x", rc=1)
        self.assertIn("(from config.toml)", refused["error"])
        self.assertNotIn("'fake-small' (from", refused["error"], "the flag's value is not blamed on the config")

    def test_an_effort_valid_for_its_model_passes(self):
        out = self.bridge("start", "--model", "fake-big", "--effort", "ultra", "x")
        self.wait_state(out["run_id"])


class ABrokenLookupNeverBlocksARun(BridgeCase):

    def test_each_way_the_lookup_can_fail(self):
        broken = ("", "!fail", "!garbage",
                  json.dumps({"models": [{"slug": "fake-big", "supported_reasoning_levels": 5}]}),
                  json.dumps({"models": "not a list"}))
        for catalog in broken:
            with self.subTest(catalog=catalog):
                out = self.bridge("start", "--model", "fake-big", "--effort", "anything", "x",
                                  env={"FAKE_CODEX_MODELS": catalog})
                self.assertEqual(self.wait_state(out["run_id"])["state"], "completed")

    def test_a_batch_is_not_blocked_either(self):
        tf = self.tasks_file({"prompt": "a", "model": "fake-big"})
        out = self.bridge("batch", "--group", "g", "--tasks-file", tf,
                          env={"FAKE_CODEX_MODELS": "!garbage"})
        self.assertEqual(out["spawned"], 1)
        self.wait_all(out)


class VersionFloors(unittest.TestCase):
    """`codex.codex_cli.support_for`: what a `codex --version` line says this install can do. 0.122.0 is the first release with `--ignore-user-config`, which every isolated run passes; 0.160.0 is the first on which the read-only profile was measured to reach both `exec` and `exec resume`. A version that cannot be read is no reason to refuse a run, and no promise that the profile works."""

    def support(self, text):
        out = engine("codex.codex_cli").support_for(text)
        return out["version"], out["isolation"], out["profile"]

    def test_each_side_of_each_floor(self):
        cases = [("codex-cli 0.121.9", ("0.121.9", False, False)),
                 ("codex-cli 0.122.0", ("0.122.0", True, False)),
                 ("codex-cli 0.159.4", ("0.159.4", True, False)),
                 ("codex-cli 0.160.0", ("0.160.0", True, True)),
                 ("codex-cli 0.161.2", ("0.161.2", True, True)),
                 ("codex-cli 1.0.0", ("1.0.0", True, True))]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.support(text), expected)

    def test_a_pre_release_is_below_its_release(self):
        self.assertEqual(self.support("codex-cli 0.160.0-alpha.3"), ("0.160.0-alpha.3", True, False))
        self.assertEqual(self.support("codex-cli 0.122.0-alpha.1"), ("0.122.0-alpha.1", False, False))

    def test_a_version_that_cannot_be_read_is_unknown(self):
        for text in (None, "", "codex-cli", "not a version"):
            with self.subTest(text=text):
                self.assertEqual(self.support(text), (None, None, False))


class BelowTheIsolationFloor(BridgeCase):
    """Every isolated run passes `--ignore-user-config`; a Codex without it fails the run after it was reported started, so the run is refused before anything is claimed."""

    OLD = {"FAKE_CODEX_VERSION": "codex-cli 0.121.0"}

    def test_start_and_batch_are_refused_and_cost_nothing(self):
        for args in (("start", "x"), ("batch", "--group", "g", "--task", "x")):
            with self.subTest(args=args):
                refused = self.bridge(*args, rc=1, env=self.OLD)
                self.assertEqual((refused["codex_version"], refused["required_version"]), ("0.121.0", "0.122.0"))
                self.assertEqual(self.run_dirs(), [])
        self.assertEqual(self.bridge("status")["groups"], [])

    def test_a_thread_that_loads_the_users_config_does_not_need_it(self):
        self.install_legacy_registry()
        out = self.bridge("resume", LEGACY_INHERITED, "again", env=self.OLD)
        self.wait_state(out["run_id"])
        self.assertNotIn("--ignore-user-config", self.last_argv())

    def test_an_unreadable_version_is_not_refused(self):
        self.wait_state(self.bridge("start", "x", env={"FAKE_CODEX_VERSION": ""})["run_id"])


if __name__ == "__main__":
    unittest.main()
