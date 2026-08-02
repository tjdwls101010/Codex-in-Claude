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
from _registry import TERMINAL_STATES  # noqa: E402
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
        if row["state"] in TERMINAL_STATES:
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


# -- batch orchestration (v0.2.0) -------------------------------------------
# These spend several Codex turns at once rather than one at a time, so this
# half of T2 costs a multiple of the half above it.

def wait_group(project: Path, group, timeout=900):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = bridge(project, "status", "--group", group)
        if st["group_state"] != "running":
            return st
        time.sleep(3)
    raise AssertionError(f"group {group} did not finish within {timeout}s")


@case
def I9(project):
    """Three members of one batch get three distinct threads and three distinct
    process groups, and all of them finish.

    Distinctness is the claim the whole design rests on: `stop --group` signals
    each member's own pgid, and `--resume-from` pairs each member's own thread.
    Either one collapsing would be silent."""
    g = bridge(project, "batch", "start", "--group", "i9", "--sandbox", "read-only",
               "--task", "Reply with exactly: ALPHA",
               "--task", "Reply with exactly: BRAVO",
               "--task", "Reply with exactly: CHARLIE")
    assert g["spawned"] == 3, g
    st = wait_group(project, "i9")
    assert st["group_state"] == "completed", st
    threads = {r["thread_id"] for r in st["runs"]}
    pgids = {r["pgid"] for r in st["runs"]}
    assert len(threads) == 3, f"members shared a thread: {threads}"
    assert len(pgids) == 3, f"members shared a process group: {pgids}"
    res = bridge(project, "result", "--group", "i9")
    said = " ".join((r["message"] or "").upper() for r in res["results"])
    for word in ("ALPHA", "BRAVO", "CHARLIE"):
        assert word in said, f"{word} missing from group results"
    return f"3 threads, 3 pgids, totals={res['totals']}"


@case
def I10(project):
    """Worktree isolation, end to end against the real CLI.

    Three writers are told to create the SAME filename. Without isolation that
    is one file written three times; with it, three files in three checkouts —
    and `overlaps` is what turns the collision from invisible into a fact."""
    before = subprocess.run(["git", "-C", str(project), "status", "--porcelain"],
                            capture_output=True, text=True).stdout
    g = bridge(project, "batch", "start", "--group", "i10",
               "--sandbox", "workspace-write",
               "--task", "Create a file named shared.txt containing exactly the word ONE. "
                         "Then reply with exactly: DONE",
               "--task", "Create a file named shared.txt containing exactly the word TWO. "
                         "Then reply with exactly: DONE",
               "--task", "Create a file named shared.txt containing exactly the word THREE. "
                         "Then reply with exactly: DONE")
    assert g["worktrees"]["count"] == 3, f"expected 3 worktrees: {g.get('worktrees')}"
    wait_group(project, "i10")

    after = subprocess.run(["git", "-C", str(project), "status", "--porcelain"],
                           capture_output=True, text=True).stdout
    assert after == before, f"the main tree was polluted:\n{after}"

    contents = set()
    for r in g["runs"]:
        f = Path(r["worktree"]) / "shared.txt"
        assert f.exists(), f"member {r['run_id']} did not write into its own worktree"
        contents.add(f.read_text(encoding="utf-8").strip().upper())
    assert len(contents) == 3, f"three checkouts should hold three versions: {contents}"

    res = bridge(project, "result", "--group", "i10")
    overlapping = [p for p in res["overlaps"] if p.endswith("shared.txt")]
    assert overlapping, f"overlaps missed the collision: {res['overlaps']}"
    assert len(res["overlaps"][overlapping[0]]) == 3, res["overlaps"]
    return f"3 isolated checkouts, main tree clean, overlaps caught {overlapping[0]}"


@case
def I11(project):
    """--resume-from continues each member on ITS OWN thread.

    Checked against the rollout files rather than the wrapper's own bookkeeping:
    the wrapper claiming the right thread and Codex actually continuing it are
    two different assertions, and only the second one matters."""
    one = bridge(project, "batch", "start", "--group", "i11a", "--sandbox", "read-only",
                 "--task", "Remember the word NORTH. Reply with exactly: OK",
                 "--task", "Remember the word SOUTH. Reply with exactly: OK")
    wait_group(project, "i11a")
    two = bridge(project, "batch", "start", "--group", "i11b", "--resume-from", "i11a",
                 "--task", "What word did I ask you to remember? Reply with just that word.",
                 "--task", "What word did I ask you to remember? Reply with just that word.")
    wait_group(project, "i11b")

    for prev, now in zip(one["runs"], two["runs"]):
        assert now["thread_id"] == prev["thread_id"], (
            f"phase 2 landed on a different thread: {now['thread_id']} != {prev['thread_id']}")
    res = bridge(project, "result", "--group", "i11b")
    answers = [(r["message"] or "").strip().upper() for r in res["results"]]
    assert "NORTH" in answers[0], f"member 0 lost its own context: {answers[0]!r}"
    assert "SOUTH" in answers[1], f"member 1 lost its own context: {answers[1]!r}"
    return f"each member recalled its own word: {answers}"


