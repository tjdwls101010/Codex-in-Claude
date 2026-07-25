"""T1 — stopping runs without collateral damage, and collecting results."""

import json
import time
import unittest
from pathlib import Path

from helpers import BridgeTestCase, codex_bridge


class StopIsolation(BridgeTestCase):
    """The legacy wrapper's `--cancel` ran `pgrep -f "codex exec"` and killed
    every match, which is a direct conflict with running anything in parallel.
    `stop` targets one recorded process group and nothing else."""

    def _long_run(self, label):
        r = self.start(f"long {label}", "--label", label,
                       env_extra={"FAKE_CODEX_HANG": "120"})
        deadline = time.time() + 30
        while time.time() < deadline:
            row = self.bridge("status", "--run", r["run_id"])["runs"][0]
            if row["state"] == "running" and row["codex_pid"]:
                return r, row
            time.sleep(0.1)
        self.fail(f"run {label} never reached running")

    def test_stop_one_run_leaves_the_others_alone(self):
        a, arow = self._long_run("a")
        b, brow = self._long_run("b")
        self.assertNotEqual(arow["pgid"], brow["pgid"],
                            "each run must own a distinct process group")

        out = self.bridge("stop", "--run", a["run_id"])
        self.assertTrue(out["stopped"][0]["signalled"])
        self.assertIn("SIGINT", out["stopped"][0]["signals_sent"],
                      "SIGINT first: Codex flushes its rollout and stays resumable")

        self.wait_for_state(a["run_id"], states=("interrupted", "failed", "completed"))
        after = self.bridge("status", "--run", b["run_id"])["runs"][0]
        self.assertEqual(after["state"], "running",
                         "stopping one run must not touch a concurrent one")
        self.assertTrue(codex_bridge.pid_alive(brow["codex_pid"]))
        self.bridge("stop", "--run", b["run_id"])

    def test_stop_marks_the_run_interrupted_and_keeps_the_thread(self):
        a, _ = self._long_run("a")
        out = self.bridge("stop", "--run", a["run_id"])
        self.assertEqual(out["stopped"][0]["thread_id"], a["thread_id"],
                         "an interrupted run is still resumable, so the thread matters")
        row = self.wait_for_state(a["run_id"],
                                  states=("interrupted", "failed", "completed"))
        self.assertIn(row["state"], ("interrupted", "failed"))

    def test_stop_requires_an_explicit_target(self):
        out = self.bridge("stop", expect_rc=1)
        self.assertIn("--all-mine", out["error"])

    def test_all_mine_only_touches_this_session(self):
        mine, _ = self._long_run("mine")
        # A run recorded as belonging to a different Claude session.
        other, orow = self._long_run("other")
        meta_path = self.project / ".codex-runs" / other["run_id"] / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["claude_session_id"] = "some-other-session"
        meta_path.write_text(json.dumps(meta))

        out = self.bridge("stop", "--all-mine")
        stopped = {s["run_id"] for s in out["stopped"]}
        self.assertIn(mine["run_id"], stopped)
        self.assertNotIn(other["run_id"], stopped,
                         "--all-mine must mean this session's runs, not everyone's")
        self.assertTrue(codex_bridge.pid_alive(orow["codex_pid"]))
        self.bridge("stop", "--run", other["run_id"])

    def test_stopping_an_already_finished_run_is_harmless(self):
        r = self.start("quick")
        self.wait_for_state(r["run_id"])
        out = self.bridge("stop", "--run", r["run_id"])
        self.assertEqual(out["stopped"][0]["state"], "completed",
                         "a finished run must not be re-marked as interrupted")

    def test_detached_runs_are_flagged(self):
        r = self.start("bg", "--detach", env_extra={"FAKE_CODEX_HANG": "60"})
        self.assertTrue(r["detached"])
        row = self.bridge("status", "--run", r["run_id"])["runs"][0]
        self.assertTrue(row["detached"])
        self.bridge("stop", "--run", r["run_id"])


