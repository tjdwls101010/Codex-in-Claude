"""T1 — per-member worktree assignment, and taking them away again.

The three facts this milestone is built on were measured before it was written
(`harness-spec.md` V-13/V-14/V-15). These tests hold the code to them.
"""

from __future__ import annotations

import json
import subprocess
import time
import unicodedata
import unittest
from pathlib import Path

from helpers import BridgeTestCase      # puts the scripts dir on sys.path

from _registry import TERMINAL_STATES   # noqa: E402
from _worktree import repo_identity     # noqa: E402


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

    def plant(self, run_id, abs_paths):
        ev = self.project / ".codex-runs" / run_id / "events.jsonl"
        with ev.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "type": "item.completed",
                "item": {"id": f"fc-{run_id}", "type": "file_change",
                         "changes": [{"path": p, "kind": "modify"} for p in abs_paths]},
            }) + "\n")


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

    def test_a_rejected_member_leaves_no_worktree_behind(self):
        """The worktree is cut after every check that can still refuse the run.
        Cutting it earlier leaked: a member rejected afterwards has no meta.json
        and so no run_id, and `batch clean` resolves worktrees through the
        manifest's run ids — the worktree survived every documented removal path
        while `batch clean` reported the group fully cleaned."""
        tf = self.tasks_file({"prompt": "a", "image": ["/nonexistent/x.png"]},
                             {"prompt": "b"}, {"prompt": "c"})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        self.assertIn("image not found", out["runs"][0]["error"])
        self.assertEqual(out["spawned"], 2)
        for r in out["runs"][1:]:
            self.wait_for_state(r["run_id"])

        listed = self.git("worktree", "list", "--porcelain").stdout
        cut = [ln for ln in listed.splitlines() if ln.startswith("worktree ")]
        self.assertEqual(len(cut), 3, "main tree plus exactly the two members")
        res = self.bridge("batch", "clean", "--group", "p1")
        self.assertTrue(res["name_released"])
        self.assertEqual(self.bridge("doctor")["worktrees"], 0,
                         "'name_released' must mean nothing was left behind")

    def test_an_unresolvable_base_fails_instead_of_silently_sharing_the_tree(self):
        """A typo'd --base answered with a degrade note would produce the one
        outcome the flag was used to avoid, and blame an empty repository."""
        out = self.bridge("batch", "start", "--group", "p1", "--base", "no-such-ref",
                          "--task", "a", "--task", "b", expect_rc=1)
        self.assertIn("does not resolve", out["error"])
        self.assertIn("no-such-ref", out["error"])
        self.assertFalse((self.project / ".codex-runs").exists()
                         and any((self.project / ".codex-runs").glob("2*")))

    def test_instructions_missing_at_an_older_base_are_reported(self):
        """V-14: project instructions do reach a worktree run, but only from a
        base where the file exists."""
        first = self.git("rev-parse", "HEAD").stdout.strip()
        (self.project / "AGENTS.md").write_text("# project rules\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "add agents")
        out = self.start_group("--base", first)
        self.assertEqual(out["worktrees"]["missing_at_base"], ["AGENTS.md"])
        self.assertIn("without the project instructions",
                      out["worktrees"]["missing_note"])
        for r in out["runs"]:
            self.assertFalse((Path(r["worktree"]) / "AGENTS.md").exists())
            self.wait_for_state(r["run_id"])

    def test_nothing_is_reported_missing_when_the_base_is_head(self):
        (self.project / "AGENTS.md").write_text("# project rules\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "add agents")
        out = self.start_group()
        self.assertNotIn("missing_at_base", out["worktrees"])
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


class OverlapsUnderIsolation(WorktreeTestCase):
    """Codex reports ABSOLUTE paths, and under worktree isolation every member
    has a different absolute prefix.

    The T1 test that already covered `overlaps` planted repo-relative paths,
    which is not the shape real events have — so it passed while the feature was
    blind in the only situation it exists for. Found by running a real batch:
    three members each creating `shared.txt` in their own worktree produced
    `overlaps: {}`. The cleaner the isolation, the more reliably it lied."""

    def test_the_same_repo_path_in_two_worktrees_is_an_overlap(self):
        out = self.start_group()
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        for r in out["runs"]:
            self.plant(r["run_id"], [str(Path(r["worktree"]) / "src" / "shared.py")])
        res = self.bridge("result", "--group", "p1")
        self.assertEqual(list(res["overlaps"]), ["src/shared.py"],
                         "absolute per-worktree paths must be compared relative "
                         "to each run's own root")
        self.assertEqual(sorted(res["overlaps"]["src/shared.py"]),
                         sorted(r["run_id"] for r in out["runs"]))

    def test_different_paths_in_two_worktrees_are_not_an_overlap(self):
        out = self.start_group()
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        for r, name in zip(out["runs"], ("alpha.py", "bravo.py")):
            self.plant(r["run_id"], [str(Path(r["worktree"]) / "src" / name)])
        self.assertEqual(self.bridge("result", "--group", "p1")["overlaps"], {})

    def test_the_same_name_in_two_different_repositories_is_not_an_overlap(self):
        """Making paths relative fixed the worktree case and broke this one: a
        per-task `cwd` puts two members in unrelated repositories, where an
        `output.txt` each is two files, not one. The key carries the repository
        — `--git-common-dir`, which every worktree of a repo shares and no two
        repos do — so relativising cannot merge them."""
        other = self.tmp / "otherrepo"
        (other / "src").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(other)], check=True, capture_output=True)
        (other / "src" / "output.txt").write_text("x\n")
        for a in (["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t",
                                  "commit", "-qm", "init"]):
            self.git(*a, cwd=other)

        tf = self.tasks_file({"prompt": "a"}, {"prompt": "b", "cwd": str(other)})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        for r, root in zip(out["runs"], (self.project, other)):
            self.wait_for_state(r["run_id"])
            self.plant(r["run_id"], [str(Path(root) / "src" / "output.txt")])
        self.assertEqual(self.bridge("result", "--group", "p1")["overlaps"], {},
                         "two repositories' output.txt are two files")

    def test_nested_roots_in_one_repository_still_see_the_same_file(self):
        """The mirror of the case above, and the one relativising to each run's
        own cwd got wrong: two members rooted at different depths of one
        repository that write the same file must still match. Paths are made
        relative to the repository's top level, not to wherever the run
        started."""
        sub = self.project / "src"
        sub.mkdir()
        (sub / "shared.py").write_text("x = 1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "add src")
        tf = self.tasks_file({"prompt": "a"}, {"prompt": "b", "cwd": str(sub)})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
            self.plant(r["run_id"], [str(sub / "shared.py")])
        self.assertEqual(list(self.bridge("result", "--group", "p1")["overlaps"]),
                         ["src/shared.py"])

    def test_a_path_outside_the_run_root_keeps_its_absolute_form(self):
        """`../../elsewhere` compares no better than the absolute path and reads
        worse, so a path that escapes the root is left alone."""
        out = self.start_group()
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        outside = str(self.tmp / "outside.py")
        for r in out["runs"]:
            self.plant(r["run_id"], [outside])
        res = self.bridge("result", "--group", "p1")
        self.assertEqual(list(res["overlaps"]), [outside])


NFC = unicodedata.normalize("NFC", "공유")
NFD = unicodedata.normalize("NFD", "공유")


class OverlapsAdversarial(WorktreeTestCase):
    """`overlaps` has been wrong three times, and the third design had never been
    attacked. These are the shapes the existing tests do not reach.

    The Unicode ones matter more than they look. APFS is normalisation-
    *preserving* and normalisation-*insensitive* — it stores whichever form it
    was handed and opens the file under either — so NFC and NFD are two names
    for one file that can both be true at once on disk. HFS+ used to fold every
    name to NFD, which would at least have been consistent. `git rev-parse
    --show-toplevel` reports the form on disk no matter which form its `-C`
    argument had (measured), so a run whose events carry the other form fails
    `relative_to` and falls back to an absolute key — a silent miss in exactly
    the field that exists to catch two members writing one file."""

    def test_one_file_named_two_ways_is_one_overlap(self):
        out = self.start_group()
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        for r, form in zip(out["runs"], (NFD, NFC)):
            self.plant(r["run_id"], [str(Path(r["worktree"]) / "src" / f"{form}.py")])
        res = self.bridge("result", "--group", "p1")
        self.assertEqual(list(res["overlaps"]), [f"src/{NFC}.py"],
                         "NFD and NFC name the same file on APFS; keys must fold")
        self.assertEqual(len(res["overlaps"][f"src/{NFC}.py"]), 2)

    def test_a_repository_stored_nfd_still_relativises_an_nfc_path(self):
        """The directory, not the file. `top` comes from git and carries the
        on-disk form; the event path may carry the other one."""
        repo = self.tmp / unicodedata.normalize("NFD", "프로젝트")
        (repo / "src").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        (repo / "src" / "x.py").write_text("x = 1\n")
        self.git("add", "-A", cwd=repo)
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init",
                 cwd=repo)

        tf = self.tasks_file({"prompt": "a", "cwd": str(repo)},
                             {"prompt": "b", "cwd": str(repo)})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        nfc_repo = self.tmp / unicodedata.normalize("NFC", "프로젝트")
        for r, root in zip(out["runs"], (repo, nfc_repo)):
            self.wait_for_state(r["run_id"])
            self.plant(r["run_id"], [str(Path(root) / "src" / "x.py")])
        self.assertEqual(list(self.bridge("result", "--group", "p1")["overlaps"]),
                         ["src/x.py"],
                         "a path spelled in the other normalisation must still "
                         "relativise instead of falling back to absolute")

    def test_a_submodule_is_not_its_parent_repository(self):
        """A submodule's `--git-common-dir` is `<parent>/.git/modules/<name>`
        (measured), so the same relative path in both is two files. The existing
        two-repositories test cannot reach this: here one repository is nested
        inside the other's checkout."""
        src = self.tmp / "subsrc"
        src.mkdir()
        subprocess.run(["git", "init", "-q", str(src)], check=True, capture_output=True)
        (src / "f.txt").write_text("x\n")
        self.git("add", "-A", cwd=src)
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init",
                 cwd=src)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 str(src), "vendor")

        parent_repo, _ = repo_identity(self.project)
        sub_repo, sub_top = repo_identity(self.project / "vendor")
        self.assertNotEqual(parent_repo, sub_repo,
                            "a submodule must not share its parent's identity")

        tf = self.tasks_file({"prompt": "a"},
                             {"prompt": "b", "cwd": str(self.project / "vendor")})
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        for r, root in zip(out["runs"], (self.project, sub_top)):
            self.wait_for_state(r["run_id"])
            self.plant(r["run_id"], [str(Path(root) / "f.txt")])
        self.assertEqual(self.bridge("result", "--group", "p1")["overlaps"], {},
                         "parent/f.txt and vendor/f.txt are two files")

    def test_two_worktrees_of_a_bare_repository_share_one_key(self):
        """A bare repository has no working tree of its own, so every checkout
        is a worktree — the isolation case with nothing to fall back on."""
        bare = self.tmp / "bare.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True,
                       capture_output=True)
        self.git("remote", "add", "o", str(self.project), cwd=bare)
        self.git("fetch", "-q", "o", cwd=bare)
        head = self.git("rev-parse", "o/HEAD", cwd=bare).stdout.strip()
        roots = []
        for name in ("w1", "w2"):
            self.git("worktree", "add", "-q", "--detach", str(self.tmp / name), head,
                     cwd=bare)
            roots.append(self.tmp / name)

        ids = [repo_identity(r)[0] for r in roots]
        self.assertEqual(ids[0], ids[1],
                         "two worktrees of one bare repository are one repository")

        tf = self.tasks_file(*({"prompt": "x", "cwd": str(r)} for r in roots))
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tf)
        for r, root in zip(out["runs"], roots):
            self.wait_for_state(r["run_id"])
            self.plant(r["run_id"], [str(root / "tracked.txt")])
        self.assertEqual(list(self.bridge("result", "--group", "p1")["overlaps"]),
                         ["tracked.txt"])

    def test_phase_two_does_not_overlap_its_own_predecessor(self):
        """D30's reason for keying by run rather than by worktree: a resumed
        member lands in the same tree its predecessor used, so a worktree key
        would make every phase-2 member overlap the run it continues."""
        first = self.start_group(n=2)
        for r in first["runs"]:
            self.wait_for_state(r["run_id"])
            self.plant(r["run_id"], [str(Path(r["worktree"]) / "src" / "shared.py")])

        second = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                             "--task", "go on", "--task", "go on")
        for r in second["runs"]:
            self.wait_for_state(r["run_id"])
            # A resumed member has no worktree of its own — it inherits its
            # predecessor's as its cwd, which is the whole reason this matters.
            self.plant(r["run_id"], [str(Path(r["cwd"]) / "src" / "shared.py")])

        res = self.bridge("result", "--group", "p2")
        members = sorted(r["run_id"] for r in second["runs"])
        self.assertEqual(sorted(res["overlaps"]["src/shared.py"]), members,
                         "phase 2's overlap is between its own members only")
        for rid in (r["run_id"] for r in first["runs"]):
            self.assertNotIn(rid, res["overlaps"]["src/shared.py"])

    def test_a_newline_in_a_path_is_carried_intact(self):
        """`log` writes bare text lines for Monitor to read, so a path is one
        place a newline could split a record in two."""
        out = self.start_group()
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        for r in out["runs"]:
            self.plant(r["run_id"], [str(Path(r["worktree"]) / "src" / "two\nlines.py")])
        res = self.bridge("result", "--group", "p1")
        self.assertEqual(list(res["overlaps"]), ["src/two\nlines.py"])

    def test_repo_identity_degrades_where_git_cannot_answer(self):
        """`meta.json` keeps the path a run was given, and the directory can be
        gone by the time results are collected — moved, or removed from under a
        live run. `changed_paths` must get `(None, None)` and keep the path
        absolute, not raise on the way to a group result."""
        self.assertEqual(repo_identity(self.project / "does-not-exist"), (None, None))
        self.assertEqual(repo_identity(self.project / ".git"), (None, None))
        self.assertEqual(repo_identity(self.tmp), (None, None))


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
        self.assertIn("batch of 3 tasks", prompt)
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
        self.assertIn("batch of 2 tasks", prompt)
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

    def test_force_says_what_it_overrode(self):
        """One flag lifts all three protections, and a caller usually reaches
        for it to get past one. What it actually overrode has to be in the
        result, not only in --help."""
        out = self.finished_group()
        (Path(out["runs"][0]["worktree"]) / "result.txt").write_text("work\n")
        (self.project / ".codex-runs" / ".groups" / "p2.json").write_text(
            json.dumps({"group": "p2", "derived_from": "p1", "members": []}))
        res = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(res["forced_past"]["derived_groups"], ["p2"])
        self.assertEqual(res["forced_past"]["discarded_uncommitted"],
                         [out["runs"][0]["worktree"]])
        self.assertIn("not only the one you were after", res["forced_note"])

    def test_a_clean_that_overrode_nothing_says_nothing(self):
        self.finished_group()
        res = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertNotIn("forced_past", res)

    def test_a_run_still_living_in_a_worktree_stops_the_clean(self):
        """Asked of the registry, not of the group graph. `derived_from` is one
        hop and evaporates when an intermediate manifest is cleaned: p1 -> p2 ->
        p3, clean p2, and p1 looks unreferenced while p3 is still running in
        p1's worktree. A run's own recorded cwd cannot go stale that way."""
        one = self.finished_group()
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--task", "a", "--task", "b")
        for r in two["runs"]:
            self.wait_for_state(r["run_id"])
        three = self.bridge("batch", "start", "--group", "p3", "--resume-from", "p2",
                            "--task", "a", "--task", "b",
                            env_extra={"FAKE_CODEX_HANG": "60"})
        self.wait_for_state(three["runs"][0]["run_id"], ("running",), timeout=30)

        # Break the chain exactly the way the reviewer did.
        self.bridge("batch", "clean", "--group", "p2", "--force")
        self.assertEqual(derived_of(self.project, "p1"), [],
                         "the group graph now says p1 is unreferenced")

        res = self.bridge("batch", "clean", "--group", "p1")
        self.assertEqual(res["removed"], [])
        self.assertFalse(res["name_released"])
        occupants = {r for k in res["kept"] for r in k["occupied_by"]}
        self.assertTrue(occupants & {r["run_id"] for r in three["runs"]},
                        "the live phase-3 members must be named as occupants")
        for r in one["runs"]:
            self.assertTrue(Path(r["worktree"]).exists())
        self.bridge("stop", "--group", "p3")

    def test_forcing_past_a_live_occupant_says_so(self):
        one = self.finished_group()
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--task", "a", "--task", "b",
                          env_extra={"FAKE_CODEX_HANG": "60"})
        self.wait_for_state(two["runs"][0]["run_id"], ("running",), timeout=30)
        res = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertIn(two["runs"][0]["run_id"],
                      res["forced_past"]["removed_under_live_runs"])
        self.bridge("stop", "--group", "p2")
        del one

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


