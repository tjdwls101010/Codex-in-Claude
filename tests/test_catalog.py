"""The model catalog: read from `codex debug models`, trimmed to what a caller chooses from, used to refuse a model or effort before anything spawns — and never a reason a run cannot start.
"""

from __future__ import annotations

import json
import unittest

from support.harness import BridgeCase


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
        out = self.bridge("batch", "start", "--group", "g", "--tasks-file", tf,
                          env={"FAKE_CODEX_MODELS": "!garbage"})
        self.assertEqual(out["spawned"], 1)
        self.wait_all(out)


if __name__ == "__main__":
    unittest.main()
