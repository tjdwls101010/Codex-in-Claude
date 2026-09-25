"""Installs: the skill reached through a symlink, from a directory that has nothing to do with the project, must run exactly as it does in place.

A user-level install is `~/.claude/skills/codex -> <checkout>`, so the path the caller types is the link while the running script's own path is the target. The launcher exits as soon as it has a handle; a detached supervisor it re-executes finishes the run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unittest

from support.harness import SCRIPTS, BridgeCase, ENTRY, alive, engine, wait_until

SKILL_MD = ENTRY.parent.parent / "SKILL.md"


class ThroughASymlink(BridgeCase):

    def setUp(self):
        super().setUp()
        skills = self.tmp / "홈 디렉터리" / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "codex").symlink_to(ENTRY.parent.parent, target_is_directory=True)
        self.linked = skills / "codex" / "scripts" / ENTRY.name
        self.elsewhere = self.tmp / "unrelated"
        self.elsewhere.mkdir()

    def test_a_run_started_through_the_link_is_finished_by_its_detached_supervisor(self):
        launcher = subprocess.Popen([sys.executable, str(self.linked), "start", "--project", str(self.project),
                                     "--label", "via-link", "x"],
                                    cwd=str(self.elsewhere), env={**self.env, "FAKE_CODEX_HANG": "2"},
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    text=True)
        stdout, stderr = launcher.communicate(timeout=60)
        self.assertEqual(launcher.returncode, 0, stderr)
        out = json.loads(stdout)
        meta = self.meta(out["run_id"])
        self.assertNotEqual(meta["supervisor_pid"], launcher.pid)
        self.assertTrue(alive(meta["supervisor_pid"]), "the supervisor outlives the launcher")
        self.assertEqual(self.runs_invoked()[-1]["cwd"], str(self.project))

        def finished():
            p = self.bridge_raw("result", "--project", self.project, "--run", out["run_id"],
                                entry=self.linked, cwd=self.elsewhere)
            res = json.loads(p.stdout)
            return res if res["state"] == "completed" else None

        res = wait_until(finished, timeout=30, interval=0.2)
        self.assertTrue(res)
        self.assertEqual(res["message"], "OK")

    def test_doctor_through_the_link_reports_the_installed_skill(self):
        p = self.bridge_raw("doctor", "--project", self.project, entry=self.linked, cwd=self.elsewhere)
        rep = json.loads(p.stdout)
        self.assertEqual(rep["project"], str(self.project))
        self.assertEqual(rep["skill_dir"], str(ENTRY.parent.parent.resolve()))


class TheSkillTextPointsAtRealThings(unittest.TestCase):
    """SKILL.md may name commands, flags and reply fields; each has to exist, and the pre-approval has to match the call it shows."""

    def setUp(self):
        self.text = SKILL_MD.read_text()
        front, self.body = self.text.split("\n---\n", 1)
        self.allowed = re.findall(r"^\s+- Bash\((.*)\)$", front, re.M)
        parser = engine("cli.parser").build_parser()
        self.flags = {}

        def walk(p, path):
            for a in p._actions:
                if isinstance(a, argparse._SubParsersAction):
                    for name, sp in a.choices.items():
                        walk(sp, path + (name,))
                else:
                    self.flags.setdefault(path, set()).update(a.option_strings)
        walk(parser, ())

    def test_the_pre_approval_matches_the_call_line_and_the_entrypoint(self):
        self.assertEqual(len(self.allowed), 1)
        pattern = self.allowed[0]
        self.assertTrue(pattern.endswith(" *"))
        prefix = pattern[:-2]
        self.assertIn(f"`{prefix} <command>", self.body, "the call the text teaches is the one pre-approved")
        self.assertEqual(prefix, f'python3 "${{CLAUDE_SKILL_DIR}}/scripts/{ENTRY.name}"')
        self.assertTrue((SKILL_MD.parent / "scripts" / ENTRY.name).is_file())

    def test_every_command_and_flag_named_exists(self):
        commands = {" ".join(path) for path in self.flags if path}
        groups = {path[0] for path in self.flags if len(path) > 1}
        all_flags = set().union(*self.flags.values())
        missing = []
        for span in re.findall(r"`([^`]+)`", self.body):
            words = span.split()
            if not words:
                continue
            if words[0] in groups and len(words) > 1 and not words[1].startswith("-") and " ".join(words[:2]) not in commands:
                missing.append(f"{span}: no such subcommand")
                continue
            path = tuple(words[:2]) if " ".join(words[:2]) in commands else tuple(words[:1])
            if " ".join(path) in commands:
                for flag in (w for w in words if w.startswith("--")):
                    if flag not in self.flags[path]:
                        missing.append(f"{span}: {flag}")
            elif any(w.startswith("--") for w in words) and not words[0].startswith(("--", "<")):
                missing.append(f"{span}: no such command")
            else:
                for flag in (w for w in words if w.startswith("--") and w != "--help"):
                    if flag not in all_flags:
                        missing.append(f"{span}: {flag}")
        self.assertEqual(missing, [])

    def test_every_field_named_is_a_key_the_code_writes(self):
        # Catches a renamed or misspelt field; a key the code writes only into its own records would still pass.
        code = "\n".join(p.read_text() for p in SCRIPTS.rglob("*.py"))
        # Names Codex owns rather than this skill's replies.
        codex_owned = {"turn_context"}
        commands = {path[0] for path in self.flags if path}
        fields = set(re.findall(r"`([a-z][a-z_]*)`", self.body)) - codex_owned - commands
        self.assertTrue(fields, "the check found no field names to check")
        self.assertEqual(sorted(f for f in fields if not re.search(rf'"{f}"\s*:|\["{f}"\]', code)), [])

    def test_no_provenance(self):
        self.assertEqual(re.findall(r"\b[Mm]easured\b|\b[RDBFC][0-9]{1,2}\b|\bV-[0-9]+\b|\baudit\b|\bfield report\b|\b[0-9]+ sessions\b", self.text), [])


if __name__ == "__main__":
    unittest.main()
