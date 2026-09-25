#!/usr/bin/env python3
"""Run one S6 scenario against the draft or the control SKILL.md, isolated, and save what the session did.

    python3 tests/e2e/run_e2e.py --scenario 1 --variant draft --out /tmp/e2e

Writes <out>/<scenario>-<variant>/: transcript*.jsonl (stream-json), digest.txt (every tool call, with Bash's run_in_background and timeout), and the throwaway repo. Real Codex runs are made; this is opt-in and costs tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / ".claude" / "skills" / "codex"

FILES = {
    1: {"src/calc.py": "def average(values):\n    return sum(values) / len(values)\n\n\ndef percent(part, whole):\n    return part / whole * 10\n\n\ndef clamp(x, lo, hi):\n    return max(lo, min(x, hi))\n"},
    2: {"src/app.py": "def greet(name):\n    return 'Hello, ' + name\n\n\ndef add(a, b):\n    return a + b\n\n\ndef shout(text):\n    return text.upper() + '!'\n"},
    3: {"src/util.py": "import os\n\n\ndef join(a, b):\n    return os.path.join(a, b)\n\n\ndef stem(path):\n    return os.path.splitext(os.path.basename(path))[0]\n\n\ndef exists(path):\n    return os.path.exists(path)\n"},
    4: {"src/calc.py": "def average(values):\n    return sum(values) / len(values)\n", "README.md": "# tiny\n\nA tiny calculator package.\n"},
}

PROMPTS = {
    1: ["Have Codex review src/calc.py for bugs and tell me what it finds. Don't change any files yourself."],
    2: ["Use Codex to make three independent changes to src/app.py at the same time, one Codex run per change: (a) greet() takes an optional title argument placed before the name, (b) add() raises TypeError for non-numeric input, (c) every function gets a one-line docstring. Then bring the results into this working tree."],
    3: ["Ask Codex to add type hints to every function in src/util.py. Let it work in the background; don't wait for it in this turn.",
        "Change of plan: that Codex run should also give every function a one-line docstring — same work, one more requirement."],
    4: ["Ask Codex for a short summary of what this repository contains and tell me. This is a one-shot session: you get no later turn, so finish within this reply."],
}
HOST = {1: "stream", 2: "stream", 3: "resume", 4: "print"}


def control_text(draft: str) -> str:
    """The draft's frontmatter and its call paragraph, without any judgement text."""
    front, body = draft.split("\n---\n", 1)
    call = [p for p in body.strip().split("\n\n") if not p.startswith("#")][0]
    return f"{front}\n---\n\n# Codex as a managed subagent\n\n{call}\n"


def setup(out: Path, scenario: int, variant: str):
    if out.exists():
        shutil.rmtree(out)
    plugin = out / "plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    shutil.copy(REPO / ".claude-plugin" / "plugin.json", plugin / ".claude-plugin" / "plugin.json")
    dest = plugin / ".claude" / "skills" / "codex"
    shutil.copytree(SKILL, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".DS_Store"))
    if variant == "control":
        (dest / "SKILL.md").write_text(control_text((SKILL / "SKILL.md").read_text()))
    repo = out / "repo"
    for rel, text in FILES[scenario].items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.email=e2e@example.com", "-c", "user.name=e2e", "commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True)
    home = out / "codex-home"
    home.mkdir()
    for name in ("auth.json", "config.toml"):
        src = Path.home() / ".codex" / name
        if src.exists():
            shutil.copy(src, home / name)
    settings = out / "settings.json"
    settings.write_text(json.dumps({"sandbox": {
        "enabled": True, "allowUnsandboxedCommands": False, "autoAllowBashIfSandboxed": True,
        "enableWeakerNetworkIsolation": True,
        # the bridge runs outside Claude's sandbox because Codex applies its own sandbox-exec, which cannot nest; permission to run it still comes only from the skill's allowed-tools
        "excludedCommands": ["python3 *cli_codex.py*"],
        "filesystem": {"allowWrite": [str(home)]},
        "network": {"allowedDomains": ["chatgpt.com", "*.chatgpt.com", "api.openai.com", "*.openai.com", "*.oaistatic.com"],
                    "strictAllowlist": True}}}))
    return plugin, repo, home, settings


