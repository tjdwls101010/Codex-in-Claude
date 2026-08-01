"""T1 — per-member worktree assignment, and taking them away again.

The three facts this milestone is built on were measured before it was written
(`harness-spec.md` V-13/V-14/V-15). These tests hold the code to them.
"""

from __future__ import annotations

import json
import subprocess
import time
import unittest
from pathlib import Path

from helpers import BridgeTestCase      # puts the scripts dir on sys.path

from _registry import TERMINAL_STATES   # noqa: E402


class WorktreeTestCase(BridgeTestCase):
    """A project with a commit, so HEAD resolves and a worktree can be cut."""

    def setUp(self):
        super().setUp()
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "Test")
        (self.project / "tracked.txt").write_text("one\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.project), *args],
                              capture_output=True, text=True, check=True)

    def dirty_the_caller_tree(self):
        (self.project / "tracked.txt").write_text("two\n")

    def start_group(self, *extra, n=2, name="p1"):
        return self.bridge("batch", "start", "--group", name,
                           *[a for i in range(n) for a in ("--task", f"task {i}")],
                           *extra)

    def tasks_file(self, *objs):
        f = self.tmp / "tasks.jsonl"
        f.write_text("\n".join(json.dumps(o) for o in objs) + "\n")
        return str(f)


class Assignment(WorktreeTestCase):

    def test_two_writing_members_each_get_their_own_checkout(self):
        out = self.start_group()
        paths = [r["worktree"] for r in out["runs"]]
        self.assertEqual(len(set(paths)), 2, "isolation means a checkout each")
        for r, p in zip(out["runs"], paths):
            self.assertEqual(r["cwd"], p, "the run must actually run in it")
            self.assertTrue((Path(p) / "tracked.txt").exists())
            self.wait_for_state(r["run_id"])

    def test_the_main_tree_is_not_disturbed(self):
        """V-13. `.codex-runs/.gitignore` is `*`, so the isolation costs the
        caller nothing in their own `git status`."""
        self.dirty_the_caller_tree()
        out = self.start_group()
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
            (Path(r["worktree"]) / "made-by-codex.txt").write_text("x\n")
        status = self.git("status", "--porcelain").stdout
        self.assertEqual(status.strip(), "M tracked.txt",
                         "only the caller's own edit may appear")

    def test_a_lone_writer_is_not_isolated(self):
        out = self.start_group(n=1)
        self.assertIsNone(out["runs"][0].get("worktree"))
        self.assertEqual(out["worktrees"]["count"], 0)
        self.assertIn("nobody to collide with", out["worktrees"]["note"])
        self.wait_for_state(out["runs"][0]["run_id"])

    def test_worktree_forces_isolation_for_a_lone_writer(self):
        out = self.start_group("--worktree", n=1)
        self.assertIsNotNone(out["runs"][0]["worktree"])
        self.wait_for_state(out["runs"][0]["run_id"])

    def test_no_worktree_turns_it_off(self):
        out = self.start_group("--no-worktree")
        for r in out["runs"]:
            self.assertIsNone(r.get("worktree"))
            self.assertEqual(r["cwd"], str(self.project))
            self.wait_for_state(r["run_id"])
        self.assertIn("--no-worktree", out["worktrees"]["note"])

    def test_read_only_members_are_not_counted_and_not_isolated(self):
        """D35 is per member, not per batch: a read-only member has nothing to
        isolate, and two of them are not two writers."""
        tf = self.tasks_file({"prompt": "a", "sandbox": "read-only"},
                             {"prompt": "b", "sandbox": "read-only"})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        for r in out["runs"]:
            self.assertIsNone(r.get("worktree"))
            self.wait_for_state(r["run_id"])

    def test_a_review_member_stays_in_the_callers_tree(self):
        """V-15 is the whole reason this exclusion exists: a fresh detached
        worktree has zero lines of `git diff HEAD`, so a reviewer put inside one
        would be reviewing nothing — the uncommitted work it was started to look
        at lives only in the caller's tree."""
        self.dirty_the_caller_tree()
        tf = self.tasks_file({"prompt": "w1"}, {"prompt": "w2"},
                             {"kind": "review", "review": {"uncommitted": True}})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        writers, review = out["runs"][:2], out["runs"][2]
        for r in writers:
            self.assertIsNotNone(r["worktree"])
        self.assertIsNone(review.get("worktree"))
        self.assertEqual(review["cwd"], str(self.project),
                         "the reviewer must see the changes it was asked about")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_an_explicit_cwd_beats_the_inferred_default(self):
        other = self.tmp / "elsewhere"
        other.mkdir()
        tf = self.tasks_file({"prompt": "a", "cwd": str(other)}, {"prompt": "b"})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        self.assertIsNone(out["runs"][0].get("worktree"))
        self.assertEqual(out["runs"][0]["cwd"], str(other))
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_base_cuts_from_the_named_commit(self):
        first = self.git("rev-parse", "HEAD").stdout.strip()
        (self.project / "later.txt").write_text("later\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "second")
        out = self.start_group("--base", first)
        self.assertEqual(out["worktrees"]["base"], first)
        wt = Path(out["runs"][0]["worktree"])
        self.assertFalse((wt / "later.txt").exists(),
                         "the worktree must be at the commit it was told")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_a_non_git_project_degrades_instead_of_failing(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        out = self.bridge("batch", "start", "--group", "p1", "--project", str(plain),
                          "--task", "a", "--task", "b")
        self.assertEqual(out["spawned"], 2)
        self.assertIn("not a git repository", out["worktrees"]["note"])
        for r in out["runs"]:
            self.assertIsNone(r.get("worktree"))
            self.assertEqual(r["cwd"], str(plain))
            deadline = time.time() + 30
            meta = plain / ".codex-runs" / r["run_id"] / "meta.json"
            while time.time() < deadline:
                if json.loads(meta.read_text()).get("state") in TERMINAL_STATES:
                    break
                time.sleep(0.1)


class Preamble(WorktreeTestCase):
    """§4.4 / D20. Facts Codex cannot observe from inside its own turn, and
    which it otherwise asserts wrongly rather than hedging (V-18)."""

    def sent_prompt(self, run_id):
        meta = json.loads(
            (self.project / ".codex-runs" / run_id / "meta.json").read_text())
        return meta["argv"][-1]

    def test_a_batch_member_is_told_the_group_size_and_name(self):
        out = self.start_group(n=3)
        prompt = self.sent_prompt(out["runs"][0]["run_id"])
        self.assertIn("one of 3 Codex runs", prompt)
        self.assertIn('group "p1"', prompt)
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_an_isolated_member_is_told_its_tree_is_not_the_callers(self):
        self.dirty_the_caller_tree()
        out = self.start_group()
        prompt = self.sent_prompt(out["runs"][0]["run_id"])
        self.assertIn("isolated git worktree", prompt)
        self.assertIn("1 uncommitted file(s)", prompt)
        self.assertIn(out["worktrees"]["base"][:12], prompt)
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_a_member_without_a_worktree_gets_no_worktree_paragraph(self):
        out = self.start_group("--no-worktree")
        prompt = self.sent_prompt(out["runs"][0]["run_id"])
        self.assertIn("one of 2 Codex runs", prompt)
        self.assertNotIn("isolated git worktree", prompt)
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_no_preamble_turns_off_the_batch_paragraphs_too(self):
        """Half a briefing is worse than none: a caller switching the preamble
        off is saying it will brief Codex itself."""
        out = self.start_group("--no-preamble")
        prompt = self.sent_prompt(out["runs"][0]["run_id"])
        self.assertNotIn("Batch context", prompt)
        self.assertNotIn("Run context", prompt)
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])

    def test_a_single_run_outside_a_batch_is_unchanged(self):
        run = self.start("solo")
        prompt = self.sent_prompt(run["run_id"])
        self.assertIn("Run context", prompt)
        self.assertNotIn("Batch context", prompt)
        self.wait_for_state(run["run_id"])


