"""U-08 — what collecting a group costs, applying T3's method to `result --group`.

`GROUP_MESSAGE_CAP = 4000` has "looks reasonable" as its only justification, and
T3's calibration was measured on single-run workloads. A batch changes the shape:
N streams collected in one payload, an `overlaps` map, and a per-member cap that
either never engages or engages constantly.

Same discipline as T3: one workload held identical across N, bytes measured on
the actual payload a caller receives, tokens reported as bytes/4 and labelled as
approximations because there is no local tokenizer for the model that reads this.

Writers are isolated per member, so the members do genuinely independent work
rather than fighting over one tree.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BRIDGE = REPO / ".claude/skills/codex/scripts/codex_bridge.py"
SIZES = [int(a) for a in sys.argv[1:]] or [3, 5, 8]

# T3's write-heavy shape: add a module, wire it in, add a test, run it.
PROMPT = ("Add a function `{name}` to `lib/util.py` that {what}, wire it into "
          "`lib/__init__.py`'s __all__, add a test for it in `tests/test_util.py`, "
          "and run `python3 -m unittest discover -s tests` to check it passes. "
          "Report what you changed and whether the suite is green.")
WORK = [
    ("clamp", "clamps a number between a low and a high bound"),
    ("chunk", "splits a list into fixed-size chunks, last one short"),
    ("dedupe", "removes duplicates from a list while keeping first-seen order"),
    ("flatten", "flattens one level of nesting in a list of lists"),
    ("compact", "drops None values from a list"),
    ("pluck", "takes a key and a list of dicts and returns that key's values"),
    ("window", "yields overlapping pairs of consecutive items"),
    ("partition", "splits a list into two by a predicate"),
]

tmp = Path(tempfile.mkdtemp(prefix="u08-")).resolve()
project = tmp / "proj"
(project / "lib").mkdir(parents=True)
(project / "tests").mkdir()
(project / "lib" / "util.py").write_text('"""Small helpers."""\n\n\ndef identity(x):\n    return x\n')
(project / "lib" / "__init__.py").write_text('from .util import identity\n\n__all__ = ["identity"]\n')
(project / "tests" / "test_util.py").write_text(
    'import sys, unittest\nfrom pathlib import Path\n'
    'sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n'
    'from lib.util import identity\n\n\n'
    'class Identity(unittest.TestCase):\n'
    '    def test_identity(self):\n        self.assertEqual(identity(3), 3)\n')
subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
for a in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
    subprocess.run(["git", "-C", str(project), *a], check=True, capture_output=True)
subprocess.run(["git", "-C", str(project), "add", "-A"], check=True, capture_output=True)
subprocess.run(["git", "-C", str(project), "commit", "-qm", "init"], check=True,
               capture_output=True)


def run(*args, timeout=2400):
    return subprocess.run([sys.executable, str(BRIDGE), *[str(a) for a in args]],
                          cwd=str(project), capture_output=True, text=True,
                          timeout=timeout)


def bridge(*args, **kw):
    p = run(*args, **kw)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {"_rc": p.returncode, "_out": p.stdout[-500:], "_err": p.stderr[-500:]}


rows = []
for n in SIZES:
    group = f"u08n{n}"
    tasks = []
    for name, what in WORK[:n]:
        tasks += ["--task", PROMPT.format(name=name, what=what)]
    out = bridge("batch", "start", "--group", group, "--effort", "low", *tasks)
    if "runs" not in out:
        rows.append({"n": n, "error": out})
        print(json.dumps(rows[-1])[:400], flush=True)
        continue
    ids = [r["run_id"] for r in out["runs"] if r.get("run_id")]
    run("status", "--group", group, "--follow", "--interval", "5",
        "--follow-timeout", "2400")

    p_group = run("result", "--group", group)
    group_bytes = len(p_group.stdout.encode())
    res = json.loads(p_group.stdout.strip().splitlines()[-1])

    per_run_bytes = 0
    for rid in ids:
        per_run_bytes += len(run("result", "--run", rid).stdout.encode())

    msgs = [r.get("message_bytes") or 0 for r in res.get("results", [])]
    truncated = sum(1 for r in res.get("results", []) if r.get("message_truncated"))
    rows.append({
        "n": n,
        "group_state": res.get("group_state"),
        "result_group_bytes": group_bytes,
        "sum_result_run_bytes": per_run_bytes,
        "ratio_group_over_separate": round(group_bytes / per_run_bytes, 3) if per_run_bytes else None,
        "member_message_bytes": msgs,
        "members_truncated_at_cap": truncated,
        "overlaps": len(res.get("overlaps") or {}),
        "overlap_paths": list(res.get("overlaps") or {})[:5],
        "totals": res.get("totals"),
        "approx_tokens_group": round(group_bytes / 4),
    })
    print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    bridge("batch", "clean", "--group", group, "--force")

print("\n=== SUMMARY ===")
print(json.dumps(rows, ensure_ascii=False, indent=2))
shutil.rmtree(tmp, ignore_errors=True)
