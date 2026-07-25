#!/usr/bin/env python3
"""T2 — integration against the real Codex CLI. Costs real Codex tokens.

Gated behind an explicit flag so it can never run by accident:

    CODEX_SKILL_TEST_INTEGRATION=1 python3 tests/integration/run_integration.py
    …                                  … --only I4          # one case
    …                                  … --keep             # keep the scratch repo

Everything runs against a throwaway git repository under the system temp dir.
Nothing touches the user's projects.

I4 is the case that matters most: it re-verifies against the actual CLI the
sandbox-drift defect the whole registry exists to close.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
BRIDGE = REPO / ".claude" / "skills" / "codex" / "scripts" / "codex_bridge.py"
sys.path.insert(0, str(BRIDGE.parent))
from _util import codex_home, nfc  # noqa: E402

RESULTS = []


# -- helpers ----------------------------------------------------------------

def bridge(project: Path, *args, expect_rc=0, timeout=900):
    p = subprocess.run([sys.executable, str(BRIDGE), *[str(a) for a in args]],
                       cwd=str(project), capture_output=True, text=True, timeout=timeout)
    if p.returncode != expect_rc:
        raise AssertionError(f"bridge {args} rc={p.returncode}\n{p.stdout}\n{p.stderr}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def bridge_text(project: Path, *args, timeout=900):
    p = subprocess.run([sys.executable, str(BRIDGE), *[str(a) for a in args]],
                       cwd=str(project), capture_output=True, text=True, timeout=timeout)
    return p.stdout


def wait_done(project: Path, run_id, timeout=900):
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = bridge(project, "status", "--run", run_id)["runs"][0]
        if row["state"] in ("completed", "failed", "interrupted", "orphaned"):
            return row
        time.sleep(3)
    raise AssertionError(f"{run_id} did not finish within {timeout}s")


def rollout_path(thread_id):
    hits = list((codex_home() / "sessions").rglob(f"*{thread_id}*.jsonl"))
    if not hits:
        raise AssertionError(f"no rollout file for thread {thread_id}")
    return hits[0]


def turn_contexts(thread_id):
    """Per-turn ground truth: what the turn actually ran under."""
    out = []
    for line in rollout_path(thread_id).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") == "turn_context":
            p = o["payload"]
            out.append({
                "sandbox": (p.get("sandbox_policy") or {}).get("type"),
                "model": p.get("model"),
                "effort": (p.get("collaboration_mode") or {}).get("settings", {}).get("reasoning_effort"),
                "cwd": p.get("cwd"),
            })
    return out


def solid_png(path: Path, rgb=(220, 20, 60), size=64):
    """A pure-stdlib PNG so I8 needs no image library."""
    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b""))


def case(fn):
    fn._is_case = True
    return fn


def run_case(name, fn, project):
    t0 = time.time()
    print(f"\n=== {name} " + "=" * (64 - len(name)))
    try:
        detail = fn(project) or ""
        RESULTS.append((name, "PASS", detail, time.time() - t0))
        print(f"--- {name} PASS ({time.time() - t0:.0f}s) {detail}")
    except Exception as e:
        RESULTS.append((name, "FAIL", str(e), time.time() - t0))
        print(f"--- {name} FAIL ({time.time() - t0:.0f}s): {e}")


# -- the cases --------------------------------------------------------------

@case
def I1(project):
    """Background start captures a thread id, the log grows, result returns the message."""
    r = bridge(project, "start", "--label", "i1", "--sandbox", "read-only",
               "Reply with exactly: INTEGRATION_ONE")
    assert r["thread_id"], "no thread_id captured from the background start"
    assert r["state"] in ("running", "starting", "completed"), r["state"]
    row = wait_done(project, r["run_id"])
    assert row["state"] == "completed", row
    ev = Path(r["events"])
    assert ev.stat().st_size > 0, "events.jsonl never grew"
    res = bridge(project, "result", "--run", r["run_id"])
    assert "INTEGRATION_ONE" in (res["message"] or ""), res["message"]
    assert res["usage"]["input_tokens"] > 0, res["usage"]
    return f"thread={r['thread_id'][:13]} in={res['usage']['input_tokens']}"


@case
def I2(project):
    """Stop mid-run, then resume with a correction: same thread, rollout appended."""
    r = bridge(project, "start", "--label", "i2", "--sandbox", "workspace-write",
               "Run each of these as a SEPARATE shell command, one at a time: "
               "'sleep 3 && echo a', 'sleep 3 && echo b', 'sleep 3 && echo c', "
               "'sleep 3 && echo d', 'sleep 3 && echo e'.")
    tid = r["thread_id"]
    assert tid, "no thread id"
    # Let it get properly under way before interrupting.
    deadline = time.time() + 60
    while time.time() < deadline:
        row = bridge(project, "status", "--run", r["run_id"])["runs"][0]
        if row["commands"] >= 1:
            break
        time.sleep(2)
    before = len(rollout_path(tid).read_text(errors="replace").splitlines())

    stopped = bridge(project, "stop", "--run", r["run_id"])
    assert stopped["stopped"][0]["signalled"], stopped
    row = wait_done(project, r["run_id"], timeout=120)
    assert row["state"] in ("interrupted", "failed"), row["state"]

    r2 = bridge(project, "resume", r["run_id"],
                "Stop what you were doing. Reply with exactly: CORRECTED")
    assert r2["thread_id"] == tid, f"resume moved to a different thread: {r2['thread_id']}"
    assert r2["run_id"] != r["run_id"], "resume must create a new run id"
    wait_done(project, r2["run_id"])
    res = bridge(project, "result", "--run", r2["run_id"])
    assert "CORRECTED" in (res["message"] or ""), res["message"]
    after = len(rollout_path(tid).read_text(errors="replace").splitlines())
    assert after > before, f"rollout did not grow: {before} -> {after}"
    return f"same thread, rollout {before}->{after} lines"


@case
def I3(project):
    """Two parallel runs; stopping one leaves the other to complete."""
    a = bridge(project, "start", "--label", "i3a", "--sandbox", "workspace-write",
               "Run each as a SEPARATE shell command: 'sleep 4 && echo a1', "
               "'sleep 4 && echo a2', 'sleep 4 && echo a3', 'sleep 4 && echo a4'.")
    b = bridge(project, "start", "--label", "i3b", "--sandbox", "read-only",
               "Reply with exactly: SURVIVOR")
    assert a["thread_id"] != b["thread_id"], "parallel starts shared a thread"
    rows = {r["label"]: r for r in bridge(project, "status", "--all")["runs"]}
    assert rows["i3a"]["pgid"] != rows["i3b"]["pgid"], "parallel runs shared a process group"

    time.sleep(6)
    bridge(project, "stop", "--run", a["run_id"])
    wait_done(project, a["run_id"], timeout=120)
    rb = wait_done(project, b["run_id"])
    assert rb["state"] == "completed", f"the other run was collateral damage: {rb}"
    res = bridge(project, "result", "--run", b["run_id"])
    assert "SURVIVOR" in (res["message"] or ""), res["message"]
    return "stopped one, the other completed"


@case
def I4(project):
    """THE regression, against the real CLI.

    A read-only thread, resumed, must still be read-only — verified from the
    rollout's per-turn record, and by the write actually being refused.
    """
    r = bridge(project, "start", "--label", "i4", "--sandbox", "read-only",
               "Reply with exactly: LOCKED")
    tid = r["thread_id"]
    wait_done(project, r["run_id"])
    tc = turn_contexts(tid)
    assert tc[-1]["sandbox"] == "read-only", f"turn 1 sandbox: {tc[-1]}"

    marker = "i4_escalation_probe.txt"
    r2 = bridge(project, "resume", r["run_id"],
                f"Create a file named {marker} in the current working directory "
                "containing the word ESCALATED. If you cannot, say why.")
    wait_done(project, r2["run_id"])

    tc = turn_contexts(tid)
    assert len(tc) >= 2, f"expected at least two turn_context records, got {len(tc)}"
    assert tc[-1]["sandbox"] == "read-only", (
        f"SANDBOX DRIFTED ON RESUME: {tc[-1]['sandbox']!r} — the registry's "
        f"re-injection failed, which is the defect this project exists to close")
    assert not (project / marker).exists(), f"{marker} was written under a read-only policy"

    argv = json.loads((project / ".codex-runs" / r2["run_id"] / "meta.json").read_text())["argv"]
    assert 'sandbox_mode="read-only"' in argv, f"resume argv lacks the sandbox: {argv}"
    return f"turns={[t['sandbox'] for t in tc]}, write refused"


@case
def I5(project):
    """--output-schema comes back as JSON that parses."""
    schema = project / "verdict.schema.json"
    schema.write_text(json.dumps({
        "type": "object",
        "required": ["language", "confident"],
        "properties": {"language": {"type": "string"},
                       "confident": {"type": "boolean"}},
        "additionalProperties": False}))
    r = bridge(project, "start", "--label", "i5", "--sandbox", "read-only",
               "--schema", str(schema),
               "What programming language is this repository written in? Answer with the "
               "JSON object the output schema describes.")
    wait_done(project, r["run_id"])
    res = bridge(project, "result", "--run", r["run_id"])
    assert isinstance(res.get("json"), dict), f"no parsed json: {res}"
    assert set(res["json"]) == {"language", "confident"}, res["json"]
    assert isinstance(res["json"]["confident"], bool), res["json"]
    return f"json={res['json']}"


@case
def I6(project):
    """review --uncommitted over a real change produces findings."""
    bad = project / "unsafe.py"
    bad.write_text(
        "import subprocess\n\n\n"
        "def run_user_command(user_input):\n"
        "    # builds a shell string straight from caller input\n"
        "    return subprocess.run(user_input, shell=True, capture_output=True)\n\n\n"
        "def divide(a, b):\n"
        "    return a / b\n")
    r = bridge(project, "review", "--label", "i6", "--uncommitted", "--sandbox", "read-only")
    wait_done(project, r["run_id"])
    res = bridge(project, "result", "--run", r["run_id"])
    msg = (res["message"] or "")
    assert len(msg.strip()) > 40, f"review said almost nothing: {msg!r}"
    assert res["usage"] is None and "unavailable" in res.get("usage_note", ""), (
        f"review usage should be reported unavailable, got {res['usage']}")
    bad.unlink()
    return f"{len(msg)} chars of findings; usage correctly null"


@case
def I7(project):
    """Isolation actually isolates.

    This deliberately does NOT assert a token ratio. The plan expected ~3x,
    from a planning-session measurement of 46,238 vs 15,863. Re-measured on the
    same machine, the same prompt now costs 17,327 inherited vs 15,837 isolated
    — 1.09x — because the savings depend entirely on how much of the user's
    config actually loads at that moment (MCP servers that fail to start
    contribute nothing). A threshold here tests the user's Codex configuration,
    not this wrapper, and fails for reasons no code change can fix.

    What IS the wrapper's responsibility, and is stable: the flag is passed and
    has an observable effect. Isolation yields a clean stream where inherited
    config leaks config-error events, and it is never more expensive.
    """
    prompt = "Reply with exactly: OK"
    iso = bridge(project, "start", "--label", "i7-iso", "--sandbox", "read-only", prompt)
    wait_done(project, iso["run_id"])
    inh = bridge(project, "start", "--label", "i7-inherit", "--sandbox", "read-only",
                 "--inherit-config", prompt)
    wait_done(project, inh["run_id"])

    r_iso = bridge(project, "status", "--run", iso["run_id"])["runs"][0]
    r_inh = bridge(project, "status", "--run", inh["run_id"])["runs"][0]
    a = bridge(project, "result", "--run", iso["run_id"])["usage"]["input_tokens"]
    b = bridge(project, "result", "--run", inh["run_id"])["usage"]["input_tokens"]

    assert "--ignore-user-config" in json.loads(
        (project / ".codex-runs" / iso["run_id"] / "meta.json").read_text())["argv"]
    assert "--ignore-user-config" not in json.loads(
        (project / ".codex-runs" / inh["run_id"] / "meta.json").read_text())["argv"]
    assert r_iso["config_error_events"] == 0, (
        f"an isolated run leaked {r_iso['config_error_events']} config-error events — "
        f"--ignore-user-config is not taking effect")
    assert b >= a, f"isolation should never cost more: isolated={a} inherited={b}"
    ratio = b / a
    note = "" if r_inh["config_error_events"] else "  (note: this config leaks no errors)"
    return (f"isolated={a}/{r_iso['config_error_events']}err "
            f"inherited={b}/{r_inh['config_error_events']}err ({ratio:.2f}x){note}")


@case
def I8(project):
    """-i attaches an image and the model can see it."""
    img = project / "swatch.png"
    solid_png(img, rgb=(220, 20, 60))
    r = bridge(project, "start", "--label", "i8", "--sandbox", "read-only",
               "--image", str(img),
               "Look at the attached image. It is a single solid colour. Reply with just "
               "that colour's common name in English, one word.")
    wait_done(project, r["run_id"])
    argv = json.loads((project / ".codex-runs" / r["run_id"] / "meta.json").read_text())["argv"]
    assert "-i" in argv and str(img) in argv, f"image not in argv: {argv}"
    res = bridge(project, "result", "--run", r["run_id"])
    msg = (res["message"] or "").lower()
    assert any(w in msg for w in ("red", "crimson", "pink", "magenta", "rose", "scarlet")), (
        f"model did not describe the attached crimson image: {res['message']!r}")
    img.unlink()
    return f"model saw: {res['message'].strip()[:40]!r}"


CASES = {name: fn for name, fn in sorted(globals().items())
         if callable(fn) and getattr(fn, "_is_case", False)}


# -- driver -----------------------------------------------------------------

def make_project(base: Path) -> Path:
    p = base / "scratch"
    (p / "src").mkdir(parents=True)
    (p / "README.md").write_text("# scratch\n\nA throwaway repo for Codex integration tests.\n")
    (p / "src" / "main.py").write_text(
        "def add(a, b):\n    return a + b\n\n\n"
        "def main():\n    print(add(2, 3))\n\n\n"
        'if __name__ == "__main__":\n    main()\n')
    subprocess.run(["git", "init", "-q", str(p)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(p), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(p), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True, capture_output=True)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append", help="run only these case ids")
    ap.add_argument("--keep", action="store_true", help="keep the scratch repo")
    ap.add_argument("--json", help="write results as JSON to this path")
    args = ap.parse_args()

    if os.environ.get("CODEX_SKILL_TEST_INTEGRATION") != "1":
        sys.exit("refusing to run: set CODEX_SKILL_TEST_INTEGRATION=1 "
                 "(this tier spends real Codex tokens)")
    if not shutil.which("codex"):
        sys.exit("`codex` is not on PATH")

    base = Path(tempfile.mkdtemp(prefix="codex-t2-")).resolve()
    project = make_project(base)
    print(f"scratch repo: {project}")

    selected = args.only or list(CASES)
    unknown = [c for c in selected if c not in CASES]
    if unknown:
        sys.exit(f"unknown case(s): {unknown}; known: {sorted(CASES)}")

    t0 = time.time()
    for name in selected:
        run_case(name, CASES[name], project)

    print("\n" + "=" * 72)
    passed = sum(1 for _, v, _, _ in RESULTS if v == "PASS")
    for name, verdict, detail, secs in RESULTS:
        print(f"  {verdict:<4} {name:<4} {secs:>5.0f}s  {detail}")
    print(f"\n{passed}/{len(RESULTS)} passed in {time.time() - t0:.0f}s")

    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"case": n, "verdict": v, "detail": d, "seconds": round(s, 1)}
             for n, v, d, s in RESULTS], indent=2))
    if args.keep:
        print(f"scratch repo kept at {project}")
    else:
        shutil.rmtree(base, ignore_errors=True)
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
