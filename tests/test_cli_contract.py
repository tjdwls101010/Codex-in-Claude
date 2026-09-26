"""The CLI's output frame, its selector rules, and what reaches `codex`.

Callers parse stdout, so the frame is the contract: one line of JSON per command, success or failure, except the streaming views. And the argv a run hands to Codex is the other half of the contract, because Codex's own flag surface differs between `exec` and `exec resume`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unittest

from support.harness import ENTRY, BridgeCase, FIXTURES, engine


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

    def test_an_unparseable_command_line_is_one_json_line_too(self):
        p = self.bridge_raw("start", "--no-such-flag", "x")
        self.assertEqual((p.returncode, p.stderr), (2, ""))
        self.assertIn("unrecognized arguments", json.loads(p.stdout)["error"])

    def test_a_reader_that_went_away_ends_the_command_quietly(self):
        # A caller that pipes into `head` closes the pipe early; that is not an error worth a traceback, for a reply or a refusal.
        for args in (("status",), ("status", "--run", "no-such-run")):
            with self.subTest(args=args):
                r, w = os.pipe()
                os.close(r)
                try:
                    p = subprocess.run([sys.executable, str(ENTRY), *args], cwd=str(self.project), env=self.env,
                                       stdout=w, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, timeout=60)
                finally:
                    os.close(w)
                self.assertEqual(p.stderr, "")

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


class ExitCodes(BridgeCase):
    """0 success; 2 the command line itself must change, answered as JSON with the `--help` to read; 1 the registry's state refused or the run failed; 3 `doctor` found a blocker."""

    def help_for(self, *words):
        return " ".join(["uv run", f'"{ENTRY}"', *words, "--help"])

    def refused(self, *args, rc, **kw):
        p = self.bridge_raw(*args, **kw)
        self.assertEqual(p.returncode, rc, p.stdout + p.stderr)
        self.assertEqual(p.stderr, "")
        lines = p.stdout.splitlines()
        self.assertEqual(len(lines), 1, p.stdout)
        out = json.loads(lines[0])
        self.assertIn("error", out)
        return out

    def test_a_command_line_that_does_not_parse_is_json_naming_the_help_to_read(self):
        for args, words in ((("start", "--no-such-flag", "x"), ("start",)),
                            (("batch", "start", "--no-such-flag"), ("batch", "start")),
                            (("resume", "--no-such-flag", "r", "x"), ("resume",)),
                            (("no-such-command",), ())):
            with self.subTest(args=args):
                self.assertEqual(self.refused(*args, rc=2)["help"], self.help_for(*words))

    def test_help_still_prints_and_succeeds(self):
        p = self.bridge_raw("status", "--help")
        self.assertEqual(p.returncode, 0)
        self.assertIn("usage:", p.stdout)

    def test_a_command_line_that_must_change_is_2_with_its_help(self):
        cases = [(("status", "--follow"), ("status",)),
                 (("log", "--group", "g", "--since", "0"), ("log",)),
                 (("start", "   "), ("start",)),
                 (("start", "--schema", self.tmp / "nope.json", "x"), ("start",)),
                 (("resume", "--sandbox", "read-only"), ("resume",)),
                 (("batch", "start", "--group", "a/b", "--task", "x"), ("batch", "start")),
                 (("batch", "start", "--group", "g", "--base", "HEAD", "--task", "x"), ("batch", "start"))]
        for args, words in cases:
            with self.subTest(args=args):
                self.assertEqual(self.refused(*args, rc=2)["help"], self.help_for(*words))
        self.assertEqual(self.run_dirs(), [])

    def test_an_input_file_that_is_not_utf8_is_2_with_its_help(self):
        bad = self.tmp / "bad.txt"
        bad.write_bytes(b"\xff\xfe not utf-8")
        self.assertEqual(self.refused("start", "--prompt-file", bad, rc=2)["help"], self.help_for("start"))
        self.assertEqual(self.refused("batch", "start", "--group", "g", "--tasks-file", bad, rc=2)["help"],
                         self.help_for("batch", "start"))
        # Python decodes stdin by a policy the environment picks (a C locale escapes bad bytes instead of failing), so both are driven.
        for policy in ("utf-8:strict", "utf-8:surrogateescape"):
            p = subprocess.run([sys.executable, str(ENTRY), "start", "-"], cwd=str(self.project),
                               env={**self.env, "PYTHONIOENCODING": policy},
                               input=b"\xff\xfe not utf-8", capture_output=True, timeout=60)
            self.assertEqual((p.returncode, json.loads(p.stdout).get("help")), (2, self.help_for("start")), policy)
        self.assertEqual(self.run_dirs(), [])

    def test_a_refusal_by_the_registry_is_1_without_help(self):
        for args in (("status", "--run", "no-such-run"), ("result", "--group", "no-such-group"),
                     ("resume", "no-such-run", "x")):
            with self.subTest(args=args):
                self.assertNotIn("help", self.refused(*args, rc=1))


