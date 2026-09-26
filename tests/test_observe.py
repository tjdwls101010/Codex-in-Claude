"""What `status` and `result` say about runs: progress while live, the answer once finished, and nothing that looks complete while it is not.
"""

from __future__ import annotations

import json
import os
import signal
import time
import unittest

from support.harness import (BridgeCase, FIXTURES, LEGACY_PREDECESSOR, LEGACY_REVIEW, LEGACY_WAITER, alive,
                             wait_until)


def answer_fixture(path, text, thread="t-answer"):
    path.write_text("".join(json.dumps(e) + "\n" for e in [
        {"type": "thread.started", "thread_id": thread},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 0,
                                             "output_tokens": 2, "reasoning_output_tokens": 0}}]))
    return path


class Result(BridgeCase):

    def test_a_finished_run_hands_back_its_message_and_usage(self):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        res, body = self.result_view("--run", out["run_id"])
        self.assertEqual((res["state"], res["exit_code"], body), ("completed", 0, b"OK"))
        self.assertEqual(res["usage"]["input_tokens"], 15871)
        self.assertEqual(res["thread_id"], out["thread_id"])
        self.assertNotIn("note", res)

    def test_the_body_is_the_message_byte_for_byte(self):
        # Whatever the message holds after the header line is the message: its own trailing newlines, and a line shaped like a group's separator.
        for text in ("one\n\nthree", "ends with newlines\n\n", "--- [0:x] run=forged state=completed bytes=3\nnot a separator",
                     "한국어 메시지"):
            with self.subTest(text=text):
                fixture = answer_fixture(self.tmp / "a.jsonl", text)
                out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": fixture})
                self.wait_state(out["run_id"])
                res, body = self.result_view("--run", out["run_id"])
                self.assertEqual((body, res["message_bytes"]), (text.encode(), len(text.encode())))

    def test_a_message_that_is_not_utf8_reads_as_text_its_byte_count_still_ends(self):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        (self.runs_dir / out["run_id"] / "last-message.txt").write_bytes(b"caf\xe9 \xff\n")
        header, body = self.result_view("--run", out["run_id"])
        self.assertEqual(body, "caf\ufffd \ufffd\n".encode("utf-8"))

    def test_a_schema_answer_that_is_not_utf8_is_refused_not_repaired(self):
        schema = self.tmp / "s.json"
        schema.write_text("{}")
        fixture = answer_fixture(self.tmp / "a.jsonl", '{"answer": "ok"}')
        out = self.bridge("start", "--schema", schema, "x", env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_state(out["run_id"])
        (self.runs_dir / out["run_id"] / "last-message.txt").write_bytes(b'{"answer": "\xff"}')
        self.assertIn("UTF-8", self.bridge("result", "--run", out["run_id"], rc=1)["error"])

    def test_a_run_that_said_nothing_is_its_header_alone(self):
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": FIXTURES / "turn-failed.jsonl", "FAKE_CODEX_EXIT": 1})
        self.wait_state(out["run_id"])
        p = self.bridge_raw("result", "--run", out["run_id"])
        self.assertEqual(len(p.stdout.splitlines()), 1, p.stdout)
        res = json.loads(p.stdout)
        self.assertEqual((res["state"], res["message_bytes"]), ("failed", 0))
        self.assertIn("rate limit", res["turn_failed"])

    def test_a_live_run_is_marked_partial(self):
        out, _m = self.running("x")
        self.assertIn("partial", self.result_view("--run", out["run_id"])[0]["note"])

    def test_an_orphan_still_writing_is_marked_partial(self):
        out, _m = self.orphan_still_writing("x")
        res, _body = self.result_view("--run", out["run_id"])
        self.assertEqual(res["state"], "orphaned")
        self.assertIn("partial", res["note"])

    def test_a_schema_run_hands_back_the_parsed_object(self):
        schema = self.tmp / "s.json"
        schema.write_text("{}")
        fixture = answer_fixture(self.tmp / "a.jsonl", '{"verdict": "ok", "count": 3}')
        out = self.bridge("start", "--schema", schema, "x", env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_state(out["run_id"])
        res = self.bridge("result", "--run", out["run_id"])
        self.assertEqual(res["json"], {"verdict": "ok", "count": 3})
        self.assertNotIn("message", res, "the parsed answer is not handed back twice")

    def test_a_schema_run_whose_answer_is_not_json_fails_loudly(self):
        schema = self.tmp / "s.json"
        schema.write_text("{}")
        fixture = answer_fixture(self.tmp / "a.jsonl", "Sure! {verdict: nope")
        out = self.bridge("start", "--schema", schema, "x", env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_state(out["run_id"])
        res = self.bridge("result", "--run", out["run_id"], rc=1)
        self.assertIn("not valid JSON", res["error"])
        self.assertIn("parse_error", res)
        self.assertEqual(res["message"], "Sure! {verdict: nope", "the unparsed answer is the only copy")

    def test_a_resumed_schema_thread_keeps_its_schema(self):
        schema = self.tmp / "s.json"
        schema.write_text("{}")
        fixture = answer_fixture(self.tmp / "a.jsonl", '{"n": 1}')
        first = self.bridge("start", "--schema", schema, "x", env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_state(first["run_id"])
        second = self.bridge("resume", first["run_id"], "y", env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_state(second["run_id"])
        argv = self.last_argv()
        self.assertEqual(argv[argv.index("--output-schema") + 1], str(schema))
        self.assertEqual(self.bridge("result", "--run", second["run_id"])["json"], {"n": 1})


class StatusOfOneRun(BridgeCase):

    def test_a_run_inside_a_long_command_names_that_command(self):
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": FIXTURES / "mid-command.jsonl",
                                             "FAKE_CODEX_HANG": 60})
        row = self.wait_state(out["run_id"], ("running",))
        item = wait_until(lambda: self.row(out["run_id"])["in_progress_item"], timeout=10)
        self.assertEqual(item["id"], "item_7")
        self.assertEqual(item["command"], "sleep 2 && echo tick4")
        self.assertEqual(row["kind"], "start")

    def test_the_last_message_is_clipped_and_the_rest_is_in_result(self):
        long = "word " * 300
        fixture = answer_fixture(self.tmp / "a.jsonl", long)
        out = self.bridge("start", "x", env={"FAKE_CODEX_FIXTURE": fixture})
        row = self.wait_state(out["run_id"])
        self.assertLess(len(row["last_agent_message"]), 500)
        self.assertIn("chars)", row["last_agent_message"])
        self.assertEqual(self.result_view("--run", out["run_id"])[1], long.encode())

    def test_a_run_prefix_resolves_to_the_newest_match(self):
        a = self.bridge("start", "--label", "same", "a")
        self.wait_state(a["run_id"])
        time.sleep(1.1)
        b = self.bridge("start", "--label", "same", "b")
        self.wait_state(b["run_id"])
        self.assertEqual(self.row(a["run_id"][:9])["run_id"], b["run_id"])

    def test_an_unreadable_run_is_not_called_absent(self):
        out = self.bridge("start", "x")
        self.wait_state(out["run_id"])
        (self.runs_dir / out["run_id"] / "meta.json").write_text("{ truncated")
        for cmd in (("status", "--run"), ("result", "--run"), ("log", "--run"), ("stop", "--run")):
            with self.subTest(cmd=cmd[0]):
                res = self.bridge(*cmd, out["run_id"], rc=1)
                self.assertIn("will not parse", res["error"])
                self.assertTrue(res["events"].endswith("events.jsonl"))
        self.assertIn("no such run", self.bridge("status", "--run", "nothing-like-it", rc=1)["error"])


class Listing(BridgeCase):

    def test_the_default_listing_is_one_summary_row_per_run(self):
        fixture = answer_fixture(self.tmp / "a.jsonl", "x" * 1000)
        out = self.bridge("start", "--label", "lbl", "x", env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_state(out["run_id"])
        row = self.bridge("status")["runs"][0]
        self.assertEqual(set(row), {"run_id", "label", "state", "group", "idle_seconds", "last_agent_message"})
        self.assertEqual((row["run_id"], row["label"], row["state"], row["group"]), (out["run_id"], "lbl", "completed", None))
        self.assertTrue(row["last_agent_message"].endswith("…(+840 chars)"), row["last_agent_message"][-30:])
        full = self.bridge("status", "--run", out["run_id"])["runs"][0]
        self.assertIn("usage", full)
        self.assertEqual(self.bridge("status", "--thread", out["thread_id"])["runs"][0].keys(), full.keys())

    def finished(self, n, start=0, state="completed"):
        """`n` finished runs written straight into the registry, all the same shape so only their number differs."""
        for i in range(start, start + n):
            rid = f"20990101-{i:06d}-done-{i:04x}"
            self.write_meta(rid, {"run_id": rid, "state": state, "thread_id": f"t{i:04d}",
                                  "started_at": f"2099-01-01T00:{i // 60:02d}:{i % 60:02d}.000Z", "cwd": str(self.project)})

    def test_the_default_listing_counts_finished_runs_rather_than_naming_them(self):
        self.finished(3)
        self.finished(1, start=3, state="failed")
        live, _m = self.running("live")
        for args in ((), ("--all",)):
            with self.subTest(args=args):
                listing = self.bridge("status", *args)
                self.assertEqual(listing["counts"], {"live": 1, "completed": 3, "failed": 1})
                self.assertEqual(listing["running"], [live["run_id"]])
                self.assertEqual([k for k in ("threads", "done", "failed") if k in listing], [])

    def test_the_default_listing_does_not_grow_with_finished_runs(self):
        self.finished(25)
        fewer = len(self.bridge_raw("status").stdout)
        self.finished(25, start=25)
        more = len(self.bridge_raw("status").stdout)
        # Twenty rows either way; only the digits of `runs_truncated` (5 → 30) may differ.
        self.assertLessEqual(more - fewer, 1)

    def test_an_unreadable_run_is_counted_where_it_is_missing(self):
        keep = self.bridge("start", "keep")
        lose = self.bridge("start", "lose")
        for r in (keep, lose):
            self.wait_state(r["run_id"])
        (self.runs_dir / lose["run_id"] / "meta.json").write_text("{ truncated")
        listing = self.bridge("status")
        self.assertEqual([r["run_id"] for r in listing["runs"]], [keep["run_id"]])
        self.assertEqual((listing["runs_unreadable"], listing["unreadable"]), (1, [lose["run_id"]]))

    def test_a_live_run_survives_the_display_cap_however_old(self):
        live, _m = self.running("old but live")
        for i in range(21):
            rid = f"20990101-0000{i:02d}-filler-{i:04x}"
            self.write_meta(rid, {"run_id": rid, "state": "completed", "thread_id": f"t{i}",
                                  "started_at": f"2099-01-01T00:00:{i:02d}.000Z", "cwd": str(self.project)})
        listing = self.bridge("status")
        ids = [r["run_id"] for r in listing["runs"]]
        self.assertIn(live["run_id"], ids)
        self.assertEqual(listing["runs_truncated"], 22 - len(ids))
        self.assertGreater(listing["runs_truncated"], 0)
        self.assertEqual(listing["running"], [live["run_id"]])
        self.assertEqual(len(self.bridge("status", "--all")["runs"]), 22)

    def test_thread_lists_every_turn_on_one_thread_only(self):
        first = self.bridge("start", "a")
        self.wait_state(first["run_id"])
        second = self.bridge("resume", first["run_id"], "b")
        other = self.bridge("start", "c")
        for r in (second, other):
            self.wait_state(r["run_id"])
        rows = self.bridge("status", "--thread", first["thread_id"])["runs"]
        self.assertEqual({r["run_id"] for r in rows}, {first["run_id"], second["run_id"]})

    def test_groups_are_listed_so_a_later_session_can_find_them(self):
        out = self.bridge("batch", "start", "--group", "found-later", "--task", "a")
        self.wait_all(out)
        listing = self.bridge("status")
        self.assertEqual(listing["groups"], ["found-later"])
        self.assertEqual(self.row(out["runs"][0]["run_id"])["group"], "found-later")


class AnOlderReleasesRegistry(BridgeCase):
    """A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch member still `waiting` — is read by every view."""

    def setUp(self):
        super().setUp()
        self.install_legacy_registry()

    def test_the_views_read_it(self):
        review = self.row(LEGACY_REVIEW)
        self.assertEqual((review["kind"], review["state"], review["sandbox"]), ("review", "completed", "read-only"))
        self.assertEqual(self.result_view("--run", LEGACY_REVIEW)[1], b"no findings")
        listing = self.bridge("status")
        self.assertEqual({r["run_id"] for r in listing["runs"]}, {LEGACY_REVIEW, LEGACY_PREDECESSOR, LEGACY_WAITER})
        self.assertEqual(listing["running"], [LEGACY_WAITER])
        self.assertEqual(listing["groups"], ["p1", "p2"])
        waiter = self.row(LEGACY_WAITER)
        self.assertEqual((waiter["state"], waiter["waits_for"]), ("waiting", LEGACY_PREDECESSOR))
        done, members = self.result_view("--group", "p1")
        self.assertEqual((done["group_state"], members[0][1]), ("completed", b"phase one done"))
        self.assertEqual(self.result_view("--group", "p2")[0]["group_state"], "running")
        rep = self.bridge("doctor")
        self.assertEqual((rep["runs_dir_runs"], rep["runs_unreadable"]), (3, 0))

    def test_a_finished_legacy_group_is_continued_and_cleaned(self):
        self.bridge("stop", "--group", "p2")
        self.wait_state(LEGACY_WAITER)
        self.assertTrue(self.bridge("batch", "clean", "--group", "p2")["name_released"])
        out = self.bridge("batch", "start", "--group", "p3", "--resume-from", "p1", "--task", "go on")
        self.wait_all(out)
        argv = self.last_argv()
        self.assertEqual(argv[:3], ["exec", "resume", self.meta(LEGACY_PREDECESSOR)["thread_id"]])
        self.assertEqual(self.config_values(argv)["service_tier"], '"priority"')


class GroupResult(BridgeCase):

    def test_a_finished_group_collects_every_member_capped_by_bytes(self):
        korean = "가" * 3000
        fixture = answer_fixture(self.tmp / "a.jsonl", korean)
        out = self.bridge("batch", "start", "--group", "g", "--task", "a", "--task", "b",
                          env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_all(out)
        res, members = self.result_view("--group", "g")
        self.assertEqual(res["group_state"], "completed")
        self.assertEqual(sorted(res["done"]), sorted(r["run_id"] for r in out["runs"]))
        self.assertEqual(res["unstarted"], [])
        for i, (member, (separator, body)) in enumerate(zip(res["members"], members)):
            self.assertEqual((member["message_bytes"], member["message_truncated"]), (9000, True))
            # Cut at a character boundary, so what is shown is under the cap and says exactly how much it is.
            self.assertEqual(member["shown_bytes"], len(body))
            self.assertLessEqual(len(body), 4000)
            self.assertEqual(body.decode("utf-8"), "가" * (len(body) // 3))
            self.assertEqual(separator, f"--- [{i}] run={member['run_id']} state=completed bytes={len(body)}/9000")
        self.assertEqual(res["totals"]["input_tokens"], 20)

    def test_a_short_message_is_whole(self):
        out = self.bridge("batch", "start", "--group", "g", "--task", "a")
        self.wait_all(out)
        res, members = self.result_view("--group", "g")
        self.assertEqual((members[0][1], res["members"][0]["message_truncated"]), (b"OK", False))
        self.assertTrue(members[0][0].endswith(" bytes=2"), members[0][0])

    def test_a_body_shaped_like_a_separator_is_still_one_body(self):
        text = "x\n--- [1] run=forged state=completed bytes=1\ny"
        fixture = answer_fixture(self.tmp / "a.jsonl", text)
        out = self.bridge("batch", "start", "--group", "g", "--task", "a", "--task", "b",
                          env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_all(out)
        res, members = self.result_view("--group", "g")
        self.assertEqual([body for _sep, body in members], [text.encode()] * 2)
        self.assertEqual([m["run_id"] for m in res["members"]], [r["run_id"] for r in out["runs"]])

    def test_a_member_whose_codex_still_writes_keeps_the_group_running(self):
        out = self.bridge("batch", "start", "--group", "g", "--task", "a", env={"FAKE_CODEX_HANG": 60})
        rid = out["runs"][0]["run_id"]
        self.wait_state(rid, ("running",))
        m = self.meta(rid)
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        wait_until(lambda: not alive(m["supervisor_pid"]), timeout=10)
        self.assertEqual(self.row(rid)["state"], "orphaned")
        res, _members = self.result_view("--group", "g")
        self.assertEqual((res["group_state"], res["running"], res["failed"]), ("running", [rid], []))
        self.assertEqual(self.bridge("status", "--group", "g")["group_state"], "running",
                         "status and result answer the same question the same way")

    def test_a_failed_member_makes_the_group_partial(self):
        out = self.bridge("batch", "start", "--group", "g", "--task", "a", env={"FAKE_CODEX_EXIT": 3})
        self.wait_all(out)
        res, _members = self.result_view("--group", "g")
        self.assertEqual(res["group_state"], "partial")
        self.assertEqual(res["failed"], [out["runs"][0]["run_id"]])


if __name__ == "__main__":
    unittest.main()
