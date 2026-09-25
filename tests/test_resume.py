"""Resuming a thread: its settings stay what they were, it is found by the ref the caller has, and it gets one turn at a time.

`codex exec resume` has no `-s` and inherits no per-invocation setting from the thread, so a turn that does not re-assert the recorded sandbox, model and effort drifts to whatever config layer is in effect. The registry is where those settings live.
"""

from __future__ import annotations

import json
import os
import signal
import unittest

from support.harness import BridgeCase, LEGACY_PREDECESSOR, LEGACY_REVIEW, alive, wait_until


class ResumeCase(BridgeCase):

    def first_then_resume(self, start_args=(), resume_args=(), ref_key="run_id"):
        first = self.bridge("start", *start_args, "first turn")
        self.wait_state(first["run_id"])
        second = self.bridge("resume", first[ref_key], *resume_args, "second turn")
        self.wait_state(second["run_id"])
        return first, second, self.runs_invoked()[-1]


class SettingsAreReasserted(ResumeCase):

    def test_every_recorded_setting_reaches_the_resumed_turn(self):
        first, second, rec = self.first_then_resume(
            ("--sandbox", "read-only", "--model", "fake-big", "--effort", "low", "--no-priority"))
        argv = rec["argv"]
        self.assertEqual(argv[:3], ["exec", "resume", first["thread_id"]])
        self.assertEqual(self.config_values(argv),
                         {"sandbox_mode": '"read-only"', "model_reasoning_effort": '"low"'})
        self.assertEqual(argv[argv.index("-m") + 1], "fake-big")
        self.assertIn("--ignore-user-config", argv)
        for flag in ("-s", "--sandbox", "-C", "--cd", "--add-dir"):
            self.assertNotIn(flag, argv)
        self.assertEqual(second["thread_id"], first["thread_id"])
        self.assertNotEqual(second["run_id"], first["run_id"])
        self.assertEqual(self.row(second["run_id"])["parent_run_id"], first["run_id"])

    def test_the_resumed_turn_runs_in_the_threads_directory(self):
        sub = self.project / "nested"
        sub.mkdir()
        _first, _second, rec = self.first_then_resume(("--cwd", sub))
        self.assertEqual(rec["cwd"], str(sub))

    def test_changing_the_sandbox_is_explicit_and_recorded(self):
        _first, second, rec = self.first_then_resume(("--sandbox", "read-only"), ("--sandbox", "workspace-write"))
        self.assertEqual(self.config_values(rec["argv"])["sandbox_mode"], '"workspace-write"')
        self.assertEqual(second["sandbox_changed_from"], "read-only")
        row = self.row(second["run_id"])
        self.assertEqual((row["sandbox"], row["sandbox_changed_from"]), ("workspace-write", "read-only"))

    def test_options_between_the_ref_and_the_prompt_keep_the_prompt(self):
        first = self.bridge("start", "x")
        self.wait_state(first["run_id"])
        out = self.bridge("resume", first["run_id"], "--label", "again", "the prompt")
        self.wait_state(out["run_id"])
        self.assertTrue(self.last_argv()[-1].endswith("the prompt"))


