"""T1 — event filtering, incremental cursors, and the `show` escape hatch.

These are the assertions that make the context-discipline claim real rather than
aspirational: if `compact` ever leaks a command's stdout, the whole reason the
filter exists is gone, and nothing else in the system would notice.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import FIXTURES, BridgeTestCase
from _events import (DEFAULT_LEVEL, final_usage, format_events, head_tail,
                     read_events, scan_progress, strip_wrapper)

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


class FinalUsage(unittest.TestCase):
    """Codex reports usage cumulatively per turn, so `final_usage` reads from
    the end and the last record wins. The docstring says so; nothing asserted
    it, and the whole behaviour is one `reversed(...)` in a comprehension —
    R17's category exactly. Found by a Codex member asked to name one untested
    behaviour of this module."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.f = self.tmp / "events.jsonl"

    def test_the_latest_usage_record_wins(self):
        first = {"input_tokens": 10, "output_tokens": 1}
        second = {"input_tokens": 25, "output_tokens": 3}
        self.f.write_text(json.dumps({"type": "turn.completed", "usage": first}) + "\n"
                          + json.dumps({"type": "turn.completed", "usage": second}) + "\n")
        self.assertEqual(final_usage(self.f), second)


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

    def test_cursor_trailer_names_the_run(self):
        """F11: a bare `# cursor=<n>` is indistinguishable between two runs in
        flight, so feeding the wrong one back is easy. The trailer must be
        self-identifying."""
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        p = self.bridge_raw("log", "--run", r["run_id"])
        self.assertEqual(p.returncode, 0, p.stderr)
        trailer = [ln for ln in p.stdout.splitlines() if ln.startswith("# cursor=")]
        self.assertEqual(len(trailer), 1)
        self.assertRegex(trailer[0], r"^# cursor=\d+ run=" + re.escape(r["run_id"]) + r"$")

    def test_an_out_of_range_since_fails_loud_instead_of_going_silent(self):
        """F11: the old guard (`since >= size`) accepted an out-of-range
        `--since` silently, printed nothing, and exited 0 — echoing the bad
        cursor straight back so the stream stayed dead forever."""
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        events_path = Path(r["events"])
        way_past = events_path.stat().st_size + 100_000
        out = self.bridge("log", "--run", r["run_id"], "--since", way_past, expect_rc=1)
        self.assertIn("past the end", out["error"])
        self.assertEqual(out["run_id"], r["run_id"])

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
                            "--follow-timeout", "45")
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


