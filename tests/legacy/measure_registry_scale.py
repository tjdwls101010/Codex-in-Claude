"""U-07 — what the registry costs once a project has been used for a while.

Synthesises N run directories in a throwaway project and times the commands a
caller actually waits on. The meta.json shape is taken from a real run made by
the bridge with the fake codex on PATH, never hand-written: guessing the shape
is how the overlaps fixture ended up testing nothing (R11).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BRIDGE = REPO / ".claude/skills/codex/scripts/codex_bridge.py"
FAKE = HERE / "fake_codex"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 500

sys.path.insert(0, str(BRIDGE.parent))
from _registry import claim_run_dir, write_meta, read_meta  # noqa: E402

env = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_CODEX_")}
env["PATH"] = f"{FAKE}{os.pathsep}{env.get('PATH','')}"
env["CLAUDE_CODE_SESSION_ID"] = "u07"

tmp = Path(tempfile.mkdtemp(prefix="u07-")).resolve()
project = tmp / "proj"
project.mkdir(parents=True)
subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
for a in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
    subprocess.run(["git", "-C", str(project), *a], check=True, capture_output=True)
(project / "f.txt").write_text("x\n")
subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
subprocess.run(["git", "-C", str(project), "commit", "-qm", "i"], check=True,
               capture_output=True)


def bridge(*args, timeout=300):
    return subprocess.run([sys.executable, str(BRIDGE), *[str(a) for a in args]],
                          cwd=str(project), env=env, capture_output=True, text=True,
                          timeout=timeout)


def timed(label, *args):
    t0 = time.perf_counter()
    p = bridge(*args)
    dt = time.perf_counter() - t0
    ok = p.returncode in (0, 2)
    return {"command": label, "seconds": round(dt, 3), "rc": p.returncode, "ok": ok}


# --- one real run, so the synthesised ones have the true shape ---------------
seed = json.loads(bridge("start", "seed").stdout.strip().splitlines()[-1])
runs_dir = project / ".codex-runs"
deadline = time.time() + 60
while time.time() < deadline:
    m = read_meta(runs_dir / seed["run_id"]) or {}
    if m.get("state") in ("completed", "failed", "interrupted", "orphaned"):
        break
    time.sleep(0.1)
template = read_meta(runs_dir / seed["run_id"])
assert template and template.get("state"), "seed run never reached a terminal state"
# The seed's own stream is four lines. `doctor` sums every file under the runs
# dir, so measuring against that would understate it by two orders of
# magnitude; the biggest recorded fixture is a realistic write-heavy run.
seed_events = (HERE / "fixtures/mixed-bigout-and-failure.jsonl").read_bytes()
seed_msg = (runs_dir / seed["run_id"] / "last-message.txt")
seed_msg = seed_msg.read_bytes() if seed_msg.exists() else b""

print(f"seed run {seed['run_id']} state={template['state']}", flush=True)

# --- synthesise -------------------------------------------------------------
t0 = time.perf_counter()
for i in range(N):
    run_id, rd = claim_run_dir(runs_dir, f"u07-{i:06d}")
    m = dict(template)
    m["run_id"] = run_id
    m["thread_id"] = f"thread-{i:06d}"
    m["started_at"] = f"2026-08-03T{i//3600%24:02d}:{i//60%60:02d}:{i%60:02d}.000Z"
    m["usage"] = {"input_tokens": 15000 + (i % 500), "output_tokens": 200}
    write_meta(rd, m)
    (rd / "events.jsonl").write_bytes(seed_events)
    if seed_msg:
        (rd / "last-message.txt").write_bytes(seed_msg)
build = time.perf_counter() - t0
total_runs = sum(1 for d in runs_dir.iterdir() if d.is_dir() and not d.name.startswith("."))
print(f"synthesised {N} runs in {build:.1f}s (registry now holds {total_runs})", flush=True)

# --- measure ----------------------------------------------------------------
rows = [
    timed("status", "status"),
    timed("status --all", "status", "--all"),
    timed("doctor", "doctor"),
    timed("result --run <seed>", "result", "--run", seed["run_id"]),
]
t0 = time.perf_counter()
p = bridge("batch", "start", "--group", "bench", "--task", "a")
rows.append({"command": "batch start (1 member)", "seconds": round(time.perf_counter() - t0, 3),
             "rc": p.returncode, "ok": p.returncode == 0})
if p.returncode == 0:
    grp = json.loads(p.stdout.strip().splitlines()[-1])
    rid = grp["runs"][0]["run_id"]
    deadline = time.time() + 60
    while time.time() < deadline:
        if (read_meta(runs_dir / rid) or {}).get("state") in (
                "completed", "failed", "interrupted", "orphaned"):
            break
        time.sleep(0.1)
    rows.append(timed("status --group", "status", "--group", "bench"))
    rows.append(timed("status --group --follow", "status", "--group", "bench",
                      "--follow", "--follow-timeout", "5"))
    rows.append(timed("result --group", "result", "--group", "bench"))
else:
    print("batch start failed:", p.stdout[-500:], p.stderr[-500:])

print(json.dumps({"n_runs": total_runs, "synth_seconds": round(build, 1),
                  "measurements": rows}, indent=2))
shutil.rmtree(tmp, ignore_errors=True)
