"""T1 — argv composition, and the sandbox-drift regression.

The most important test in the suite is `test_resume_reasserts_recorded_sandbox`.
Everything else here guards the two invariants that make it hold by
construction: sandbox always travels as `-c sandbox_mode=`, and the working
directory is never passed with `-C`.
"""

import json
import unittest

from helpers import BridgeTestCase   # puts the scripts dir on sys.path

import _codex                        # noqa: E402
import _util                         # noqa: E402


class ArgvComposition(BridgeTestCase):

    def test_start_defaults(self):
        r = self.start("hello")
        self.wait_for_state(r["run_id"])
        argv = self.last_argv()
        self.assertEqual(argv[0], "exec")
        self.assertIn("--json", argv)
        self.assertIn("--ignore-user-config", argv, "isolated is the default (D2)")
        self.assertIn('sandbox_mode="workspace-write"', argv, "D3 default sandbox")
        self.assertIn('service_tier="priority"', argv, "D18: re-injected under isolation")
        self.assertNoFlag(argv, "-s", "--sandbox", "-C", "--cd")

    def test_no_model_or_effort_pinned_by_default(self):
        """D19 — inherit Codex's own defaults so the skill does not go stale."""
        r = self.start("hello")
        self.wait_for_state(r["run_id"])
        argv = self.last_argv()
        self.assertNoFlag(argv, "-m", "--model")
        self.assertFalse([a for a in argv if a.startswith("model_reasoning_effort=")],
                         f"effort must not be pinned by default; argv={argv}")

    def test_inherit_config_drops_isolation_and_priority(self):
        r = self.start("hello", "--inherit-config")
        self.wait_for_state(r["run_id"])
        argv = self.last_argv()
        self.assertNotIn("--ignore-user-config", argv)
        self.assertFalse([a for a in argv if a.startswith("service_tier=")],
                         "priority is only re-injected to undo what isolation removed")

    def test_priority_can_be_forced_off_and_on(self):
        r = self.start("a", "--no-priority")
        self.wait_for_state(r["run_id"])
        self.assertFalse([a for a in self.last_argv() if a.startswith("service_tier=")])
        r = self.start("b", "--inherit-config", "--priority")
        self.wait_for_state(r["run_id"])
        self.assertIn('service_tier="priority"', self.last_argv())

    def test_all_sandbox_modes_emit_as_config(self):
        for mode in ("read-only", "workspace-write", "danger-full-access"):
            with self.subTest(mode=mode):
                r = self.start(f"x {mode}", "--sandbox", mode)
                self.wait_for_state(r["run_id"])
                argv = self.last_argv()
                self.assertIn(f'sandbox_mode="{mode}"', argv)
                self.assertNoFlag(argv, "-s", "--sandbox")

    def test_model_effort_schema_image_adddir(self):
        schema = self.tmp / "s.json"
        schema.write_text(json.dumps({"type": "object"}))
        img = self.tmp / "shot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        extra = self.tmp / "extra"
        extra.mkdir()
        r = self.start("x", "--model", "gpt-5.6-sol", "--effort", "high",
                       "--schema", str(schema), "--image", str(img),
                       "--add-dir", str(extra), "--config", "foo.bar=1")
        self.wait_for_state(r["run_id"])
        argv = self.last_argv()
        self.assertFlagPair(argv, "-m", "gpt-5.6-sol")
        self.assertIn('model_reasoning_effort="high"', argv)
        self.assertFlagPair(argv, "--output-schema", str(schema))
        self.assertFlagPair(argv, "-i", str(img))
        self.assertFlagPair(argv, "--add-dir", str(extra))
        self.assertIn("foo.bar=1", argv, "raw --config passthrough must not be re-quoted")

    def test_cwd_is_set_on_the_child_never_via_dash_C(self):
        """Invariant 2: -C does not exist on resume or review, so it is never used."""
        sub = self.project / "nested"
        sub.mkdir()
        r = self.start("x", "--cwd", str(sub))
        self.wait_for_state(r["run_id"])
        rec = self.argv_records()[-1]
        self.assertNoFlag(rec["argv"], "-C", "--cd")
        self.assertEqual(str(_util.nfc(rec["cwd"])),
                         str(_util.nfc(str(sub.resolve()))),
                         "the child process must actually run in the requested cwd")

    def test_prompt_is_last_and_carries_the_preamble(self):
        r = self.start("summarise the repo")
        self.wait_for_state(r["run_id"])
        argv = self.last_argv()
        self.assertIn("summarise the repo", argv[-1])
        self.assertIn("single non-interactive", argv[-1],
                      "B19 situational preamble is on by default")

    def test_prompt_is_separated_by_a_double_dash(self):
        """`codex exec`'s `-i/--image <FILE>...` takes MULTIPLE values and
        greedily eats the next positional, so without `--` the prompt becomes a
        second image path and Codex exits having read nothing. A prompt starting
        with `-` is rejected outright for the same lack of a terminator."""
        r = self.start("summarise")
        self.wait_for_state(r["run_id"])
        argv = self.last_argv()
        self.assertEqual(argv[-2], "--", f"prompt must be preceded by `--`; got {argv[-3:]}")

    def test_image_before_prompt_does_not_swallow_it(self):
        img = self.tmp / "a.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        r = self.start("describe the image", "--image", str(img))
        row = self.wait_for_state(r["run_id"])
        self.assertEqual(row["state"], "completed",
                         "the run died — the prompt was probably eaten by -i")
        argv = self.last_argv()
        self.assertTrue(argv[-1].endswith("describe the image"), argv[-1][-60:])
        self.assertEqual(argv[-2], "--")
        self.assertIn("-i", argv)

    def test_two_images_still_leave_the_prompt_intact(self):
        for n in ("a", "b"):
            (self.tmp / f"{n}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        r = self.start("compare them", "--image", str(self.tmp / "a.png"),
                       "--image", str(self.tmp / "b.png"))
        row = self.wait_for_state(r["run_id"])
        self.assertEqual(row["state"], "completed")
        self.assertTrue(self.last_argv()[-1].endswith("compare them"))

    def test_a_prompt_starting_with_a_dash_survives(self):
        # --no-preamble so the prompt genuinely begins with a dash; with the
        # preamble prepended it would not exercise the case at all.
        r = self.start("--- please summarise this diff ---", "--no-preamble")
        row = self.wait_for_state(r["run_id"])
        self.assertEqual(row["state"], "completed",
                         "a dash-leading prompt must not be parsed as a flag")
        self.assertEqual(self.last_argv()[-1], "--- please summarise this diff ---")

    def test_no_preamble_disables_it(self):
        r = self.start("bare prompt", "--no-preamble")
        self.wait_for_state(r["run_id"])
        self.assertEqual(self.last_argv()[-1], "bare prompt")

    def test_stdin_is_devnull(self):
        """Codex reads stdin when it is not a TTY; a live stdin risks a block."""
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        self.assertFalse(self.argv_records()[-1]["stdin_is_tty"])

    def test_skip_git_repo_check_only_outside_a_repo(self):
        """The wrapper never silently disables a Codex guard where it applies."""
        r = self.start("inside a repo")
        self.wait_for_state(r["run_id"])
        self.assertNotIn("--skip-git-repo-check", self.last_argv())

        plain = self.tmp / "not-a-repo"
        plain.mkdir()
        r = self.bridge("start", "--project", str(self.project),
                        "--cwd", str(plain), "outside a repo")
        self.wait_for_state(r["run_id"])
        self.assertIn("--skip-git-repo-check", self.last_argv())


