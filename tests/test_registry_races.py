"""The registry under real concurrent processes: many writers on one meta.json, a stale reap racing a completion, and many runs claimed in the same second.

Batches make concurrency the normal case: N supervisors write while followers read once a second and every `status` may reap.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from support.harness import ENGINE_MODULES, ENTRY, BridgeCase, engine, wait_until


def _write_own_key(run_dir, writer, rounds, errors):
    registry = engine("registry")
    for i in range(rounds):
        try:
            registry.update_meta(Path(run_dir), **{f"w{writer}": i})
        except Exception as e:
            errors.put(f"writer {writer} round {i}: {type(e).__name__}: {e}")


def _read(run_dir, rounds, errors):
    registry = engine("registry")
    for i in range(rounds):
        m = registry.read_meta(Path(run_dir))
        if not m or m.get("run_id") != "fixture":
            errors.put(f"reader round {i} saw {m!r}")


class ManyWritersOneMeta(unittest.TestCase):

    def setUp(self):
        self.registry = engine("registry")
        self.run_dir = Path(tempfile.mkdtemp(prefix="codex-race-")).resolve()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.run_dir)]))
        self.registry.write_meta(self.run_dir, {"run_id": "fixture", "state": "running"})

    def test_writers_never_fail_never_lose_a_key_and_a_reader_never_sees_a_torn_file(self):
        ctx = mp.get_context("spawn")
        errors = ctx.Queue()
        procs = [ctx.Process(target=_write_own_key, args=(str(self.run_dir), w, 60, errors)) for w in range(4)]
        procs.append(ctx.Process(target=_read, args=(str(self.run_dir), 300, errors)))
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=120)
        found = []
        while not errors.empty():
            found.append(errors.get())
        self.assertEqual(found, [])
        meta = self.registry.read_meta(self.run_dir)
        self.assertEqual({k: meta[k] for k in ("run_id", "w0", "w1", "w2", "w3")},
                         {"run_id": "fixture", "w0": 59, "w1": 59, "w2": 59, "w3": 59})
        self.assertEqual(list(self.run_dir.glob(".meta.json.*")), [], "no staging file is left behind")


class AStaleReap(unittest.TestCase):
    """`reap` decides from a snapshot and commits only if the state on disk is still active, so an outcome written in between wins."""

    def setUp(self):
        self.registry = engine("registry")
        self.run_dir = Path(tempfile.mkdtemp(prefix="codex-reap-")).resolve()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.run_dir)]))

    def dead_pid(self):
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        return p.pid

    def test_does_not_overwrite_a_completion_written_after_its_snapshot(self):
        self.registry.write_meta(self.run_dir, {"run_id": "r", "state": "running", "supervisor_pid": self.dead_pid()})
        stale = self.registry.read_meta(self.run_dir)
        # The supervisor finishing, from another process, between the snapshot and the reap.
        subprocess.run([sys.executable, "-c",
                        "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                        "import importlib; r = importlib.import_module(sys.argv[2]); "
                        "r.update_meta(Path(sys.argv[3]), state='completed', exit_code=0, ended_at='T')",
                        str(ENTRY.parent), ENGINE_MODULES["registry"], str(self.run_dir)],
                       check=True)
        out = self.registry.reap(self.run_dir, stale)
        self.assertEqual((out["state"], out["exit_code"], out["ended_at"]), ("completed", 0, "T"))
        self.assertEqual(self.registry.read_meta(self.run_dir)["state"], "completed")

    def test_still_marks_a_run_whose_supervisor_is_gone(self):
        self.registry.write_meta(self.run_dir, {"run_id": "r", "state": "running", "supervisor_pid": self.dead_pid()})
        self.assertEqual(self.registry.reap(self.run_dir, self.registry.read_meta(self.run_dir))["state"], "orphaned")

    def test_a_run_still_being_built_by_a_live_creator_is_not_reaped_however_old(self):
        self.registry.write_meta(self.run_dir, {"run_id": "r", "state": "starting", "creator_pid": os.getpid()})
        old = time.time() - 600
        os.utime(self.run_dir / "meta.json", (old, old))
        self.assertEqual(self.registry.reap(self.run_dir, self.registry.read_meta(self.run_dir))["state"], "starting")
        self.registry.write_meta(self.run_dir, {"run_id": "r", "state": "starting", "creator_pid": self.dead_pid()})
        os.utime(self.run_dir / "meta.json", (old, old))
        self.assertEqual(self.registry.reap(self.run_dir, self.registry.read_meta(self.run_dir))["state"], "orphaned")


class ManyRunsAtOnce(BridgeCase):

    def test_same_second_same_label_starts_all_get_their_own_run(self):
        procs = [self.spawn("start", "--label", "same", f"task {i}") for i in range(8)]
        outs = [p.communicate(timeout=90)[0] for p in procs]
        self.assertEqual([p.returncode for p in procs], [0] * 8, outs)
        ids = [json.loads(o)["run_id"] for o in outs]
        self.assertEqual(len(set(ids)), 8)
        seen_unreadable = []

        def all_done():
            listing = self.bridge("status", "--all")
            if listing.get("runs_unreadable"):
                seen_unreadable.append(listing["unreadable"])
            return all(r["state"] == "completed" for r in listing["runs"]) and len(listing["runs"]) == 8

        self.assertTrue(wait_until(all_done, timeout=60, interval=0.02))
        self.assertEqual(seen_unreadable, [], "a reader saw a meta.json mid-write")


if __name__ == "__main__":
    unittest.main()