class UserDefaultsAndTheirPrecedence(ResumeCase):
    """An explicit flag, then what a resumed thread recorded, then the user's config.toml, then nothing — and the sandbox is never read from the config."""

    CONFIG = 'model = "fake-big"\nmodel_reasoning_effort = "high"\nservice_tier = "fast"\n'

    def config(self, body):
        (self.codex_home / "config.toml").write_text(body)

    def started_argv(self, *args):
        out = self.bridge("start", *args, "x")
        self.wait_state(out["run_id"])
        return self.last_argv()

    def test_a_fresh_isolated_run_takes_the_three_keys_from_the_config(self):
        self.config(self.CONFIG)
        argv = self.started_argv()
        self.assertEqual(argv[argv.index("-m") + 1], "fake-big")
        cfg = self.config_values(argv)
        self.assertEqual((cfg["model_reasoning_effort"], cfg["service_tier"]), ('"high"', '"fast"'))

    def test_a_flag_beats_the_config(self):
        self.config(self.CONFIG)
        argv = self.started_argv("--model", "fake-small", "--effort", "medium", "--no-priority")
        self.assertEqual(argv[argv.index("-m") + 1], "fake-small")
        self.assertEqual(self.config_values(argv), {"sandbox_mode": '"workspace-write"',
                                                    "model_reasoning_effort": '"medium"'})

    def test_the_sandbox_is_never_taken_from_the_config(self):
        self.config('sandbox_mode = "danger-full-access"\n')
        self.assertEqual(self.config_values(self.started_argv("--sandbox", "read-only"))["sandbox_mode"],
                         '"read-only"')
        self.assertEqual(self.config_values(self.started_argv())["sandbox_mode"], '"workspace-write"')

    def test_a_table_below_the_top_level_is_not_the_top_level(self):
        self.config('[profiles.work]\nmodel = "fake-small"\n')
        self.assertNotIn("-m", self.started_argv())

    def test_inheriting_the_config_does_not_restate_it(self):
        self.config(self.CONFIG)
        argv = self.started_argv("--inherit-config")
        self.assertNotIn("--ignore-user-config", argv)
        self.assertNotIn("-m", argv)
        self.assertEqual(self.config_values(argv), {"sandbox_mode": '"workspace-write"'})

    def test_no_config_pins_nothing(self):
        argv = self.started_argv()
        self.assertNotIn("-m", argv)
        self.assertEqual(self.config_values(argv), {"sandbox_mode": '"workspace-write"'})

    def test_a_resume_keeps_what_the_thread_recorded_not_what_the_config_says_now(self):
        self.config(self.CONFIG)
        first = self.bridge("start", "x")
        self.wait_state(first["run_id"])
        self.config('model = "fake-small"\nmodel_reasoning_effort = "low"\n')
        out = self.bridge("resume", first["run_id"], "y")
        self.wait_state(out["run_id"])
        argv = self.last_argv()
        self.assertEqual(argv[argv.index("-m") + 1], "fake-big")
        self.assertEqual(self.config_values(argv)["model_reasoning_effort"], '"high"')

    def test_a_recorded_no_tier_stays_no_tier(self):
        self.config(self.CONFIG)
        _f, _s, rec = self.first_then_resume(("--no-priority",))
        self.assertNotIn("service_tier", self.config_values(rec["argv"]))

    def test_a_thread_from_an_older_release_keeps_its_boolean_tier(self):
        self.install_legacy_registry()
        for ref in (LEGACY_PREDECESSOR, LEGACY_REVIEW):
            with self.subTest(ref=ref):
                self.bridge("stop", "--all")
                out = self.bridge("resume", ref, "--force", "again")
                self.wait_state(out["run_id"])
                argv = self.last_argv()
                self.assertEqual(self.config_values(argv)["service_tier"], '"priority"')
                self.assertEqual(argv[argv.index("-m") + 1], "gpt-5.6-sol",
                                 "a recorded model is not re-checked against today's catalog")


class FindingTheThread(ResumeCase):

    def test_a_thread_id_resolves_to_the_run_that_recorded_it(self):
        first, second, rec = self.first_then_resume(ref_key="thread_id")
        self.assertEqual(rec["argv"][2], first["thread_id"])
        self.assertEqual(self.row(second["run_id"])["parent_run_id"], first["run_id"])

    def test_last_picks_the_one_live_run(self):
        done = self.bridge("start", "done")
        self.wait_state(done["run_id"])
        live, _m = self.running("live")
        out = self.bridge("resume", "--last", "--force", "go on")
        self.assertEqual(out["resolved_from_run_id"], live["run_id"])
        self.bridge("stop", "--all")

    def test_last_with_nothing_live_takes_the_newest_and_says_so(self):
        for p in ("a", "b"):
            self.wait_state(self.bridge("start", "--label", p, p)["run_id"])
        newest = self.bridge("status", "--all")["runs"][-1]
        out = self.bridge("resume", "--last", "go on")
        self.wait_state(out["run_id"])
        self.assertEqual(out["resolved_from_run_id"], newest["run_id"])
        self.assertIn("newest", out["resolved_from"])
        self.assertEqual(out["label"], newest["label"])

    def test_last_with_two_live_runs_is_refused_with_the_candidates(self):
        a, _ = self.running("a")
        b, _ = self.running("b")
        refused = self.bridge("resume", "--last", "go on", rc=1)
        self.assertEqual({c["run_id"] for c in refused["candidates"]}, {a["run_id"], b["run_id"]})

    def test_a_run_that_never_recorded_a_thread_cannot_be_resumed(self):
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": os.devnull, "FAKE_CODEX_EXIT": 1})
        self.wait_state(out["run_id"])
        self.assertIsNone(self.row(out["run_id"])["thread_id"])
        self.assertIn("thread id", self.bridge("resume", out["run_id"], "again", rc=1)["error"])

    def test_too_many_positionals_are_refused(self):
        self.assertIn("too many", self.bridge("resume", "a", "b", "c", rc=1)["error"])