class Results(BridgeTestCase):

    def test_result_returns_the_final_message_and_usage(self):
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        out = self.bridge("result", "--run", r["run_id"])
        self.assertEqual(out["state"], "completed")
        self.assertEqual(out["exit_code"], 0)
        self.assertEqual(out["message"].strip(), "OK")
        self.assertEqual(out["usage"]["input_tokens"], 15871)

    def test_result_of_a_running_run_says_it_is_partial(self):
        r = self.start("slow", env_extra={"FAKE_CODEX_HANG": "60"})
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.bridge("status", "--run", r["run_id"])["runs"][0]["state"] == "running":
                break
            time.sleep(0.1)
        out = self.bridge("result", "--run", r["run_id"])
        self.assertIn("partial", out.get("note", ""))
        self.bridge("stop", "--run", r["run_id"])

    def test_schema_run_parses_valid_json(self):
        schema = self.tmp / "schema.json"
        schema.write_text(json.dumps({"type": "object",
                                      "properties": {"verdict": {"type": "string"}}}))
        fixture = self.tmp / "json-answer.jsonl"
        fixture.write_text("\n".join([
            json.dumps({"type": "thread.started", "thread_id": "t-json"}),
            json.dumps({"type": "turn.started"}),
            json.dumps({"type": "item.completed", "item": {
                "id": "item_0", "type": "agent_message",
                "text": '{"verdict": "looks good", "count": 3}'}}),
            json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 10, "cached_input_tokens": 0,
                "output_tokens": 2, "reasoning_output_tokens": 0}}),
        ]) + "\n")
        r = self.start("x", "--schema", str(schema),
                       env_extra={"FAKE_CODEX_FIXTURE": str(fixture)})
        self.wait_for_state(r["run_id"])
        self.assertFlagPair(self.last_argv(), "--output-schema", str(schema))
        out = self.bridge("result", "--run", r["run_id"])
        self.assertEqual(out["json"], {"verdict": "looks good", "count": 3})

    def test_schema_run_fails_loudly_on_malformed_json(self):
        """Handing back a malformed object as if it had the schema's shape is
        worse than failing here."""
        schema = self.tmp / "schema.json"
        schema.write_text(json.dumps({"type": "object"}))
        fixture = self.tmp / "bad.jsonl"
        fixture.write_text("\n".join([
            json.dumps({"type": "thread.started", "thread_id": "t-bad"}),
            json.dumps({"type": "item.completed", "item": {
                "id": "item_0", "type": "agent_message",
                "text": "Sure! Here is the JSON: {verdict: nope"}}),
            json.dumps({"type": "turn.completed", "usage": {}}),
        ]) + "\n")
        r = self.start("x", "--schema", str(schema),
                       env_extra={"FAKE_CODEX_FIXTURE": str(fixture)})
        self.wait_for_state(r["run_id"])
        out = self.bridge("result", "--run", r["run_id"], expect_rc=1)
        self.assertIn("not valid JSON", out["error"])
        self.assertIn("parse_error", out)
        self.assertIn("message_preview", out)

    def test_missing_schema_file_is_rejected_before_spawning(self):
        out = self.bridge("start", "--schema", str(self.tmp / "nope.json"), "x",
                          expect_rc=1)
        self.assertIn("schema file not found", out["error"])
        self.assertEqual(self.argv_records(), [], "nothing should have been spawned")

    def test_missing_image_is_rejected_before_spawning(self):
        out = self.bridge("start", "--image", str(self.tmp / "nope.png"), "x",
                          expect_rc=1)
        self.assertIn("image not found", out["error"])
        self.assertEqual(self.argv_records(), [])

    def test_review_usage_is_reported_unavailable_not_zero(self):
        """Measured: review runs report all-zero usage after doing real work.
        Zero is a wrong number; null is a true one."""
        r = self.bridge("review", "--uncommitted",
                        env_extra={"FAKE_CODEX_FIXTURE":
                                   str(Path(__file__).parent / "fixtures"
                                       / "review-clean-tree.jsonl")})
        self.wait_for_state(r["run_id"])
        row = self.bridge("status", "--run", r["run_id"])["runs"][0]
        self.assertIsNone(row["usage"])
        self.assertIn("unavailable", row["usage_note"])
        out = self.bridge("result", "--run", r["run_id"])
        self.assertIsNone(out["usage"])
        self.assertIn("unavailable", out["usage_note"])


class ForegroundMode(BridgeTestCase):

    def test_foreground_blocks_and_returns_the_answer(self):
        out = self.bridge("start", "--foreground", "x")
        self.assertEqual(out["state"], "completed")
        self.assertEqual(out["exit_code"], 0)
        self.assertEqual(out["last_agent_message"], "OK")

    def test_foreground_timeout_interrupts(self):
        out = self.bridge("start", "--foreground", "--timeout", "2", "x",
                          env_extra={"FAKE_CODEX_HANG": "60"})
        self.assertEqual(out["state"], "interrupted")
        row = self.bridge("status", "--run", out["run_id"])["runs"][0]
        self.assertIn("timed out", row["error"])


class PromptSources(BridgeTestCase):

    def test_prompt_file(self):
        f = self.tmp / "p.md"
        f.write_text("prompt from a file\nwith two lines")
        r = self.bridge("start", "--prompt-file", str(f))
        self.wait_for_state(r["run_id"])
        self.assertIn("prompt from a file", self.last_argv()[-1])

    def test_empty_prompt_is_rejected(self):
        out = self.bridge("start", "   ", expect_rc=1)
        self.assertIn("prompt is required", out["error"])


if __name__ == "__main__":
    unittest.main()
