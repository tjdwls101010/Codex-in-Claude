"""The CLI's output frame, its selector rules, and what reaches `codex`.

Callers parse stdout, so the frame is the contract: one line of JSON per command, success or failure, except the streaming views. And the argv a run hands to Codex is the other half of the contract, because Codex's own flag surface differs between `exec` and `exec resume`.
"""

from __future__ import annotations

import json
import re
import unittest

from support.harness import BridgeCase, FIXTURES


class OutputFrame(BridgeCase):

    def test_success_and_refusal_are_both_one_json_line_on_stdout(self):
        ok = self.bridge_raw("status")
        refused = self.bridge_raw("status", "--run", "no-such-run")
        for p, rc in ((ok, 0), (refused, 1)):
            with self.subTest(rc=rc):
                self.assertEqual(p.returncode, rc)
                self.assertEqual(len(p.stdout.splitlines()), 1, p.stdout)
                json.loads(p.stdout)
        self.assertIn("error", json.loads(refused.stdout))

    def test_an_unparseable_command_line_is_argparse_usage_on_stderr(self):
        p = self.bridge_raw("start", "--no-such-flag", "x")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, "")
        self.assertIn("unrecognized arguments", p.stderr)

    def test_log_streams_text_and_ends_with_a_cursor_naming_the_run(self):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        p = self.bridge_raw("log", "--run", out["run_id"])
        lines = p.stdout.splitlines()
        self.assertRegex(lines[-1], rf"^# cursor=\d+ run={re.escape(out['run_id'])}$")
        self.assertEqual([ln for ln in lines if ln.startswith("# cursor=")], [lines[-1]])

    def test_group_follow_prints_state_lines_then_one_terminal_line(self):
        out = self.bridge("batch", "start", "--group", "g", "--sandbox", "read-only", "--task", "a", "--task", "b")
        self.wait_all(out)
        p = self.bridge_raw("status", "--group", "g", "--follow")
        lines = p.stdout.splitlines()
        self.assertEqual(p.returncode, 0)
        for ln in lines[:-1]:
            self.assertRegex(ln, r"^run \S+ \S+ -> \w+( exit=-?\d+)?$")
        self.assertRegex(lines[-1], r"^group\.completed group=g done=2 failed=0$")


class SelectorsAreExclusive(BridgeCase):
    """Two selectors name different things; honouring one silently drops the other."""

    def setUp(self):
        super().setUp()
        self.run_id = self.bridge("start", "one")["run_id"]
        self.wait_state(self.run_id)
        self.wait_all(self.bridge("batch", "start", "--group", "g", "--task", "a"))

    def test_each_competing_pair_is_refused(self):
        cases = [("status", "--run", self.run_id, "--group", "g"),
                 ("status", "--run", self.run_id, "--thread", "t"),
                 ("status", "--thread", "t", "--group", "g"),
                 ("result", "--run", self.run_id, "--group", "g"),
                 ("stop", "--run", self.run_id, "--group", "g"),
                 ("stop", "--run", self.run_id, "--all"),
                 ("stop", "--group", "g", "--all")]
        for args in cases:
            with self.subTest(args=args):
                self.assertIn("error", self.bridge(*args, rc=1))

    def test_log_run_and_group_are_refused_by_the_parser(self):
        p = self.bridge_raw("log", "--run", self.run_id, "--group", "g")
        self.assertEqual(p.returncode, 2)

    def test_stop_and_result_need_a_target(self):
        for cmd in ("stop", "result"):
            with self.subTest(cmd=cmd):
                self.assertIn("--run", self.bridge(cmd, rc=1)["error"])

    def test_status_all_is_a_cap_not_a_selector(self):
        self.assertEqual(self.bridge("status", "--run", self.run_id, "--all")["runs"][0]["run_id"], self.run_id)


class FlagsThatWouldDecideNothing(BridgeCase):
    """A flag that parses and changes nothing reads as having been obeyed, so each is refused."""

    def test_each_is_refused(self):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        self.wait_all(self.bridge("batch", "start", "--group", "g", "--task", "x"))
        cases = [("status", "--follow"),
                 ("status", "--group", "g", "--follow-timeout", "5"),
                 ("log", "--run", out["run_id"], "--heartbeat", "5"),
                 ("log", "--run", out["run_id"], "--follow-timeout", "5"),
                 ("log", "--run", out["run_id"], "--follow", "--heartbeat", "0"),
                 ("log", "--group", "g", "--since", "0"),
                 ("batch", "start", "--group", "h", "--base", "HEAD", "--task", "x")]
        for args in cases:
            with self.subTest(args=args):
                self.assertIn("error", self.bridge(*args, rc=1))
        self.assertEqual(self.bridge("status")["groups"], ["g"], "a refused batch must not claim its name")


