"""`batch start --worktree`: which members get a checkout, what the checkout holds, how `batch clean` protects work nobody collected, and how `overlaps` compares paths across checkouts.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import unicodedata
import unittest
from pathlib import Path

from support.harness import BridgeCase, alive, wait_until


class WorktreeCase(BridgeCase):

    def group(self, *extra, n=2, name="p1", **kw):
        return self.bridge("batch", "start", "--group", name,
                           *[a for i in range(n) for a in ("--task", f"task {i}")], *extra, **kw)

    def finished(self, *extra, **kw):
        out = self.group("--worktree", *extra, **kw)
        self.wait_all(out)
        return out

    def registered_worktrees(self):
        listed = self.git("worktree", "list", "--porcelain").stdout
        return [ln.split(" ", 1)[1] for ln in listed.splitlines() if ln.startswith("worktree ")][1:]

    def plant(self, run_id, paths):
        """Append a file_change naming these absolute paths, the shape real events have."""
        with (self.runs_dir / run_id / "events.jsonl").open("a") as fh:
            fh.write(json.dumps({"type": "item.completed", "item": {
                "id": f"fc-{run_id}", "type": "file_change",
                "changes": [{"path": str(p), "kind": "update"} for p in paths]}}) + "\n")

    def overlaps(self, name="p1"):
        return self.bridge("result", "--group", name)["overlaps"]


class WhoGetsACheckout(WorktreeCase):

    def test_members_share_the_callers_tree_unless_asked(self):
        out = self.group()
        self.wait_all(out)
        for r in out["runs"]:
            self.assertEqual((r.get("worktree"), r["cwd"]), (None, str(self.project)))
        self.assertIn("--worktree", out["worktrees"]["note"])

    def test_a_lone_writer_is_told_nothing_about_sharing(self):
        out = self.group(n=1)
        self.wait_all(out)
        self.assertNotIn("worktrees", out)

    def test_each_writer_gets_its_own_checkout_and_runs_in_it(self):
        out = self.finished()
        paths = [r["worktree"] for r in out["runs"]]
        self.assertEqual(len(set(paths)), 2)
        self.assertEqual([r["cwd"] for r in out["runs"]], paths)
        self.assertEqual(sorted(r["cwd"] for r in self.runs_invoked()), sorted(paths))
        for r in out["runs"]:
            self.assertEqual(Path(r["worktree"]), self.runs_dir / r["run_id"] / "wt")
            self.assertEqual(self.row(r["run_id"])["worktree"], r["worktree"])
            self.assertIn("isolated git worktree", self.runs_invoked()[0]["argv"][-1])

    def test_a_lone_writer_is_isolated_when_asked(self):
        self.assertIsNotNone(self.finished(n=1)["runs"][0]["worktree"])

    def test_read_only_and_explicit_cwd_members_stay_where_they_were_put(self):
        other = self.tmp / "elsewhere"
        other.mkdir()
        tf = self.tasks_file("w1", "w2", {"prompt": "look", "sandbox": "read-only"},
                             {"prompt": "there", "cwd": str(other)})
        out = self.bridge("batch", "start", "--group", "p1", "--worktree", "--tasks-file", tf)
        self.wait_all(out)
        self.assertTrue(all(r.get("worktree") for r in out["runs"][:2]))
        self.assertEqual([(r.get("worktree"), r["cwd"]) for r in out["runs"][2:]],
                         [(None, str(self.project)), (None, str(other))])

    def test_a_phase_that_continues_threads_keeps_their_directories(self):
        one = self.finished()
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1", "--worktree",
                          "--task", "a", "--task", "b")
        self.wait_all(two)
        self.assertEqual([r["cwd"] for r in two["runs"]], [r["worktree"] for r in one["runs"]])
        self.assertEqual(len(self.registered_worktrees()), 2, "no new checkout for a resume")
        self.assertIn("resumed thread", two["worktrees"]["note"])

    def test_a_project_that_is_not_a_repository_degrades_to_sharing(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.extra_runs_dirs = [plain / ".codex-runs"]
        out = self.group("--worktree", "--project", plain)
        self.assertEqual(out["spawned"], 2)
        self.assertIn("not a git repository", out["worktrees"]["note"])
        self.assertTrue(all(r["cwd"] == str(plain) for r in out["runs"]))

    def test_an_unresolvable_base_is_refused_before_anything_is_claimed(self):
        refused = self.group("--worktree", "--base", "no-such-ref", rc=1)
        self.assertIn("no-such-ref", refused["error"])
        self.assertEqual(self.run_dirs(), [])


class WhatACheckoutHolds(WorktreeCase):
    """A checkout is `git worktree add` output: tracked files at the base commit and nothing else."""

    def test_tracked_files_at_base_and_none_of_the_callers_uncommitted_or_ignored_work(self):
        (self.project / ".gitignore").write_text(".venv/\ncache.db\n")
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore")
        (self.project / ".venv").mkdir()
        (self.project / ".venv" / "python").write_text("#!")
        (self.project / "cache.db").write_text("x")
        (self.project / "tracked.txt").write_text("edited, not committed\n")
        (self.project / "untracked.txt").write_text("new\n")
        out = self.finished()
        wt = Path(out["runs"][0]["worktree"])
        self.assertEqual((wt / "tracked.txt").read_text(), "one\n")
        for absent in ("untracked.txt", ".venv", "cache.db"):
            self.assertFalse((wt / absent).exists(), absent)
        self.assertEqual(sorted(out["worktrees"]["missing_ignored"]), [".venv/", "cache.db"])
        self.assertEqual(out["worktrees"]["uncommitted_files_in_caller_tree"], 2)
        self.assertIn("2 uncommitted file(s)", self.runs_invoked()[0]["argv"][-1])

    def test_the_callers_git_status_is_undisturbed(self):
        out = self.finished()
        (Path(out["runs"][0]["worktree"]) / "made-by-codex.txt").write_text("x\n")
        self.assertEqual(self.git("status", "--porcelain").stdout, "")

    def test_base_names_the_commit_and_instructions_missing_there_are_reported(self):
        first = self.git("rev-parse", "HEAD").stdout.strip()
        (self.project / "AGENTS.md").write_text("# rules\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "agents")
        out = self.finished("--base", first)
        self.assertEqual(out["worktrees"]["base"], first)
        self.assertEqual(out["worktrees"]["missing_at_base"], ["AGENTS.md"])
        self.assertFalse((Path(out["runs"][0]["worktree"]) / "AGENTS.md").exists())
        self.assertNotIn("missing_at_base", self.finished(name="p2")["worktrees"])

    def test_a_member_refused_at_spawn_leaves_no_checkout(self):
        tf = self.tasks_file({"prompt": "a", "image": ["/nonexistent/x.png"]}, "b", "c")
        out = self.bridge("batch", "start", "--group", "p1", "--worktree", "--tasks-file", tf)
        self.wait_all(out)
        self.assertIn("image not found", out["runs"][0]["error"])
        self.assertEqual(len(self.registered_worktrees()), 2)


class Clean(WorktreeCase):

    def test_a_clean_group_is_removed_and_its_name_released(self):
        out = self.finished()
        res = self.bridge("batch", "clean", "--group", "p1")
        self.assertEqual((len(res["removed"]), res["kept"], res["name_released"]), (2, [], True))
        for r in out["runs"]:
            self.assertFalse(Path(r["worktree"]).exists())
        self.assertEqual(self.registered_worktrees(), [])
        self.wait_all(self.group(name="p1"))

    def test_uncollected_work_is_kept_until_forced(self):
        out = self.finished()
        dirty = Path(out["runs"][0]["worktree"])
        (dirty / "result.txt").write_text("work\n")
        res = self.bridge("batch", "clean", "--group", "p1")
        self.assertEqual([(k["path"], k["dirty"]) for k in res["kept"]], [(str(dirty), True)])
        self.assertFalse(res["name_released"])
        self.assertTrue(dirty.exists())
        forced = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertTrue(forced["name_released"])
        self.assertEqual(forced["forced_past"]["discarded_uncommitted"], [str(dirty)])
        self.assertFalse(dirty.exists())

    def test_a_clean_that_overrode_nothing_says_nothing(self):
        self.finished()
        self.assertNotIn("forced_past", self.bridge("batch", "clean", "--group", "p1", "--force"))

    def test_a_live_member_refuses_a_plain_clean(self):
        out = self.group("--worktree", env={"FAKE_CODEX_HANG": 60})
        res = self.bridge("batch", "clean", "--group", "p1", rc=1)
        self.assertEqual(sorted(m["run_id"] for m in res["running"]), sorted(r["run_id"] for r in out["runs"]))
        self.assertTrue(all(Path(r["worktree"]).exists() for r in out["runs"]))

    def test_force_does_not_reach_a_live_member(self):
        out = self.group("--worktree", env={"FAKE_CODEX_HANG": 60})
        res = self.bridge("batch", "clean", "--group", "p1", "--force", rc=1)
        self.assertEqual(sorted(m["run_id"] for m in res["running"]), sorted(r["run_id"] for r in out["runs"]))
        self.assertEqual(res["stop"], ["stop --group p1"])
        self.assertTrue(all(Path(r["worktree"]).exists() for r in out["runs"]))
        self.bridge(*res["stop"][0].split())
        self.wait_all(out)
        self.assertTrue(self.bridge("batch", "clean", "--group", "p1", "--force")["name_released"])

    def test_force_does_not_reach_a_worktree_another_group_is_working_in(self):
        one = self.finished()
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1", "--task", "a", "--task", "b",
                          env={"FAKE_CODEX_HANG": 60})
        res = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(res["removed"], [])
        self.assertFalse(res["name_released"])
        self.assertEqual(sorted(o for k in res["kept"] for o in k["occupied_by"]), sorted(r["run_id"] for r in two["runs"]))
        self.assertEqual({c for k in res["kept"] for c in k["stop"]}, {"stop --group p2"})
        self.assertTrue(all(Path(r["worktree"]).exists() for r in one["runs"]))

    def test_force_does_not_reach_a_worktree_a_lone_run_works_inside(self):
        one = self.finished(n=1)
        inside = Path(one["runs"][0]["worktree"]) / "sub"
        inside.mkdir()
        lone, _m = self.running("--cwd", inside, "x")
        res = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual([k["stop"] for k in res["kept"]], [[f"stop --run {lone['run_id']}"]])
        self.assertTrue(inside.exists())

    def test_an_orphan_still_writing_refuses_a_plain_clean(self):
        out = self.group("--worktree", n=1, env={"FAKE_CODEX_HANG": 60})
        rid = out["runs"][0]["run_id"]
        self.wait_state(rid, ("running",))
        m = self.meta(rid)
        os.kill(int(m["supervisor_pid"]), signal.SIGKILL)
        wait_until(lambda: not alive(m["supervisor_pid"]), timeout=10)
        self.assertEqual(self.row(rid)["state"], "orphaned")
        res = self.bridge("batch", "clean", "--group", "p1", rc=1)
        self.assertEqual([x["run_id"] for x in res["running"]], [rid])

    def test_a_run_living_in_a_checkout_keeps_it_when_the_group_graph_has_forgotten(self):
        one = self.finished()
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1", "--task", "a", "--task", "b")
        self.wait_all(two)
        three = self.bridge("batch", "start", "--group", "p3", "--resume-from", "p2", "--task", "a", "--task", "b",
                            env={"FAKE_CODEX_HANG": 60})
        self.bridge("batch", "clean", "--group", "p2", "--force")
        res = self.bridge("batch", "clean", "--group", "p1")
        self.assertEqual(res["removed"], [])
        self.assertFalse(res["name_released"])
        self.assertEqual({o for k in res["kept"] for o in k["occupied_by"]}, {r["run_id"] for r in three["runs"]})
        self.assertTrue(all(Path(r["worktree"]).exists() for r in one["runs"]))

    def test_a_group_another_group_resumed_is_protected(self):
        self.finished()
        self.wait_all(self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                                  "--task", "a", "--task", "b"))
        refused = self.bridge("batch", "clean", "--group", "p1", rc=1)
        self.assertEqual(refused["derived_groups"], ["p2"])
        forced = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(forced["forced_past"]["derived_groups"], ["p2"])

    def test_an_unknown_group_is_named(self):
        self.assertIn("no such group", self.bridge("batch", "clean", "--group", "nope", rc=1)["error"])

    def test_force_lifts_a_git_lock_left_by_an_interrupted_checkout(self):
        out = self.finished()
        path = out["runs"][0]["worktree"]
        self.git("worktree", "lock", "--reason", "initializing", path)
        refused = self.bridge("batch", "clean", "--group", "p1")
        self.assertIn(path, [k["path"] for k in refused["kept"]])
        self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(self.registered_worktrees(), [])

    def test_checkouts_cut_by_a_batch_killed_mid_spawn_are_still_cleaned(self):
        p = self.spawn("batch", "start", "--group", "p1", "--worktree", "--task", "one", "--task", "two",
                       "--task", "three", env={"FAKE_CODEX_PRE_DELAY": 6})
        manifest = self.runs_dir / ".groups" / "p1.json"

        def cut_but_unrecorded():
            if not manifest.exists():
                return None
            recorded = {m["run_id"] for m in json.loads(manifest.read_text())["members"] if m.get("run_id")}
            orphans = [d for d in self.run_dirs() if d not in recorded and (self.runs_dir / d / "wt").exists()]
            return orphans or None

        orphans = wait_until(cut_but_unrecorded, timeout=40, interval=0.02)
        self.assertTrue(orphans, "never saw a checkout the manifest had not recorded")
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        for rid in self.run_dirs():
            self.wait_state(rid)
        # The crash can also land between `git worktree add` and the meta.json write that records the path. Staged once the member has stopped writing its own meta.
        self.write_meta(orphans[0], {**self.meta(orphans[0]), "worktree": None})
        status = self.bridge("status", "--group", "p1")
        self.assertEqual(len(status["runs"]) + len(status["unstarted"]), 3)
        self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(self.registered_worktrees(), [])

    def test_a_checkout_removed_by_hand_is_not_reported_as_removed(self):
        out = self.finished()
        gone = out["runs"][0]["worktree"]
        subprocess.run(["rm", "-rf", gone], check=True)
        res = self.bridge("batch", "clean", "--group", "p1")
        self.assertEqual([r["path"] for r in res["removed"]], [out["runs"][1]["worktree"]])
        self.assertEqual(self.registered_worktrees(), [])
        self.assertTrue(res["name_released"])

    def test_a_member_whose_meta_will_not_parse_is_not_presumed_dead(self):
        out = self.finished()
        victim = out["runs"][0]["run_id"]
        (self.runs_dir / victim / "meta.json").write_text("{ truncated")
        res = self.bridge("batch", "clean", "--group", "p1", rc=1)
        self.assertIn(victim, [r["run_id"] for r in res["running"]])
        self.assertTrue((self.runs_dir / victim / "wt").exists())


NFC = unicodedata.normalize("NFC", "공유")
NFD = unicodedata.normalize("NFD", "공유")


class Overlaps(WorktreeCase):
    """Codex reports absolute paths, and each checkout has its own prefix, so paths are compared as (repository, repo-relative path)."""

    def test_one_repo_path_in_two_checkouts_is_an_overlap(self):
        out = self.finished()
        for r in out["runs"]:
            self.plant(r["run_id"], [Path(r["worktree"]) / "src" / "shared.py"])
        self.assertEqual(self.overlaps(), {"src/shared.py": [r["run_id"] for r in out["runs"]]})

    def test_different_paths_are_not(self):
        out = self.finished()
        for r, name in zip(out["runs"], ("a.py", "b.py")):
            self.plant(r["run_id"], [Path(r["worktree"]) / name])
        self.assertEqual(self.overlaps(), {})

    def test_the_same_name_in_two_repositories_is_two_files(self):
        other = self.tmp / "other"
        other.mkdir()
        self.git("init", "-q", cwd=other)
        (other / "x").write_text("x")
        self.git("add", "-A", cwd=other)
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i", cwd=other)
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file",
                          self.tasks_file("a", {"prompt": "b", "cwd": str(other)}))
        self.wait_all(out)
        for r, root in zip(out["runs"], (self.project, other)):
            self.plant(r["run_id"], [root / "out.txt"])
        self.assertEqual(self.overlaps(), {})

    def test_nested_roots_in_one_repository_see_one_file(self):
        sub = self.project / "src"
        sub.mkdir()
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file",
                          self.tasks_file("a", {"prompt": "b", "cwd": str(sub)}))
        self.wait_all(out)
        for r in out["runs"]:
            self.plant(r["run_id"], [sub / "shared.py"])
        self.assertEqual(list(self.overlaps()), ["src/shared.py"])

    def test_one_file_spelled_in_two_normalisations_is_one_overlap(self):
        out = self.finished()
        for r, form in zip(out["runs"], (NFD, NFC)):
            self.plant(r["run_id"], [Path(r["worktree"]) / f"{form}.py"])
        self.assertEqual(list(self.overlaps()), [f"{NFC}.py"])

    def test_phase_two_is_not_compared_with_its_own_predecessors(self):
        one = self.finished()
        for r in one["runs"]:
            self.plant(r["run_id"], [Path(r["worktree"]) / "shared.py"])
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1", "--task", "a", "--task", "b")
        self.wait_all(two)
        for r in two["runs"]:
            self.plant(r["run_id"], [Path(r["cwd"]) / "shared.py"])
        self.assertEqual(sorted(self.overlaps("p2")["shared.py"]), sorted(r["run_id"] for r in two["runs"]))


if __name__ == "__main__":
    unittest.main()
