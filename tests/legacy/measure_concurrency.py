"""U-06 — concurrency above the N=8 that V-11/V-12 measured.

Same method as V-11: one trivial prompt, one CODEX_HOME, real `codex exec`
through the bridge, N members as one batch. Records the two things that are
different failures and were being conflated:

  (a) how long `batch start` takes to RETURN — the sequential spawn loop, with
      up to THREAD_ID_WAIT per member. A latency finding.
  (b) whether sqlite contention or rate limiting actually appears. Only this
      one is D34's condition for reconsidering --stagger.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
BRIDGE = REPO / ".claude/skills/codex/scripts/codex_bridge.py"
SIZES = [int(a) for a in sys.argv[1:]] or [12, 16, 24]
PROMPT = "Reply with exactly the word ACKNOWLEDGED and nothing else."

tmp = Path(tempfile.mkdtemp(prefix="u06-")).resolve()
project = tmp / "proj"
project.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
for a in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
    subprocess.run(["git", "-C", str(project), *a], check=True, capture_output=True)
(project / "f.txt").write_text("x\n")
subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
subprocess.run(["git", "-C", str(project), "commit", "-qm", "i"], check=True,
               capture_output=True)


def bridge(*args, timeout=1800):
    p = subprocess.run([sys.executable, str(BRIDGE), *[str(a) for a in args]],
                       cwd=str(project), capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {"_rc": p.returncode, "_out": p.stdout[-600:], "_err": p.stderr[-600:]}


CONTENTION = re.compile(r"database is locked|SQLITE_BUSY|rate.?limit|429|too many requests",
                        re.I)
rows = []
for n in SIZES:
    group = f"u06n{n}"
    tasks = []
    for i in range(n):
        tasks += ["--task", PROMPT]
    t0 = time.perf_counter()
    out = bridge("batch", "start", "--group", group, "--sandbox", "read-only",
                 "--effort", "low", *tasks)
    spawn = time.perf_counter() - t0
    if "runs" not in out:
        rows.append({"n": n, "error": out})
        print(json.dumps(rows[-1])[:400], flush=True)
        continue
    ids = [r["run_id"] for r in out["runs"] if r.get("run_id")]
    threads = [r.get("thread_id") for r in out["runs"] if r.get("thread_id")]

    t1 = time.perf_counter()
    subprocess.run([sys.executable, str(BRIDGE), "status", "--group", group,
                    "--follow", "--interval", "5", "--follow-timeout", "1800"],
                   cwd=str(project), capture_output=True, text=True, timeout=1900)
    wall = time.perf_counter() - t1

    res = bridge("result", "--group", group)
    states = {}
    hits = []
    for rid in ids:
        m = json.loads((project / ".codex-runs" / rid / "meta.json").read_text())
        states[m.get("state")] = states.get(m.get("state"), 0) + 1
        for f in ("events.jsonl", "stderr.log"):
            p = project / ".codex-runs" / rid / f
            if p.exists():
                for line in p.read_text(errors="replace").splitlines():
                    if CONTENTION.search(line):
                        hits.append(line[:200])
    rows.append({
        "n": n,
        "spawned": len(ids),
        "batch_start_seconds": round(spawn, 2),
        "group_wall_seconds": round(wall, 2),
        "distinct_thread_ids": len(set(threads)),
        "thread_ids_total": len(threads),
        "states": states,
        "group_state": res.get("group_state"),
        "contention_hits": len(hits),
        "contention_samples": hits[:3],
        "totals": res.get("totals"),
    })
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    bridge("batch", "clean", "--group", group, "--force")

print("\n=== SUMMARY ===")
print(json.dumps(rows, ensure_ascii=False, indent=2))
shutil.rmtree(tmp, ignore_errors=True)
