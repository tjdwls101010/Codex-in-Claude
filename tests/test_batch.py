"""Batches: N runs under one name, validated before anything starts, recorded slot by slot, and continued positionally with --resume-from.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import unittest

from support.harness import BridgeCase, alive, wait_until


class BatchCase(BridgeCase):

    def manifest(self, name):
        return json.loads((self.runs_dir / ".groups" / f"{name}.json").read_text())

    def batch(self, name, *tasks, extra=(), **kw):
        args = [a for t in tasks for a in ("--task", t)]
        return self.bridge("batch", "start", "--group", name, *extra, *args, **kw)

    def assert_cost_nothing(self, before_dirs, before_groups):
        self.assertEqual(self.run_dirs(), before_dirs)
        self.assertEqual(self.bridge("status")["groups"], before_groups)


class Starting(BatchCase):

    def test_members_start_in_order_and_the_manifest_records_it(self):
        out = self.batch("p1", "alpha", "bravo", "charlie")
        self.assertEqual((out["spawned"], out["requested"]), (3, 3))
        self.assertNotIn("projected_cost", out, "an estimate arriving after the spawn cannot inform it")
        ids = [r["run_id"] for r in out["runs"]]
        self.assertEqual(len(set(ids)), 3)
        self.wait_all(out)
        members = self.manifest("p1")["members"]
        self.assertEqual([m["run_id"] for m in members], ids)
        self.assertEqual([m["index"] for m in members], [0, 1, 2])
        prompts = [r["argv"][-1] for r in self.runs_invoked()]
        for word, prompt in zip(("alpha", "bravo", "charlie"), prompts):
            self.assertTrue(prompt.endswith(word))
            self.assertIn('group "p1"', prompt)
            self.assertIn("batch of 3 tasks", prompt)

    def test_group_options_are_defaults_a_task_overrides(self):
        tf = self.tasks_file({"prompt": "a", "label": "A"}, {"prompt": "b", "label": "B", "sandbox": "read-only"})
        out = self.bridge("batch", "start", "--group", "p1", "--sandbox", "danger-full-access",
                          "--task", "first", "--label", "flag", "--tasks-file", tf)
        self.assertEqual([r["label"] for r in out["runs"]], ["flag", "A", "B"])
        self.assertEqual([r["sandbox"] for r in out["runs"]], ["danger-full-access"] * 2 + ["read-only"])
        self.wait_all(out)
        self.assertEqual([self.config_values(r["argv"])["sandbox_mode"] for r in self.runs_invoked()],
                         ['"danger-full-access"'] * 2 + ['"read-only"'])

    def test_a_name_is_single_use_and_a_refusal_costs_nothing(self):
        self.wait_all(self.batch("p1", "x"))
        before = self.run_dirs()
        refused = self.batch("p1", "y", rc=1)
        self.assertIn("already exists", refused["error"])
        self.assertEqual(self.run_dirs(), before)

    def test_a_name_that_could_escape_the_registry_is_refused(self):
        self.assertIn("path separators", self.batch("../oops", "x", rc=2)["error"])

    def test_prompt_and_image_are_per_task_fields_only(self):
        img = self.tmp / "a.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")
        prompt = self.tmp / "p.md"
        prompt.write_text("from a file")
        for flag, value in (("--prompt-file", prompt), ("--image", img)):
            with self.subTest(flag=flag):
                self.assertIn("unrecognized arguments",
                              self.bridge("batch", "start", "--group", "p1", flag, value, "--task", "x", rc=2)["error"])
        self.assertEqual(self.run_dirs(), [])
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file",
                          self.tasks_file({"prompt": "look", "image": [str(img)]}))
        self.wait_all(out)
        argv = self.last_argv()
        self.assertEqual(argv[argv.index("-i") + 1], str(img))

    def test_reading_stdin_for_one_task_leaves_it_usable_for_the_next(self):
        out = self.batch("p1", "-", "-", stdin="from stdin")
        self.assertEqual((out["spawned"], out["requested"]), (2, 2), out)
        self.wait_all(out)

    def test_a_batch_needs_a_task(self):
        self.assertIn("at least one", self.bridge("batch", "start", "--group", "p1", rc=2)["error"])


class TasksAreValidatedBeforeAnythingStarts(BatchCase):

    CASES = [
        ({"prompt": "a", "sandox": "read-only"}, "unknown field"),
        ({"prompt": 123}, "'prompt' must be str"),
        ({"prompt": "a", "image": "one.png"}, "'image' must be list"),
        ({"prompt": "a", "image": [7]}, "list of paths"),
        ({"prompt": "a", "kind": "fork"}, "kind must be start or resume"),
        ({"prompt": "a", "kind": "resume"}, "needs a 'resume' field"),
        ({"prompt": "a", "model": "no-such-model"}, "unknown model"),
        ({"prompt": "a", "model": "fake-small", "effort": "ultra"}, "does not accept effort"),
    ]

    def test_each_broken_task_refuses_the_batch_and_names_its_line(self):
        for bad, message in self.CASES:
            with self.subTest(bad=bad):
                tf = self.tasks_file("fine", bad)
                refused = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf, rc=2)
                self.assertIn(message, refused["error"])
                self.assertRegex(refused["error"], r"(line|task) 2")
        self.assert_cost_nothing([], [])

    def test_a_line_that_is_not_json_is_named(self):
        tf = self.tmp / "bad.jsonl"
        tf.write_text('{"prompt": "ok"}\nnot json\n')
        self.assertIn("line 2", self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf, rc=2)["error"])

    def test_blank_lines_and_comments_are_skipped(self):
        tf = self.tmp / "t.jsonl"
        tf.write_text('# a comment\n\n{"prompt": "only"}\n')
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        self.assertEqual(out["spawned"], 1)
        self.wait_all(out)


class OneMemberFailingDoesNotTakeTheOthers(BatchCase):

    def test_a_member_that_cannot_spawn_keeps_its_slot(self):
        tf = self.tasks_file("good one", {"prompt": "bad", "schema": "/nonexistent/schema.json"}, "good two")
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        self.assertEqual((out["requested"], out["spawned"]), (3, 2))
        self.assertEqual([r["index"] for r in out["runs"]], [0, 1, 2])
        self.assertIn("schema", out["runs"][1]["error"])
        self.assertNotIn("run_id", out["runs"][1])
        self.wait_all(out)
        self.assertNotIn("run_id", self.manifest("p1")["members"][1])
        status = self.bridge("status", "--group", "p1")
        self.assertEqual(status["group_state"], "partial")
        self.assertEqual([u["index"] for u in status["unstarted"]], [1])

    def test_members_that_spawned_before_the_batch_was_killed_stay_reachable(self):
        p = self.spawn("batch", "start", "--group", "p1", "--task", "one", "--task", "two", "--task", "three",
                       env={"FAKE_CODEX_PRE_DELAY": 6, "FAKE_CODEX_HANG": 30})
        path = self.runs_dir / ".groups" / "p1.json"
        spawned = wait_until(lambda: path.exists() and [m["run_id"] for m in self.manifest("p1")["members"]
                                                        if m.get("run_id")], timeout=40)
        self.assertTrue(spawned)
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        status = self.bridge("status", "--group", "p1")
        self.assertEqual(sorted(r["run_id"] for r in status["runs"]), sorted(spawned))
        self.assertEqual(len(status["unstarted"]), 3 - len(spawned))
        self.assertEqual(status["group_state"], "running")
        stopped = self.bridge("stop", "--group", "p1")["stopped"]
        self.assertEqual(sorted(s["run_id"] for s in stopped), sorted(spawned))
        for rid in spawned:
            self.wait_state(rid)
        self.assertEqual(self.bridge("status", "--group", "p1")["group_state"], "partial")


class ResumeFrom(BatchCase):
    """Phase two pairs task i with member i of phase one, in start order, and refuses the whole batch before claiming anything when a pairing cannot be honoured."""

    def phase_one(self, *tasks, **kw):
        out = self.batch("p1", *(tasks or ("a", "b")), **kw)
        return out

    def test_task_i_resumes_member_i(self):
        one = self.phase_one()
        self.wait_all(one)
        two = self.batch("p2", "go on a", "go on b", extra=("--resume-from", "p1"))
        self.wait_all(two)
        resumed = [r for r in self.runs_invoked() if r["argv"][1] == "resume"]
        self.assertEqual([r["argv"][2] for r in resumed], [r["thread_id"] for r in one["runs"]])
        self.assertTrue(resumed[0]["argv"][-1].endswith("go on a"))
        self.assertEqual(two["resumed_from"], {"group": "p1", "members": [r["run_id"] for r in one["runs"]]})
        self.assertEqual(self.manifest("p2")["derived_from"], "p1")

    def test_a_task_that_names_its_own_target_keeps_it(self):
        one = self.phase_one()
        target = self.bridge("start", "outside the group")
        self.wait_all(one)
        self.wait_state(target["run_id"])
        tf = self.tasks_file({"prompt": "x", "kind": "resume", "resume": target["run_id"]}, "y")
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1", "--tasks-file", tf)
        self.wait_all(two)
        resumed = [r["argv"][2] for r in self.runs_invoked() if r["argv"][1] == "resume"]
        self.assertEqual(resumed, [target["thread_id"], one["runs"][1]["thread_id"]])

    def test_a_resume_field_on_a_start_task_is_ambiguous(self):
        one = self.phase_one()
        self.wait_all(one)
        tf = self.tasks_file({"prompt": "x", "resume": one["runs"][0]["run_id"]}, "y")
        refused = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1", "--tasks-file", tf, rc=2)
        self.assertIn("kind", refused["error"])

    def refused(self, *tasks, extra=()):
        before_dirs, before_groups = self.run_dirs(), self.bridge("status")["groups"]
        out = self.batch("p2", *tasks, extra=("--resume-from", "p1", *extra), rc=1)
        self.assert_cost_nothing(before_dirs, before_groups)
        return out

    def test_an_unknown_group(self):
        self.assertIn("no such group", self.refused("x")["error"])

    def test_a_manifest_that_will_not_parse(self):
        self.wait_all(self.phase_one())
        (self.runs_dir / ".groups" / "p1.json").write_text("{ truncated")
        self.assertIn("will not parse", self.refused("x", "y")["error"])

    def test_a_group_where_nothing_started(self):
        tf = self.tasks_file({"prompt": "bad", "schema": "/nonexistent.json"})
        self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        self.assertIn("no members that started", self.refused("x")["error"])

    def test_a_member_with_no_thread(self):
        one = self.phase_one(env={"FAKE_CODEX_FIXTURE": os.devnull, "FAKE_CODEX_EXIT": 1})
        self.wait_all(one)
        refused = self.refused("x", "y")
        self.assertIn("thread id", refused["error"])
        self.assertEqual(sorted(refused["members"]), sorted(r["run_id"] for r in one["runs"]))

    def test_a_member_whose_run_directory_is_gone(self):
        one = self.phase_one()
        self.wait_all(one)
        shutil.rmtree(self.runs_dir / one["runs"][1]["run_id"])
        before = len(self.runs_invoked())
        self.assertIn("thread id", self.refused("x", "y")["error"])
        self.assertEqual(len(self.runs_invoked()), before, "no member of phase two may start")

    def test_a_count_mismatch(self):
        self.wait_all(self.phase_one())
        self.assertIn("2 started member(s)", self.refused("only one")["error"])

    def test_a_member_still_running(self):
        one = self.phase_one(env={"FAKE_CODEX_HANG": 60})
        refused = self.refused("x", "y")
        self.assertEqual(sorted(m["run_id"] for m in refused["running"]), sorted(r["run_id"] for r in one["runs"]))

    def test_a_member_whose_supervisor_died_while_its_codex_writes(self):
        one = self.phase_one("a", env={"FAKE_CODEX_HANG": 60})
        rid = one["runs"][0]["run_id"]
        m = wait_until(lambda: (lambda m: m if m.get("codex_pid") else None)(self.meta(rid)), timeout=30)
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        wait_until(lambda: not alive(m["supervisor_pid"]), timeout=10)
        self.assertEqual(self.row(rid)["state"], "orphaned")
        self.assertEqual([x["run_id"] for x in self.refused("x")["running"]], [rid])

    def test_writers_sharing_a_tree_are_counted_with_the_sandbox_they_will_get(self):
        one = self.batch("p1", "a", "b", extra=("--sandbox", "read-only"))
        self.wait_all(one)
        two = self.batch("p2", "x", "y", extra=("--resume-from", "p1", "--sandbox", "workspace-write"))
        self.wait_all(two)
        self.assertEqual([r["sandbox"] for r in two["runs"]], ["workspace-write"] * 2)
        self.assertIn(f"2 members write to {self.project}", two["worktrees"]["note"])

    def test_force_continues_live_members_anyway(self):
        one = self.phase_one(env={"FAKE_CODEX_HANG": 60})
        two = self.batch("p2", "x", "y", extra=("--resume-from", "p1", "--force"))
        self.assertEqual(two["spawned"], 2)
        self.assertEqual([r["kind"] for r in two["runs"]], ["resume", "resume"])
        del one


class FollowingAGroup(BatchCase):

    def test_log_group_interleaves_members_behind_a_header_and_ends_on_the_group(self):
        fixture = self.tmp / "two-line.jsonl"
        fixture.write_text("".join(json.dumps(e) + "\n" for e in [
            {"type": "thread.started", "thread_id": "t"},
            {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": "line one\nline two"}}]))
        tf = self.tasks_file({"prompt": "a", "label": "alpha"}, {"prompt": "b"},
                             {"prompt": "c", "label": "x\ngroup.completed group=g done=9 failed=0"})
        out = self.bridge("batch", "start", "--group", "g", "--tasks-file", tf, env={"FAKE_CODEX_FIXTURE": fixture})
        self.wait_all(out)
        lines = self.bridge_raw("log", "--group", "g", "--follow").stdout.splitlines()
        ids = [r["run_id"] for r in out["runs"]]
        self.assertEqual(lines[0], f"group.members group=g 0={ids[0]}:alpha 1={ids[1]} "
                                   f"2={ids[2]}:x group.completed group=g done=9 failed=0")
        body = lines[1:-1]
        self.assertIn("[0:alpha] msg line one", body)
        self.assertIn("[0:alpha] line two", body, "every physical line carries its member")
        self.assertIn("[1] msg line one", body)
        for ln in body:
            self.assertRegex(ln, r"^\[\d(:[^\]]+)?\] ")
        self.assertEqual(lines[-1], "group.completed group=g done=3 failed=0")

    def test_a_live_group_follow_can_be_bounded(self):
        self.batch("g", "a", env={"FAKE_CODEX_HANG": 60})
        p = self.bridge_raw("status", "--group", "g", "--follow", "--follow-timeout", 1.5)
        self.assertRegex(p.stdout.splitlines()[-1], r"^group\.still-running group=g running=1 done=0 failed=0$")
        p = self.bridge_raw("log", "--group", "g", "--follow", "--follow-timeout", 1.5)
        self.assertRegex(p.stdout.splitlines()[-1], r"^group\.still-running group=g ")

    def test_stopping_a_group_ends_it_partial(self):
        out = self.batch("g", "a", "b", env={"FAKE_CODEX_HANG": 60})
        for r in out["runs"]:
            self.wait_state(r["run_id"], ("running",))
        self.assertEqual(len(self.bridge("stop", "--group", "g")["stopped"]), 2)
        p = self.bridge_raw("status", "--group", "g", "--follow", "--follow-timeout", 30)
        self.assertEqual(p.stdout.splitlines()[-1], "group.partial group=g done=0 failed=2")


if __name__ == "__main__":
    unittest.main()
