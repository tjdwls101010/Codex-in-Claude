"""T1 — what the registry says after something dies.

Most of this project's defects have lived just past a failure, not on the happy
path: the concurrent-writer corruption, a group claimed but never populated, a
worktree left behind. Every one of them was found by accident. Nothing here had
ever been injected on purpose.

The single question each test asks is the one D27 settled: after this failure,
does `status` / `result` / `doctor` say something true? A wrong answer is worse
than an error, because only the error gets acted on.
"""

from __future__ import annotations

import errno
import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import BRIDGE, BridgeTestCase   # puts the scripts dir on sys.path

from _registry import read_meta, write_meta   # noqa: E402


class FaultTestCase(BridgeTestCase):
    """A project with a commit, so worktrees can be cut from HEAD."""

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

    def runs_dir(self):
        return self.project / ".codex-runs"

    def kill_tree(self, proc):
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            proc.wait(timeout=10)

    def hanging_run(self, *extra):
        """A background run whose Codex will not exit on its own."""
        out = self.bridge("start", *extra, "work",
                          env_extra={"FAKE_CODEX_HANG": "1"})
        deadline = time.time() + 20
        while time.time() < deadline:
            m = read_meta(self.runs_dir() / out["run_id"]) or {}
            if m.get("supervisor_pid") and m.get("codex_pid"):
                return out["run_id"], m
            time.sleep(0.1)
        self.fail("the run never recorded both pids")

    def alive(self, pid):
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False


