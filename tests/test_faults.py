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

    def worktrees_cut(self):
        out = subprocess.run(["git", "-C", str(self.project), "worktree", "list",
                              "--porcelain"], capture_output=True, text=True).stdout
        return [l.split(" ", 1)[1] for l in out.splitlines()
                if l.startswith("worktree ")][1:]

    def test_what_was_cut_is_still_reachable_and_still_counted(self):
        """Killed *inside* the window, not merely somewhere near it.

        Waiting for "two members in the manifest" and killing then lands the
        signal wherever the scheduler happens to put it, so this passed about
        six times in ten and the four failures were the defect. The window that
        matters is the one between `create_run` cutting a worktree and the spawn
        loop learning the run id, so the test waits until it can *see* that
        state — a checkout on disk with no run id in the manifest — and kills
        there every time."""
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
        deadline = time.time() + 40
        in_window = False
        while time.time() < deadline:
            if manifest.exists():
                members = (json.loads(manifest.read_text()) or {}).get("members") or []
                with_id = [m for m in members if m.get("run_id")]
                if len(self.worktrees_cut()) > len(with_id):
                    in_window = True
                    break
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        self.assertTrue(in_window, "never observed a checkout whose member had no "
                                   "run id; this test asserts nothing without it")
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


class WhenARunIsStillBeingBuilt(FaultTestCase):
    """Publishing a run before cutting its worktree made it visible to `reap`
    before it had done anything slow — and `git worktree add` is allowed sixty
    seconds, twice `reap`'s thirty-second grace. A live run would be branded
    `orphaned`, which is terminal, so it dropped out of `batch clean`'s live
    guard and out of the occupancy check; `-f -f` then removed the checkout its
    owner was still writing into. Two fixes cancelling each other out."""

    def test_a_live_creator_is_not_reaped_however_slow_it_is(self):
        run_dir = self.runs_dir() / "r-building"
        run_dir.mkdir(parents=True)
        write_meta(run_dir, {"run_id": "r-building", "state": "starting",
                             "supervisor_pid": None, "creator_pid": os.getpid()})
        # Older than the grace period by a wide margin.
        old = time.time() - 600
        os.utime(run_dir / "meta.json", (old, old))

        from _registry import reap
        out = reap(run_dir, read_meta(run_dir))
        self.assertEqual(out["state"], "starting",
                         "a run whose creator is alive is being built, not dead")

    def test_a_dead_creator_is_still_reaped(self):
        run_dir = self.runs_dir() / "r-abandoned"
        run_dir.mkdir(parents=True)
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        write_meta(run_dir, {"run_id": "r-abandoned", "state": "starting",
                             "supervisor_pid": None, "creator_pid": dead.pid})
        old = time.time() - 600
        os.utime(run_dir / "meta.json", (old, old))

        from _registry import reap
        self.assertEqual(reap(run_dir, read_meta(run_dir))["state"], "orphaned",
                         "the grace period must still end for a creator that died")


class WhenAMembersMetaCannotBeParsed(FaultTestCase):
    """`batch clean` skipped a member whose meta would not parse when deciding
    whether anything was live, and then found its worktree anyway by convention
    — so a run last recorded `running` lost the only copy of its work with no
    `--force` ever passed. Unknown is not terminal."""

    def test_clean_refuses_rather_than_guessing_the_run_is_dead(self):
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        victim = out["runs"][0]["run_id"]
        (self.runs_dir() / victim / "meta.json").write_text("{ truncated")

        res = self.bridge("batch", "clean", "--group", "p1", expect_rc=1)
        self.assertIn("running members", res["error"])
        self.assertIn(victim, [r["run_id"] for r in res["running"]])
        self.assertTrue((self.runs_dir() / victim / "wt").exists(),
                        "the worktree must survive a clean that was refused")

        forced = self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(len(forced["removed"]), 2)

    def test_the_group_views_do_not_call_a_broken_run_a_missing_one(self):
        out = self.bridge("batch", "start", "--group", "p1", "--task", "a")
        rid = out["runs"][0]["run_id"]
        self.wait_for_state(rid)
        (self.runs_dir() / rid / "meta.json").write_text("{ truncated")

        st = self.bridge("status", "--group", "p1")
        self.assertEqual(st["runs_unreadable"], 1)
        reason = st["unstarted"][0]["error"]
        self.assertIn("will not parse", reason)
        self.assertNotIn("no longer in the registry", reason,
                         "the directory is still there; saying otherwise sends "
                         "the caller away from work that is still on disk")

        p = self.bridge_raw("status", "--group", "p1", "--follow",
                            "--follow-timeout", "5")
        self.assertIn("unreadable=1", p.stdout,
                      "the branch a caller polls has to say it too")


