"""T1 — the registry under concurrent writers.

Every one of these reproduces a defect the 2026-08-01 audit found (F1, F2, F15).
They exist because batch orchestration makes concurrency the normal case rather
than the rare one: a group of N runs means N supervisors writing into the
registry while a `status --group --follow` reads it once a second.

The multi-process cases really do fork. `os.replace` is atomic and a threaded
test would pass against the broken code, because the bug is not in the rename —
it is that every writer stages through the *same tmp path*, so writer B truncates
A's inode and A's rename then fails on a file that no longer exists.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import BRIDGE

sys.path.insert(0, str(BRIDGE.parent))
import _registry  # noqa: E402


# -- worker bodies (module level so they survive spawn on macOS) -------------

def _hammer_write(run_dir_str, writer_id, rounds, errors):
    """Write our own key over and over. Any exception is the bug."""
    run_dir = Path(run_dir_str)
    for i in range(rounds):
        try:
            _registry.update_meta(run_dir, **{f"w{writer_id}": i})
        except Exception as e:
            errors.put(f"writer {writer_id} round {i}: {type(e).__name__}: {e}")


def _hammer_read(run_dir_str, rounds, errors):
    """A reader must never see a half-written or missing file."""
    run_dir = Path(run_dir_str)
    for i in range(rounds):
        meta = _registry.read_meta(run_dir)
        if meta is None:
            errors.put(f"reader round {i}: read_meta returned None")
        elif meta.get("run_id") != "fixture":
            errors.put(f"reader round {i}: lost run_id, saw {meta.get('run_id')!r}")


class RegistryConcurrentWrites(unittest.TestCase):
    """F1 — `write_meta` staged every writer through a fixed `.meta.json.tmp`,
    and `update_meta` was a lock-free read-modify-write."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codexreg-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        _registry.write_meta(self.run_dir, {"run_id": "fixture", "state": "running"})

    def test_concurrent_writers_never_raise(self):
        """The audit reproduced 120 uncaught FileNotFoundError in 240 attempts."""
        ctx = mp.get_context("spawn")
        errors = ctx.Queue()
        procs = [ctx.Process(target=_hammer_write,
                             args=(str(self.run_dir), w, 60, errors))
                 for w in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)

        found = []
        while not errors.empty():
            found.append(errors.get())
        self.assertEqual(found, [], f"{len(found)} concurrent-write failures")

    def test_concurrent_writers_do_not_lose_each_others_keys(self):
        """A lock-free read-modify-write drops the other writer's field: both
        read the same base, both merge only their own key, last write wins."""
        ctx = mp.get_context("spawn")
        errors = ctx.Queue()
        procs = [ctx.Process(target=_hammer_write,
                             args=(str(self.run_dir), w, 40, errors))
                 for w in range(3)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)

        meta = _registry.read_meta(self.run_dir)
        self.assertIsNotNone(meta, "meta.json unreadable after concurrent writes")
        for w in range(3):
            self.assertIn(f"w{w}", meta,
                          f"writer {w}'s key was lost to a racing writer: {meta}")
        self.assertEqual(meta.get("run_id"), "fixture",
                         "the pre-existing field was dropped by a merge")

    def test_reader_never_sees_a_torn_file(self):
        ctx = mp.get_context("spawn")
        errors = ctx.Queue()
        writers = [ctx.Process(target=_hammer_write,
                               args=(str(self.run_dir), w, 60, errors))
                   for w in range(3)]
        reader = ctx.Process(target=_hammer_read,
                             args=(str(self.run_dir), 200, errors))
        for p in (*writers, reader):
            p.start()
        for p in (*writers, reader):
            p.join(timeout=60)

        found = []
        while not errors.empty():
            found.append(errors.get())
        self.assertEqual(found, [], f"{len(found)} torn reads/writes")


