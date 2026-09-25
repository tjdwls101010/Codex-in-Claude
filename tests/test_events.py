"""Reading a run's event stream: exact cursors, damaged lines that are counted rather than dropped, the filter levels, and `show`.

Command output is the one field that can put a whole file into the caller's context, so `compact` withholds it and reports its size, and `show` fetches one item on request.
"""

from __future__ import annotations

import json
import unittest

from support.harness import BridgeCase, FIXTURES

MIXED = FIXTURES / "mixed-bigout-and-failure.jsonl"


class Cursors(BridgeCase):

    def finished(self, **env):
        out = self.bridge("start", "x", env=env)
        self.wait_state(out["run_id"])
        return out["run_id"], self.runs_dir / out["run_id"] / "events.jsonl"

    def test_polling_a_live_run_never_duplicates_or_skips(self):
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": MIXED, "FAKE_CODEX_DELAY": 0.15})
        seen, cursor = [], 0
        while True:
            done = self.row(out["run_id"])["state"] == "completed"
            body, cursor = self.log("--run", out["run_id"], "--since", cursor)
            seen += body
            if done:
                break
        whole, end = self.log("--run", out["run_id"])
        self.assertEqual(seen, whole)
        self.assertEqual(cursor, end)

    def test_a_second_poll_at_the_same_cursor_is_empty(self):
        rid, _ = self.finished()
        first, c1 = self.log("--run", rid)
        self.assertTrue(first)
        again, c2 = self.log("--run", rid, "--since", c1)
        self.assertEqual((again, c2), ([], c1))

    def test_a_half_written_last_line_waits_for_the_next_poll(self):
        rid, events = self.finished()
        _body, cursor = self.log("--run", rid)
        with events.open("a") as fh:
            fh.write('{"type":"turn.st')
        self.assertEqual(self.log("--run", rid, "--since", cursor), ([], cursor))
        with events.open("a") as fh:
            fh.write('arted"}\n')
        body, after = self.log("--run", rid, "--since", cursor)
        self.assertEqual(body, ["turn.started"])
        self.assertEqual(after, events.stat().st_size)

    def test_a_cursor_past_the_end_is_refused(self):
        rid, events = self.finished()
        out = self.bridge("log", "--run", rid, "--since", events.stat().st_size + 1000, rc=1)
        self.assertIn("past the end", out["error"])
        self.assertEqual(out["run_id"], rid)

    def test_a_cursor_that_is_not_a_line_boundary_is_refused(self):
        rid, events = self.finished()
        first_line = len(events.read_bytes().split(b"\n")[0])
        out = self.bridge("log", "--run", rid, "--since", first_line - 3, rc=1)
        self.assertIn("run=", out["error"])


class DamagedLines(BridgeCase):
    """A line that will not parse is kept as `unparsed` and counted, apart from Codex's own error items."""

    def damaged(self, bad=2):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        events = self.runs_dir / out["run_id"] / "events.jsonl"
        lines = events.read_text().splitlines()
        lines[:bad] = ["{ this will not parse"] * bad
        events.write_text("\n".join(lines) + "\n")
        return out["run_id"], events

    def test_a_healthy_run_carries_no_count(self):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        self.assertNotIn("unparsed_events", self.row(out["run_id"]))

    def test_every_view_reports_them(self):
        rid, _ = self.damaged(2)
        body, _ = self.log("--run", rid)
        self.assertEqual(sum(ln.startswith("unparsed ") for ln in body), 2)
        row = self.row(rid)
        self.assertEqual((row["unparsed_events"], row["config_error_events"]), (2, 0))
        self.assertEqual(self.bridge("result", "--run", rid)["unparsed_events"], 2)

    def test_a_finished_run_cut_off_mid_line_counts_the_fragment(self):
        rid, events = self.damaged(0)
        with events.open("a") as fh:
            fh.write('{"type":"item.completed","item":{"id":"item_9","ty')
        self.assertEqual(self.row(rid)["unparsed_events"], 1)


