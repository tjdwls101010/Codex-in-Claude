"""`codex.argv`: the argv a run hands Codex, and the paragraphs in front of its prompt."""

from __future__ import annotations

import unittest

from support.harness import engine

argv_mod = engine("codex.argv")

META = {"run_dir": "/r/run-1", "sandbox": "read-only", "isolated": True, "model": None, "effort": None,
        "service_tier": None, "schema_path": None, "images": [], "add_dirs": [], "skip_git_repo_check": False}


def build(kind="start", prompt="do it", thread_ref=None, **meta):
    return argv_mod.build_argv({**META, **meta}, kind=kind, prompt=prompt, thread_ref=thread_ref)


class BuildArgv(unittest.TestCase):

    def test_a_start_with_every_setting(self):
        self.assertEqual(
            build(model="m1", effort="high", service_tier="fast", schema_path="/s.json", images=["/a.png", "/b.png"],
                  add_dirs=["/extra"], skip_git_repo_check=True),
            ["codex", "exec", "--json", "--ignore-user-config", "--skip-git-repo-check",
             "-c", 'sandbox_mode="read-only"', "-c", 'service_tier="fast"', "-c", 'model_reasoning_effort="high"',
             "-m", "m1", "--output-schema", "/s.json", "-o", "/r/run-1/last-message.txt",
             "--add-dir", "/extra", "-i", "/a.png", "-i", "/b.png", "--", "do it"])

    def test_a_resume_names_its_thread_and_has_no_exec_only_flags(self):
        argv = build(kind="resume", thread_ref="thread-9", add_dirs=["/extra"], isolated=False)
        self.assertEqual(argv[:5], ["codex", "exec", "resume", "thread-9", "--json"])
        self.assertNotIn("--add-dir", argv)
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


class Preamble(unittest.TestCase):

    def test_every_prompt_is_told_it_is_non_interactive(self):
        sent = argv_mod.apply_preamble("the task")
        self.assertTrue(sent.startswith("[Run context: you are a single non-interactive"))
        self.assertTrue(sent.endswith("\n\nthe task"))

    def test_a_batch_member_is_told_its_group_and_checkout(self):
        sent = argv_mod.apply_preamble("t", batch={"n": 3, "group": "g1", "worktree": "/wt", "base": "a" * 40,
                                                   "uncommitted": 2})
        self.assertIn('batch of 3 tasks launched together as group "g1"', sent)
        self.assertIn("isolated git worktree at /wt, created from commit aaaaaaaaaaaa.", sent)
        self.assertIn("does not contain the 2 uncommitted file(s)", sent)

    def test_an_unknown_uncommitted_count_is_never_stated_as_zero(self):
        self.assertIn("how many is unknown", argv_mod.uncommitted_clause(None))
        self.assertIn("no uncommitted work", argv_mod.uncommitted_clause(0))


if __name__ == "__main__":
    unittest.main()