class ABatchKilledWhileSpawning(FaultTestCase):
    """A batch of three with worktrees, killed between members. The existing
    coverage killed a batch of two with no worktrees, so the checkouts — the
    part that outlives the process and holds the only copy of a member's work —
    were never in the picture."""

    def test_what_was_cut_is_still_reachable_and_still_counted(self):
        env = dict(self.env)
        env["FAKE_CODEX_PRE_DELAY"] = "6"
        proc = subprocess.Popen(
            [sys.executable, str(BRIDGE), "batch", "start", "--group", "p1",
             "--project", str(self.project), "--worktree",
             "--task", "one", "--task", "two", "--task", "three"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            start_new_session=True)
        self.addCleanup(self.kill_tree, proc)

        manifest = self.runs_dir() / ".groups" / "p1.json"
        deadline = time.time() + 30
        members = []
        while time.time() < deadline:
            if manifest.exists():
                members = (json.loads(manifest.read_text()) or {}).get("members") or []
                if len(members) >= 2:
                    break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        self.assertGreaterEqual(len(members), 2, "at least two members must have "
                                                 "spawned before the kill")
        self.kill_tree(proc)

        members = json.loads(manifest.read_text())["members"]
        spawned = [m["run_id"] for m in members if m.get("run_id")]
        status = self.bridge("status", "--group", "p1")
        self.assertNotEqual(status["group_state"], "completed",
                            "a batch that never finished spawning is not completed")
        self.assertEqual(sorted(r["run_id"] for r in status["runs"]), sorted(spawned))
        self.assertEqual(len(status["unstarted"]), 3 - len(spawned),
                         "the tasks the batch never reached are still its members")

        # The worktrees are the part nothing else has a copy of, and
        # `batch clean --group` is the only thing that removes them — so a
        # checkout belonging to no member of the group can never be cleaned.
        self.bridge("stop", "--group", "p1")
        for rid in spawned:
            self.wait_for_state(rid)
        before = self.bridge("doctor", expect_rc=doctor_rc(self))["worktrees"]
        self.assertGreater(before, 0, "this test is about worktrees; none were cut")
        self.bridge("batch", "clean", "--group", "p1", "--force")
        after = self.bridge("doctor", expect_rc=doctor_rc(self))["worktrees"]
        self.assertEqual(after, 0,
                         "every checkout the dead batch cut must be reachable "
                         "through the group that cut it")


def doctor_rc(case):
    """`doctor` exits 2 when it has blockers and 0 when it does not; a test that
    cares about the report body should not also have to predict which."""
    p = case.bridge_raw("doctor")
    return p.returncode


class WhenOnlyOneHalfOfARunDies(FaultTestCase):
    """A background run is two processes — the supervisor and Codex itself —
    and `reap` judges liveness from the supervisor alone. That is the right
    choice (the supervisor is what writes the outcome) but it has a consequence
    nothing asserted on."""

    def test_a_dead_supervisor_orphans_a_run_whose_codex_is_still_alive(self):
        run_id, meta = self.hanging_run()
        os.kill(int(meta["supervisor_pid"]), signal.SIGKILL)
        time.sleep(0.5)
        self.assertTrue(self.alive(meta["codex_pid"]),
                        "this test is about the window where Codex outlives its "
                        "supervisor; it did not")

        row = self.bridge("status", "--run", run_id)["runs"][0]
        self.assertEqual(row["state"], "orphaned")
        # Honest, and worth saying out loud: `orphaned` means "nothing is left
        # to record this run's outcome", not "nothing is running". The Codex
        # process is still there and `stop` is still the way to end it.
        self.assertTrue(self.alive(meta["codex_pid"]))
        self.bridge("stop", "--run", run_id)
        deadline = time.time() + 10
        while time.time() < deadline and self.alive(meta["codex_pid"]):
            time.sleep(0.1)
        self.assertFalse(self.alive(meta["codex_pid"]),
                         "stop signals the process group, so it reaches Codex "
                         "even with no supervisor left to ask")

    def test_a_dead_codex_leaves_its_supervisor_to_record_the_outcome(self):
        run_id, meta = self.hanging_run()
        os.kill(int(meta["codex_pid"]), signal.SIGKILL)
        row = self.wait_for_state(run_id)
        self.assertNotEqual(row["state"], "orphaned",
                            "the supervisor survived and must write a real "
                            "outcome rather than leaving a corpse to be reaped")
        self.assertIn(row["state"], ("failed", "interrupted"))

    def test_killing_the_whole_group_leaves_nothing_stuck_running(self):
        run_id, meta = self.hanging_run()
        os.killpg(int(meta["pgid"]), signal.SIGKILL)
        row = self.wait_for_state(run_id)
        self.assertEqual(row["state"], "orphaned")
        self.assertIsNotNone(row.get("ended_at"),
                             "a terminal state without an end time cannot be "
                             "distinguished from one still in flight")


class WhenTheRegistryCannotBeWritten(FaultTestCase):

    def test_a_failed_meta_write_leaves_the_previous_one_intact(self):
        """`write_meta` stages to a unique tmp and renames. A write that dies
        partway must leave neither a half-written meta.json nor debris that the
        next reader has to skip past."""
        run_dir = self.runs_dir() / "r-fault"
        run_dir.mkdir(parents=True)
        write_meta(run_dir, {"run_id": "r-fault", "state": "running"})

        real = Path.write_text

        def die_partway(self_path, data, *a, **kw):
            if self_path.name.startswith(".meta.json."):
                real(self_path, data[: len(data) // 2], *a, **kw)
                raise OSError(errno.ENOSPC, "No space left on device")
            return real(self_path, data, *a, **kw)

        with mock.patch.object(Path, "write_text", die_partway):
            with self.assertRaises(OSError):
                write_meta(run_dir, {"run_id": "r-fault", "state": "completed"})

        self.assertEqual(read_meta(run_dir), {"run_id": "r-fault", "state": "running"},
                         "the old meta.json must survive a failed replacement")
        self.assertEqual([p.name for p in run_dir.glob(".meta.json.*.tmp")], [],
                         "a failed write must not leave a staging file behind")

    def test_a_read_only_runs_dir_fails_loudly_and_doctor_names_it(self):
        runs = self.runs_dir()
        runs.mkdir(parents=True, exist_ok=True)
        os.chmod(runs, 0o500)
        self.addCleanup(os.chmod, runs, 0o700)

        out = self.bridge("start", "work", expect_rc=1)
        self.assertIn("error", out)

        doctor = self.bridge("doctor", expect_rc=2)
        self.assertFalse(doctor["runs_dir_writable"])
        self.assertTrue(any("not writable" in b for b in doctor["blockers"]))


class WhenAMetaFileCannotBeParsed(FaultTestCase):
    """`read_meta` swallows a parse error and `iter_runs` drops the run, so a
    corrupt run does not crash anything — it disappears. Disappearing quietly is
    the failure mode D27 exists to refuse: the caller is told about every run
    except the one that is broken."""

    def test_a_run_whose_meta_is_unreadable_is_reported_not_dropped(self):
        first = self.bridge("start", "one")["run_id"]
        self.wait_for_state(first)
        second = self.bridge("start", "two")["run_id"]
        self.wait_for_state(second)
        (self.runs_dir() / second / "meta.json").write_text("{ truncated")

        status = self.bridge("status")
        self.assertEqual([r["run_id"] for r in status["runs"]], [first])
        self.assertEqual(status.get("runs_unreadable"), 1,
                         "a run that cannot be read is still a run, and saying "
                         "nothing about it is the silent failure D27 refuses")

        doctor = self.bridge("doctor", expect_rc=doctor_rc(self))
        self.assertEqual(doctor.get("runs_unreadable"), 1)
        self.assertTrue(any("unreadable" in w for w in doctor["warnings"]))


class WhenAGroupManifestCannotBeParsed(FaultTestCase):

    def test_a_corrupt_manifest_fails_loudly_rather_than_looking_empty(self):
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        (self.runs_dir() / ".groups" / "p1.json").write_text("{ truncated")

        for cmd in (("status", "--group", "p1"), ("result", "--group", "p1")):
            res = self.bridge(*cmd, expect_rc=1)
            self.assertIn("error", res,
                          f"{cmd[0]} --group must refuse a manifest it cannot "
                          f"read instead of reporting an empty group")


class WhenAWorktreeIsRemovedFromUnderALiveRun(FaultTestCase):

    def test_clean_does_not_claim_to_have_removed_what_is_gone(self):
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        victim = Path(out["runs"][0]["worktree"])
        subprocess.run(["rm", "-rf", str(victim)], check=True)

        res = self.bridge("batch", "clean", "--group", "p1", expect_rc=0)
        self.assertNotIn(str(victim), res.get("removed", []),
                         "a path that was already gone was not removed by this")
        self.assertEqual(self.bridge("doctor", expect_rc=doctor_rc(self))["worktrees"], 0)


if __name__ == "__main__":
    unittest.main()
