"""Reading a run's event stream: damaged lines that are counted rather than dropped, what `log` prints, and the readers that hand `status` and `result` changed paths and stderr in the skill's terms."""

from __future__ import annotations

import json
import shutil
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


class WhatLogPrints(BridgeCase):
    """`log` is one look at what a run did: every command with its exit code and output size, a failed command's output excerpted, the agent's own words whole, and a closing line naming the run and its state."""

    def setUp(self):
        super().setUp()
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": MIXED})
        self.wait_state(out["run_id"])
        self.rid = out["run_id"]
        self.body, self.end = self.log("--run", self.rid)

    def test_each_command_is_its_exit_code_and_size_without_the_shell(self):
        cmds = [ln for ln in self.body if ln.startswith("cmd ")]
        self.assertEqual(len(cmds), 3, self.body)
        self.assertRegex(cmds[0], r"^cmd exit=0 out=\d{5}B cat big\.txt$")
        self.assertRegex(cmds[1], r"^cmd exit=1 out=\d+B ls /definitely/not/a/real/path$")
        self.assertFalse([ln for ln in self.body if "/bin/zsh" in ln or "item_" in ln], "the shell wrapper and item ids are noise")

    def test_a_failed_commands_output_is_excerpted_and_a_successful_ones_is_not(self):
        excerpt = [ln for ln in self.body if ln.startswith("    | ")]
        self.assertTrue(any("No such file" in ln for ln in excerpt), self.body)
        self.assertFalse(any("quick brown fox" in ln for ln in excerpt))

    def test_the_agents_own_words_are_never_cut(self):
        self.assertIn("Exit codes, in order:\n\n1. `cat big.txt`: `0`", "\n".join(self.body))

    def test_it_ends_on_the_run_and_its_state(self):
        self.assertEqual(self.end, f"run={self.rid} state=completed")
        self.assertFalse([ln for ln in self.body if ln.startswith("run=") or ln.startswith("# ")])

    def test_the_state_and_the_events_agree_when_the_run_ends_mid_read(self):
        thread, started, done = ('{"type": "thread.started", "thread_id": "t"}\n', '{"type": "turn.started"}\n',
                                 '{"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 1}}\n')
        for start, moves, reads in (("running", ["completed"], [thread + started]),
                                    ("starting", ["running", "completed"], [thread, thread + started])):
            with self.subTest(moves=moves):
                shutil.rmtree(self.runs_dir, ignore_errors=True)
                rid = self.run_moving_mid_read(moves, reads, thread + started + done, start=start)
                body, end = self.log("--run", rid)
                self.assertEqual((body[-1], end), ("turn.completed in=7 cached=? out=1 reasoning=?", f"run={rid} state=completed"))

    def test_a_live_run_shows_the_command_it_is_inside(self):
        out, _m = self.running("y", FAKE_CODEX_FIXTURE=FIXTURES / "mid-command.jsonl")
        body, end = self.log("--run", out["run_id"])
        self.assertEqual(body[-1], "cmd.running sleep 2 && echo tick4")
        self.assertEqual(len([ln for ln in body if ln.startswith("cmd.running")]), 1, "a finished command shows only its result")
        self.assertEqual(end, f"run={out['run_id']} state=running")


def stream(*events):
    """An event file holding these events built by hand, one JSON line each."""
    path = Path(tempfile.mkdtemp(prefix="codex-events-")) / "events.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return path


class EventLines(unittest.TestCase):
    """`codex.codex_cli.event_lines` on events built by hand, one kind at a time."""

    def setUp(self):
        self.codex_cli = engine("codex.codex_cli")

    def lines(self, *events, project=None):
        return self.codex_cli.event_lines(stream(*events), rel_to=project)

    def command(self, exit_code, output, status="completed"):
        return {"type": "item.completed", "item": {"id": "item_3", "type": "command_execution", "command": "/bin/zsh -lc 'make test'",
                                                   "aggregated_output": output, "exit_code": exit_code, "status": status}}

    def test_turn_lines(self):
        usage = {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2, "reasoning_output_tokens": 1}
        self.assertEqual(self.lines({"type": "thread.started", "thread_id": "t1"}, {"type": "turn.started"},
                                    {"type": "turn.completed", "usage": usage}),
                         ["thread t1", "turn.started", "turn.completed in=10 cached=4 out=2 reasoning=1"])

    def test_a_command_still_running_is_shown_and_a_finished_one_only_by_its_result(self):
        started = {"type": "item.started", "item": {"id": "item_3", "type": "command_execution", "command": "/bin/zsh -lc 'make test'"}}
        self.assertEqual(self.lines(started), ["cmd.running make test"])
        self.assertEqual(self.lines(started, self.command(0, "ok\n")), ["cmd exit=0 out=3B make test"])

    def test_the_shell_wrapper_goes_whether_or_not_codex_quoted_the_command(self):
        bare = {"type": "item.completed", "item": {"id": "c", "type": "command_execution", "command": "/bin/zsh -lc ls",
                                                   "aggregated_output": "", "exit_code": 0}}
        self.assertEqual(self.lines(bare), ["cmd exit=0 out=0B ls"])

    def test_a_failed_command_carries_the_head_and_tail_of_its_output(self):
        self.assertEqual(self.lines(self.command(2, "boom\n", "failed")), ["cmd exit=2 out=5B make test", "    | boom"])
        big = "".join(f"line {i:04d}\n" for i in range(1000))
        lines = self.lines(self.command(1, big, "failed"))
        self.assertIn("line 0000", lines[1])
        self.assertIn("line 0999", lines[1])
        self.assertIn("bytes omitted", lines[1])
        self.assertLess(len(lines[1].encode()), 4000)

    def test_todo_lists_and_reasoning_are_left_out(self):
        todo = {"type": "item.completed", "item": {"id": "i", "type": "todo_list", "items": [{"text": "a"}]}}
        reasoning = {"type": "item.completed", "item": {"id": "r", "type": "reasoning", "text": "thinking"}}
        # Codex reports a todo list's progress as `item.updated`, between its start and its completion.
        updated = {"type": "item.updated", "item": {"id": "i", "type": "todo_list", "items": [{"text": "a", "completed": True}]}}
        self.assertEqual(self.lines(todo, updated, reasoning), [])

    def test_other_kinds_are_one_line_each(self):
        evs = [{"type": "item.completed", "item": {"id": "e", "type": "error", "message": "bad config"}},
               {"type": "item.completed", "item": {"id": "w", "type": "web_search", "query": "q"}},
               {"type": "item.completed", "item": {"id": "m", "type": "mcp_tool_call", "server": "s", "tool": "t",
                                                    "status": "completed"}},
               {"type": "_unparsed", "raw": "{ broken"},
               {"type": "something.new", "x": 1}]
        self.assertEqual(self.lines(*evs),
                         ["error bad config", "search q", "mcp s/t status=completed", "unparsed { broken",
                          'something.new {"x": 1}'])

    def test_a_file_change_is_paths_relative_to_the_run(self):
        ev = {"type": "item.completed", "item": {"id": "f", "type": "file_change",
                                                 "changes": [{"path": "/p/src/a.py", "kind": "update"}]}}
        self.assertEqual(self.lines(ev, project=Path("/p")), ["file update src/a.py"])
        empty = {"type": "item.completed", "item": {"id": "f", "type": "file_change", "changes": []}}
        self.assertEqual(self.lines(empty), ["file (no changes listed)"])


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
