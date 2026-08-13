"""Ten oracles over one concurrency soak.

The driver is the expensive part; the oracles are all assertions over the same
recorded history, so the tenth costs almost nothing more than the first. That is
the whole reason to state ten rather than the two that motivated the exercise.

The soak runs once per class and every oracle reads that one run. Its size is
tuned to stay inside a normal suite — set `SOAK_WORKERS` / `SOAK_OPS` higher to
turn it into a real soak, and `SOAK_SEED` to re-issue a particular plan. On
failure the seed and the history file are named, so the pressure can be
reproduced even though the interleaving cannot be.

`--as-ready` will lean on oracle 5 in particular: it makes one member start
while others are still running, and one-turn-per-thread is the invariant that
makes that safe to do per thread rather than per group.
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

from helpers import BRIDGE, FAKE_CODEX_DIR
from soak import Soak

sys.path.insert(0, str(BRIDGE.parent))
from _registry import TERMINAL_STATES  # noqa: E402

SEED = int(os.environ.get("SOAK_SEED", "260813"))
WORKERS = int(os.environ.get("SOAK_WORKERS", "6"))
OPS = int(os.environ.get("SOAK_OPS", "8"))


class SoakOracles(unittest.TestCase):
    """One soak, ten questions."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="codex-soak-")).resolve()
        cls.project = cls.tmp / "proj"
        cls.project.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(cls.project)], check=True,
                       capture_output=True)
        for a in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", str(cls.project), *a], check=True,
                           capture_output=True)
        (cls.project / "f.txt").write_text("x\n")
        subprocess.run(["git", "-C", str(cls.project), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "commit", "-qm", "init"],
                       check=True, capture_output=True)
        cls.history_path = cls.tmp / f"soak-{SEED}.jsonl"
        cls.soak = Soak(cls.project, SEED, workers=WORKERS, ops_each=OPS,
                        history_path=cls.history_path).run()

    @classmethod
    def tearDownClass(cls):
        runs = cls.project / ".codex-runs"
        if runs.is_dir():
            for d in runs.iterdir():
                try:
                    m = json.loads((d / "meta.json").read_text())
                except Exception:
                    continue
                for pid in (m.get("supervisor_pid"), m.get("codex_pid")):
                    try:
                        os.kill(int(pid), 9)
                    except Exception:
                        pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def where(self):
        return (f"\nseed={SEED} workers={WORKERS} ops={OPS}"
                f"\nhistory: {self.history_path}"
                f"\nre-issue this plan with SOAK_SEED={SEED}")

    def registry(self):
        """Every run directory's meta, read directly. Deliberately not through
        `status`: oracles 1 and 3 are about what the registry holds, and asking
        the tool under test to summarise itself would let one bug hide another."""
        out = {}
        runs = self.project / ".codex-runs"
        for d in sorted(runs.iterdir()) if runs.is_dir() else []:
            if not d.is_dir() or d.name.startswith("."):
                continue
            try:
                out[d.name] = json.loads((d / "meta.json").read_text())
            except Exception:
                out[d.name] = None
        return out

    def test_the_soak_actually_did_something(self):
        """An oracle suite over an empty history passes vacuously."""
        started = [h for h in self.soak.history if h.get("rc") == 0
                   and h.get("kind") in ("start", "batch_start", "resume")]
        self.assertGreaterEqual(len(started), 3, self.where())
        self.assertGreaterEqual(len(self.registry()), 3, self.where())

    # -- 1 ------------------------------------------------------------------
    def test_every_run_handed_back_appears_exactly_once(self):
        _, listing = self.soak.query("status", "--all")
        self.assertIsNotNone(listing, "status --all did not answer" + self.where())
        listed = [r["run_id"] for r in listing["runs"]]
        self.assertEqual(len(listed), len(set(listed)),
                         "a run is listed twice" + self.where())
        on_disk = set(self.registry())
        missing = [r for r in set(self.soak.runs) if r in on_disk
                   and r not in set(listed)]
        self.assertEqual(missing, [],
                         "runs the bridge handed back, still on disk, absent "
                         "from `status --all`" + self.where())

    # -- 2 ------------------------------------------------------------------
    def test_no_reader_ever_saw_a_half_written_meta(self):
        self.assertEqual(
            self.soak.torn, [],
            "a reader polling throughout the soak saw meta.json mid-write; "
            "`os.replace` is what is supposed to make the swap atomic"
            + self.where())

    # -- 3 ------------------------------------------------------------------
    def test_every_run_reached_a_terminal_state(self):
        stuck = {rid: (m or {}).get("state") for rid, m in self.registry().items()
                 if m is not None and m.get("state") not in TERMINAL_STATES}
        self.assertEqual(stuck, {},
                         "runs still non-terminal after every child exited and "
                         "the soak settled" + self.where())

    # -- 4 ------------------------------------------------------------------
    def test_thread_ids_are_unique_per_thread_not_per_run(self):
        """A resumed run shares its parent's thread on purpose, so the invariant
        is that one thread is never handed out as two *new* threads."""
        fresh = [m.get("thread_id") for m in self.registry().values()
                 if m and m.get("kind") == "start" and m.get("thread_id")]
        self.assertEqual(len(fresh), len(set(fresh)),
                         "two independently started runs share a thread id"
                         + self.where())

    # -- 5 ------------------------------------------------------------------
    def test_no_thread_ever_had_two_live_turns(self):
        """D5's direct target, and the invariant `--as-ready` will rest on.

        Read off the recorded intervals rather than sampled live, because the
        overlap this forbids may last milliseconds.
        """
        spans = {}
        for rid, m in self.registry().items():
            if not m or not m.get("thread_id"):
                continue
            started, ended = m.get("started_at"), m.get("ended_at")
            if started and ended:
                spans.setdefault(m["thread_id"], []).append((started, ended, rid))
        overlaps = []
        for tid, runs in spans.items():
            for a in sorted(runs):
                for b in sorted(runs):
                    if a[2] >= b[2]:
                        continue
                    if a[0] < b[1] and b[0] < a[1]:
                        overlaps.append({"thread": tid, "runs": [a[2], b[2]]})
        self.assertEqual(overlaps, [],
                         "two turns overlapped on one thread — they race on the "
                         "same rollout file" + self.where())

    # -- 6 ------------------------------------------------------------------
    def test_a_group_name_was_never_granted_twice(self):
        claims = [h for h in self.soak.history
                  if h.get("kind") == "batch_start" and h.get("rc") == 0]
        names = [h["argv"][h["argv"].index("--group") + 1] for h in claims]
        self.assertEqual(len(names), len(set(names)),
                         "one group name was claimed by two batches" + self.where())

    # -- 7 ------------------------------------------------------------------
    def test_a_groups_membership_is_the_size_it_reported(self):
        for h in self.soak.history:
            if h.get("kind") != "batch_start" or h.get("rc") != 0:
                continue
            out = self.soak.parsed(h)
            if not out:
                continue
            name = out["group"]
            srec, status = self.soak.query("status", "--group", name)
            if srec["rc"] != 0:
                # A plan that cleaned this group released its name, and the
                # membership going with it is the documented behaviour.
                continue
            rrec, results = self.soak.query("result", "--group", name)
            with self.subTest(group=name):
                self.assertEqual(len(status["runs"]), out["spawned"],
                                 f"batch start said {out['spawned']}" + self.where())
                self.assertEqual(rrec["rc"], 0,
                                 "status can see the group but result cannot"
                                 + self.where())
                self.assertEqual(len(results["results"]), out["spawned"],
                                 "the two group views disagree on membership"
                                 + self.where())

    # -- 8 ------------------------------------------------------------------
    def test_every_invocation_printed_exactly_one_line_of_json(self):
        bad = []
        for h in self.soak.history:
            if "stdout" not in h or h["kind"] == "log":   # `log` is text by contract
                continue
            lines = [ln for ln in h["stdout"].splitlines() if ln.strip()]
            if len(lines) != 1:
                bad.append({"argv": h["argv"], "lines": len(lines)})
                continue
            try:
                json.loads(lines[0])
            except Exception as e:
                bad.append({"argv": h["argv"], "error": repr(e),
                            "stdout": h["stdout"][:200]})
        self.assertEqual(bad, [],
                         "stdout is the parsing contract every caller depends on; "
                         "a traceback leaking into it breaks them all"
                         + self.where())

    # -- 9 ------------------------------------------------------------------
    def test_cleaning_a_group_leaves_no_worktree_behind(self):
        cleaned = [h for h in self.soak.history
                   if h.get("kind") == "batch_clean" and h.get("rc") == 0]
        if not cleaned:
            self.skipTest("this plan cleaned no group")
        listed = subprocess.run(["git", "-C", str(self.project), "worktree",
                                 "list", "--porcelain"],
                                capture_output=True, text=True).stdout
        for h in cleaned:
            out = self.soak.parsed(h)
            for removed in (out or {}).get("removed", []):
                with self.subTest(run=removed["run_id"]):
                    self.assertNotIn(removed["path"], listed,
                                     "git still lists a removed worktree"
                                     + self.where())

    # -- 10 -----------------------------------------------------------------
    def test_a_cursor_walk_covers_the_stream_exactly_once(self):
        """`log --since` is how a caller reads a growing stream incrementally.
        Skipping loses events silently; repeating double-counts them. Walk one
        run's finished stream in small steps and compare against the file."""
        candidates = [rid for rid, m in self.registry().items()
                      if m and (self.project / ".codex-runs" / rid /
                                "events.jsonl").stat().st_size > 0]
        if not candidates:
            self.skipTest("no run produced events")
        run_id = sorted(candidates)[0]
        path = self.project / ".codex-runs" / run_id / "events.jsonl"
        expected = path.read_bytes()

        seen, cursor, steps = b"", 0, 0
        while cursor < len(expected) and steps < 200:
            steps += 1
            p = subprocess.run(
                [sys.executable, str(BRIDGE), "log", "--run", run_id,
                 "--since", str(cursor), "--level", "raw"],
                cwd=str(self.project), env={**os.environ,
                                            "PATH": f"{FAKE_CODEX_DIR}{os.pathsep}"
                                                    f"{os.environ['PATH']}"},
                capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr + self.where())
            nxt = None
            for ln in p.stdout.splitlines():
                if ln.startswith("# cursor="):
                    nxt = int(ln[len("# cursor="):].split(" ", 1)[0])
            self.assertIsNotNone(nxt, "log printed no cursor" + self.where())
            self.assertGreaterEqual(
                nxt, cursor, "the cursor went backwards, so a reader would "
                             "re-read events it already had" + self.where())
            seen += expected[cursor:nxt]
            if nxt == cursor:
                break
            cursor = nxt
        self.assertEqual(
            seen, expected[:cursor],
            "walking the stream by cursor did not reproduce it byte for byte"
            + self.where())
        self.assertEqual(
            cursor, len(expected),
            "the cursor walk stopped short of the end of the stream"
            + self.where())


if __name__ == "__main__":
    unittest.main()
