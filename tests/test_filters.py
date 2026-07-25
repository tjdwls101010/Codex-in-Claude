"""T1 — event filtering, incremental cursors, and the `show` escape hatch.

These are the assertions that make the context-discipline claim real rather than
aspirational: if `compact` ever leaks a command's stdout, the whole reason the
filter exists is gone, and nothing else in the system would notice.
"""

import json
import unittest
from pathlib import Path

from helpers import FIXTURES, BridgeTestCase
from _events import (DEFAULT_LEVEL, format_events, head_tail, read_events,
                     scan_progress, strip_wrapper)

BIG = FIXTURES / "mixed-bigout-and-failure.jsonl"


def load(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


class LevelsPure(unittest.TestCase):
    """Filtering is a pure function; test it directly against a real stream."""

    @classmethod
    def setUpClass(cls):
        cls.events = load(BIG)
        # The fixture is a real run: `cat big.txt` (22,000 B, exit 0), a failing
        # `ls` (exit 1), and a file write.
        cls.big_output = None
        cls.fail_output = None
        for ev in cls.events:
            it = ev.get("item") or {}
            if ev.get("type") == "item.completed" and it.get("type") == "command_execution":
                if it.get("exit_code") == 0 and len(it.get("aggregated_output") or "") > 10000:
                    cls.big_output = it["aggregated_output"]
                if it.get("exit_code") == 1:
                    cls.fail_output = it["aggregated_output"]
        assert cls.big_output and cls.fail_output, "fixture no longer has the shape we need"

    def render(self, level):
        return "\n".join(format_events(self.events, level))

    def test_compact_never_leaks_command_output(self):
        text = self.render("compact")
        # A distinctive slice of the 22 KB the command actually printed.
        needle = self.big_output.splitlines()[50]
        self.assertNotIn(needle, text,
                         "compact must not carry aggregated_output — this is the "
                         "entire context risk the filter exists to control")
        self.assertNotIn(self.fail_output.strip(), text)
        self.assertLess(len(text), 2000,
                        f"compact rendering of a 24 KB stream should be tiny, got {len(text)}")

    def test_compact_still_shows_every_decision_point(self):
        text = self.render("compact")
        self.assertIn("thread ", text)
        self.assertIn("turn.completed", text)
        self.assertIn("exit=0", text)
        self.assertIn("exit=1", text, "a failure must be visible even at the smallest level")
        self.assertIn("cat big.txt", text, "the command itself is cheap and load-bearing")
        self.assertIn("msg ", text)

    def test_compact_reports_withheld_output_size(self):
        """The byte count is what turns `show --item` into a decision rather
        than a guess."""
        text = self.render("compact")
        self.assertRegex(text, r"cmd\[item_\d+\] exit=0 out=2\d{4}B",
                         f"expected a ~22 KB size marker; got:\n{text}")

    def test_normal_shows_failed_output_and_hides_successful_output(self):
        text = self.render("normal")
        self.assertIn(self.fail_output.strip(), text,
                      "a failed command's output is exactly what the caller needs")
        self.assertNotIn(self.big_output.splitlines()[50], text,
                         "a successful command's output is exactly what they do not")

    def test_full_includes_both_but_caps_each_item(self):
        text = self.render("full")
        self.assertIn(self.big_output.splitlines()[0], text)
        self.assertIn("bytes omitted", text, "full is bounded, not unbounded")
        self.assertLess(len(text), 12000)

    def test_raw_is_passthrough(self):
        lines = format_events(self.events, "raw")
        self.assertEqual(len(lines), len(self.events))
        self.assertEqual(json.loads(lines[0]), self.events[0])

    def test_levels_are_monotonic_in_size(self):
        sizes = {lv: len(self.render(lv)) for lv in ("compact", "normal", "full")}
        self.assertLess(sizes["compact"], sizes["normal"])
        self.assertLess(sizes["normal"], sizes["full"])

    def test_agent_message_is_never_truncated(self):
        long_text = "A sentence. " * 400
        ev = [{"type": "item.completed",
               "item": {"id": "item_9", "type": "agent_message", "text": long_text}}]
        for level in ("compact", "normal", "full"):
            out = "\n".join(format_events(ev, level))
            self.assertIn(long_text.strip(), out,
                          f"{level} must keep the answer intact — it is what the run is for")

    def test_file_change_shows_paths_and_kind_only(self):
        ev = [{"type": "item.completed", "item": {
            "id": "item_1", "type": "file_change", "status": "completed",
            "changes": [{"path": "/proj/src/a.py", "kind": "add"},
                        {"path": "/proj/b.txt", "kind": "modify"}]}}]
        out = "\n".join(format_events(ev, "compact", Path("/proj")))
        self.assertIn("file add src/a.py", out)
        self.assertIn("file modify b.txt", out)

    def test_errors_are_never_hidden(self):
        events = load(FIXTURES / "inherit-config-errors.jsonl")
        out = "\n".join(format_events(events, "compact"))
        self.assertIn("error ", out)
        self.assertIn("duplicate agent role", out)

    def test_strip_wrapper(self):
        self.assertEqual(strip_wrapper("""/bin/zsh -lc 'git status --short'"""),
                         "git status --short")
        self.assertEqual(strip_wrapper('/bin/zsh -lc "echo hi"'), "echo hi")
        self.assertEqual(strip_wrapper("/bin/bash -c 'ls'"), "ls")
        self.assertEqual(strip_wrapper("plain command"), "plain command",
                         "an unwrapped command must pass through unchanged")
        self.assertEqual(strip_wrapper(""), "")

    def test_head_tail_announces_what_it_dropped(self):
        s = "x" * 5000
        out = head_tail(s, 100, 100)
        self.assertIn("4800 bytes omitted", out)
        self.assertEqual(len(head_tail("short", 100, 100)), 5)

    def test_default_level_is_the_measured_one(self):
        self.assertEqual(DEFAULT_LEVEL, "compact",
                         "the shipped default is chosen from "
                         "docs/measurements/filter-calibration.md")


class CursorExactness(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.f = self.tmp / "events.jsonl"

    def test_incremental_reads_never_duplicate_or_skip(self):
        events = load(BIG)
        seen, cursor = [], 0
        with self.f.open("w") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")
                fh.flush()
                batch, cursor = read_events(self.f, cursor)
                seen.extend(batch)
        self.assertEqual(len(seen), len(events))
        self.assertEqual([e.get("type") for e in seen], [e.get("type") for e in events])
        self.assertEqual(cursor, self.f.stat().st_size)

    def test_a_partial_trailing_line_is_left_for_the_next_poll(self):
        """The file is appended to live, so a half-written line must not be
        consumed as though it were complete."""
        self.f.write_text('{"type":"thread.started","thread_id":"t"}\n{"type":"turn.st')
        batch, cursor = read_events(self.f, 0)
        self.assertEqual(len(batch), 1)
        self.assertEqual(cursor, 42)
        with self.f.open("a") as fh:
            fh.write('arted"}\n')
        batch2, cursor2 = read_events(self.f, cursor)
        self.assertEqual([e["type"] for e in batch2], ["turn.started"])
        self.assertEqual(cursor2, self.f.stat().st_size)

    def test_reading_past_the_end_is_a_no_op(self):
        self.f.write_text('{"type":"turn.started"}\n')
        _, cursor = read_events(self.f, 0)
        batch, cursor2 = read_events(self.f, cursor)
        self.assertEqual(batch, [])
        self.assertEqual(cursor2, cursor)

    def test_a_corrupt_line_does_not_lose_the_rest_of_the_stream(self):
        self.f.write_text('{"type":"turn.started"}\nNOT JSON\n{"type":"turn.completed"}\n')
        batch, _ = read_events(self.f, 0)
        self.assertEqual([e["type"] for e in batch],
                         ["turn.started", "_unparsed", "turn.completed"])

    def test_missing_file_is_empty_not_an_error(self):
        self.assertEqual(read_events(self.tmp / "nope.jsonl", 0), ([], 0))


class LogAndShowEndToEnd(BridgeTestCase):

    fixture = "mixed-bigout-and-failure.jsonl"

    def test_cursor_round_trips_across_polls(self):
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        first, c1 = self.log_lines("--run", r["run_id"])
        self.assertGreater(len(first), 3)
        second, c2 = self.log_lines("--run", r["run_id"], "--since", c1)
        self.assertEqual(second, [], "a second poll at the same cursor must be empty")
        self.assertEqual(c1, c2)
        allover, _ = self.log_lines("--run", r["run_id"], "--since", 0)
        self.assertEqual(allover, first)

    def test_show_returns_full_output_for_one_item(self):
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        body, _ = self.log_lines("--run", r["run_id"])
        item = next(l.split("[")[1].split("]")[0] for l in body
                    if l.startswith("cmd[") and "out=2" in l)
        # 22 KB of output against the 20 KB default cap: truncated, and said so.
        capped = self.bridge("show", "--run", r["run_id"], "--item", item)
        self.assertEqual(capped["item_type"], "command_execution")
        self.assertTrue(capped["truncated"])
        self.assertGreater(capped["total_bytes"], 20000)

        # Raising the cap returns the whole thing.
        out = self.bridge("show", "--run", r["run_id"], "--item", item,
                          "--max-bytes", "100000")
        self.assertFalse(out["truncated"])
        self.assertEqual(len(out["output"].encode()), out["total_bytes"])
        self.assertIn("line 0050", out["output"])
        self.assertIn("line 0400", out["output"], "the tail must survive too")
        self.assertNotIn("/bin/zsh -lc", out["command"], "the wrapper is stripped")

    def test_show_truncates_loudly(self):
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        body, _ = self.log_lines("--run", r["run_id"])
        item = next(l.split("[")[1].split("]")[0] for l in body
                    if l.startswith("cmd[") and "out=2" in l)
        out = self.bridge("show", "--run", r["run_id"], "--item", item, "--max-bytes", "500")
        self.assertTrue(out["truncated"])
        self.assertEqual(out["shown_bytes"], 500)
        self.assertIn("withheld", out["truncation_notice"])
        self.assertIn("raise --max-bytes", out["truncation_notice"])

    def test_show_of_an_unknown_item_lists_what_is_available(self):
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        out = self.bridge("show", "--run", r["run_id"], "--item", "item_999", expect_rc=1)
        self.assertIn("no item", out["error"])
        self.assertTrue(out["available"], "an error should say what the caller could ask for")

    def test_item_ids_are_scoped_to_a_run_not_a_thread(self):
        """`item.id` restarts at item_0 on every invocation, so the same id in
        two runs on one thread must resolve independently."""
        r1 = self.start("first")
        self.wait_for_state(r1["run_id"])
        r2 = self.bridge("resume", r1["run_id"], "second")
        self.wait_for_state(r2["run_id"])
        self.assertEqual(r1["thread_id"], r2["thread_id"])
        a = self.bridge("show", "--run", r1["run_id"], "--item", "item_0")
        b = self.bridge("show", "--run", r2["run_id"], "--item", "item_0")
        self.assertEqual(a["run_id"], r1["run_id"])
        self.assertEqual(b["run_id"], r2["run_id"])

    def test_follow_emits_a_terminal_line(self):
        """Silence must never look like success: --follow has to say how it
        ended, or a crashed run and a working one produce identical output."""
        r = self.start("x", env_extra={"FAKE_CODEX_EXIT": "4"})
        p = self.bridge_raw("log", "--run", r["run_id"], "--follow",
                            "--interval", "0.2", "--follow-timeout", "45")
        self.assertEqual(p.returncode, 0)
        self.assertIn("run.failed", p.stdout)
        self.assertIn("exit=4", p.stdout)
        self.assertIn("# cursor=", p.stdout)

    def test_log_without_run_uses_the_latest(self):
        r1 = self.start("first")
        self.wait_for_state(r1["run_id"])
        r2 = self.start("second")
        self.wait_for_state(r2["run_id"])
        body, _ = self.log_lines()
        joined = "\n".join(body)
        self.assertIn("thread ", joined)


if __name__ == "__main__":
    unittest.main()
