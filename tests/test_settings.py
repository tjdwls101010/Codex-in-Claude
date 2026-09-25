"""`core.settings.resolve`: one precedence for every setting — the flag, then what the continued thread recorded (while isolation is unchanged), then the user's config.toml (isolated runs only), then nothing. The sandbox is never taken from the config."""

from __future__ import annotations

import unittest

from support.harness import engine

settings = engine("core.settings")

USER = {"model": "cfg-model", "effort": "cfg-effort", "service_tier": "fast"}
THREAD = {"isolated": True, "sandbox": "read-only", "model": "old-model", "effort": "low",
          "service_tier": "priority", "cwd": "/thread/dir"}


def resolve(**kw):
    return settings.resolve(**kw)


class Precedence(unittest.TestCase):

    def test_a_fresh_run_with_nothing_configured_pins_nothing(self):
        r = resolve()
        self.assertEqual((r["isolated"], r["sandbox"], r["model"], r["effort"], r["service_tier"], r["cwd"]),
                         (True, "workspace-write", None, None, None, None))

    def test_a_fresh_isolated_run_takes_the_config(self):
        r = resolve(user=USER)
        self.assertEqual((r["model"], r["effort"], r["service_tier"]), ("cfg-model", "cfg-effort", "fast"))
        self.assertEqual(r["adopted"], {"model": "cfg-model", "effort": "cfg-effort",
                                        "model_source": "config.toml", "effort_source": "config.toml"})

    def test_flags_beat_the_config_and_are_not_blamed_on_it(self):
        r = resolve(model="m", effort="e", priority=False, sandbox="danger-full-access", user=USER)
        self.assertEqual((r["model"], r["effort"], r["service_tier"], r["sandbox"]), ("m", "e", None, "danger-full-access"))
        self.assertEqual((r["adopted"]["model_source"], r["adopted"]["effort_source"]), (None, None))

    def test_inheriting_the_config_means_codex_reads_it_itself(self):
        r = resolve(inherit_config=True, user=USER)
        self.assertEqual((r["isolated"], r["model"], r["effort"], r["service_tier"]), (False, None, None, None))
        self.assertEqual(r["adopted"]["model"], None)

    def test_a_resume_keeps_the_threads_record_over_the_config(self):
        r = resolve(base=THREAD, user=USER)
        self.assertEqual((r["sandbox"], r["model"], r["effort"], r["service_tier"], r["cwd"]),
                         ("read-only", "old-model", "low", "priority", "/thread/dir"))
        self.assertEqual((r["adopted"]["model"], r["adopted"]["effort"]), (None, None),
                         "nothing inherited is re-checked against today's catalog")

    def test_an_empty_record_is_a_record(self):
        r = resolve(base={**THREAD, "model": None, "effort": None, "service_tier": None}, user=USER)
        self.assertEqual((r["model"], r["effort"], r["service_tier"]), (None, None, None))

    def test_changing_isolation_on_resume_drops_the_record(self):
        r = resolve(base=THREAD, inherit_config=True, user=USER)
        self.assertEqual((r["isolated"], r["model"], r["effort"]), (False, None, None))
        self.assertEqual(r["sandbox"], "read-only", "the sandbox is re-asserted whatever else changes")

    def test_a_flag_still_beats_the_record(self):
        r = resolve(base=THREAD, sandbox="workspace-write", model="new", priority=False, user=USER)
        self.assertEqual((r["sandbox"], r["model"], r["effort"], r["service_tier"]), ("workspace-write", "new", "low", None))
        self.assertEqual((r["adopted"]["model"], r["adopted"]["effort"]), ("new", None))

    def test_an_older_threads_boolean_tier(self):
        legacy = {k: v for k, v in THREAD.items() if k != "service_tier"}
        self.assertEqual(resolve(base={**legacy, "priority": True})["service_tier"], "priority")
        self.assertIsNone(resolve(base={**legacy, "priority": False})["service_tier"])
        self.assertIsNone(resolve(base={**THREAD, "service_tier": None, "priority": True})["service_tier"],
                          "a present service_tier, even None, is a choice")

    def test_priority_true_forces_the_tier(self):
        self.assertEqual(resolve(priority=True)["service_tier"], "priority")

    def test_the_sandbox_is_never_the_configs(self):
        self.assertEqual(resolve(user={**USER, "sandbox_mode": "danger-full-access"})["sandbox"], "workspace-write")

    def test_a_record_without_isolation_counts_as_isolated(self):
        r = resolve(base={"sandbox": "read-only", "model": "m"}, user=USER)
        self.assertEqual((r["isolated"], r["model"]), (True, "m"))


if __name__ == "__main__":
    unittest.main()