class WhatReachesCodex(BridgeCase):
    """The sandbox always travels as `-c sandbox_mode=` and the working directory is set on the child, because `exec resume` has neither `-s` nor `-C`."""

    def started(self, *args, **kw):
        out = self.bridge("start", *args, **kw)
        self.wait_state(out["run_id"])
        return out, self.runs_invoked()[-1]

    def test_a_default_start(self):
        _out, rec = self.started("hello")
        argv = rec["argv"]
        self.assertEqual(argv[:2], ["exec", "--json"])
        self.assertIn("--ignore-user-config", argv)
        self.assertEqual(self.config_values(argv), {"sandbox_mode": '"workspace-write"'})
        for flag in ("-s", "--sandbox", "-C", "--cd", "-m"):
            self.assertNotIn(flag, argv)
        self.assertFalse(rec["stdin_is_tty"])
        self.assertEqual(rec["codex_home"], str(self.codex_home))

    def test_every_sandbox_mode_is_a_config_entry(self):
        for mode in ("read-only", "workspace-write", "danger-full-access"):
            with self.subTest(mode=mode):
                _out, rec = self.started("--sandbox", mode, "x")
                self.assertEqual(self.config_values(rec["argv"])["sandbox_mode"], f'"{mode}"')

    def test_named_settings_are_passed_through(self):
        schema = self.tmp / "s.json"
        schema.write_text("{}")
        extra = self.tmp / "extra"
        extra.mkdir()
        _out, rec = self.started("--model", "fake-big", "--effort", "high", "--priority",
                                 "--schema", schema, "--add-dir", extra, "x")
        argv = rec["argv"]
        self.assertEqual(argv[argv.index("-m") + 1], "fake-big")
        self.assertEqual(argv[argv.index("--output-schema") + 1], str(schema))
        self.assertEqual(argv[argv.index("--add-dir") + 1], str(extra))
        cfg = self.config_values(argv)
        self.assertEqual(cfg["model_reasoning_effort"], '"high"')
        self.assertEqual(cfg["service_tier"], '"priority"')

    def test_the_prompt_is_last_after_a_terminator_and_behind_the_run_context(self):
        _out, rec = self.started("summarise the repo")
        argv = rec["argv"]
        self.assertEqual(argv[-2], "--")
        self.assertTrue(argv[-1].endswith("summarise the repo"))
        self.assertIn("non-interactive", argv[-1])

    def test_images_do_not_swallow_the_prompt(self):
        imgs = []
        for n in ("a", "b"):
            (self.tmp / f"{n}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            imgs += ["--image", self.tmp / f"{n}.png"]
        out, rec = self.started(*imgs, "compare them")
        self.assertEqual(self.row(out["run_id"])["state"], "completed", "codex found no prompt")
        self.assertEqual([rec["argv"][i + 1] for i, t in enumerate(rec["argv"]) if t == "-i"],
                         [str(self.tmp / "a.png"), str(self.tmp / "b.png")])
        self.assertTrue(rec["argv"][-1].endswith("compare them"))

    def test_the_tier_flags_are_one_choice_and_a_prompt_after_the_terminator_is_only_a_prompt(self):
        p = self.bridge_raw("start", "--priority", "--no-priority", "x")
        self.assertEqual(p.returncode, 2)
        self.assertIn("not allowed with", p.stderr)
        out, rec = self.started("--priority", "--", "--no-priority")
        self.assertTrue(rec["argv"][-1].endswith("\n\n--no-priority"))
        self.assertEqual(self.config_values(rec["argv"])["service_tier"], '"priority"')

    def test_a_prompt_starting_with_a_dash_survives(self):
        out, rec = self.started("--- summarise this diff ---")
        self.assertEqual(self.row(out["run_id"])["state"], "completed")
        self.assertTrue(rec["argv"][-1].endswith("--- summarise this diff ---"))

    def test_the_run_works_in_its_cwd_without_dash_C(self):
        sub = self.project / "nested"
        sub.mkdir()
        _out, rec = self.started("--cwd", sub, "x")
        self.assertEqual(rec["cwd"], str(sub))
        self.assertNotIn("-C", rec["argv"])

    def test_the_git_repo_check_is_skipped_only_outside_a_repository(self):
        _out, rec = self.started("inside")
        self.assertNotIn("--skip-git-repo-check", rec["argv"])
        plain = self.tmp / "plain"
        plain.mkdir()
        _out, rec = self.started("--cwd", plain, "outside")
        self.assertIn("--skip-git-repo-check", rec["argv"])

    def test_the_prompt_can_come_from_a_file_or_stdin(self):
        f = self.tmp / "p.md"
        f.write_text("from a file\nsecond line")
        _out, rec = self.started("--prompt-file", f)
        self.assertTrue(rec["argv"][-1].endswith("from a file\nsecond line"))
        _out, rec = self.started("-", stdin="from stdin")
        self.assertTrue(rec["argv"][-1].endswith("from stdin"))

    def test_an_empty_prompt_is_refused_before_anything_is_claimed(self):
        self.assertIn("prompt", self.bridge("start", "   ", rc=1)["error"])
        self.assertEqual(self.run_dirs(), [])

    def test_missing_inputs_are_refused_before_spawning(self):
        for args in (("--schema", self.tmp / "nope.json"), ("--image", self.tmp / "nope.png"),
                     ("--cwd", self.tmp / "nowhere")):
            with self.subTest(args=args):
                self.bridge("start", *args, "x", rc=1)
        self.assertEqual(self.runs_invoked(), [])


class TheRegistryGoesWhereItIsTold(BridgeCase):

    def test_runs_dir_moves_the_registry_and_only_it_resolves_the_run(self):
        elsewhere = self.tmp / "registry"
        self.extra_runs_dirs = [elsewhere]
        out = self.bridge("start", "--runs-dir", elsewhere, "x")
        self.assertTrue(out["events"].startswith(str(elsewhere)))
        self.assertEqual(self.wait_state(out["run_id"], extra=("--runs-dir", elsewhere))["state"], "completed")
        self.assertFalse(self.runs_dir.exists())
        self.bridge("status", "--run", out["run_id"], rc=1)


if __name__ == "__main__":
    unittest.main()