class WhenTwoResumesRaceOnOneThread(FaultTestCase):
    """`refuse_concurrent_turn` used to be the caller's job, which put the
    check and the new run's publication in different critical sections — in
    none, in other words. Two resumes a fraction of a second apart both saw an
    idle thread and both started a turn on it, each reporting success, and two
    Codex processes then appended to one rollout file.

    With the check and the publish inside one per-thread lock, this is
    deterministic rather than lucky: whichever process takes the lock second
    sees the first one's run and refuses."""

    def test_exactly_one_of_two_simultaneous_resumes_wins(self):
        first = self.bridge("start", "seed")
        self.wait_for_state(first["run_id"])

        procs = [subprocess.Popen(
            [sys.executable, str(BRIDGE), "resume", first["run_id"],
             "--project", str(self.project), "second turn"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env,
            text=True) for _ in range(2)]
        outs = [p.communicate() for p in procs]
        codes = [p.returncode for p in procs]

        self.assertEqual(sorted(codes), [0, 1],
                         f"exactly one resume may win; got {codes}\n"
                         + "\n".join(o[0] or o[1] for o in outs))
        refused = next(o[0] for o, c in zip(outs, codes) if c == 1)
        self.assertIn("live turn", refused)

        started = [json.loads(o[0].strip().splitlines()[-1])["run_id"]
                   for o, c in zip(outs, codes) if c == 0]
        live = [r for r in self.bridge("status")["runs"]
                if r["thread_id"] == first["thread_id"]
                and r["run_id"] != first["run_id"]]
        self.assertEqual([r["run_id"] for r in live], started,
                         "the registry must hold exactly the one run that won")
        for rid in started:
            self.wait_for_state(rid)

    def test_force_still_lets_a_second_turn_through(self):
        first = self.bridge("start", "seed")
        self.wait_for_state(first["run_id"])
        a = self.bridge("resume", first["run_id"], "one",
                        env_extra={"FAKE_CODEX_HANG": "1"})
        b = self.bridge("resume", first["run_id"], "--force", "two")
        self.assertNotEqual(a["run_id"], b["run_id"])
        self.bridge("stop", "--run", a["run_id"])
        for rid in (a["run_id"], b["run_id"]):
            self.wait_for_state(rid)


class WhenGitHasLockedAWorktree(FaultTestCase):
    """`git worktree add` holds a lock for the duration of the checkout, so a
    `batch start` killed inside it leaves one locked forever. A single
    `--force` does not lift a git lock — only `-f -f` does — and `batch clean`
    says in its own output that `--force` "lifted every protection at once"."""

    def test_force_lifts_a_git_lock_too(self):
        out = self.bridge("batch", "start", "--group", "p1",
                          "--task", "a", "--task", "b")
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        path = out["runs"][0]["worktree"]
        self.git("worktree", "lock", "--reason", "initializing", path)

        refused = self.bridge("batch", "clean", "--group", "p1")
        self.assertTrue(any(k["path"] == path for k in refused["kept"]),
                        "a locked worktree must be reported, not skipped")
        self.assertFalse(refused["name_released"],
                         "the name stays claimed while something is left behind")

        self.bridge("batch", "clean", "--group", "p1", "--force")
        self.assertEqual(self.bridge("doctor", expect_rc=doctor_rc(self))["worktrees"], 0)


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


class WhenAGroupNameIsReclaimedMidSpawn(FaultTestCase):
    """`batch clean` can release a name whose manifest has been claimed but has
    no members yet — it looks abandoned, because a just-claimed manifest and an
    abandoned one are the same file. A third process can then claim the name,
    and the first batch's `write_members` is a read-modify-write that would
    merge its members into the stranger's manifest: C's `requested`, A's
    members, and D36's single-use guarantee silently gone."""

    def groups_dir(self):
        return self.runs_dir() / ".groups"

    def test_a_writer_notices_the_manifest_stopped_being_its_own(self):
        from _batch import claim_group, write_members
        runs = self.runs_dir()
        runs.mkdir(parents=True, exist_ok=True)
        mine = claim_group(runs, "p1", requested=2)["epoch"]

        # Cleaned, then claimed again by someone else.
        (self.groups_dir() / "p1.json").unlink()
        theirs = claim_group(runs, "p1", requested=5)["epoch"]
        self.assertNotEqual(mine, theirs)

        with self.assertRaises(SystemExit):
            write_members(runs, "p1", [{"index": 0, "run_id": "r-a"}], epoch=mine)

        after = json.loads((self.groups_dir() / "p1.json").read_text())
        self.assertEqual(after["requested"], 5, "the other batch's manifest is intact")
        self.assertEqual(after["members"], [])

    def test_the_owner_still_writes_normally(self):
        from _batch import claim_group, write_members
        runs = self.runs_dir()
        runs.mkdir(parents=True, exist_ok=True)
        epoch = claim_group(runs, "p1", requested=1)["epoch"]
        write_members(runs, "p1", [{"index": 0, "run_id": "r-a"}], epoch=epoch)
        after = json.loads((self.groups_dir() / "p1.json").read_text())
        self.assertEqual([m["run_id"] for m in after["members"]], ["r-a"])


class WhenLiveWritersOverlapWithoutMatchingExactly(FaultTestCase):
    """`concurrent_writers`, at run creation, has always treated `/p` and
    `/p/sub` as one tree via `is_within`. `doctor` grouped by the exact `cwd`
    string, so the same two runs landed in two buckets of one and it warned
    about neither — the after-the-fact report blind to what the creation-time
    check had already seen."""

    def test_doctor_sees_a_parent_child_overlap(self):
        sub = self.project / "sub"
        sub.mkdir()
        a = self.bridge("start", "--sandbox", "workspace-write", "a",
                        env_extra={"FAKE_CODEX_HANG": "1"})
        b = self.bridge("start", "--sandbox", "workspace-write", "--cwd", str(sub), "b",
                        env_extra={"FAKE_CODEX_HANG": "1"})
        self.addCleanup(self.bridge, "stop", "--all")

        doctor = self.bridge("doctor", expect_rc=doctor_rc(self))
        overlap = [w for w in doctor["warnings"] if "overlap in" in w]
        self.assertTrue(overlap, f"no overlap warning; got {doctor['warnings']}")
        self.assertIn(a["run_id"], overlap[0])
        self.assertIn(b["run_id"], overlap[0])


class WhenACursorComesFromAnotherRun(FaultTestCase):
    """`--since` was only refused when it pointed past the end of the file. An
    offset that happened to be *inside* it was accepted, the read started
    mid-line, and the event straddling that offset was delivered as an
    anonymous `_unparsed` blob with its first half missing — one event
    destroyed, exit 0, under a docstring promising nothing is skipped."""

    def test_an_offset_that_is_not_an_event_boundary_is_refused(self):
        from _events import read_events, CursorOutOfRange
        r = self.bridge("start", "work")
        self.wait_for_state(r["run_id"])
        events = self.runs_dir() / r["run_id"] / "events.jsonl"
        raw = events.read_bytes()
        boundaries = {0}
        off = 0
        for line in raw.split(b"\n")[:-1]:
            off += len(line) + 1
            boundaries.add(off)
        mid = next(i for i in range(1, len(raw)) if i not in boundaries)

        with self.assertRaises(CursorOutOfRange):
            read_events(events, mid)
        for good in sorted(boundaries):
            evs, _ = read_events(events, good)
            self.assertEqual([e for e in evs if e.get("type") == "_unparsed"], [],
                             "a real boundary must never produce a mangled event")

    def test_the_cli_refuses_it_too_and_says_where_to_look(self):
        r = self.bridge("start", "work")
        self.wait_for_state(r["run_id"])
        events = self.runs_dir() / r["run_id"] / "events.jsonl"
        p = self.bridge_raw("log", "--run", r["run_id"], "--since",
                            str(len(events.read_bytes().split(b"\n")[0]) - 3))
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("run=", p.stdout + p.stderr)


class WhenTheRefIsOneTheRegistryHasNeverSeen(FaultTestCase):
    """The per-thread guard compares against each run's recorded `thread_id`,
    and a resume of a ref this project has never recorded publishes with
    `thread_id: null` — the real id only arrives later, from the spawned
    process, long after the lock is released. So the guard was blind to
    precisely the case SKILL.md leads with: picking up a thread started in the
    Codex TUI."""

    def test_two_resumes_of_one_unknown_ref_do_not_both_win(self):
        ref = "019fc000-0000-7000-8000-000000000abc"
        procs = [subprocess.Popen(
            [sys.executable, str(BRIDGE), "resume", ref,
             "--project", str(self.project), "--sandbox", "read-only", "go"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env,
            text=True) for _ in range(2)]
        outs = [p.communicate() for p in procs]
        codes = [p.returncode for p in procs]
        self.assertEqual(sorted(codes), [0, 1],
                         f"exactly one may win; got {codes}\n"
                         + "\n".join(o[0] or o[1] for o in outs))
        self.assertIn("live turn", next(o[0] for o, c in zip(outs, codes) if c == 1))
        for o, c in zip(outs, codes):
            if c == 0:
                self.wait_for_state(json.loads(o[0].strip().splitlines()[-1])["run_id"])

    def test_the_ref_is_recorded_so_a_later_reader_can_see_it(self):
        ref = "some-thread-name"
        out = self.bridge("resume", ref, "--sandbox", "read-only", "go")
        self.wait_for_state(out["run_id"])
        meta = read_meta(self.runs_dir() / out["run_id"])
        self.assertEqual(meta["resume_ref"], ref)


class WhenAForegroundRunRecordsItsProcessGroup(FaultTestCase):
    """`start_new_session` was set only when `--timeout` was also given, so a
    plain foreground run wrote the *caller's* process group into its meta —
    and `stop --run` on it would have signalled the caller."""

    def test_the_pgid_belongs_to_the_run_not_the_caller(self):
        out = self.bridge("start", "--foreground", "work")
        meta = read_meta(self.runs_dir() / out["run_id"])
        self.assertIsNotNone(meta["pgid"])
        self.assertNotEqual(int(meta["pgid"]), os.getpgid(0),
                            "a foreground run must not record the caller's group")


class WhenDoctorCannotEvenAsk(FaultTestCase):
    """`codex login status` also fails when it cannot load config at all, with
    a perfectly good auth.json present. Calling that "not authenticated" sends
    the caller to `codex login`, which fails identically, forever."""

    def test_a_config_error_is_not_reported_as_an_auth_problem(self):
        rep = self.bridge("doctor", expect_rc=2,
                          env_extra={"FAKE_CODEX_LOGIN_RC": "1",
                                     "FAKE_CODEX_LOGIN_OUT":
                                         "Error loading configuration: config.toml:1:26"})
        blocker = next(b for b in rep["blockers"] if "login status" in b)
        self.assertIn("not an auth one", blocker)
        self.assertNotIn("not authenticated", blocker)

    def test_a_real_auth_failure_still_says_so(self):
        rep = self.bridge("doctor", expect_rc=2,
                          env_extra={"FAKE_CODEX_LOGIN_RC": "1",
                                     "FAKE_CODEX_LOGIN_OUT": "Not logged in"})
        self.assertTrue(any("not authenticated" in b for b in rep["blockers"]))


class WhenTheUserHasTheirOwnWorktree(FaultTestCase):
    """`registered()` is `git worktree list` for the whole repository. Reporting
    someone else's checkout as "from batch runs, checked out under
    .codex-runs" is false twice over, and `batch clean` cannot touch it."""

    def test_doctor_only_counts_the_ones_it_cut(self):
        # A registry that exists, which is when doctor reports worktrees at all.
        self.wait_for_state(self.bridge("start", "seed")["run_id"])
        mine = self.tmp / "my-own-worktree"
        self.git("worktree", "add", "--detach", str(mine), "HEAD")
        self.addCleanup(self.git, "worktree", "remove", "--force", str(mine))

        rep = self.bridge("doctor", expect_rc=doctor_rc(self))
        self.assertEqual(rep["worktrees"], 0)
        self.assertFalse(any("from batch runs" in w for w in rep["warnings"]),
                         "a checkout this skill did not cut is not its business")


class WhenAReviewMemberReportsZeroUsage(FaultTestCase):
    """A review turn reports all-zero usage after real work. The single-run
    surfaces have said "unavailable, not free" since v0.1.0; the group one
    reported a confident zero and summed it into `totals`, undercounting any
    batch that mixed a reviewer with writers."""

    fixture = "review-clean-tree.jsonl"

    def test_the_group_result_does_not_call_it_free(self):
        tf = self.tmp / "tasks.jsonl"
        tf.write_text(json.dumps({"kind": "review",
                                  "review": {"uncommitted": True}}) + "\n")
        out = self.bridge("batch", "start", "--group", "p1", "--tasks-file", str(tf))
        for r in out["runs"]:
            self.wait_for_state(r["run_id"])
        res = self.bridge("result", "--group", "p1")
        row = res["results"][0]
        self.assertIsNone(row["usage"])
        self.assertIn("unavailable, not free", row["usage_note"])
        self.assertEqual(res["usage_unmeasured"], [row["run_id"]])


class WhenTwoSelectorsArePassedTogether(FaultTestCase):
    """`status` learned that `--run` and `--group` are different questions.
    `stop` and `result` never did, and they honoured opposite ones — so
    `stop --group G --run L` left every member of G running and said nothing."""

    def test_stop_and_result_refuse_the_pair_like_status_does(self):
        r = self.bridge("start", "one")
        self.wait_for_state(r["run_id"])
        self.bridge("batch", "start", "--group", "p1", "--task", "a")
        for cmd in ("stop", "result", "status"):
            with self.subTest(cmd=cmd):
                out = self.bridge(cmd, "--run", r["run_id"], "--group", "p1",
                                  expect_rc=1)
                self.assertIn("different questions", out["error"])