class ResumeFrom(WorktreeTestCase):
    """M4c. Phase 2 continues phase 1 member for member, keeping each thread
    and the worktree that thread already lives in."""

    def phase_one(self, n=2):
        out = self.start_group(n=n)
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        return out

    def test_each_task_resumes_the_member_in_the_same_position(self):
        one = self.phase_one()
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--task", "keep going a", "--task", "keep going b")
        self.assertEqual(two["resumed_from"]["group"], "p1")
        self.assertEqual(two["resumed_from"]["members"],
                         [r["run_id"] for r in one["runs"]])
        for prev, now in zip(one["runs"], two["runs"]):
            meta = json.loads((self.project / ".codex-runs" / now["run_id"]
                               / "meta.json").read_text())
            self.assertEqual(meta["kind"], "resume")
            self.assertEqual(meta["parent_run_id"], prev["run_id"])
            self.wait_for_state(now["run_id"])

    def test_phase_two_inherits_the_worktree_rather_than_getting_a_new_one(self):
        one = self.phase_one()
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--task", "a", "--task", "b")
        for prev, now in zip(one["runs"], two["runs"]):
            self.assertEqual(now["cwd"], prev["worktree"],
                             "the thread continues where it already lives")
            self.assertIsNone(now.get("worktree"))
            self.wait_for_state(now["run_id"])
        self.assertEqual(self.bridge("doctor")["worktrees"], 2,
                         "resuming must not cut a second checkout per member")

    def test_a_count_mismatch_fails_before_anything_starts(self):
        """Pairing a short list lands a phase-2 task on the wrong phase-1
        thread, and every member after the mismatch continues work it was not
        written for."""
        self.phase_one()
        out = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--task", "only one", expect_rc=1)
        self.assertIn("one task to one member", out["error"])
        self.assertIn("2 started member", out["error"])
        self.assertIsNone(read_group_file(self.project, "p2"),
                          "a rejected pairing must not claim the new name")

    def test_a_live_phase_one_member_stops_the_whole_pairing(self):
        grp = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b",
                          env_extra={"FAKE_CODEX_HANG": "60"})
        self.wait_for_state(grp["runs"][0]["run_id"], ("running",), timeout=30)
        out = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--task", "a", "--task", "b", expect_rc=1)
        self.assertIn("still has members running", out["error"])
        self.assertTrue(out["running"])
        self.bridge("stop", "--group", "p1")

    def test_the_new_group_records_where_it_came_from(self):
        self.phase_one()
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--task", "a", "--task", "b")
        self.assertEqual(read_group_file(self.project, "p2")["derived_from"], "p1")
        # Which is exactly what makes phase 1 un-cleanable while phase 2 lives.
        res = self.bridge("batch", "clean", "--group", "p1", expect_rc=1)
        self.assertEqual(res["derived_groups"], ["p2"])
        for r in two["runs"]:
            self.wait_for_state(r["run_id"])

    def test_a_task_that_names_its_own_thread_keeps_it(self):
        """Explicit beats inferred, the same rule that governs a per-item cwd."""
        one = self.phase_one()
        outsider = self.start("a thread that was never in the group")
        self.wait_for_state(outsider["run_id"])
        tf = self.tasks_file(
            {"prompt": "a", "kind": "resume", "resume": outsider["run_id"]},
            {"prompt": "b"})
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--tasks-file", tf)
        parents = [json.loads((self.project / ".codex-runs" / r["run_id"]
                               / "meta.json").read_text())["parent_run_id"]
                   for r in two["runs"]]
        self.assertEqual(parents, [outsider["run_id"], one["runs"][1]["run_id"]],
                         "slot 0 keeps what it named; slot 1 still pairs")
        for r in two["runs"]:
            self.wait_for_state(r["run_id"])

    def test_a_stray_resume_field_on_a_start_task_is_refused(self):
        """Neither reading is safe to pick silently: honouring it leaves the
        paired member unresumed while the output still claims it was paired,
        and ignoring it discards a target the caller wrote down."""
        self.phase_one()
        tf = self.tasks_file({"prompt": "a", "kind": "start", "resume": "stale-id"},
                             {"prompt": "b"})
        out = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--tasks-file", tf, expect_rc=1)
        self.assertIn("names a thread to resume but its kind is 'start'",
                      out["error"])

    def test_a_review_task_cannot_be_a_continuation(self):
        """Rewriting it would turn a read-only review into a full agentic turn
        on someone else's thread — a larger authority than was asked for, and
        invisible in the output."""
        self.phase_one()
        tf = self.tasks_file({"prompt": "look", "kind": "review",
                              "review": {"uncommitted": True}},
                             {"prompt": "b"})
        out = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--tasks-file", tf, expect_rc=1)
        self.assertIn("a review cannot be that continuation", out["error"])

    def test_an_unnamed_resume_task_is_paired_rather_than_rejected(self):
        """--resume-from supplies the target positionally, so under it an
        unnamed `kind: resume` is the normal form, not an omission."""
        one = self.phase_one()
        tf = self.tasks_file({"prompt": "a", "kind": "resume"},
                             {"prompt": "b", "kind": "resume"})
        two = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--tasks-file", tf)
        for prev, now in zip(one["runs"], two["runs"]):
            meta = json.loads((self.project / ".codex-runs" / now["run_id"]
                               / "meta.json").read_text())
            self.assertEqual(meta["parent_run_id"], prev["run_id"])
            self.wait_for_state(now["run_id"])

    def test_a_member_that_never_got_a_thread_cannot_be_resumed(self):
        """A run id is not a thread. A member whose Codex died before emitting
        `thread.started` has a directory and a terminal state but nothing to
        continue, and a ref-less `codex exec resume` fails asynchronously —
        after this command has already said it started fine."""
        grp = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b",
                          env_extra={"FAKE_CODEX_EXIT": "1",
                                     "FAKE_CODEX_FIXTURE": str(self.empty_stream())})
        for r in grp["runs"]:
            self.wait_for_state(r["run_id"])
            meta = json.loads((self.project / ".codex-runs" / r["run_id"]
                               / "meta.json").read_text())
            self.assertIsNone(meta["thread_id"])
        out = self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                          "--task", "x", "--task", "y", expect_rc=1)
        self.assertIn("never recorded a thread id", out["error"])
        self.assertEqual(len(out["members"]), 2)

    def test_resuming_a_threadless_run_directly_is_refused_too(self):
        run = self.bridge("start", "a", env_extra={
            "FAKE_CODEX_EXIT": "1", "FAKE_CODEX_FIXTURE": str(self.empty_stream())})
        self.wait_for_state(run["run_id"])
        out = self.bridge("resume", run["run_id"], "more", expect_rc=1)
        self.assertIn("nothing to resume", out["error"])

    def empty_stream(self):
        f = self.tmp / "empty.jsonl"
        f.write_text("")
        return f

    def test_an_unknown_previous_group_says_so(self):
        out = self.bridge("batch", "start", "--group", "p2", "--resume-from", "nope",
                          "--task", "a", expect_rc=1)
        self.assertIn("no such group to resume from", out["error"])