class AGroupsMidRunSignal(BridgeTestCase):
    """C9 — `log --run --follow` gives one run its events as they arrive; a
    group had no equivalent, so wanting the same thing meant arming N followers.

    A field report did the other thing instead: `status --group --follow` prints
    only state *changes*, and a twenty-minute member is `running` throughout, so
    the reviewer's bootstrap trouble, two suite failures and a render phase were
    all found by hand-polling. That reporter wrote their own polling loop, got
    its format wrong, and came within one step of reporting a false completion.
    """

    fixture = "mixed-bigout-and-failure.jsonl"

    def group(self, name="g", n=2, *extra):
        out = self.bridge("batch", "start", "--group", name, "--sandbox",
                          "read-only",
                          *[a for i in range(n) for a in ("--task", f"t{i}")],
                          *extra)
        self.assertEqual(out["spawned"], n, out)
        return out

    def follow(self, name="g", *extra):
        p = self.bridge_raw("log", "--group", name, "--follow", *extra,
                            timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        return [ln for ln in p.stdout.splitlines() if ln.strip()]

    def test_a_header_names_which_run_each_index_is(self):
        """The prefix has to be short enough to read at a glance and still lead
        back to a `stop --run`. One header line buys both."""
        g = self.group()
        lines = self.follow()
        for r in g["runs"]:
            self.assertIn(r["run_id"], lines[0])
        self.assertTrue(lines[0].startswith("group.members group=g"), lines[0])

    def test_every_event_line_says_which_member_it_came_from(self):
        g = self.group()
        body = [ln for ln in self.follow()[1:] if not ln.startswith("group.")]
        self.assertTrue(body, "the members' events did not reach the stream")
        for ln in body:
            self.assertRegex(ln, r"^\[\d+(:[^\]]+)?\] ")
        self.assertEqual({ln[1] for ln in body}, {"0", "1"},
                         "one member's stream is missing from the interleave")

    def test_the_label_rides_in_the_prefix_when_there_is_one(self):
        self.group("h", 2, "--label", "audit")
        body = [ln for ln in self.follow("h")[1:] if not ln.startswith("group.")]
        self.assertTrue(all(ln.startswith("[0:audit] ") or ln.startswith("[1:audit] ")
                            for ln in body), body[:3])

    def test_a_label_cannot_forge_a_terminal_line(self):
        """This is a line-oriented protocol and the label is caller text. A
        label holding a newline splits the header and every prefix into extra
        physical lines, and one shaped like the group's closing line puts a
        forged ending into the stream a watcher is armed on."""
        forged = "x\ngroup.completed group=hoax done=9 failed=0"
        self.bridge("batch", "start", "--group", "lbl", "--sandbox",
                    "read-only", "--label", forged, "--task", "a")
        lines = self.follow("lbl")
        group_lines = [ln for ln in lines if ln.startswith("group.")]
        self.assertEqual(len(group_lines), 2, group_lines)
        self.assertTrue(group_lines[0].startswith("group.members group=lbl"))
        self.assertRegex(group_lines[1], r"^group\.\w+ group=lbl ")
        self.assertNotIn("group=hoax", "".join(
            ln for ln in lines if ln.startswith("group.completed")))

    def test_it_ends_on_the_groups_own_terminal_line(self):
        """The same line `status --group --follow` ends on, because a watcher
        armed on either has to recognise the ending without being told which
        follower it attached."""
        self.group()
        self.assertRegex(self.follow()[-1],
                         r"^group\.\w+ group=g done=\d+ failed=\d+")

    def test_since_is_refused_because_a_group_has_no_single_cursor(self):
        """Every member has its own byte offset into its own file. One integer
        cannot address them, and accepting it would answer with some member's
        events silently dropped."""
        self.group()
        for value in ("10", "0"):
            with self.subTest(since=value):
                p = self.bridge_raw("log", "--group", "g", "--since", value)
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertIn("cursor", json.loads(p.stdout)["error"])

    def test_a_group_and_a_run_cannot_both_be_named(self):
        self.group()
        p = self.bridge_raw("log", "--group", "g", "--run", "whatever")
        self.assertEqual(p.returncode, 2, p.stdout)


class AHeartbeatSeparatesABusyRunFromADeadFollower(BridgeTestCase):
    """`follow_group` already prints `running -> stalled` after 300 idle
    seconds, so a *dead run* announces itself. What nothing announced was a live
    follower with nothing to say — and the two look identical from outside,
    which is what sent a field reporter back to hand-polling.

    Opt-in, because the line means something only to a watcher woken per event.
    """

    def test_the_group_follower_beats_while_a_member_is_working(self):
        self.bridge("batch", "start", "--group", "g", "--sandbox", "read-only",
                    "--task", "a", "--task", "b",
                    env_extra={"FAKE_CODEX_HANG": "30"})
        p = self.bridge_raw("status", "--group", "g", "--follow",
                            "--heartbeat", "1", "--follow-timeout", "4",
                            timeout=60)
        beats = [ln for ln in p.stdout.splitlines()
                 if ln.startswith("still-running ")]
        self.assertGreaterEqual(len(beats), 2, p.stdout)
        self.assertRegex(beats[0], r"^still-running elapsed=\d+ running=2$")
        self.bridge("stop", "--all")

    def test_a_single_runs_follower_beats_too(self):
        r = self.bridge("start", "x", env_extra={"FAKE_CODEX_HANG": "30"})
        self.wait_for_state(r["run_id"], ("running",), timeout=30)
        p = self.bridge_raw("log", "--run", r["run_id"], "--follow",
                            "--heartbeat", "1", "--follow-timeout", "4",
                            timeout=60)
        beats = [ln for ln in p.stdout.splitlines()
                 if ln.startswith("still-running ")]
        self.assertGreaterEqual(len(beats), 2, p.stdout)
        self.assertRegex(beats[0], r"^still-running elapsed=\d+ running=1$")
        self.bridge("stop", "--all")

    def test_it_is_refused_where_nothing_could_print_it(self):
        """A flag that parses and decides nothing reads as having been obeyed,
        which is the whole reason five of them were retired this round."""
        r = self.bridge("start", "x")
        self.wait_for_state(r["run_id"])
        for extra in (("--heartbeat", "1"),
                      ("--heartbeat", "0", "--follow"),
                      ("--heartbeat", "-1", "--follow")):
            with self.subTest(args=extra):
                out = self.bridge("log", "--run", r["run_id"], *extra,
                                  expect_rc=1)
                self.assertIn("--heartbeat", out["error"])

    def test_a_group_follower_refuses_it_the_same_way(self):
        self.bridge("batch", "start", "--group", "g", "--sandbox", "read-only",
                    "--task", "a")
        out = self.bridge("status", "--group", "g", "--heartbeat", "1",
                          expect_rc=1)
        self.assertIn("--heartbeat", out["error"])

    def test_off_by_default(self):
        r = self.bridge("start", "x", env_extra={"FAKE_CODEX_HANG": "3"})
        p = self.bridge_raw("log", "--run", r["run_id"], "--follow",
                            timeout=60)
        self.assertNotIn("still-running", p.stdout)


if __name__ == "__main__":
    unittest.main()
