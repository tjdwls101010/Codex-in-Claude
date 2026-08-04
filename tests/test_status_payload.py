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


class FollowNeedsAGroup(BridgeTestCase):
    """`--follow` is registered on `status` as a whole but only the `--group`
    branch reads it: the others emit a snapshot and exit. Accepting it silently
    hands the caller an answer they read as "I waited for this", and everything
    they conclude from that instant's state is then correctly reasoned from a
    false premise — R13's failure, not a usage error."""

    def test_follow_without_a_group_is_refused(self):
        r = self.start("do a thing")
        for args in (("status", "--run", r["run_id"], "--follow"),
                     ("status", "--follow"),
                     ("status", "--all", "--follow")):
            out = self.bridge(*args, expect_rc=1)
            self.assertIn("--follow needs --group", out["error"])
            self.assertIn("log --run", out["error"],
                          "the refusal has to name the command that does work")

    def test_a_run_and_a_group_together_are_refused(self):
        """The first guard only asked whether `--group` was present, so
        `--run X --group g --follow` walked past it and the `--run` branch then
        won — a snapshot again, with `--group` dropped entirely. Found by a
        Codex `review` member reading the commit that added the guard."""
        r = self.start("do a thing")
        self.bridge("batch", "start", "--group", "p1", "--task", "a")
        for args in (("status", "--run", r["run_id"], "--group", "p1"),
                     ("status", "--run", r["run_id"], "--group", "p1", "--follow")):
            out = self.bridge(*args, expect_rc=1)
            self.assertIn("different questions", out["error"])

    def test_follow_with_a_group_is_still_accepted(self):
        self.bridge("batch", "start", "--group", "p1", "--task", "a")
        # `--follow` streams text and ends on a terminal line; it is the one
        # subcommand path that does not answer in JSON.
        p = self.bridge_raw("status", "--group", "p1", "--follow",
                            "--follow-timeout", "20")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout.strip().splitlines()[-1],
                         r"^group\.(completed|partial|still-running) ")


class ExternalThreadTitles(BridgeTestCase):
    """Codex stores the whole prompt as a thread's title, preamble included,
    and this listing returns up to fifty of them. Capped for the same reason
    `result --group` caps a member's message."""

    def test_the_cap_announces_what_it_dropped(self):
        """The guard itself, at the boundary. A test in this tier cannot reach
        the payload: `--include-external` reads Codex's own thread database
        filtered to the project's cwd, and a temp project has no threads in it,
        so asserting over an empty list would pass while the cap did nothing.
        That the cap is actually applied in `cmd_status` is a T5 measurement
        against the real CLI, not a T1
        one — which is the whole distinction this round is about. The measured
        numbers live on `EXTERNAL_TITLE_CAP` so there is one copy of them."""
        import codex_bridge
        cap = codex_bridge.EXTERNAL_TITLE_CAP
        short = "already short"
        self.assertEqual(codex_bridge.clip(short, cap), short)
        long_title = "x" * (cap + 500)
        capped = codex_bridge.clip(long_title, cap)
        self.assertLess(len(capped), len(long_title))
        self.assertIn("+500 chars", capped)

    def test_the_flag_still_returns_the_note_and_the_threads_key(self):
        self.start("do a thing")
        out = self.bridge("status", "--include-external")
        self.assertIn("external_threads", out)
        self.assertIn("external_note", out)
        self.assertIn("--sandbox", out["external_note"],
                      "an outside thread has no recorded sandbox to re-assert, "
                      "and the note is the only place that is said")


if __name__ == "__main__":
    unittest.main()
