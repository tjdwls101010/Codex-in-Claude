"""`codex.codex_cli`'s `build_argv` and `apply_preamble`: the argv a run hands Codex, and the paragraphs in front of its prompt."""

from __future__ import annotations

import tomllib
import unittest

from support.harness import engine

codex_cli = engine("codex.codex_cli")

META = {"run_dir": "/r/run-1", "sandbox": "read-only", "isolated": True, "model": None, "effort": None,
        "service_tier": None, "schema_path": None, "skip_git_repo_check": False}


def build(kind="start", prompt="do it", thread_ref=None, **meta):
    return codex_cli.build_argv({**META, **meta}, kind=kind, prompt=prompt, thread_ref=thread_ref)


class BuildArgv(unittest.TestCase):

    def test_a_start_with_every_setting(self):
        self.assertEqual(
            build(model="m1", effort="high", service_tier="fast", schema_path="/s.json", skip_git_repo_check=True),
            ["codex", "exec", "--json", "--ignore-user-config", "--skip-git-repo-check",
             "-c", 'sandbox_mode="read-only"', "-c", 'service_tier="fast"', "-c", 'model_reasoning_effort="high"',
             "-m", "m1", "--output-schema", "/s.json", "-o", "/r/run-1/last-message.txt", "--", "do it"])

    def test_a_resume_names_its_thread_and_a_thread_that_loads_the_config_is_not_isolated(self):
        argv = build(kind="resume", thread_ref="thread-9", isolated=False)
        self.assertEqual(argv[:5], ["codex", "exec", "resume", "thread-9", "--json"])
        self.assertNotIn("--ignore-user-config", argv)
        self.assertEqual(argv[argv.index("-c") + 1], 'sandbox_mode="read-only"')

    def test_neither_dash_s_nor_dash_C_ever_appears(self):
        for kind in ("start", "resume"):
            argv = build(kind=kind, thread_ref="t")
            for flag in ("-s", "--sandbox", "-C", "--cd"):
                self.assertNotIn(flag, argv)

    def test_a_prompt_that_looks_like_a_flag_is_behind_the_terminator(self):
        self.assertEqual(build(prompt="--no-priority")[-2:], ["--", "--no-priority"])

    def test_no_prompt_means_no_terminator(self):
        self.assertNotIn("--", build(prompt=None))


# The profile a read-only run that can write scratch is handed, from the measured form: everything readable, TMPDIR and ~/.cache writable, the run's own directory named read-only so it stays so even inside TMPDIR, network off, selected by name — with no `sandbox_mode`, which would pick the legacy sandbox instead.
SCRATCH = ["-c", 'permissions.codex_skill_read_only.filesystem={":root"="read", ":tmpdir"="write", "~/.cache"="write", "/work/proj"="read"}',
           "-c", "permissions.codex_skill_read_only.network.enabled=false",
           "-c", 'default_permissions="codex_skill_read_only"']


class ReadOnlyProfile(unittest.TestCase):

    def test_a_scratch_read_only_run_gets_the_profile_in_place_of_the_sandbox(self):
        self.assertEqual(build(read_only="scratch", cwd="/work/proj", effort="high"),
                         ["codex", "exec", "--json", "--ignore-user-config", *SCRATCH,
                          "-c", 'model_reasoning_effort="high"', "-o", "/r/run-1/last-message.txt", "--", "do it"])

    def test_a_resume_reasserts_it_for_the_directory_the_thread_recorded(self):
        argv = build(kind="resume", thread_ref="thread-9", read_only="scratch", cwd="/work/proj")
        self.assertEqual(argv[:6], ["codex", "exec", "resume", "thread-9", "--json", "--ignore-user-config"])
        self.assertEqual(argv[6:12], SCRATCH)

    def test_strict_or_unmarked_read_only_is_the_legacy_sandbox(self):
        for marker in (None, "strict"):
            with self.subTest(marker=marker):
                argv = build(read_only=marker, cwd="/work/proj")
                self.assertEqual(argv[argv.index("-c"):argv.index("-c") + 2], ["-c", 'sandbox_mode="read-only"'])
                self.assertFalse([a for a in argv if "permissions" in a])

    def test_a_writing_sandbox_never_gets_the_profile(self):
        for mode in ("workspace-write", "danger-full-access"):
            with self.subTest(mode=mode):
                argv = build(sandbox=mode, read_only="scratch", cwd="/work/proj")
                self.assertIn(f'sandbox_mode="{mode}"', argv)
                self.assertFalse([a for a in argv if "permissions" in a])

    def test_a_directory_toml_has_to_escape_stays_one_key(self):
        cwd = '/we"ird\\dir/한글 공백'
        argv = build(read_only="scratch", cwd=cwd)
        entry = next(a for a in argv if a.startswith("permissions.codex_skill_read_only.filesystem="))
        table = tomllib.loads("t = " + entry.split("=", 1)[1])["t"]
        self.assertEqual(table, {":root": "read", ":tmpdir": "write", "~/.cache": "write", cwd: "read"})


class Preamble(unittest.TestCase):

    def test_every_prompt_is_told_it_is_non_interactive(self):
        sent = codex_cli.apply_preamble("the task")
        self.assertTrue(sent.startswith("[Run context: you are a single non-interactive"))
        self.assertTrue(sent.endswith("\n\nthe task"))

    def test_a_batch_member_is_told_its_group_and_checkout(self):
        sent = codex_cli.apply_preamble("t", batch={"n": 3, "group": "g1", "worktree": "/wt", "base": "a" * 40,
                                                   "uncommitted": 2})
        self.assertIn('batch of 3 tasks launched together as group "g1"', sent)
        self.assertIn("isolated git worktree at /wt, created from commit aaaaaaaaaaaa.", sent)
        self.assertIn("does not contain the 2 uncommitted file(s)", sent)

    def test_an_unknown_uncommitted_count_is_never_stated_as_zero(self):
        def told(n):
            return codex_cli.apply_preamble("t", batch={"n": 2, "group": "g", "worktree": "/wt", "base": "b" * 40,
                                                        "uncommitted": n})
        self.assertIn("how many is unknown", told(None))
        self.assertNotIn("the 0 uncommitted", told(None))
        self.assertIn("no uncommitted work", told(0))


if __name__ == "__main__":
    unittest.main()