class SandboxDriftRegression(BridgeTestCase):
    """`codex exec resume` inherits no per-invocation setting from the thread.

    Measured against codex-cli 0.144.1 on one thread, three turns: a
    workspace-write thread resumed with no flags came back `read-only` with the
    reasoning effort dropped, and a read-only thread resumed under the user's
    config came back `danger-full-access` and wrote a file its original policy
    forbade. The registry exists to make these settings stable across turns.
    """

    def _start_and_resume(self, start_args=(), resume_args=()):
        r = self.start("first turn", *start_args)
        self.wait_for_state(r["run_id"])
        r2 = self.bridge("resume", r["run_id"], *resume_args, "second turn")
        self.wait_for_state(r2["run_id"])
        return r, r2

    def test_resume_reasserts_recorded_sandbox(self):
        """THE regression test: the sandbox recorded at creation is in the
        resume argv, verbatim, as `-c sandbox_mode=`."""
        r, r2 = self._start_and_resume(start_args=("--sandbox", "read-only"))
        recs = self.argv_records()
        self.assertEqual(len(recs), 2, "expected exactly one start and one resume")
        resume_argv = recs[1]["argv"]

        self.assertEqual(resume_argv[:2], ["exec", "resume"])
        self.assertIn('sandbox_mode="read-only"', resume_argv,
                      "the resume argv MUST carry the recorded sandbox; without it "
                      "Codex falls back to the config layer and the run silently "
                      f"changes policy. argv={resume_argv}")
        self.assertNoFlag(resume_argv, "-s", "--sandbox",
                          )
        self.assertEqual(r["thread_id"], r2["thread_id"],
                         "a resumed run is a new run on the SAME thread")
        self.assertNotEqual(r["run_id"], r2["run_id"])

    def test_resume_reasserts_every_setting_not_only_sandbox(self):
        # start_args deliberately use NON-default values for priority and
        # extra_config: with defaults (isolated=True -> priority=True,
        # extra_config=[]) this test would pass even if inheritance were
        # broken, because start's own derivation happens to match.
        r, r2 = self._start_and_resume(
            start_args=("--sandbox", "read-only", "--model", "gpt-5.6-sol",
                        "--effort", "low", "--no-priority",
                        "--config", "tools.web_search=true"))
        argv = self.argv_records()[1]["argv"]
        self.assertIn('sandbox_mode="read-only"', argv)
        self.assertIn('model_reasoning_effort="low"', argv,
                      "effort drifts to null on an unre-asserted resume")
        self.assertFlagPair(argv, "-m", "gpt-5.6-sol")
        self.assertIn("--ignore-user-config", argv)
        self.assertFalse([a for a in argv if a.startswith("service_tier=")],
                         "priority must not be re-derived from isolation on resume")
        self.assertFlagPair(argv, "-c", "tools.web_search=true")

    def test_resume_keeps_the_parents_cwd(self):
        sub = self.project / "worktree"
        sub.mkdir()
        r = self.start("first", "--cwd", str(sub))
        self.wait_for_state(r["run_id"])
        r2 = self.bridge("resume", r["run_id"], "second")
        self.wait_for_state(r2["run_id"])
        rec = self.argv_records()[1]
        self.assertNoFlag(rec["argv"], "-C", "--cd")
        self.assertEqual(_util.nfc(rec["cwd"]),
                         _util.nfc(str(sub.resolve())))

    def test_changing_the_sandbox_on_resume_is_explicit_and_recorded(self):
        r, r2 = self._start_and_resume(start_args=("--sandbox", "read-only"),
                                       resume_args=("--sandbox", "workspace-write"))
        argv = self.argv_records()[1]["argv"]
        self.assertIn('sandbox_mode="workspace-write"', argv)
        self.assertEqual(r2.get("sandbox_changed_from"), "read-only",
                         "a sandbox change must never be silent, in either direction")
        st = self.bridge("status", "--run", r2["run_id"])["runs"][0]
        self.assertEqual(st["sandbox_changed_from"], "read-only")
        self.assertEqual(st["sandbox"], "workspace-write")

    def test_resume_never_emits_dash_s_or_dash_C(self):
        self._start_and_resume()
        self.assertNoFlag(self.argv_records()[1]["argv"], "-s", "--sandbox", "-C",
                          "--cd", "--add-dir")

    def test_review_never_emits_dash_s_dash_C_or_image(self):
        r = self.bridge("review", "--uncommitted", "--sandbox", "read-only")
        self.wait_for_state(r["run_id"])
        argv = self.last_argv()
        self.assertEqual(argv[:2], ["exec", "review"])
        self.assertIn("--uncommitted", argv)
        self.assertIn('sandbox_mode="read-only"', argv)
        self.assertNoFlag(argv, "-s", "--sandbox", "-C", "--cd", "--add-dir", "-i", "--image")

    def test_resume_by_thread_id_and_by_last(self):
        r = self.start("first")
        self.wait_for_state(r["run_id"])
        r2 = self.bridge("resume", r["thread_id"], "by thread id")
        self.wait_for_state(r2["run_id"])
        self.assertEqual(self.argv_records()[1]["argv"][2], r["thread_id"])

        r3 = self.bridge("resume", "--last", "by last")
        self.wait_for_state(r3["run_id"])
        self.assertEqual(self.argv_records()[2]["argv"][2], r["thread_id"])
        self.assertEqual(r3["thread_id"], r["thread_id"])

    def test_resume_of_an_unknown_ref_passes_it_through_as_a_thread_name(self):
        """`codex exec resume` accepts a thread name, so an id we have never
        seen is a legitimate request, not an error."""
        r = self.bridge("resume", "some-thread-name", "go")
        self.wait_for_state(r["run_id"])
        argv = self.argv_records()[0]["argv"]
        self.assertEqual(argv[:3], ["exec", "resume", "some-thread-name"])
        self.assertIn('sandbox_mode="workspace-write"', argv,
                      "an unknown thread has no recorded sandbox, so the default "
                      "applies -- but it is still asserted explicitly")