@case
def I12(project):
    """One member failing does not take the batch with it, and the group says so.

    The failure is forced with a schema file that does not exist, which is
    refused before that member ever spawns — D11's isolation has to hold for a
    refusal as much as for a crash."""
    g = bridge(project, "batch", "start", "--group", "i12", "--sandbox", "read-only",
               "--task", "Reply with exactly: SURVIVOR")
    assert g["spawned"] == 1
    wait_group(project, "i12")

    tf = project / "i12-tasks.jsonl"
    tf.write_text("\n".join([
        json.dumps({"prompt": "Reply with exactly: LIVES"}),
        json.dumps({"prompt": "doomed", "schema": "/nonexistent/schema.json"}),
    ]) + "\n")
    g2 = bridge(project, "batch", "start", "--group", "i12b", "--sandbox", "read-only",
                "--tasks-file", str(tf))
    assert g2["requested"] == 2 and g2["spawned"] == 1, g2
    assert "schema" in g2["runs"][1]["error"], g2["runs"][1]
    st = wait_group(project, "i12b")
    assert st["group_state"] == "partial", st
    res = bridge(project, "result", "--group", "i12b")
    assert "LIVES" in (res["results"][0]["message"] or "").upper(), res["results"][0]
    tf.unlink()
    return "1 of 2 spawned, survivor completed, group_state=partial"


@case
def I13(project):
    """`status --group --follow` ends with a terminal line rather than silence.

    B21's rule applied to a group: a follower that just stops printing is
    indistinguishable from a run that is still going, so the terminal line is
    what makes the absence of news readable."""
    g = bridge(project, "batch", "start", "--group", "i13", "--sandbox", "read-only",
               "--task", "Reply with exactly: FOLLOWED",
               "--task", "Reply with exactly: FOLLOWED")
    del g
    out = bridge_text(project, "status", "--group", "i13", "--follow",
                      "--follow-timeout", "600", "--interval", "2")
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    assert lines, "follow printed nothing at all"
    last = lines[-1]
    assert last.startswith("group.completed") or last.startswith("group.partial"), (
        f"no terminal line; last was {last!r}")
    return f"{len(lines)} lines, terminal: {last[:60]!r}"


@case
def I14(project):
    """A background --timeout records `timed_out`, and the thread survives it.

    The state has to be its own: `interrupted` would say the caller stopped it
    and `failed` would say Codex broke, and only "it ran out of the time I gave
    it" is answered by raising the timeout. V-16 measured resumability in the
    foreground; this is the background path the batch actually uses."""
    r = bridge(project, "start", "--label", "i14", "--sandbox", "read-only",
               "--timeout", "20",
               "Count slowly from 1 to 40, writing one number per line, thinking "
               "carefully about each one before you write it.")
    row = wait_done(project, r["run_id"], timeout=300)
    assert row["state"] == "timed_out", f"expected timed_out, got {row['state']}: {row}"

    r2 = bridge(project, "resume", r["run_id"], "--sandbox", "read-only",
                "Never mind the counting. Reply with exactly: RESUMED")
    row2 = wait_done(project, r2["run_id"])
    assert row2["state"] == "completed", row2
    assert r2["thread_id"] == r["thread_id"], "resume opened a new thread"
    res = bridge(project, "result", "--run", r2["run_id"])
    assert "RESUMED" in (res["message"] or "").upper(), res["message"]
    return f"timed_out at 20s, same thread resumed to completed"


@case
def I15(project):
    """`batch clean` will not discard uncollected work, and `--force` will.

    The refusal is git's own — `git worktree remove` declines a dirty tree —
    and the point of the case is that the wrapper surfaces it rather than
    working around it."""
    g = bridge(project, "batch", "start", "--group", "i15",
               "--sandbox", "workspace-write",
               "--task", "Create a file named note.txt containing the word KEEP. "
                         "Reply with exactly: DONE",
               "--task", "Create a file named note.txt containing the word KEEP. "
                         "Reply with exactly: DONE")
    wait_group(project, "i15")
    paths = [Path(r["worktree"]) for r in g["runs"]]
    assert all(p.exists() for p in paths), g

    refused = bridge(project, "batch", "clean", "--group", "i15")
    assert refused["removed"] == [], refused
    assert len(refused["kept"]) == 2, refused
    assert all(k["dirty"] for k in refused["kept"]), refused
    assert refused["name_released"] is False, refused
    assert all(p.exists() for p in paths), "a refused clean removed something anyway"

    forced = bridge(project, "batch", "clean", "--group", "i15", "--force")
    assert len(forced["removed"]) == 2, forced
    assert forced["name_released"] is True, forced
    assert not any(p.exists() for p in paths), "worktrees survived --force"
    assert forced["forced_past"]["discarded_uncommitted"], forced

    listed = subprocess.run(["git", "-C", str(project), "worktree", "list", "--porcelain"],
                            capture_output=True, text=True).stdout
    left = [ln for ln in listed.splitlines() if ln.startswith("worktree ")]
    assert len(left) == 1, f"worktrees left registered with git: {left}"
    return "refused while dirty, --force removed both, git's list back to just the main tree"


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
