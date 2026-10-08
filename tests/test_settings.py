"""`codex.runs.settings_for`: one precedence for every setting — the flag, then what the continued thread recorded, then the user's config.toml (isolated runs only), then nothing. The sandbox is never taken from the config."""

from __future__ import annotations

import unittest

from support.harness import engine

runs = engine("codex.runs")

USER = {"model": "cfg-model", "effort": "cfg-effort", "service_tier": "fast"}
THREAD = {"isolated": True, "sandbox": "read-only", "model": "old-model", "effort": "low",
          "service_tier": "priority", "cwd": "/thread/dir"}


def resolve(**kw):
    return runs.settings_for(**kw)


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
        r = resolve(model="m", effort="e", sandbox="danger-full-access", user=USER)
        self.assertEqual((r["model"], r["effort"], r["service_tier"], r["sandbox"]), ("m", "e", "fast", "danger-full-access"))
        self.assertEqual((r["adopted"]["model_source"], r["adopted"]["effort_source"]), (None, None))

    def test_a_thread_that_loads_the_config_takes_nothing_from_it(self):
        r = resolve(base={**THREAD, "isolated": False, "model": None, "effort": None, "service_tier": None}, user=USER)
        self.assertEqual((r["isolated"], r["model"], r["effort"], r["service_tier"]), (False, None, None, None),
                         "Codex reads config.toml itself")
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

    def test_a_flag_still_beats_the_record(self):
        r = resolve(base=THREAD, sandbox="workspace-write", model="new", user=USER)
        self.assertEqual((r["sandbox"], r["model"], r["effort"], r["service_tier"]), ("workspace-write", "new", "low", "priority"))
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


class ReadOnlyMarker(unittest.TestCase):
    """Which read-only a run gets. `scratch` writes TMPDIR and ~/.cache, so tests and builds run; `strict` is the legacy sandbox, which cannot write even a temporary file. A run takes up scratch only when it is new or names --sandbox read-only, and only isolated; a thread that recorded scratch keeps it; any other read-only thread keeps the strict sandbox it recorded, so no thread's permissions widen without being asked. `read_only_blocker` is why this install or directory cannot use scratch, and it becomes the note."""

    LEGACY = {**THREAD}  # read-only, isolated, no marker: recorded before scratch existed

    def marker(self, **kw):
        r = resolve(**kw)
        return r["read_only"], r["read_only_note"]

    def test_a_new_read_only_run_takes_scratch(self):
        self.assertEqual(self.marker(sandbox="read-only"), ("scratch", None))

    def test_a_blocker_makes_it_strict_and_says_why(self):
        self.assertEqual(self.marker(sandbox="read-only", read_only_blocker="why not"), ("strict", "why not"))

    def test_a_writing_sandbox_has_no_marker(self):
        for kw in ({}, {"sandbox": "danger-full-access"}, {"base": {**THREAD, "read_only": "scratch"}, "sandbox": "workspace-write"}):
            with self.subTest(kw=kw):
                self.assertEqual(self.marker(**kw), (None, None))

    def test_a_thread_that_recorded_scratch_keeps_it(self):
        self.assertEqual(self.marker(base={**THREAD, "read_only": "scratch"}), ("scratch", None))
        self.assertEqual(self.marker(base={**THREAD, "read_only": "scratch"}, read_only_blocker="old codex"),
                         ("strict", "old codex"))

    def test_an_older_or_strict_thread_stays_strict_unless_asked(self):
        for base in (self.LEGACY, {**THREAD, "read_only": "strict"}):
            with self.subTest(base=base.get("read_only")):
                marker, note = self.marker(base=base)
                self.assertEqual(marker, "strict")
                self.assertTrue(note)
                self.assertEqual(self.marker(base=base, sandbox="read-only"), ("scratch", None))

    def test_a_thread_that_loads_the_users_config_stays_strict_even_when_asked(self):
        base = {**THREAD, "isolated": False}
        for kw in ({}, {"sandbox": "read-only"}):
            with self.subTest(kw=kw):
                marker, note = self.marker(base=base, **kw)
                self.assertEqual(marker, "strict")
                self.assertTrue(note)

if __name__ == "__main__":
    unittest.main()
