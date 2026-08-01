"""T1 — what `status` and `result` report (audit findings F3, F8).

F3: `cmd_status` used to truncate `rows` to the newest 20 before deriving
`running`/`threads` from them, so a live run older than the truncation window
silently vanished from `running`. A phase gate is literally
`len(running) == 0`, so that made the gate pass while the run was still
writing.

F8: `turn.failed` was parsed by `_events.py` and never surfaced, so a failed
run showed `message: null` and the reason needed a second `log` call.
"""

import json
import os
import subprocess
import time
import unittest
from datetime import datetime, timedelta, timezone

from helpers import BRIDGE, BridgeTestCase

import sys
sys.path.insert(0, str(BRIDGE.parent))
import _registry  # noqa: E402


def _iso(dt):
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class StatusTruncation(BridgeTestCase):
    """F3: 25 runs, the oldest 3 still alive — `status` without `--all` must
    still report those 3 in `running`."""

    def setUp(self):
        super().setUp()
        self._sleepers = []

    def _plant_run(self, runs_dir, index, started_at, alive):
        run_id = f"20260101-000000-run-{index:04d}"
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True)
        meta = {
            "run_id": run_id, "thread_id": f"thread-{index:04d}", "kind": "start",
            "label": None, "started_at": started_at,
            "cwd": str(self.project), "sandbox": "read-only", "model": None,
            "effort": None, "isolated": False,
        }
        if alive:
            # A genuinely alive process, not the test runner's own pid: the
            # test harness's cleanup does `kill -9` on every recorded
            # supervisor/codex pid, and it must not hit this process.
            proc = subprocess.Popen(["sleep", "300"])
            self._sleepers.append(proc)
            meta.update(state="running", supervisor_pid=proc.pid,
                       codex_pid=proc.pid, pgid=os.getpgid(proc.pid))
        else:
            meta.update(state="completed", exit_code=0, ended_at=started_at,
                       supervisor_pid=None, codex_pid=None, pgid=None)
        _registry.write_meta(run_dir, meta)
        return run_id

    def test_oldest_alive_runs_survive_truncation(self):
        runs_dir = _registry.ensure_runs_dir(self.project / ".codex-runs")
        base = datetime.now(timezone.utc)
        alive_ids = []
        for i in range(25):
            started_at = _iso(base + timedelta(seconds=i))
            alive = i < 3  # the OLDEST three are still running
            run_id = self._plant_run(runs_dir, i, started_at, alive)
            if alive:
                alive_ids.append(run_id)

        out = self.bridge("status")
        self.assertEqual(out["total_runs"], 25)
        self.assertEqual(out["runs_truncated"], 2,
                         "3 live rows kept + 20 newest, 3 of which overlap: "
                         "25 total - (3 live + 20 newest - 3 overlap) = 2")
        self.assertEqual(set(out["running"]), set(alive_ids),
                         "running must be derived from the full list, not the "
                         "truncated display list")
        self.assertEqual(len(out["done"]), 22)

        # --all must still agree on the full picture.
        out_all = self.bridge("status", "--all")
        self.assertEqual(out_all["runs_truncated"], 0)
        self.assertEqual(len(out_all["runs"]), 25)
        self.assertEqual(set(out_all["running"]), set(alive_ids))


class TurnFailedFixture(BridgeTestCase):
    """F8: a run whose Codex turn failed must surface the reason without a
    second `log` call."""

    fixture = "turn-failed.jsonl"

    def test_turn_failed_visible_from_status_and_result(self):
        r = self.start("do a thing", env_extra={"FAKE_CODEX_EXIT": "1"})
        row = self.wait_for_state(r["run_id"], states=("failed",))
        self.assertEqual(row["state"], "failed")
        self.assertIsNotNone(row["turn_failed"])
        self.assertIn("rate limit exceeded", row["turn_failed"])

        out = self.bridge("result", "--run", r["run_id"])
        self.assertIsNotNone(out["turn_failed"])
        self.assertIn("rate limit exceeded", out["turn_failed"])


if __name__ == "__main__":
    unittest.main()