class ReviewArgumentValidation(BridgeTestCase):

    def test_review_rejects_combinations(self):
        out = self.bridge("review", "--uncommitted", "--base", "main", expect_rc=1)
        self.assertIn("exactly one of", out["error"])

    def test_review_requires_one_selector(self):
        out = self.bridge("review", expect_rc=1)
        self.assertIn("exactly one of", out["error"])

    def test_title_requires_commit(self):
        out = self.bridge("review", "--uncommitted", "--title", "x", expect_rc=1)
        self.assertIn("--title is only valid with --commit", out["error"])

    def test_commit_with_title(self):
        r = self.bridge("review", "--commit", "abc123", "--title", "My change")
        self.wait_for_state(r["run_id"])
        argv = self.last_argv()
        self.assertFlagPair(argv, "--commit", "abc123")
        self.assertFlagPair(argv, "--title", "My change")

    def test_base_branch(self):
        r = self.bridge("review", "--base", "origin/main")
        self.wait_for_state(r["run_id"])
        self.assertFlagPair(self.last_argv(), "--base", "origin/main")


class PureArgvUnits(unittest.TestCase):
    """build_argv in isolation, for cases awkward to reach end-to-end."""

    def base(self, **kw):
        meta = {"run_dir": "/tmp/x", "sandbox": "workspace-write", "isolated": True,
                "priority": True, "model": None, "effort": None, "schema_path": None,
                "images": [], "add_dirs": [], "extra_config": [],
                "skip_git_repo_check": False}
        meta.update(kw)
        return meta

    def test_config_values_are_toml_quoted(self):
        """`-c` values parse as TOML, so a string value is quoted; an unquoted
        bare word only works through the raw-string fallback."""
        argv = _codex.build_argv(self.base(), kind="start", prompt="p")
        self.assertIn('sandbox_mode="workspace-write"', argv)

    def test_raw_config_passthrough_is_verbatim(self):
        argv = _codex.build_argv(
            self.base(extra_config=["tools.web_search=true", "num=3"]),
            kind="start", prompt="p")
        self.assertIn("tools.web_search=true", argv)
        self.assertIn("num=3", argv)

    def test_output_last_message_always_present(self):
        for kind in ("start", "resume", "review"):
            argv = _codex.build_argv(self.base(), kind=kind, prompt="p",
                                           thread_ref="t", review_args=["--uncommitted"])
            self.assertIn("-o", argv, f"{kind} must capture the final message")

    def test_add_dir_is_exec_only(self):
        meta = self.base(add_dirs=["/some/dir"])
        self.assertIn("--add-dir", _codex.build_argv(meta, kind="start", prompt="p"))
        self.assertNotIn("--add-dir",
                         _codex.build_argv(meta, kind="resume", prompt="p", thread_ref="t"))
        self.assertNotIn("--add-dir",
                         _codex.build_argv(meta, kind="review", review_args=["--uncommitted"]))

    def test_resume_last_uses_the_flag_not_a_positional(self):
        argv = _codex.build_argv(self.base(), kind="resume", prompt="p",
                                       thread_ref="--last")
        self.assertEqual(argv[:4], ["codex", "exec", "resume", "--last"])


if __name__ == "__main__":
    unittest.main()