class Levels(BridgeCase):

    def setUp(self):
        super().setUp()
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": MIXED})
        self.wait_state(out["run_id"])
        self.rid = out["run_id"]

    def at(self, level):
        return self.log("--run", self.rid, "--level", level)[0]

    def test_compact_reports_each_commands_size_and_withholds_its_output(self):
        body = self.at("compact")
        cmds = [ln for ln in body if ln.startswith("cmd[")]
        self.assertEqual(len(cmds), 3)
        self.assertRegex(cmds[0], r"^cmd\[item_1\] exit=0 out=\d{5}B cat big\.txt$")
        self.assertIn("exit=1", cmds[1])
        self.assertFalse([ln for ln in body if ln.startswith("    | ")])
        self.assertFalse([ln for ln in body if "/bin/zsh" in ln], "the shell wrapper is noise")

    def test_the_agents_own_words_are_never_cut(self):
        text = "\n".join(self.at("compact"))
        self.assertIn("Exit codes, in order:\n\n1. `cat big.txt`: `0`", text)

    def test_normal_adds_the_output_of_failed_commands_only(self):
        body = self.at("normal")
        excerpt = [ln for ln in body if ln.startswith("    | ")]
        self.assertTrue(excerpt)
        self.assertTrue(any("No such file" in ln for ln in excerpt))
        self.assertFalse(any("quick brown fox" in ln for ln in excerpt))

    def test_full_adds_a_bounded_excerpt_of_every_command(self):
        body = "\n".join(self.at("full"))
        self.assertIn("quick brown fox", body)
        self.assertIn("bytes omitted", body)
        self.assertLess(len(body.encode()), 20000, "the 22 KB output is excerpted, not reproduced")

    def test_raw_is_the_event_lines_themselves(self):
        body = self.at("raw")
        stream = (self.runs_dir / self.rid / "events.jsonl").read_text().splitlines()
        self.assertEqual([json.loads(ln) for ln in body], [json.loads(ln) for ln in stream])

    def test_an_unknown_level_is_refused_by_the_parser(self):
        self.assertEqual(self.bridge_raw("log", "--run", self.rid, "--level", "verbose").returncode, 2)


class Show(BridgeCase):

    def setUp(self):
        super().setUp()
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": MIXED})
        self.wait_state(out["run_id"])
        self.rid = out["run_id"]

    def test_one_items_output_is_capped_loudly_and_whole_on_request(self):
        capped = self.bridge("show", "--run", self.rid, "--item", "item_1", "--max-bytes", 500)
        self.assertTrue(capped["truncated"])
        self.assertEqual(len(capped["output"].encode()), 500)
        self.assertIn("--max-bytes", capped["truncation_notice"])
        whole = self.bridge("show", "--run", self.rid, "--item", "item_1", "--max-bytes", 100000)
        self.assertFalse(whole["truncated"])
        self.assertEqual(len(whole["output"].encode()), whole["total_bytes"])
        self.assertEqual(capped["total_bytes"], whole["total_bytes"])
        self.assertEqual(whole["command"], "cat big.txt")
        self.assertIn("line 0400", whole["output"])

    def test_the_default_cap_applies_to_a_large_output(self):
        out = self.bridge("show", "--run", self.rid, "--item", "item_1")
        self.assertTrue(out["truncated"])
        self.assertGreater(out["total_bytes"], len(out["output"].encode()))

    def test_an_unknown_item_lists_what_exists(self):
        out = self.bridge("show", "--run", self.rid, "--item", "item_99", rc=1)
        self.assertIn("item_1:command_execution", out["available"])

    def test_item_ids_belong_to_one_run(self):
        second = self.bridge("resume", self.rid, "again")
        self.wait_state(second["run_id"])
        a = self.bridge("show", "--run", self.rid, "--item", "item_0")
        b = self.bridge("show", "--run", second["run_id"], "--item", "item_0")
        self.assertNotEqual(a["item"]["text"], b["item"]["text"])

    def test_a_file_change_returns_its_whole_change_list(self):
        fixture = self.tmp / "fc.jsonl"
        changes = [{"path": str(self.project / f"f{i}.py"), "kind": "add"} for i in range(3)]
        fixture.write_text("".join(json.dumps(e) + "\n" for e in [
            {"type": "thread.started", "thread_id": "t"},
            {"type": "item.completed", "item": {"id": "item_0", "type": "file_change", "changes": changes}}]))
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_state(out["run_id"])
        self.assertEqual(self.bridge("show", "--run", out["run_id"], "--item", "item_0")["changes"], changes)
        body, _ = self.log("--run", out["run_id"])
        self.assertIn("file add f0.py", body, "paths are shown relative to the run's cwd")


if __name__ == "__main__":
    unittest.main()