class Clean(WorktreeTestCase):

    def finished_group(self, **kw):
        out = self.start_group(**kw)
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        return out

    def test_clean_removes_the_worktrees_and_releases_the_name(self):
        out = self.finished_group()
        res = self.bridge("batch", "clean", "--group", "p1")
        self.assertEqual(len(res["removed"]), 2)
        self.assertTrue(res["name_released"])
        for r in out["runs"]:
            self.assertFalse(Path(r["worktree"]).exists())
        # Releasing the name is what makes a group reusable — and the only way
        # to reclaim one from a `batch start` that died mid-spawn.
        again = self.bridge("batch", "start", "--group", "p1", "--task", "x")
        self.wait_for_state(again["runs"][0]["run_id"])

    def test_uncollected_results_are_not_discarded(self):
        """D06. Not a check this code performs — `git worktree remove` refuses a
        dirty worktree by itself (V-13), and git's notion of dirty is the right
        one. The refusal is reported as the reason."""
        out = self.finished_group()
        (Path(out["runs"][0]["worktree"]) / "result.txt").write_text("work\n")
        res = self.bridge("batch", "clean", "--group", "p1")
        kept = {k["run_id"]: k for k in res["kept"]}
        self.assertIn(out["runs"][0]["run_id"], kept)
        self.assertTrue(kept[out["runs"][0]["run_id"]]["dirty"])
        self.assertFalse(res["name_released"],
                         "the group must stay addressable while it has leftovers")
        self.assertTrue(Path(out["runs"][0]["worktree"]).exists())

    def test_force_discards_them(self):
        out = self.finished_group()
        (Path(out["runs"][0]["worktree"]) / "result.txt").write_text("work\n")
        res = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(len(res["removed"]), 2)
        self.assertTrue(res["name_released"])

    def test_a_live_member_stops_the_clean(self):
        out = self.start_group(n=1, name="live")
        # n=1 is not isolated; start a second, hanging, writing member instead.
        self.wait_for_state(out["runs"][0]["run_id"])
        grp = self.bridge("batch", "start", "--group", "p2",
                          "--task", "a", "--task", "b",
                          env_extra={"FAKE_CODEX_HANG": "60"})
        self.wait_for_state(grp["runs"][0]["run_id"], ("running",), timeout=30)
        res = self.bridge("batch", "clean", "--group", "p2", expect_rc=1)
        self.assertIn("running members", res["error"])
        self.assertTrue(res["running"])
        self.bridge("stop", "--group", "p2")

    def test_an_unknown_group_says_so(self):
        res = self.bridge("batch", "clean", "--group", "nope", expect_rc=1)
        self.assertIn("no such group", res["error"])

    def test_a_group_another_group_resumed_into_is_protected(self):
        """A phase-2 member works inside its phase-1 predecessor's worktree, so
        cleaning phase 1 pulls the tree out from under runs still using it."""
        out = self.finished_group()
        runs_dir = self.project / ".codex-runs"
        manifest = runs_dir / ".groups" / "p2.json"
        manifest.write_text(json.dumps(
            {"group": "p2", "derived_from": "p1", "members": []}))
        res = self.bridge("batch", "clean", "--group", "p1", expect_rc=1)
        self.assertIn("resumed by another group", res["error"])
        self.assertEqual(res["derived_groups"], ["p2"])
        self.assertTrue(Path(out["runs"][0]["worktree"]).exists())

    def test_force_overrides_the_dependent_group_refusal(self):
        self.finished_group()
        (self.project / ".codex-runs" / ".groups" / "p2.json").write_text(
            json.dumps({"group": "p2", "derived_from": "p1", "members": []}))
        res = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(len(res["removed"]), 2)


class DoctorReportsTheCost(WorktreeTestCase):

    def test_doctor_counts_residual_worktrees_and_says_what_removes_them(self):
        """§13. The place that creates the cost is the place that reports it —
        facts only, no policy and no automatic cleanup (D06, D23)."""
        out = self.start_group()
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        rep = self.bridge("doctor")
        self.assertEqual(rep["worktrees"], 2)
        self.assertEqual(rep["groups"], ["p1"])
        self.assertGreater(rep["runs_dir_bytes"], 0)
        self.assertEqual(rep["runs_dir_runs"], 2)
        self.assertTrue(any("batch clean" in w for w in rep["warnings"]))
        self.assertTrue(rep["ok"], "a residual worktree is not a blocker")

    def test_no_warning_once_they_are_gone(self):
        out = self.start_group()
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        self.bridge("batch", "clean", "--group", "p1")
        rep = self.bridge("doctor")
        self.assertEqual(rep["worktrees"], 0)
        self.assertFalse(any("worktree(s) from batch runs" in w
                             for w in rep["warnings"]))


if __name__ == "__main__":
    unittest.main()
