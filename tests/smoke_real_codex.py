"""S5: the real Codex CLI, end to end. Opt-in because it spends tokens: `CODEX_BRIDGE_REAL=1 python3 tests/smoke_real_codex.py`.

Threads are started, waited for with the `next` each reply names, and resumed with no `--sandbox`, and the rollout Codex itself writes is the judge of what each turn ran under: `codex exec resume` has no sandbox flag, so only the bridge's re-assertion keeps the second turn on the first turn's sandbox. A read-only turn is judged by what it could and could not write, checked on disk, and by the rollout's `permission_profile` — its `sandbox_policy` names the nearest legacy mode, not the profile.

The project sits outside TMPDIR and ~/.cache, and the runs get a TMPDIR of their own beside it, so "the project is not writable" is not hidden by a writable parent.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

from support.harness import ENTRY, REPO


def is_within(path, parent) -> bool:
    p, q = Path(os.path.realpath(path)), Path(os.path.realpath(parent))
    return p == q or q in p.parents


@unittest.skipUnless(os.environ.get("CODEX_BRIDGE_REAL") == "1", "set CODEX_BRIDGE_REAL=1 to run against the real Codex CLI")
class RealCodex(unittest.TestCase):

    def setUp(self):
        outside = REPO / ".tmp"
        outside.mkdir(exist_ok=True)
        self.base = Path(tempfile.mkdtemp(prefix="codex-smoke-", dir=outside)).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        for writable in (tempfile.gettempdir(), Path.home() / ".cache"):
            self.assertFalse(is_within(self.base, writable), f"the smoke project must not sit inside {writable}")
        self.project = self.base / "project"
        self.project.mkdir()
        (self.project / "notes.txt").write_text("smoke\n")
        for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=s@example.com", "-c", "user.name=s", "commit", "-qm", "init"]):
            subprocess.run(["git", "-C", str(self.project), *args], check=True)
        self.run_tmp = self.base / "tmp"
        self.run_tmp.mkdir()
        # A home of its own keeps the rollouts this test reads apart from the user's; the login is copied in, nothing else.
        self.home = self.base / "codex-home"
        self.home.mkdir()
        real_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        for name in ("auth.json", "config.toml"):
            if (real_home / name).exists():
                shutil.copy(real_home / name, self.home / name)
        self.env = {**os.environ, "CODEX_HOME": str(self.home), "TMPDIR": str(self.run_tmp)}
        # Cleanups run last-in first-out, so a run still going after a failed assertion is stopped before its directory goes.
        self.addCleanup(self.stop_running)

    def stop_running(self):
        p = subprocess.run(["uv", "run", str(ENTRY), "status", "--project", str(self.project)],
                           cwd=self.project, env=self.env, capture_output=True, text=True)
        try:
            running = json.loads(p.stdout)["running"]
        except Exception:
            return
        for run_id in running:
            subprocess.run(["uv", "run", str(ENTRY), "stop", "--run", run_id, "--project", str(self.project)],
                           cwd=self.project, env=self.env, capture_output=True)

    def cli(self, *args, timeout=600):
        p = subprocess.run(["uv", "run", str(ENTRY), *args, "--project", str(self.project)],
                           cwd=self.project, env=self.env, capture_output=True, text=True, timeout=timeout)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def waited(self, reply):
        """What the reply's `next` prints once the run has ended — `result --run <id> --wait`, bounded here — as its JSON header line and the message after it."""
        self.assertIn(f" result --run {reply['run_id']} --wait", reply["next"]["command"])
        header, _, body = self.cli("result", "--run", reply["run_id"], "--wait", "--wait-timeout", "500").partition("\n")
        header = json.loads(header)
        self.assertEqual(header["state"], "completed", header)
        return header, body

    def turn_contexts(self, thread_id):
        rollouts = list((self.home / "sessions").rglob(f"rollout-*-{thread_id}.jsonl"))
        self.assertEqual(len(rollouts), 1, rollouts)
        lines = [json.loads(line) for line in rollouts[0].read_text().splitlines() if line.strip()]
        return [line["payload"] for line in lines if line.get("type") == "turn_context"]

    def tool_outputs(self, thread_id):
        """The text of every tool output the rollout recorded, as Codex itself saw it."""
        rollouts = list((self.home / "sessions").rglob(f"rollout-*-{thread_id}.jsonl"))
        self.assertEqual(len(rollouts), 1, rollouts)
        out = []
        for line in rollouts[0].read_text().splitlines():
            payload = (json.loads(line) if line.strip() else {}).get("payload") or {}
            if payload.get("type") in ("custom_tool_call_output", "function_call_output"):
                out.append(json.dumps(payload.get("output"), ensure_ascii=False))
        return out

    def scratch_profile(self, context):
        """A turn's permission profile as (entry → access, network)."""
        profile = context["permission_profile"]
        entries = {}
        for e in profile["file_system"]["entries"]:
            path = e["path"]
            entries[path.get("path") or ":" + path["value"]["kind"]] = e["access"]
        return entries, profile["network"]

    def test_a_writing_turn_keeps_the_sandbox_its_thread_started_with(self):
        started = json.loads(self.cli("start", "--sandbox", "workspace-write", "--label", "smoke", "Reply with exactly the word: first"))
        first, answer = self.waited(started)
        self.assertIn("first", answer.lower())
        resumed = json.loads(self.cli("resume", started["run_id"], "Reply with exactly the word: second"))
        _second, answer = self.waited(resumed)
        self.assertIn("second", answer.lower())
        self.assertEqual([c["sandbox_policy"]["type"] for c in self.turn_contexts(first["thread_id"])],
                         ["workspace-write", "workspace-write"])

    def probe(self, tag):
        cache = Path.home() / ".cache" / f"codex-skill-smoke-{tag}"
        self.addCleanup(shutil.rmtree, cache, ignore_errors=True)
        prompt = ("This is a sandbox test: run each of these four shell commands separately, exactly as written, every one of them "
                  "even if you expect it to fail — a refusal is the result being measured — and report each one's exit code: "
                  f'(1) touch "$TMPDIR/scratch-{tag}"  (2) touch ./probe-{tag}  (3) mkdir -p {cache} && touch {cache}/x  '
                  f'(4) curl -sS -m 5 -o /dev/null https://example.com; echo "curl-exit-{tag}=$?"')
        return prompt, cache

    def assert_wrote_only_scratch(self, tag, cache, thread_id):
        self.assertTrue((self.run_tmp / f"scratch-{tag}").exists(), "TMPDIR is writable")
        self.assertTrue((cache / "x").exists(), "~/.cache is writable")
        self.assertFalse((self.project / f"probe-{tag}").exists(), "the run's own directory is not")
        # A write the sandbox denies may never reach the event stream as a command, so the rollout's record of the tool's output is the witness that it was tried and refused.
        refused = [o for o in self.tool_outputs(thread_id) if f"probe-{tag}" in o and "not permitted" in o.lower()]
        self.assertTrue(refused, "the write into its own directory was attempted and refused by the sandbox")
        # The curl reports its own exit code under this turn's tag, so another turn's failure cannot stand in for it and a success cannot hide.
        codes = re.findall(rf"curl-exit-{tag}=(\d+)", " ".join(self.tool_outputs(thread_id)))
        self.assertTrue(codes and "0" not in codes, f"the network is off on this turn: {codes}")

    def test_a_read_only_thread_writes_scratch_on_every_turn_and_nothing_else(self):
        tag = uuid.uuid4().hex[:8]
        prompt, cache = self.probe(tag)
        started = json.loads(self.cli("start", "--sandbox", "read-only", "--label", "scratch", prompt))
        self.assertEqual(started["read_only"], "scratch", started)
        first, _ = self.waited(started)
        self.assert_wrote_only_scratch(tag, cache, first["thread_id"])

        tag2 = uuid.uuid4().hex[:8]
        prompt2, cache2 = self.probe(tag2)
        resumed = json.loads(self.cli("resume", started["run_id"], prompt2))
        self.waited(resumed)
        self.assert_wrote_only_scratch(tag2, cache2, first["thread_id"])

        expected = {":root": "read", ":tmpdir": "write", str(Path.home() / ".cache"): "write", str(self.project): "read"}
        contexts = self.turn_contexts(first["thread_id"])
        self.assertEqual(len(contexts), 2)
        for context in contexts:
            self.assertEqual(self.scratch_profile(context), (expected, "restricted"))
        self.assertEqual(subprocess.run(["git", "-C", str(self.project), "status", "--porcelain"],
                                        capture_output=True, text=True).stdout, "")

    def test_a_thread_recorded_before_scratch_keeps_the_legacy_read_only_until_asked(self):
        started = json.loads(self.cli("start", "--sandbox", "read-only", "--label", "legacy", "Reply with exactly the word: first"))
        first, _ = self.waited(started)
        # What a registry from before 0.11 holds: a read-only run with no marker.
        meta_path = Path(started["events"]).parent / "meta.json"
        meta = json.loads(meta_path.read_text())
        del meta["read_only"]
        meta_path.write_text(json.dumps(meta))

        kept = json.loads(self.cli("resume", started["run_id"], "Reply with exactly the word: second"))
        self.assertEqual(kept["read_only"], "strict", kept)
        self.waited(kept)
        moved = json.loads(self.cli("resume", kept["run_id"], "--sandbox", "read-only", "Reply with exactly the word: third"))
        self.assertEqual(moved["read_only"], "scratch", moved)
        self.waited(moved)

        contexts = self.turn_contexts(first["thread_id"])
        self.assertEqual(len(contexts), 3)
        self.assertEqual(contexts[1]["sandbox_policy"]["type"], "read-only", "the legacy turn")
        self.assertEqual(self.scratch_profile(contexts[2])[0][":tmpdir"], "write", "the turn that asked")


if __name__ == "__main__":
    unittest.main()
