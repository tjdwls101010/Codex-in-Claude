"""Reading a run's event stream: damaged lines that are counted rather than dropped, what `log` prints, and the readers that hand `status` and `result` changed paths and stderr in the skill's terms."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support.harness import BridgeCase, FIXTURES, engine

MIXED = FIXTURES / "mixed-bigout-and-failure.jsonl"


class AHalfWrittenLine(BridgeCase):

    def test_waits_until_its_line_is_complete(self):
        # The file is appended to live: a line still being written is not an event yet, and shows once it is whole.
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        events = self.runs_dir / out["run_id"] / "events.jsonl"
        before, _ = self.log("--run", out["run_id"])
        with events.open("a") as fh:
            fh.write('{"type":"turn.st')
        self.assertEqual(self.log("--run", out["run_id"])[0], before)
        with events.open("a") as fh:
            fh.write('arted"}\n')
        self.assertEqual(self.log("--run", out["run_id"])[0], before + ["turn.started"])


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
        self.assertEqual(self.result_view("--run", rid)[0]["unparsed_events"], 2)

    def test_a_finished_run_cut_off_mid_line_counts_the_fragment(self):
        rid, events = self.damaged(0)
        with events.open("a") as fh:
            fh.write('{"type":"item.completed","item":{"id":"item_9","ty')
        self.assertEqual(self.row(rid)["unparsed_events"], 1)


def stream(*events):
    """An event file holding these events built by hand, one JSON line each."""
    path = Path(tempfile.mkdtemp(prefix="codex-events-")) / "events.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return path


class EventLines(unittest.TestCase):
    """`codex.codex_cli.event_lines` on events built by hand, one kind at a time."""

    def setUp(self):
        self.codex_cli = engine("codex.codex_cli")

    def lines(self, level, *events, project=None):
        path = stream(*events)
        lines, cursor = self.codex_cli.event_lines(path, 0, level, project)
        self.assertEqual(cursor, path.stat().st_size)
        return lines

    def test_turn_lines(self):
        usage = {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2, "reasoning_output_tokens": 1}
        self.assertEqual(self.lines("compact", {"type": "thread.started", "thread_id": "t1"}, {"type": "turn.started"},
                                    {"type": "turn.completed", "usage": usage}),
                         ["thread t1", "turn.started", "turn.completed in=10 cached=4 out=2 reasoning=1"])

    def test_a_started_command_is_shown_so_a_long_one_is_not_silence(self):
        item = {"id": "item_3", "type": "command_execution", "command": "/bin/zsh -lc 'make test'"}
        self.assertEqual(self.lines("compact", {"type": "item.started", "item": item}), ["cmd.start[item_3] make test"])

    def test_items_that_only_higher_levels_show(self):
        todo = {"type": "item.completed", "item": {"id": "i", "type": "todo_list", "items": [{"text": "a"}]}}
        reasoning = {"type": "item.completed", "item": {"id": "r", "type": "reasoning", "text": "thinking"}}
        self.assertEqual(self.lines("compact", todo, reasoning), [])
        self.assertEqual(len(self.lines("normal", todo, reasoning)), 1)
        self.assertEqual(self.lines("full", todo, reasoning)[1], "reasoning thinking")

    def test_other_kinds_are_one_line_each(self):
        evs = [{"type": "item.completed", "item": {"id": "e", "type": "error", "message": "bad config"}},
               {"type": "item.completed", "item": {"id": "w", "type": "web_search", "query": "q"}},
               {"type": "item.completed", "item": {"id": "m", "type": "mcp_tool_call", "server": "s", "tool": "t",
                                                    "status": "completed"}},
               {"type": "_unparsed", "raw": "{ broken"},
               {"type": "something.new", "x": 1}]
        self.assertEqual(self.lines("compact", *evs),
                         ["error bad config", "search q", "mcp[m] s/t status=completed", "unparsed { broken",
                          'something.new {"x": 1}'])

    def test_a_file_change_is_paths_relative_to_the_run(self):
        ev = {"type": "item.completed", "item": {"id": "f", "type": "file_change",
                                                 "changes": [{"path": "/p/src/a.py", "kind": "update"}]}}
        self.assertEqual(self.lines("compact", ev, project=Path("/p")), ["file update src/a.py"])



class ItemsAndPaths(unittest.TestCase):
    """`codex.codex_cli`'s readers that hand `status` and `result` the changed paths and stderr in the skill's terms."""

    COMMAND = {"id": "item_1", "type": "command_execution", "command": "/bin/zsh -lc 'make test'",
               "aggregated_output": "ok\n", "exit_code": 2, "status": "failed"}
    CHANGE = {"id": "item_2", "type": "file_change",
              "changes": [{"path": "/p/a.py", "kind": "update"}, {"path": "/p/b.py", "kind": "add"}]}
    MESSAGE = {"id": "item_3", "type": "agent_message", "text": "done"}

    def setUp(self):
        self.codex_cli = engine("codex.codex_cli")
        self.path = stream({"type": "thread.started", "thread_id": "t"},
                           {"type": "item.started", "item": {**self.COMMAND, "aggregated_output": "", "exit_code": None}},
                           {"type": "item.completed", "item": self.COMMAND},
                           {"type": "item.completed", "item": self.CHANGE},
                           {"type": "item.completed", "item": self.MESSAGE})

    def test_changed_paths_are_every_path_a_file_change_names(self):
        self.assertEqual(self.codex_cli.changed_paths(self.path), {"/p/a.py", "/p/b.py"})

    def test_a_decomposed_path_comes_back_composed(self):
        path = stream({"type": "item.completed", "item": {"id": "i", "type": "file_change",
                                                           "changes": [{"path": "/p/cafe\u0301.txt", "kind": "add"}]}})
        self.assertEqual(self.codex_cli.changed_paths(path), {"/p/caf\u00e9.txt"})

    def test_stderr_drops_blank_lines_and_the_stdin_notice_and_keeps_the_end(self):
        path = Path(tempfile.mkdtemp(prefix="codex-stderr-")) / "stderr.log"
        path.write_text("Reading additional input from stdin...\n\nerror: one\nerror: two\n")
        self.assertEqual(self.codex_cli.stderr_tail(path), "error: one\nerror: two")
        self.assertEqual(self.codex_cli.stderr_tail(path, limit=3), "two")
        path.write_text("Reading additional input from stdin...\n")
        self.assertIsNone(self.codex_cli.stderr_tail(path))
        self.assertIsNone(self.codex_cli.stderr_tail(path.with_name("absent.log")))


if __name__ == "__main__":
    unittest.main()