class TheNextStep(BridgeCase):
    """A detached run announces nothing, so every reply that starts work names the follower to run in the background, written out whole the way the pre-approval matches it."""

    def follow(self, *words):
        return {"command": " ".join(["uv run", f'"{ENTRY}"', *words]), "run_in_background": True}

    def test_start_and_resume_name_the_follower_of_the_run_they_made(self):
        out = self.bridge("start", "x")
        self.assertEqual(out["next"], self.follow("log", "--run", out["run_id"], "--follow"))
        self.wait_state(out["run_id"])
        again = self.bridge("resume", out["run_id"], "y")
        self.assertEqual(again["next"], self.follow("log", "--run", again["run_id"], "--follow"))
        self.wait_state(again["run_id"])
        last = self.bridge("resume", "--last", "z")
        self.assertEqual(last["next"], self.follow("log", "--run", last["run_id"], "--follow"))

    def test_a_batch_names_the_follower_of_its_group(self):
        out = self.bridge("batch", "start", "--group", "g", "--task", "a", "--task", "b")
        self.assertEqual(out["next"], self.follow("status", "--group", "g", "--follow"))

    def test_a_batch_that_started_nothing_has_nothing_to_follow(self):
        tf = self.tasks_file({"prompt": "a", "schema": str(self.tmp / "nope.json")})
        out = self.bridge("batch", "start", "--group", "g", "--tasks-file", tf)
        self.assertEqual(out["spawned"], 0)
        self.assertNotIn("next", out)

    def test_the_registry_named_on_the_command_line_travels_with_it(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        out = self.bridge("start", "--project", self.project, "x", cwd=elsewhere)
        self.assertEqual(out["next"], self.follow("log", "--run", out["run_id"], "--follow", "--project", str(self.project)))

    def test_the_command_it_names_runs_to_the_end(self):
        if not shutil.which("uv"):
            self.skipTest("uv is not on PATH, and the command it names is a `uv run`")
        out = self.bridge("start", "x")
        p = subprocess.run(out["next"]["command"], shell=True, cwd=str(self.project), env=self.env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout.splitlines()[-2], rf"^run\.completed run={re.escape(out['run_id'])} exit=0$")


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
                self.assertIn("not allowed with", self.bridge(*args, rc=2)["error"])

    def test_log_run_and_group_are_refused_by_the_parser(self):
        p = self.bridge_raw("log", "--run", self.run_id, "--group", "g")
        self.assertEqual(p.returncode, 2)

    def test_stop_and_result_need_a_target(self):
        for cmd in ("stop", "result"):
            with self.subTest(cmd=cmd):
                self.assertIn("--run", self.bridge(cmd, rc=2)["error"])

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
                 ("log", "--run", out["run_id"], "--follow", "--follow-timeout", "0"),
                 ("status", "--group", "g", "--follow", "--follow-timeout", "-1"),
                 ("log", "--run", out["run_id"], "--follow", "--heartbeat", "0"),
                 ("log", "--group", "g", "--since", "0"),
                 ("batch", "start", "--group", "h", "--base", "HEAD", "--task", "x")]
        for args in cases:
            with self.subTest(args=args):
                self.assertIn("error", self.bridge(*args, rc=2))
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

    def test_the_tier_flags_are_one_choice(self):
        self.assertIn("not allowed with", self.bridge("start", "--priority", "--no-priority", "x", rc=2)["error"])

    def test_a_prompt_after_the_terminator_is_only_a_prompt(self):
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
        self.assertIn("prompt", self.bridge("start", "   ", rc=2)["error"])
        self.assertEqual(self.run_dirs(), [])

    def test_missing_inputs_are_refused_before_anything_is_claimed(self):
        for args in (("--schema", self.tmp / "nope.json"), ("--image", self.tmp / "nope.png"),
                     ("--cwd", self.tmp / "nowhere")):
            with self.subTest(args=args):
                self.bridge("start", *args, "x", rc=2)
        self.assertEqual(self.runs_invoked(), [])
        self.assertEqual(self.run_dirs(), [], "a refused run leaves no directory behind, where no listing would show it")


