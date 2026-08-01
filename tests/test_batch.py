"""T1 — batch groups: starting one, addressing one, and collecting one.

The worktree half of `batch start` is M4b and is not exercised here.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import unittest

from helpers import BRIDGE, BridgeTestCase   # puts the scripts dir on sys.path

import _batch                                # noqa: E402


class BatchStart(BridgeTestCase):

    def groups_dir(self):
        return self.project / ".codex-runs" / ".groups"

    def test_starts_every_task_and_records_them_in_order(self):
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "alpha", "--task", "bravo", "--task", "charlie")
        self.assertEqual(out["group"], "p1")
        self.assertEqual(out["spawned"], 3)
        self.assertEqual(out["requested"], 3)
        ids = [r["run_id"] for r in out["runs"]]
        self.assertEqual(len(set(ids)), 3, "each member needs its own run")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

        manifest = json.loads((self.groups_dir() / "p1.json").read_text())
        self.assertEqual([m["run_id"] for m in manifest["members"]], ids,
                         "the manifest records start order, and --resume-from "
                         "pairs positionally against exactly this list")
        self.assertEqual([m["index"] for m in manifest["members"]], [0, 1, 2])

    def test_a_group_name_is_single_use(self):
        """D36. Reusing a name would make 'the members of p1' ambiguous — six
        runs, not three — and --resume-from would silently pair the wrong ones."""
        self.bridge("batch", "start", "--group", "p1", "--task", "x")
        out = self.bridge("batch", "start", "--group", "p1", "--task", "y",
                          expect_rc=1)
        self.assertIn("already exists", out["error"])
        self.assertEqual(out["members"], 1)

    def test_the_name_is_claimed_before_anything_spawns(self):
        """A duplicate name must cost nothing, so the claim happens before the
        first Codex process, not after."""
        self.bridge("batch", "start", "--group", "p1", "--task", "x")
        before = len(list((self.project / ".codex-runs").glob("2*")))
        self.bridge("batch", "start", "--group", "p1", "--task", "y", expect_rc=1)
        after = len(list((self.project / ".codex-runs").glob("2*")))
        self.assertEqual(before, after, "the rejected batch spawned a run anyway")

    def test_a_group_needs_at_least_one_task(self):
        out = self.bridge("batch", "start", "--group", "p1", expect_rc=1)
        self.assertIn("at least one", out["error"])

    def test_a_group_name_may_not_escape_the_groups_directory(self):
        out = self.bridge("batch", "start", "--group", "../oops", "--task", "x",
                          expect_rc=1)
        self.assertIn("path separators", out["error"])

    def test_group_level_options_reach_every_member(self):
        out = self.bridge("batch", "start", "--group", "p1", "--sandbox", "read-only",
                          "--task", "x", "--task", "y")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
            self.assertEqual(r["sandbox"], "read-only")
        for rec in self.argv_records():
            self.assertIn('sandbox_mode="read-only"', " ".join(rec["argv"]))

    def test_each_member_records_its_group(self):
        out = self.bridge("batch", "start", "--group", "p1", "--task", "x")
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid)
        meta = json.loads(
            (self.project / ".codex-runs" / rid / "meta.json").read_text())
        self.assertEqual(meta["group"], "p1")


class TasksFile(BridgeTestCase):

    def write_tasks(self, *objs):
        f = self.tmp / "tasks.jsonl"
        f.write_text("\n".join(json.dumps(o) for o in objs) + "\n")
        return str(f)

    def test_per_item_fields_override_the_group_defaults(self):
        """Group options are defaults, not constraints: a batch is usually the
        same thing N ways, and the per-item fields are how the exceptions get
        said."""
        tf = self.write_tasks(
            {"prompt": "a", "label": "moduleA"},
            {"prompt": "b", "label": "moduleB", "sandbox": "read-only"},
        )
        out = self.bridge("batch", "start", "--group", "p1",
                          "--sandbox", "workspace-write", "--tasks-file", tf)
        by_label = {r["label"]: r for r in out["runs"]}
        self.assertEqual(by_label["moduleA"]["sandbox"], "workspace-write")
        self.assertEqual(by_label["moduleB"]["sandbox"], "read-only")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_task_flags_come_before_file_entries(self):
        tf = self.write_tasks({"prompt": "from-file", "label": "f"})
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "from-flag", "--label", "g", "--tasks-file", tf)
        self.assertEqual([r["label"] for r in out["runs"]], ["g", "f"])
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_an_unknown_field_fails_loudly(self):
        """Silently ignoring a field means the run quietly used the group default
        instead — the caller would have no way to notice."""
        tf = self.write_tasks({"prompt": "a", "sandox": "read-only"})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf,
                          expect_rc=1)
        self.assertIn("unknown field", out["error"])

    def test_malformed_json_names_its_line(self):
        f = self.tmp / "bad.jsonl"
        f.write_text('{"prompt": "ok"}\nnot json\n')
        out = self.bridge("batch", "start", "--group", "p1",
                          "--tasks-file", str(f), expect_rc=1)
        self.assertIn("line 2", out["error"])

    def test_a_wrongly_typed_field_is_rejected_before_anything_spawns(self):
        """Checking field names caught `sandox` but not `{"prompt": 123}`, which
        reached `prompt.strip()` as an AttributeError — after the earlier members
        of the batch had already started."""
        tf = self.write_tasks({"prompt": "good"}, {"prompt": 123})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf,
                          expect_rc=1)
        self.assertIn("line 2", out["error"])
        self.assertIn("'prompt'", out["error"])
        self.assertIn("int", out["error"])
        runs = self.project / ".codex-runs"
        started = [p for p in runs.iterdir() if p.is_dir()] if runs.is_dir() else []
        self.assertEqual(started, [], "a broken tasks file must cost nothing")

    def test_a_wrongly_typed_review_or_image_field_is_rejected(self):
        for item, want in (({"prompt": "a", "review": "uncommitted"}, "dict"),
                           ({"prompt": "a", "image": "one.png"}, "list"),
                           ({"prompt": "a", "image": [7]}, "list of paths")):
            with self.subTest(item=item):
                out = self.bridge("batch", "start", "--group", "g",
                                  "--tasks-file", self.write_tasks(item),
                                  expect_rc=1)
                self.assertIn(want, out["error"])

    def test_a_resume_task_must_name_what_it_resumes(self):
        tf = self.write_tasks({"prompt": "a", "kind": "resume"})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf,
                          expect_rc=1)
        self.assertIn("resume", out["error"])

    def test_a_resume_task_continues_the_named_thread(self):
        first = self.start("seed")
        self.wait_for_state(first["run_id"])
        tf = self.write_tasks({"prompt": "more", "kind": "resume",
                               "resume": first["run_id"]})
        out = self.bridge("batch", "start", "--group", "p2", "--tasks-file", tf)
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid)
        meta = json.loads(
            (self.project / ".codex-runs" / rid / "meta.json").read_text())
        self.assertEqual(meta["kind"], "resume")
        self.assertEqual(meta["parent_run_id"], first["run_id"])


class BatchFailureIsolation(BridgeTestCase):
    """D11: one member failing to spawn does not take the batch with it, and it
    does not print a second line of JSON either — the one-line contract is what
    every caller parses against."""

    def test_a_bad_member_is_recorded_in_place_and_the_rest_still_start(self):
        f = self.tmp / "tasks.jsonl"
        f.write_text("\n".join([
            json.dumps({"prompt": "good one"}),
            json.dumps({"prompt": "bad", "schema": "/nonexistent/schema.json"}),
            json.dumps({"prompt": "good two"}),
        ]) + "\n")
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", str(f))
        self.assertEqual(out["requested"], 3)
        self.assertEqual(out["spawned"], 2)
        self.assertIsNone(out["runs"][0].get("error"))
        self.assertIn("schema", out["runs"][1]["error"])
        self.assertEqual(out["runs"][1]["index"], 1,
                         "the failed slot keeps its position rather than vanishing")
        self.assertIsNone(out["runs"][2].get("error"))
        for r in out["runs"]:
            if r.get("run_id"):
                self.wait_for_state(r["run_id"])

    def test_the_failed_member_is_in_the_manifest_without_a_run_id(self):
        f = self.tmp / "tasks.jsonl"
        f.write_text(json.dumps({"prompt": "bad", "schema": "/nope.json"}) + "\n")
        self.bridge("batch", "start", "--group", "p1", "--tasks-file", str(f))
        manifest = json.loads(
            (self.project / ".codex-runs" / ".groups" / "p1.json").read_text())
        self.assertEqual(len(manifest["members"]), 1)
        self.assertNotIn("run_id", manifest["members"][0])


class ManifestSurvivesAHalfFinishedBatch(BridgeTestCase):
    """The manifest is what every `--group` selector resolves membership
    through, so a member that has spawned must appear in it from the instant it
    exists. Writing it once at the end of the spawn loop meant a batch killed
    partway through left live Codex processes recorded nowhere: invisible to
    `status --group`, and unreachable by `stop --group`."""

    def test_members_that_spawned_are_recorded_even_if_the_batch_is_killed(self):
        env = dict(self.env)
        # Delay the first event line so each member sits in create_run's
        # thread-id wait, giving a window wide enough to kill inside.
        env["FAKE_CODEX_PRE_DELAY"] = "6"
        proc = subprocess.Popen(
            [sys.executable, str(BRIDGE), "batch", "start", "--group", "p1",
             "--project", str(self.project),
             "--task", "one", "--task", "two", "--task", "three"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            start_new_session=True)
        self.addCleanup(self._kill_tree, proc)

        manifest = self.project / ".codex-runs" / ".groups" / "p1.json"
        deadline = time.time() + 30
        members = []
        while time.time() < deadline:
            if manifest.exists():
                members = (json.loads(manifest.read_text()) or {}).get("members") or []
                if members:
                    break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        self.assertTrue(members, "the first member must be in the manifest before "
                                 "the batch finishes spawning the rest")
        self.assertTrue(members[0].get("run_id"))

        self._kill_tree(proc)
        # What the manifest recorded is still there, and still resolves.
        after = json.loads(manifest.read_text())["members"]
        self.assertGreaterEqual(len(after), 1)
        rid = after[0]["run_id"]
        self.assertTrue((self.project / ".codex-runs" / rid / "meta.json").exists())
        status = self.bridge("status", "--group", "p1")
        self.assertIn(rid, [r["run_id"] for r in status["runs"]],
                      "a spawned member must be reachable through its group")

    def _kill_tree(self, proc):
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            proc.wait(timeout=10)


class GroupManifestAtomicity(BridgeTestCase):

    def test_a_claimed_group_is_complete_the_instant_it_exists(self):
        """`O_EXCL` created the file and filled it afterwards, so a reader
        arriving in between saw a name that existed with nothing parsable behind
        it — and `read_group` cannot tell that from corruption. The claim is a
        link of an already-written file instead."""
        runs_dir = self.project / ".codex-runs"
        runs_dir.mkdir(exist_ok=True)
        _batch.claim_group(runs_dir, "p1")
        got = _batch.read_group(runs_dir, "p1")
        self.assertEqual(got["group"], "p1")
        self.assertEqual(got["members"], [])
        with self.assertRaises(FileExistsError):
            _batch.claim_group(runs_dir, "p1")
        self.assertEqual(_batch.read_group(runs_dir, "p1")["members"], [],
                         "a rejected claim must not disturb the existing manifest")
        leftovers = list((runs_dir / ".groups").glob("*.tmp"))
        self.assertEqual(leftovers, [], "no tmp file may survive a claim")


class GroupSelectors(BridgeTestCase):

    def start_group(self, *extra, name="p1", n=2, **kw):
        return self.bridge("batch", "start", "--group", name,
                           *[a for i in range(n) for a in ("--task", f"task {i}")],
                           *extra, **kw)

    def test_status_group_reports_only_its_members(self):
        outside = self.start("unrelated")
        grp = self.start_group()
        for r in grp["runs"]:
            self.wait_for_state(r["run_id"])
        self.wait_for_state(outside["run_id"])

        st = self.bridge("status", "--group", "p1")
        ids = {r["run_id"] for r in st["runs"]}
        self.assertEqual(ids, {r["run_id"] for r in grp["runs"]})
        self.assertNotIn(outside["run_id"], ids)
        self.assertEqual(st["group_state"], "completed")
        self.assertEqual(st["total_runs"], 2)

    def test_group_state_is_partial_when_a_member_fails(self):
        grp = self.start_group("--label", "x", n=1)
        rid = grp["runs"][0]["run_id"]
        self.wait_for_state(rid)
        # Force a failed state the way a real non-zero exit would leave it.
        meta_path = self.project / ".codex-runs" / rid / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["state"], meta["exit_code"] = "failed", 1
        meta_path.write_text(json.dumps(meta))
        st = self.bridge("status", "--group", "p1")
        self.assertEqual(st["group_state"], "partial")
        self.assertEqual(st["failed"], [rid])

    def test_an_unknown_group_fails_with_the_names_that_do_exist(self):
        self.start_group()
        out = self.bridge("status", "--group", "nope", expect_rc=1)
        self.assertIn("no such group", out["error"])
        self.assertEqual(out["known_groups"], ["p1"])

    def test_stop_group_leaves_runs_outside_the_group_alone(self):
        """The group version of StopIsolation. --group resolves a recorded id to
        run ids and signals each run's own pgid; the name never reaches a
        process, which is what B8 forbids."""
        outside = self.start("outsider", env_extra={"FAKE_CODEX_HANG": "60"})
        grp = self.start_group("--timeout", "600", n=2,
                               env_extra={"FAKE_CODEX_HANG": "60"})
        for r in grp["runs"]:
            self.wait_for_state(r["run_id"], ("running", "completed"), timeout=30)

        self.bridge("stop", "--group", "p1")
        for r in grp["runs"]:
            row = self.bridge("status", "--run", r["run_id"])["runs"][0]
            self.assertIn(row["state"], ("interrupted", "completed"))
        row = self.bridge("status", "--run", outside["run_id"])["runs"][0]
        self.assertEqual(row["state"], "running",
                         "stop --group reached a run outside the group")
        self.bridge("stop", "--run", outside["run_id"])

    def test_follow_prints_a_terminal_line_and_exits(self):
        """Without a terminal line a quiet group and a dead follower look
        identical — the failure B21 exists to prevent."""
        grp = self.start_group(n=2)
        for r in grp["runs"]:
            self.wait_for_state(r["run_id"])
        p = self.bridge_raw("status", "--group", "p1", "--follow",
                            "--follow-timeout", "10")
        self.assertEqual(p.returncode, 0, p.stderr)
        lines = p.stdout.strip().splitlines()
        self.assertTrue(lines[-1].startswith("group.completed group=p1"),
                        f"no terminal line: {lines}")
        self.assertIn("done=2", lines[-1])

    def test_follow_says_still_running_when_its_deadline_expires(self):
        grp = self.start_group("--timeout", "600", n=1,
                               env_extra={"FAKE_CODEX_HANG": "60"})
        rid = grp["runs"][0]["run_id"]
        self.wait_for_state(rid, ("running",), timeout=30)
        p = self.bridge_raw("status", "--group", "p1", "--follow",
                            "--follow-timeout", "2", "--interval", "0.2")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("group.still-running", p.stdout)
        self.bridge("stop", "--group", "p1")


class GroupResults(BridgeTestCase):

    def test_result_group_caps_each_message_and_says_the_real_size(self):
        """D07. The cap makes fetching the full text a decision rather than a
        guess: message_bytes says exactly what is being withheld."""
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        res = self.bridge("result", "--group", "p1")
        self.assertEqual(len(res["results"]), 2)
        for row in res["results"]:
            self.assertIn("message_bytes", row)
            self.assertIn("message_truncated", row)
            self.assertFalse(row["message_truncated"])
        self.assertEqual(res["group_state"], "completed")
        self.assertGreater(res["totals"]["input_tokens"], 0)

    def test_the_cap_cuts_and_measures_in_the_same_unit(self):
        """Slicing characters while reporting bytes made a 3,000-character
        Korean message — 9,000 bytes, nothing removed — report itself
        truncated, which is the guess the cap exists to replace with a fact."""
        out = self.bridge("batch", "start", "--group", "p1", "--task", "a")
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid)
        msg = "가" * 3000
        (self.project / ".codex-runs" / rid / "last-message.txt").write_text(
            msg, encoding="utf-8")

        row = self.bridge("result", "--group", "p1")["results"][0]
        self.assertEqual(row["message_bytes"], 9000)
        self.assertTrue(row["message_truncated"])
        self.assertLessEqual(len(row["message"].encode("utf-8")),
                             _batch.GROUP_MESSAGE_CAP)

    def test_a_message_under_the_cap_is_not_reported_truncated(self):
        out = self.bridge("batch", "start", "--group", "p1", "--task", "a")
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid)
        msg = "가" * 1000          # 3,000 bytes, under the 4,000-byte cap
        (self.project / ".codex-runs" / rid / "last-message.txt").write_text(
            msg, encoding="utf-8")

        row = self.bridge("result", "--group", "p1")["results"][0]
        self.assertFalse(row["message_truncated"])
        self.assertEqual(row["message"], msg)

    def test_overlaps_reports_only_paths_more_than_one_member_wrote(self):
        """D30. A full path list per run inverts the context discipline the skill
        exists for; the intersection is the part nobody can derive cheaply."""
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b")
        run_ids = [r["run_id"] for r in out["runs"]]
        for rid in run_ids:
            self.wait_for_state(rid)

        runs_dir = self.project / ".codex-runs"
        shared, only_a = "src/shared.py", "src/only_a.py"
        for rid, paths in ((run_ids[0], [shared, only_a]), (run_ids[1], [shared])):
            ev = runs_dir / rid / "events.jsonl"
            with ev.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "type": "item.completed",
                    "item": {"id": f"fc-{rid}", "type": "file_change",
                             "changes": [{"path": p, "kind": "modify"} for p in paths]},
                }) + "\n")

        res = self.bridge("result", "--group", "p1")
        self.assertEqual(list(res["overlaps"]), [shared])
        self.assertEqual(sorted(res["overlaps"][shared]), sorted(run_ids))
        self.assertNotIn(only_a, res["overlaps"])
        self.assertIn("merge conflict ahead", res["overlaps_note"])

    def test_result_needs_a_selector(self):
        out = self.bridge("result", expect_rc=1)
        self.assertIn("--run", out["error"])


class ProjectedCost(BridgeTestCase):
    """D37. Computed from this project's own history rather than a constant,
    because a baked-in number rots — the isolation overhead measured at design
    time moved 2.92x to 1.09x within two weeks (R8)."""

    def test_it_reports_null_and_says_why_before_there_are_samples(self):
        out = self.bridge("batch", "start", "--group", "p1", "--task", "x")
        self.assertIsNone(out["projected_cost"]["input_floor_per_run"])
        self.assertIn("not enough", out["projected_cost"]["note"])
        self.wait_for_state(out["runs"][0]["run_id"])

    def test_it_takes_the_median_of_recent_completed_isolated_runs(self):
        for i in range(4):
            r = self.start(f"seed {i}")
            self.wait_for_state(r["run_id"])
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b")
        cost = out["projected_cost"]
        self.assertIsNotNone(cost["input_floor_per_run"])
        self.assertEqual(cost["runs"], 2)
        self.assertEqual(cost["input_floor_total"],
                         cost["input_floor_per_run"] * 2)
        self.assertIn("Do not budget", cost["note"])
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_usage_is_copied_into_meta_at_completion(self):
        """projected_cost reads meta, not events — it needs the number for
        several past runs at once, before spawning anything."""
        r = self.start("x")
        self.wait_for_state(r["run_id"])
        meta = json.loads(
            (self.project / ".codex-runs" / r["run_id"] / "meta.json").read_text())
        self.assertIn("usage", meta)
        self.assertGreater(meta["usage"]["input_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