def read_group_file(project, name):
    p = project / ".codex-runs" / ".groups" / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def derived_of(project, name):
    d = project / ".codex-runs" / ".groups"
    return [p.stem for p in sorted(d.glob("*.json"))
            if json.loads(p.read_text()).get("derived_from") == name]


class ConcurrentWritersAreNamedWhereTheMistakeHappens(WorktreeTestCase):
    """Reported, never refused (D17) — concurrency in one directory is sometimes
    what the caller wants, but it is never something they can see.

    Measured in an e2e session: told to continue three writing threads, it used
    three `resume` calls into one directory and escaped damage only because the
    three edits landed in three different files. `resume` has no worktree
    option, so nothing but this could have told it."""

    def hanging_writer(self, label):
        r = self.bridge("start", "keep going", "--label", label,
                        "--sandbox", "workspace-write",
                        env_extra={"FAKE_CODEX_HANG": "60"})
        self.wait_for_state(r["run_id"], ("running",), timeout=30)
        return r

    def test_a_second_writer_in_the_same_directory_is_named(self):
        first = self.hanging_writer("one")
        second = self.bridge("start", "also going", "--sandbox", "workspace-write",
                             env_extra={"FAKE_CODEX_HANG": "60"})
        self.assertEqual([w["run_id"] for w in second["concurrent_writers"]],
                         [first["run_id"]])
        self.assertIn("--resume-from", second["concurrent_writers_note"])
        self.bridge("stop", "--all")

    def test_resuming_into_an_occupied_directory_is_named_too(self):
        """The measured failure was on the resume path, not the start path: a
        session continuing several writing threads at once has no worktree
        option to reach for, so this warning is the only thing that can tell
        it."""
        first = self.hanging_writer("one")
        second = self.bridge("start", "elsewhere", "--sandbox", "workspace-write",
                             env_extra={"FAKE_CODEX_HANG": "60"})
        out = self.bridge("resume", first["run_id"], "keep going", "--force",
                          "--sandbox", "workspace-write",
                          env_extra={"FAKE_CODEX_HANG": "60"})
        named = {w["run_id"] for w in out["concurrent_writers"]}
        self.assertIn(second["run_id"], named)
        self.assertIn("--resume-from", out["concurrent_writers_note"])
        self.bridge("stop", "--all")

    def test_a_read_only_run_is_not_a_writer_and_is_not_warned_about(self):
        self.bridge("start", "just looking", "--sandbox", "read-only",
                    env_extra={"FAKE_CODEX_HANG": "60"})
        out = self.bridge("start", "also looking", "--sandbox", "read-only",
                          env_extra={"FAKE_CODEX_HANG": "60"})
        self.assertNotIn("concurrent_writers", out)
        self.bridge("stop", "--all")

    def test_members_in_their_own_worktrees_are_exempt(self):
        """The warning must not fire on the arrangement that makes it safe."""
        out = self.start_group()
        for r in out["runs"]:
            self.assertIsNotNone(r["worktree"])
            self.assertNotIn("concurrent_writers", r)
            self.wait_for_state(r["run_id"])
        self.assertFalse(any("share" in w for w in self.bridge("doctor")["warnings"]))

    def test_doctor_does_not_call_a_dead_run_a_live_writer(self):
        """The commit that reaped `concurrent_writers` claimed doctor too and
        did not do it. This is the report a caller reaches for precisely when
        they suspect something is stuck, which is exactly when meta.json is
        most likely to still say `running` for a supervisor that has gone."""
        first = self.hanging_writer("one")
        second = self.hanging_writer("two")
        self.assertTrue(any("live runs share" in w
                            for w in self.bridge("doctor")["warnings"]))
        self.bridge("stop", "--run", second["run_id"])
        # Plant the state a dead supervisor leaves: the file still says running.
        meta_path = self.project / ".codex-runs" / second["run_id"] / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta.update(state="running", ended_at=None, exit_code=None,
                    supervisor_pid=999999, codex_pid=999999)
        meta_path.write_text(json.dumps(meta))

        rep = self.bridge("doctor")
        self.assertFalse(any("live runs share" in w for w in rep["warnings"]),
                         "a dead supervisor must not be reported as a live writer")
        self.bridge("stop", "--all")

    def test_doctor_groups_live_runs_by_their_recorded_cwd(self):
        self.hanging_writer("one")
        self.hanging_writer("two")
        rep = self.bridge("doctor")
        shared = [w for w in rep["warnings"] if "live runs share" in w]
        self.assertEqual(len(shared), 1, rep["warnings"])
        self.assertIn("2 of which can write", shared[0])
        self.assertTrue(rep["ok"], "sharing a directory is not a blocker")
        self.bridge("stop", "--all")


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