class RemovedSurface(BridgeCase):
    """Flags nothing used, removed from the parser rather than left to accept and do nothing."""

    def test_each_is_refused_by_the_parser_before_anything_is_claimed(self):
        for args in (("start", "--foreground", "x"), ("resume", "--foreground", "r", "x"),
                     ("status", "--include-external"),
                     ("batch", "start", "--group", "g", "--resume-from", "p", "--as-ready", "--task", "x")):
            with self.subTest(args=args):
                self.assertIn("unrecognized arguments", self.bridge(*args, rc=2)["error"])
        self.assertFalse(self.runs_dir.exists())

    def test_last_never_reaches_past_the_registry(self):
        con = sqlite3.connect(self.codex_home / "state_5.sqlite")
        con.execute("CREATE TABLE threads (id TEXT, cwd TEXT, title TEXT, updated_at INTEGER)")
        con.execute("INSERT INTO threads VALUES ('019f0000-0000-7000-8000-0000000000aa', ?, 't', 1)",
                    (str(self.project),))
        con.commit()
        con.close()
        refused = self.bridge("resume", "--last", "--sandbox", "read-only", "go on", rc=1)
        self.assertIn("error", refused)
        self.assertEqual(self.runs_invoked(), [])
        self.assertNotIn("thread_db", self.bridge("doctor"))


class TheRegistryGoesWhereItIsTold(BridgeCase):

    def test_runs_dir_moves_the_registry_and_only_it_resolves_the_run(self):
        elsewhere = self.tmp / "registry"
        self.extra_runs_dirs = [elsewhere]
        out = self.bridge("start", "--runs-dir", elsewhere, "x")
        self.assertTrue(out["events"].startswith(str(elsewhere)))
        self.assertEqual(self.wait_state(out["run_id"], extra=("--runs-dir", elsewhere))["state"], "completed")
        self.assertFalse(self.runs_dir.exists())
        self.bridge("status", "--run", out["run_id"], rc=1)


COMMANDS = [(), ("start",), ("resume",), ("status",), ("log",), ("show",), ("stop",), ("result",), ("batch",),
            ("batch", "start"), ("batch", "clean"), ("models",), ("doctor",)]

# Provenance does not belong in help: measurements, document ids, discovery stories. This guards against it coming back; it does not pin any sentence.
PROVENANCE = re.compile(r"\b[Mm]easured\b|\b[RDBFC][0-9]{1,2}\b|\bV-[0-9]+\b|\baudit\b|\bfield report\b")


class HelpIsTheInterface(BridgeCase):

    def arguments(self):
        import argparse
        parser = engine("cli").build_parser()
        found = []

        def walk(p, path):
            for a in p._actions:
                if isinstance(a, argparse._SubParsersAction):
                    for name, sp in a.choices.items():
                        if name != "__supervise":
                            walk(sp, path + (name,))
                elif not isinstance(a, argparse._HelpAction):
                    found.append((path, a))
        walk(parser, ())
        return found

    def test_every_argument_explains_itself(self):
        args = self.arguments()
        self.assertGreater(len(args), 60, "the walk stopped finding arguments")
        self.assertEqual([(" ".join(p), a.dest) for p, a in args if not (a.help or "").strip()], [])

    def test_no_help_carries_provenance(self):
        for cmd in COMMANDS:
            with self.subTest(cmd=cmd):
                text = self.bridge_raw(*cmd, "--help").stdout
                self.assertEqual(PROVENANCE.findall(text), [])

    def test_help_is_never_rewrapped_to_the_terminal(self):
        for path, a in self.arguments():
            with self.subTest(arg=a.dest, cmd=path):
                text = self.bridge_raw(*path, "--help", env={"COLUMNS": 40}).stdout
                self.assertIn(a.help % vars(a) if "%(" in a.help else a.help, text)

    def test_the_internal_command_is_not_listed(self):
        self.assertNotIn("__supervise", self.bridge_raw("--help").stdout)


if __name__ == "__main__":
    unittest.main()