class ReapDoesNotClobberAFinishedRun(unittest.TestCase):
    """F2 — `reap()` decided from the caller's stale snapshot and committed
    through `update_meta`, which re-reads. A run that finished in between got
    stamped `orphaned` with `exit_code: 0`, and it never self-heals."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codexreap-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()

    def test_reap_preserves_a_state_written_after_the_snapshot(self):
        # The caller's snapshot: still running, supervisor 1 (pid 1 is alive but
        # is not our supervisor -- use a pid that is certainly dead instead).
        _registry.write_meta(self.run_dir, {
            "run_id": "r", "state": "running", "supervisor_pid": 99999999,
            "started_at": "2026-08-01T00:00:00",
        })
        stale = _registry.read_meta(self.run_dir)

        # Meanwhile the supervisor finished and exited.
        _registry.update_meta(self.run_dir, state="completed", exit_code=0,
                              ended_at="2026-08-01T00:00:05")

        out = _registry.reap(self.run_dir, stale)
        self.assertEqual(out["state"], "completed",
                         "reap overwrote a genuinely completed run with its stale view")
        self.assertEqual(out.get("exit_code"), 0)
        self.assertEqual(out.get("ended_at"), "2026-08-01T00:00:05",
                         "reap clobbered the real ended_at")

        on_disk = _registry.read_meta(self.run_dir)
        self.assertEqual(on_disk["state"], "completed",
                         "the damage is permanent once written")

    def test_reap_still_marks_a_genuinely_dead_run(self):
        """The fix must not disarm reap: a run whose supervisor is gone and
        whose meta still says running is exactly what reap is for."""
        _registry.write_meta(self.run_dir, {
            "run_id": "r", "state": "running", "supervisor_pid": 99999999,
            "started_at": "2026-08-01T00:00:00",
        })
        meta = _registry.read_meta(self.run_dir)
        out = _registry.reap(self.run_dir, meta)
        self.assertEqual(out["state"], "orphaned")
        self.assertEqual(_registry.read_meta(self.run_dir)["state"], "orphaned")


class UpdateMetaIfCompareAndSet(unittest.TestCase):
    """The primitive F2's fix rests on."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codexcas-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()

    def test_applies_when_state_matches(self):
        _registry.write_meta(self.run_dir, {"state": "running"})
        out = _registry.update_meta_if(self.run_dir, ("running", "starting"),
                                       state="orphaned")
        self.assertEqual(out["state"], "orphaned")

    def test_leaves_a_nonmatching_state_alone_and_returns_what_is_on_disk(self):
        _registry.write_meta(self.run_dir, {"state": "completed", "exit_code": 0})
        out = _registry.update_meta_if(self.run_dir, ("running", "starting"),
                                       state="orphaned")
        self.assertEqual(out["state"], "completed")
        self.assertEqual(out["exit_code"], 0)
        self.assertEqual(_registry.read_meta(self.run_dir)["state"], "completed")


class RunIdCollisionIsRetried(unittest.TestCase):
    """F15 — a collision was an uncaught FileExistsError. Batch start makes
    same-second, same-label starts the normal case, which is exactly the
    condition the 4-hex suffix has to survive."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="codexcol-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.runs = self.tmp / ".codex-runs"
        self.runs.mkdir()

    def test_claims_a_fresh_dir_when_the_first_id_is_taken(self):
        seq = iter(["dup", "dup", "fresh"])
        real = _registry.new_run_id
        try:
            _registry.new_run_id = lambda label=None: next(seq)
            (self.runs / "dup").mkdir()
            run_id, run_dir = _registry.claim_run_dir(self.runs, label=None)
        finally:
            _registry.new_run_id = real
        self.assertEqual(run_id, "fresh")
        self.assertTrue(run_dir.is_dir())

    def test_gives_up_loudly_rather_than_silently_reusing_a_dir(self):
        real = _registry.new_run_id
        try:
            _registry.new_run_id = lambda label=None: "always-the-same"
            (self.runs / "always-the-same").mkdir()
            with self.assertRaises(FileExistsError):
                _registry.claim_run_dir(self.runs, label=None)
        finally:
            _registry.new_run_id = real


if __name__ == "__main__":
    unittest.main()
