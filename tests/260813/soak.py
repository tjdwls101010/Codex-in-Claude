"""A concurrency soak driver, and the record that makes its failures re-runnable.

The bridge's own history says every defect in it came from running it, never
from reading it, and the states this exercises — a registry written by several
processes at once, a reader polling a run mid-write, two turns racing for one
thread — are the ones no single-threaded test reaches at all.

What is and is not reproducible here, stated plainly because a soak that cannot
be re-run after it fails once is noise that gets deleted:

  * The PLAN — which worker performs which kind of operation, in what order — is
    a pure function of the seed. Re-running with the same seed issues the same
    sequence of commands.
  * The TARGETS are not. A worker resumes whatever thread exists when it gets
    there, so they are recorded rather than replayed.
  * The OS-level INTERLEAVING is not reproducible at all, by anything. What the
    history buys is a diagnosable failure — every command, its timing, and its
    exact output — not a deterministic replay of the race.

So a failure is reported with its seed and its history file, and the seed gets
you the same pressure rather than the same crash.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

from helpers import BRIDGE, FAKE_CODEX_DIR

# The op mix. Weights are shaped so the soak spends its time where the registry
# is actually contended — starting and observing runs — rather than on the
# operations that merely read one file.
OPS = [
    ("start", 5),
    ("batch_start", 3),
    ("resume", 4),        # the one turn-per-thread invariant lives or dies here
    ("status", 4),
    ("status_all", 2),
    ("log", 3),
    ("result", 2),
    ("stop", 2),
    ("batch_clean", 1),
]


# Worker 0 opens with these regardless of seed. Several ops can only do
# anything once something exists to address — `resume` needs a thread, `clean`
# needs a group — so a seed that happens to schedule them early produces a plan
# that quietly exercises less than it looks like it does, and an oracle that
# silently skips is one nobody notices has stopped testing anything. Coverage
# should be a property of the design, not of a lucky seed.
PROLOGUE = ["batch_start", "start"]


def plan(seed: int, workers: int, ops_each: int):
    """The sequence of op kinds each worker will attempt. Pure in the seed."""
    rng = random.Random(seed)
    kinds = [k for k, w in OPS for _ in range(w)]
    out = [[rng.choice(kinds) for _ in range(ops_each)] for _ in range(workers)]
    out[0] = PROLOGUE + out[0]
    # And someone has to clean a group, or oracle 9 never runs. It starts its
    # own rather than reaching for one of worker 0's: a worker whose early ops
    # all find empty pools no-ops through them in milliseconds and arrives here
    # before the first `batch start` anywhere has returned.
    out[-1] = out[-1] + ["batch_start", "batch_clean"]
    return out


class Soak:
    def __init__(self, project: Path, seed: int, workers=4, ops_each=6,
                 history_path: Path | None = None):
        self.project = project
        self.seed = seed
        self.plan = plan(seed, workers, ops_each)
        self.history_path = history_path
        self.history: list[dict] = []
        self.runs: list[str] = []          # run ids the bridge handed back
        self.threads: list[str] = []       # thread ids the bridge handed back
        self.groups: list[str] = []        # group names claimed successfully
        self.lock = threading.Lock()
        self.t0 = time.monotonic()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("FAKE_CODEX_")}
        self.env["PATH"] = f"{FAKE_CODEX_DIR}{os.pathsep}{self.env.get('PATH', '')}"
        self.env["CLAUDE_CODE_SESSION_ID"] = f"soak-{seed}"
        # Long enough that runs overlap and short enough that the suite stays
        # cheap: with this the workers are contending, not queueing.
        self.env["FAKE_CODEX_HANG"] = "1"

    # -- running -------------------------------------------------------------

    def call(self, worker: int, kind: str, *args, **env_extra):
        env = dict(self.env)
        env.update({k: str(v) for k, v in env_extra.items()})
        started = time.monotonic() - self.t0
        p = subprocess.run([sys.executable, str(BRIDGE), *[str(a) for a in args]],
                           cwd=str(self.project), env=env, capture_output=True,
                           text=True, timeout=120)
        record = {"worker": worker, "kind": kind, "argv": [str(a) for a in args],
                  "rc": p.returncode, "started": round(started, 4),
                  "ended": round(time.monotonic() - self.t0, 4),
                  "stdout": p.stdout, "stderr": p.stderr[-400:]}
        with self.lock:
            self.history.append(record)
        return record

    def parsed(self, record):
        """The one line of JSON, or None. Never raises — deciding whether an
        unparseable line is a defect is oracle 8's job, not this one's."""
        try:
            return json.loads(record["stdout"].strip().splitlines()[-1])
        except Exception:
            return None

    def pick(self, pool):
        with self.lock:
            return random.Random(len(self.history)).choice(pool) if pool else None

    def do(self, worker: int, kind: str, i: int):
        tag = f"w{worker}-{i}"
        if kind == "start":
            rec = self.call(worker, kind, "start", "--sandbox", "read-only",
                            "--label", tag, f"task {tag}")
            out = self.parsed(rec)
            if rec["rc"] == 0 and out:
                with self.lock:
                    self.runs.append(out["run_id"])
                    if out.get("thread_id"):
                        self.threads.append(out["thread_id"])
        elif kind == "batch_start":
            name = f"g{worker}-{i}"
            tasks = self.project.parent / f"tasks-{name}.jsonl"
            tasks.write_text("".join(
                json.dumps({"kind": "start", "prompt": f"{name} task {n}"}) + "\n"
                for n in range(2)))
            rec = self.call(worker, kind, "batch", "start", "--group", name,
                            "--tasks-file", tasks)
            out = self.parsed(rec)
            if rec["rc"] == 0 and out:
                with self.lock:
                    self.groups.append(name)
                    for r in out.get("runs", []):
                        self.runs.append(r["run_id"])
                        if r.get("thread_id"):
                            self.threads.append(r["thread_id"])
        elif kind == "resume":
            target = self.pick(self.threads)
            if not target:
                return
            rec = self.call(worker, kind, "resume", target, f"more {tag}")
            out = self.parsed(rec)
            if rec["rc"] == 0 and out:
                with self.lock:
                    self.runs.append(out["run_id"])
        elif kind == "status":
            target = self.pick(self.runs)
            if target:
                self.call(worker, kind, "status", "--run", target)
        elif kind == "status_all":
            self.call(worker, kind, "status", "--all")
        elif kind == "log":
            target = self.pick(self.runs)
            if target:
                self.call(worker, kind, "log", "--run", target, "--level", "compact")
        elif kind == "result":
            target = self.pick(self.runs)
            if target:
                self.call(worker, kind, "result", "--run", target)
        elif kind == "stop":
            target = self.pick(self.runs)
            if target:
                self.call(worker, kind, "stop", "--run", target)
        elif kind == "batch_clean":
            target = self.pick(self.groups)
            if target:
                self.call(worker, kind, "batch", "clean", "--group", target,
                          "--force")

    def worker(self, index: int):
        for i, kind in enumerate(self.plan[index]):
            try:
                self.do(index, kind, i)
            except Exception as e:      # a driver crash is a finding, not a stop
                with self.lock:
                    self.history.append({"worker": index, "kind": kind,
                                         "driver_error": repr(e)})

    def run(self):
        """Drive the plan, then poll meta.json throughout to catch torn writes."""
        stop_reading = threading.Event()
        self.torn: list[dict] = []
        reader = threading.Thread(target=self._read_continuously,
                                  args=(stop_reading,), daemon=True)
        reader.start()
        threads = [threading.Thread(target=self.worker, args=(i,))
                   for i in range(len(self.plan))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        stop_reading.set()
        reader.join(timeout=5)
        self.settle()
        self.write_history()
        return self

    def _read_continuously(self, stop: threading.Event):
        """Oracle 2's evidence. A reader that only looks after the writers are
        done can never see a torn write — the whole point is to be reading while
        `os.replace` is swapping the file under it."""
        runs_dir = self.project / ".codex-runs"
        while not stop.is_set():
            if runs_dir.is_dir():
                for d in runs_dir.iterdir():
                    meta = d / "meta.json"
                    if not meta.is_file():
                        continue
                    try:
                        json.loads(meta.read_text(encoding="utf-8"))
                    except FileNotFoundError:
                        pass        # removed by `batch clean` between the two calls
                    except Exception as e:
                        self.torn.append({"run": d.name, "error": repr(e),
                                          "at": round(time.monotonic() - self.t0, 4)})
            time.sleep(0.01)

    def settle(self, timeout=90):
        """Wait for every supervisor to record an outcome, so oracle 3 measures
        runs that were given the chance to finish."""
        from _registry import TERMINAL_STATES
        runs_dir = self.project / ".codex-runs"
        deadline = time.time() + timeout
        while time.time() < deadline:
            pending = []
            for d in sorted(runs_dir.iterdir()) if runs_dir.is_dir() else []:
                if not d.is_dir() or d.name.startswith("."):
                    continue
                try:
                    m = json.loads((d / "meta.json").read_text())
                except Exception:
                    continue
                if m.get("state") not in TERMINAL_STATES:
                    pending.append(d.name)
            if not pending:
                return
            time.sleep(0.2)

    def write_history(self):
        if not self.history_path:
            return
        self.history_path.write_text("".join(
            json.dumps({"seed": self.seed, **h}) + "\n" for h in self.history))

    # -- what the oracles read ----------------------------------------------

    def query(self, *args):
        """A settled, single-threaded read for the oracles to assert against."""
        rec = self.call(-1, "oracle", *args)
        return rec, self.parsed(rec)