class ThreadsTheRegistryNeverSaw(ResumeCase):
    """A thread started outside this skill has no recorded sandbox, so the caller has to name one."""

    def test_an_unknown_ref_is_passed_through_under_the_named_sandbox(self):
        out = self.bridge("resume", "--sandbox", "read-only", "some-thread", "go")
        self.wait_state(out["run_id"])
        argv = self.last_argv()
        self.assertEqual(argv[:3], ["exec", "resume", "some-thread"])
        self.assertEqual(self.config_values(argv)["sandbox_mode"], '"read-only"')
        self.assertEqual(self.meta(out["run_id"])["resume_ref"], "some-thread")

    def test_without_a_sandbox_it_is_refused_before_anything_is_claimed(self):
        refused = self.bridge("resume", "some-thread", "go", rc=1)
        self.assertIn("--sandbox", refused["error"])
        self.assertEqual(self.run_dirs(), [])


class OneTurnPerThread(ResumeCase):
    """Two turns on one thread append to one rollout file. The check and the new run's publication share one per-thread lock, so a race has exactly one winner."""

    def race(self, *args, n=2):
        # The winner's turn has to outlast the race, or a loser scheduled late finds the thread free again.
        procs = [self.spawn("resume", *args, env={"FAKE_CODEX_HANG": 30}) for _ in range(n)]
        outs = [p.communicate(timeout=60)[0] for p in procs]
        results = [(p.returncode, out) for p, out in zip(procs, outs)]
        codes = sorted(rc for rc, _ in results)
        self.assertEqual(codes, [0] + [1] * (n - 1), results)
        for rc, out in results:
            if rc == 1:
                self.assertIn("live turn", out)
        return results

    def test_simultaneous_resumes_of_a_known_thread_have_one_winner(self):
        first = self.bridge("start", "seed")
        self.wait_state(first["run_id"])
        results = self.race(first["run_id"], "next", n=3)
        runs = self.bridge("status", "--thread", first["thread_id"])["runs"]
        self.assertEqual(len(runs), 2, "the seed and exactly one winner")
        winner = next(json.loads(out)["run_id"] for rc, out in results if rc == 0)
        # A resume's handle comes back before its supervisor has launched codex.
        self.wait_state(winner, ("running",))
        self.assertEqual(len([r for r in self.runs_invoked() if r["argv"][1] == "resume"]), 1)

    def test_simultaneous_resumes_of_an_unknown_ref_have_one_winner(self):
        self.race("019fc000-0000-7000-8000-000000000abc", "--sandbox", "read-only", "go")

    def test_force_lets_a_second_turn_through(self):
        first = self.bridge("start", "seed")
        self.wait_state(first["run_id"])
        a = self.bridge("resume", first["run_id"], "one", env={"FAKE_CODEX_HANG": 30})
        self.assertIn("live turn", self.bridge("resume", first["run_id"], "two", rc=1)["error"])
        b = self.bridge("resume", first["run_id"], "--force", "two")
        self.assertNotEqual(a["run_id"], b["run_id"])

    def test_an_orphan_whose_codex_still_writes_holds_the_thread(self):
        out, m = self.orphan_still_writing("x")
        refused = self.bridge("resume", out["thread_id"], "second", rc=1)
        self.assertIn(out["run_id"], str(refused["live_runs"]))
        os.kill(int(m["codex_pid"]), signal.SIGKILL)
        wait_until(lambda: not alive(m["codex_pid"]), timeout=10)
        self.wait_state(self.bridge("resume", out["thread_id"], "second")["run_id"])

    def test_an_unreadable_run_blocks_only_its_own_thread(self):
        mine = self.bridge("start", "mine")
        other = self.bridge("start", "other")
        for r in (mine, other):
            self.wait_state(r["run_id"])
        (self.runs_dir / other["run_id"] / "meta.json").write_text("{ truncated")
        self.wait_state(self.bridge("resume", mine["run_id"], "fine")["run_id"])

        (self.runs_dir / mine["run_id"] / "meta.json").write_text("{ truncated")
        clone = self.bridge("start", "clone", env={"FAKE_CODEX_THREAD_ID": mine["thread_id"]})
        self.wait_state(clone["run_id"])
        refused = self.bridge("resume", clone["run_id"], "blocked", rc=1)
        self.assertIn(mine["run_id"], str(refused["unreadable_runs"]))
        self.wait_state(self.bridge("resume", clone["run_id"], "--force", "forced")["run_id"])


if __name__ == "__main__":
    unittest.main()