def base_cmd(plugin, settings, model):
    return ["claude", "-p", "--setting-sources", "", "--strict-mcp-config", "--plugin-dir", str(plugin),
            "--settings", str(settings), "--tools", "Bash,Read,Edit,Write,Glob,Grep,Monitor,Skill",
            # a skill's allowed-tools covers only a user-typed /codex:codex; a skill the model picks itself needs the user's own permission rule, which this stands in for
            "--allowedTools", f'Skill,Monitor,Bash(python3 "{plugin}/.claude/skills/codex/scripts/cli_codex.py" *)', "--permission-mode", "acceptEdits", "--model", model, "--output-format", "stream-json", "--verbose"]


def run_stream(cmd, repo, env, prompt, transcript, idle, cap):
    """A session whose stdin stays open, so a finished background task can start another turn; closed after `idle` quiet seconds following a result, or at `cap`."""
    p = subprocess.Popen(cmd + ["--input-format", "stream-json"], cwd=repo, env=env, text=True,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
    p.stdin.flush()
    last = {"t": time.time(), "result": False}

    def read():
        with transcript.open("w") as fh:
            for line in p.stdout:
                fh.write(line)
                fh.flush()
                last["t"] = time.time()
                if '"type":"result"' in line.replace(" ", ""):
                    last["result"] = True
    t = threading.Thread(target=read, daemon=True)
    t.start()
    start = time.time()
    while time.time() - start < cap and not (last["result"] and time.time() - last["t"] > idle):
        time.sleep(2)
    p.stdin.close()
    try:
        p.wait(timeout=120)
    except subprocess.TimeoutExpired:
        p.kill()
    t.join(timeout=10)


def run_print(cmd, repo, env, prompt, transcript, resume=None):
    extra = ["--resume", resume] if resume else []
    with transcript.open("w") as fh:
        subprocess.run(cmd + extra + [prompt], cwd=repo, env=env, text=True, stdout=fh, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL, timeout=3600)
    for line in transcript.read_text().splitlines():
        ev = json.loads(line)
        if ev.get("type") == "result":
            return ev.get("session_id")
    return None


def digest(out: Path):
    lines = []
    for tr in sorted(out.glob("transcript*.jsonl")):
        lines.append(f"== {tr.name}")
        for raw in tr.read_text().splitlines():
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "assistant":
                for c in ev["message"].get("content", []):
                    if c.get("type") == "tool_use":
                        i = c.get("input", {})
                        extra = " ".join(f"{k}={i[k]}" for k in ("run_in_background", "timeout") if k in i)
                        lines.append(f"{c['name']} {extra} :: {i.get('command') or i.get('file_path') or json.dumps(i)[:200]}")
                    elif c.get("type") == "text" and c.get("text", "").strip():
                        lines.append("TEXT :: " + c["text"].strip().replace("\n", " ")[:400])
            elif ev.get("type") == "result":
                lines.append(f"RESULT denials={ev.get('permission_denials')} turns={ev.get('num_turns')} :: "
                             + (ev.get("result") or "").replace("\n", " ")[:600])
    (out / "digest.txt").write_text("\n".join(lines) + "\n")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", type=int, choices=sorted(PROMPTS), required=True, help="which scenario in scenarios.md")
    ap.add_argument("--variant", choices=("draft", "control"), required=True, help="the SKILL.md as written, or only its frontmatter and call paragraph")
    ap.add_argument("--out", type=Path, required=True, help="directory to write <scenario>-<variant>/ under")
    ap.add_argument("--model", default="opus", help="model the session runs (default: opus)")
    ap.add_argument("--idle", type=float, default=240, help="stream hosts: seconds of quiet after a result before stdin is closed (default: 240)")
    ap.add_argument("--cap", type=float, default=1800, help="stream hosts: longest a session may run, in seconds (default: 1800)")
    args = ap.parse_args()
    out = args.out / f"{args.scenario}-{args.variant}"
    plugin, repo, home, settings = setup(out, args.scenario, args.variant)
    env = {**os.environ, "CODEX_HOME": str(home)}
    cmd = base_cmd(plugin, settings, args.model)
    prompts = PROMPTS[args.scenario]
    host = HOST[args.scenario]
    if host == "stream":
        run_stream(cmd, repo, env, prompts[0], out / "transcript.jsonl", args.idle, args.cap)
    elif host == "print":
        run_print(cmd, repo, env, prompts[0], out / "transcript.jsonl")
    else:
        session = run_print(cmd, repo, env, prompts[0], out / "transcript-1.jsonl")
        run_print(cmd, repo, env, prompts[1], out / "transcript-2.jsonl", resume=session)
    print("\n".join(digest(out)))


if __name__ == "__main__":
    main()
