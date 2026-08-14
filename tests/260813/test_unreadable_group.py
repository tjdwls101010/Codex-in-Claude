"""D6 — a group manifest that will not parse must not be a permanent dead end.

`read_group` collapses a parse failure into `None`, so every `--group` operation
answers "no such group". For read-only views that is merely the wrong diagnosis.
For `batch clean` it is a trap: the check runs before `--force` is ever
consulted, so the documented way past every other protection cannot reach this
one. The member runs and their worktrees stay on disk, and a worktree is the
only copy of what its run produced.

The asymmetry is what marks it as a gap rather than a policy — `--force` already
overrides a corrupt member `meta.json` (the legacy suite pins that), so the one
state with no override is the one where the manifest itself is the casualty.

Membership does not actually depend on the manifest: each run records its own
group when its directory is claimed, which is why `owned_run_ids` asks the
registry too. The manifest is the record of ORDER, and only `--resume-from`
needs that.
"""

from __future__ import annotations

import json
import time
import unittest

from helpers import BridgeCase


class UnreadableManifest(BridgeCase):

    def start_group(self, name="g", n=2):
        tasks = self.tasks_file(*[f"task {i}" for i in range(n)])
        out = self.bridge("batch", "start", "--group", name, "--tasks-file", tasks)
        for r in out["runs"]:
            self.wait_terminal(r["run_id"])
        return out

    def manifest(self, name="g"):
        return self.project / ".codex-runs" / ".groups" / f"{name}.json"

    def corrupt_manifest(self, name="g"):
        self.manifest(name).write_text("{ not json at all")

    def test_clean_says_the_manifest_is_unreadable_not_that_the_group_is_gone(self):
        self.start_group()
        self.corrupt_manifest()
        out = self.bridge("batch", "clean", "--group", "g", expect_rc=1)
        self.assertNotIn("no such group", out["error"])

    def test_force_can_clear_a_group_whose_manifest_will_not_parse(self):
        out = self.start_group()
        run_ids = [r["run_id"] for r in out["runs"]]
        self.corrupt_manifest()
        cleaned = self.bridge("batch", "clean", "--group", "g", "--force")
        self.assertEqual(
            sorted(r["run_id"] for r in cleaned["removed"]), sorted(run_ids),
            "the members are recoverable from the registry — each run records "
            "its own group — so --force has everything it needs")

    def test_the_worktrees_are_actually_gone_afterwards(self):
        self.start_group()
        self.corrupt_manifest()
        self.bridge("batch", "clean", "--group", "g", "--force")
        listed = self.git("worktree", "list", "--porcelain").stdout
        self.assertNotIn(".codex-runs", listed)

    def test_a_group_that_never_existed_still_says_so(self):
        out = self.bridge("batch", "clean", "--group", "nope", expect_rc=1)
        self.assertIn("no such group", out["error"])

    def test_a_healthy_group_still_cleans_without_force(self):
        out = self.start_group()
        cleaned = self.bridge("batch", "clean", "--group", "g")
        self.assertEqual(len(cleaned["removed"]), len(out["runs"]))
        self.assertTrue(cleaned["name_released"])

    def test_status_group_reports_the_unreadable_manifest(self):
        self.start_group()
        self.corrupt_manifest()
        out = self.bridge("status", "--group", "g", expect_rc=1)
        self.assertNotIn("no such group", out["error"])
        self.assertIn("manifest", json.dumps(out))


class UnreadableMemberBlocksPhaseTwo(BridgeCase):
    """D5's second location — `pair_with_previous`'s live-member check.

    It resolves each prior member through `find_run` and silently omits the ones
    it cannot resolve, so a phase-1 member with a corrupt meta.json drops out of
    the check that exists to stop phase 2 resuming a thread mid-turn.
    """

    def phase_one(self):
        """Two members, both finished, then one made unreadable.

        Both terminal on purpose: a member that is merely still running is
        already caught, so only a member the check cannot resolve isolates this
        guard from the per-member one downstream.
        """
        tasks = self.tasks_file("a", "b")
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", tasks)
        for r in out["runs"]:
            self.wait_terminal(r["run_id"])
        run_id = out["runs"][1]["run_id"]
        (self.project / ".codex-runs" / run_id / "meta.json").write_text("{ broken")
        return run_id

    def test_a_member_that_cannot_be_read_is_not_treated_as_finished(self):
        run_id = self.phase_one()
        refused = self.bridge("batch", "start", "--group", "p2",
                              "--resume-from", "p1",
                              "--tasks-file", self.tasks_file("c", "d"),
                              expect_rc=1)
        self.assertIn(run_id, json.dumps(refused))

    def test_nothing_of_phase_two_starts_when_the_check_refuses(self):
        """The whole point of checking the group before any member resumes:
        refusing per member would leave phase 2 half started."""
        self.phase_one()
        self.bridge("batch", "start", "--group", "p2", "--resume-from", "p1",
                    "--tasks-file", self.tasks_file("c", "d"), expect_rc=1)
        # The refusal lands above `claim_group`, so the name is still free.
        fresh = self.bridge("batch", "start", "--group", "p2",
                            "--tasks-file", self.tasks_file("c"))
        self.assertEqual(fresh["spawned"], 1)


class ALiveMemberKeepsItsGroupName(BridgeCase):
    """M3 — `batch clean --force` released the name while a live member still
    claimed it, because `kept` is populated only from worktrees on disk and a
    `kind=resume` member never has one. Every `--as-ready` waiter is such a
    member, so the reply both listed a running member and declared the name
    free. Reclaiming it then broke the new owner: `owned_run_ids` matches the
    registry on the bare group name with no epoch, so the next `batch clean`
    was refused citing a run that owner had never started."""

    def waiting_group(self):
        tasks = self.tasks_file("p1 work")
        self.bridge("batch", "start", "--group", "p1", "--tasks-file", tasks,
                    env_extra={"FAKE_CODEX_HANG": 20})
        out = self.bridge("batch", "start", "--group", "p2",
                          "--resume-from", "p1", "--as-ready",
                          "--tasks-file", self.tasks_file("p2 work"))
        rid = out["runs"][0]["run_id"]
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.meta(rid).get("state") == "waiting":
                break
            time.sleep(0.05)
        self.addCleanup(self.bridge_raw, "stop", "--all")
        return rid

    def test_a_forced_clean_does_not_free_a_name_with_live_members(self):
        self.waiting_group()
        out = self.bridge("batch", "clean", "--group", "p2", "--force")
        self.assertTrue(out["forced_past"].get("running_members"),
                        "the fixture needs a live member for this to mean "
                        "anything")
        self.assertFalse(
            out["name_released"],
            "the same reply cannot both list a running member and declare its "
            "group name free for someone else")

    def test_the_name_cannot_be_reclaimed_while_that_member_lives(self):
        self.waiting_group()
        self.bridge("batch", "clean", "--group", "p2", "--force")
        out = self.bridge("batch", "start", "--group", "p2",
                          "--tasks-file", self.tasks_file("unrelated"),
                          expect_rc=1)
        self.assertIn("already exists", out["error"])


if __name__ == "__main__":
    unittest.main()
