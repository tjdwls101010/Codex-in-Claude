"""Where the registry is: one per repository, in its main checkout's `.codex-runs`, whichever of the repository's checkouts a command runs from — while a run still works, by default, in the top level of the checkout it was started from.

A registry per checkout splits a thread from its runs: started in a linked worktree, resumed from the main checkout (or the other way round), it would be "not in this registry".
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support.harness import FAKE_CODEX_DIR, BridgeCase, engine


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *map(str, args)], capture_output=True, text=True, check=True)


def repo(path: Path) -> Path:
    """A git repository with one commit, resolved the way the skill records paths."""
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "Test")
    (path / "f.txt").write_text("x\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "init")
    return path.resolve()


class MainCheckout(unittest.TestCase):
    """`codex.git.main_checkout`: the working tree of the repository's main checkout, from any of its checkouts, asked of real repositories."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codex-main-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.main = repo(self.tmp / "main")
        self.of = engine("codex.git").main_checkout

    def test_the_main_checkout_is_itself(self):
        self.assertEqual(self.of(self.main), self.main)

    def test_a_linked_worktree_leads_to_the_main_checkout(self):
        git(self.main, "worktree", "add", "-q", self.tmp / "linked", "-b", "side")
        self.assertEqual(self.of(self.tmp / "linked"), self.main)

    def test_a_directory_in_no_repository_is_itself(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertEqual(self.of(plain), plain)

    def test_a_worktree_of_a_bare_repository_is_itself(self):
        bare = self.tmp / "bare.git"
        git(self.tmp, "clone", "-q", "--bare", self.main, bare)
        git(bare, "worktree", "add", "-q", self.tmp / "bwt")
        self.assertEqual(self.of(self.tmp / "bwt"), (self.tmp / "bwt").resolve())

    def test_a_linked_worktree_of_a_submodule_leads_to_the_submodules_own_checkout(self):
        sub = repo(self.tmp / "sub-src")
        sup = repo(self.tmp / "super")
        subprocess.run(["git", "-C", str(sup), "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "mod"],
                       capture_output=True, text=True, check=True)
        git(sup, "commit", "-qm", "add submodule")
        git(sup / "mod", "worktree", "add", "-q", self.tmp / "modwt", "-b", "side")
        self.assertEqual(self.of(self.tmp / "modwt"), sup / "mod")

    def test_a_linked_worktree_whose_main_checkout_is_gone_is_itself(self):
        git(self.main, "worktree", "add", "-q", self.tmp / "linked", "-b", "side")
        shutil.rmtree(self.main)
        self.assertEqual(self.of(self.tmp / "linked"), (self.tmp / "linked").resolve())


class OneRegistryPerRepository(BridgeCase):

    def linked(self, name="linked"):
        path = self.tmp / name
        self.git("worktree", "add", "-q", path, "-b", f"side-{name}")
        return path.resolve()

    def test_a_run_started_in_a_linked_worktree_is_recorded_in_the_main_checkout(self):
        wt = self.linked()
        out = self.bridge("start", "x", cwd=wt)
        self.assertTrue(out["events"].startswith(str(self.runs_dir) + "/"), out["events"])
        self.assertEqual((out["cwd"], out["project"]), (str(wt), str(wt)), "it works where it was started")
        self.assertNotIn("--project", out["next"]["command"])
        self.wait_state(out["run_id"])
        self.assertEqual(self.runs_invoked()[-1]["cwd"], str(wt))
        self.assertFalse((wt / ".codex-runs").exists())

    def test_its_thread_is_found_from_every_checkout(self):
        wt = self.linked()
        first = self.bridge("start", "x", cwd=wt)
        self.wait_state(first["run_id"])
        self.assertEqual(self.bridge("status", "--run", first["run_id"])["state"], "completed")
        self.assertEqual(self.result_view("--run", first["run_id"])[0]["state"], "completed")
        again = self.bridge("resume", first["run_id"], "go on", cwd=wt)
        self.wait_state(again["run_id"])
        self.assertEqual(self.runs_invoked()[-1]["cwd"], str(wt), "the thread goes on in its own directory")
        from_main = self.bridge("resume", first["thread_id"], "and on")
        self.wait_state(from_main["run_id"])

    def test_project_names_a_checkout_as_if_run_from_it(self):
        wt = self.linked()
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        out = self.bridge("start", "--project", wt, "x", cwd=elsewhere)
        self.assertTrue(out["events"].startswith(str(self.runs_dir) + "/"))
        self.assertEqual(out["cwd"], str(wt))

    def test_a_subdirectory_and_a_plain_directory_are_as_before(self):
        sub = self.project / "sub"
        sub.mkdir()
        out = self.bridge("start", "x", cwd=sub)
        self.assertTrue(out["events"].startswith(str(self.runs_dir) + "/"))
        self.assertEqual(out["cwd"], str(self.project))
        plain = self.tmp / "plain"
        plain.mkdir()
        self.extra_runs_dirs = [plain / ".codex-runs"]
        out = self.bridge("start", "x", cwd=plain)
        self.assertTrue(out["events"].startswith(str(plain / ".codex-runs") + "/"))

    def test_a_worktree_of_a_bare_repository_keeps_its_own(self):
        bare = self.tmp / "bare.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.project), str(bare)], check=True)
        subprocess.run(["git", "-C", str(bare), "worktree", "add", "-q", str(self.tmp / "bwt")], check=True)
        bwt = (self.tmp / "bwt").resolve()
        self.extra_runs_dirs = [bwt / ".codex-runs"]
        out = self.bridge("start", "x", cwd=bwt)
        self.assertTrue(out["events"].startswith(str(bwt / ".codex-runs") + "/"))

    def test_a_run_inside_a_batch_members_checkout_uses_the_same_registry(self):
        batch = self.bridge("batch", "--group", "g", "--worktree", "--task", "a")
        self.wait_all(batch)
        checkout = Path(batch["runs"][0]["worktree"])
        out = self.bridge("start", "--sandbox", "read-only", "look", cwd=checkout)
        self.assertTrue(out["events"].startswith(str(self.runs_dir) + "/"), out["events"])
        self.assertFalse((checkout / ".codex-runs").exists())

    def test_without_git_a_directory_is_no_repository_and_every_command_still_answers(self):
        # A PATH with Python and codex on it but no git: every question about a repository answers "not one".
        plain = self.tmp / "plain"
        plain.mkdir()
        self.extra_runs_dirs = [plain / ".codex-runs"]
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "python3").symlink_to(sys.executable)
        env = {"PATH": f"{FAKE_CODEX_DIR}{os.pathsep}{bin_dir}"}
        for args in (("status",), ("status", "--runs-dir", plain / ".codex-runs")):
            with self.subTest(args=args):
                self.assertEqual(self.bridge(*args, cwd=plain, env=env)["runs_dir"], str(plain / ".codex-runs"))
        out = self.bridge("batch", "--group", "g", "--task", "x", cwd=plain, env=env)
        header = json.loads(self.bridge_raw("result", "--group", "g", "--wait", cwd=plain, env=env).stdout.splitlines()[0])
        self.assertEqual((header["group_state"], header["done"]), ("completed", [out["runs"][0]["run_id"]]))
        self.assertTrue(self.bridge("doctor", cwd=plain, env=env)["ok"])

    def test_doctor_names_the_checkout_and_the_registry(self):
        wt = self.linked()
        rep = self.bridge("doctor", cwd=wt)
        self.assertEqual((rep["project"], rep["runs_dir"]), (str(wt), str(self.runs_dir)))


class WhenGitCannotAnswer(BridgeCase):
    """"git could not say" is unknown, never a no: nothing is deleted by hand, and a checkout is not taken for clean."""

    def no_git(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        if not (bin_dir / "python3").exists():
            (bin_dir / "python3").symlink_to(sys.executable)
        return {"PATH": str(bin_dir)}

    def test_force_deletes_nothing_by_hand(self):
        out = self.bridge("batch", "--group", "g", "--worktree", "--task", "a")
        self.wait_all(out)
        checkout = Path(out["runs"][0]["worktree"])
        (checkout / ".git").unlink()
        res = self.bridge("clean", "--group", "g", "--force", env=self.no_git())
        self.assertEqual((res["removed"], [k["path"] for k in res["kept"]]), ([], [str(checkout)]))
        self.assertTrue((checkout / "f.txt").exists() or (checkout / "tracked.txt").exists(), "the checkout's files are still there")

    def test_a_checkout_git_cannot_ask_about_counts_as_dirty(self):
        from unittest import mock
        out = self.bridge("batch", "--group", "g", "--worktree", "--task", "a")
        self.wait_all(out)
        with mock.patch.dict(os.environ, self.no_git()):
            self.assertTrue(engine("codex.git").is_dirty(Path(out["runs"][0]["worktree"])))


class CleaningAfterTheCheckoutIsGone(BridgeCase):
    """A batch cut from a linked worktree records that worktree as the repository its checkouts came from; once it is removed, `clean` asks the main checkout instead, and only about checkouts that repository records."""

    def test_the_main_checkout_removes_what_a_removed_worktree_cut(self):
        wt = self.tmp / "linked"
        self.git("worktree", "add", "-q", wt, "-b", "side")
        out = self.bridge("batch", "--group", "g", "--worktree", "--task", "a", "--task", "b", cwd=wt)
        self.wait_all(out)
        checkouts = [r["worktree"] for r in out["runs"]]
        self.git("worktree", "remove", "--force", wt)
        res = self.bridge("clean", "--group", "g")
        self.assertEqual(sorted(r["path"] for r in res["removed"]), sorted(checkouts), res)
        self.assertTrue(res["name_released"])
        listed = self.git("worktree", "list", "--porcelain").stdout
        self.assertFalse([c for c in checkouts if c in listed])

    def test_a_registry_named_from_another_repository_prunes_nothing_there(self):
        wt = self.tmp / "linked"
        self.git("worktree", "add", "-q", wt, "-b", "side")
        out = self.bridge("batch", "--group", "g", "--worktree", "--task", "a", cwd=wt)
        self.wait_all(out)
        self.git("worktree", "remove", "--force", wt)
        other = self.tmp / "other"
        other.mkdir()
        subprocess.run(["git", "-C", str(other), "init", "-q"], check=True)
        res = self.bridge("clean", "--group", "g", "--runs-dir", self.runs_dir, cwd=other)
        self.assertEqual(res["removed"], [])
        self.assertEqual([k["path"] for k in res["kept"]], [out["runs"][0]["worktree"]])
        self.assertTrue(res["kept"][0]["reason"])
        self.assertTrue(Path(out["runs"][0]["worktree"]).exists())

    def test_nor_prunes_the_repository_it_is_called_from(self):
        wt = self.tmp / "linked"
        self.git("worktree", "add", "-q", wt, "-b", "side")
        self.wait_all(self.bridge("batch", "--group", "g", "--worktree", "--task", "a", cwd=wt))
        self.git("worktree", "remove", "--force", wt)
        other = repo(self.tmp / "other")
        git(other, "worktree", "add", "-q", self.tmp / "others-wt", "-b", "side")
        shutil.rmtree(self.tmp / "others-wt")
        self.bridge("clean", "--group", "g", "--runs-dir", self.runs_dir, cwd=other)
        self.assertIn(str((self.tmp / "others-wt").resolve()), git(other, "worktree", "list", "--porcelain").stdout,
                      "its stale record is its own to prune")

    def test_nor_deletes_a_half_built_checkout_another_repository_never_owned(self):
        # A checkout without its .git file looks like one `git worktree add` never finished, which --force deletes by hand — but only on the word of the repository that cut it.
        wt = self.tmp / "linked"
        self.git("worktree", "add", "-q", wt, "-b", "side")
        out = self.bridge("batch", "--group", "g", "--worktree", "--task", "a", cwd=wt)
        self.wait_all(out)
        checkout = Path(out["runs"][0]["worktree"])
        (checkout / ".git").unlink()
        self.git("worktree", "remove", "--force", wt)
        other = self.tmp / "other"
        other.mkdir()
        subprocess.run(["git", "-C", str(other), "init", "-q"], check=True)
        res = self.bridge("clean", "--group", "g", "--force", "--runs-dir", self.runs_dir, cwd=other)
        self.assertEqual((res["removed"], [k["path"] for k in res["kept"]]), ([], [str(checkout)]))
        self.assertTrue(checkout.exists())


if __name__ == "__main__":
    unittest.main()
