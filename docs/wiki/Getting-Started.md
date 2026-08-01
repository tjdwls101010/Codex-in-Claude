# Getting Started

Installation, requirements, and a full first-run walkthrough. For anyone setting this plugin up for the first time — by the end of this page you'll have run a real Codex task through it and inspected the result.

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| [Codex CLI](https://developers.openai.com/codex/cli) | Verified against `0.144.1`. Must already be authenticated — run `codex login` and confirm `codex login status` exits `0` before going further. |
| Python 3.10+ | Standard library only. No `jq`, no `pip install` step. |
| Claude Code | 2.1.220 or later. |

Codex resolves its home directory as `${CODEX_HOME:-$HOME/.codex}`. If you've set `CODEX_HOME` to something else, sessions, `config.toml`, `auth.json`, and the thread database all live there instead — see [Concepts § Isolation](Concepts.md#4-isolation---ignore-user-config) and the `doctor` command in [CLI Reference](CLI-Reference.md#10-doctor) for how to confirm which one is active.

## 2. Installation

**Recommended — install as a plugin:**

```bash
claude plugin marketplace add tjdwls101010/Codex-in-Claude
claude plugin install codex@codex-in-claude
```

Verify it took:

```bash
claude plugin list
# should show: codex ... Status: ✔ enabled
```

**From a local checkout** (same commands, pointed at a path instead of a GitHub repo):

```bash
claude plugin marketplace add /path/to/Codex-in-Claude
claude plugin install codex@codex-in-claude
```

**Development install via symlink**, if you're modifying the skill itself:

```bash
ln -s /path/to/Codex-in-Claude/.claude/skills/codex ~/.claude/skills/codex
```

A symlinked skill doesn't inherit the plugin manifest's pre-approved `allowed-tools`, so every call to the bridge script prompts for approval. To get the same effect manually, add this to `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 \"$HOME/.claude/skills/codex/scripts/codex_bridge.py\" *)"
    ]
  }
}
```

A project's own `.claude/settings.json` **allow** rules only take effect once you've accepted workspace trust for that project; **deny**/**ask** rules apply immediately regardless.

## 3. Finding the Bridge Script's Path

Claude Code does not expose `$CLAUDE_PLUGIN_ROOT` or `$CLAUDE_SKILL_DIR` as actual environment variables inside the Bash tool — even for a plugin install, both are empty there (they're only expanded one layer up, in permission-rule matching). Instead, the moment the skill loads, Claude's own context is given a line reading:

```
Base directory for this skill: <dir>
```

Every command in this wiki that shows `<base directory>` means: substitute the literal path from that context line, double-quoted. Building the path from a shell variable instead (e.g. `"$SOME_VAR/scripts/codex_bridge.py"`) breaks the plugin's pre-approved permission pattern, since that pattern matches the command's literal text — so it would prompt for approval on every single poll, which defeats the point of background execution.

## 4. First Run — Diagnose, Then Delegate

**Step 1 — confirm the environment is healthy:**

```bash
python3 "<base directory>/scripts/codex_bridge.py" doctor
```

This exits `0` when Codex is reachable, authenticated, and correctly configured. If it exits `2`, the JSON output includes a `blockers` array naming exactly what's wrong (missing `codex` on `PATH`, failed login, an unwritable runs directory, Python below 3.10) — fix those before continuing. See [Troubleshooting](Troubleshooting.md) if a blocker doesn't make sense.

**Step 2 — start a real task, in the background:**

```bash
python3 "<base directory>/scripts/codex_bridge.py" start --label first-task "Explain what this repository does in three sentences"
```

This returns immediately with JSON like:

```json
{"run_id": "20260726-120000-first-task-a1b2", "thread_id": "019f...", "state": "starting", "events": "…/.codex-runs/20260726-120000-first-task-a1b2/events.jsonl", "project": "…", "sandbox": "workspace-write", "isolated": true, "detached": false}
```

Note the `run_id` — every subsequent command needs it.

**Step 3 — watch it work:**

```bash
python3 "<base directory>/scripts/codex_bridge.py" log --run <run_id> --since 0
```

This prints the run's filtered event log so far, ending with a line like `# cursor=4213`. Pass that number back as `--since 4213` on a later call to get only what's new since then.

**Step 4 — check on it, or wait for it to finish:**

```bash
python3 "<base directory>/scripts/codex_bridge.py" status --run <run_id>
```

**Step 5 — collect the result:**

```bash
python3 "<base directory>/scripts/codex_bridge.py" result --run <run_id>
```

This returns the final message and token usage once the run reaches a terminal state (`completed`, `failed`, `interrupted`, or `orphaned`).

## 5. Verifying It Worked

You should have, at minimum:

- A `run_id` returned by `start` that you were able to pass to `status`, `log`, and `result`.
- A `.codex-runs/` directory in your project root (self-`.gitignore`d — it will never show up in `git status`).
- A final message from `result` that actually answers the prompt you gave it.

If any of those didn't happen, run `doctor` again and check [Troubleshooting](Troubleshooting.md).

## 6. Where to Go Next

- [CLI Reference](CLI-Reference.md) for every subcommand and flag, including `resume`, `stop`, `review`, and `show`.
- [Sandbox Stability](Sandbox-Stability.md) to understand the defect this plugin exists to close.
- [Context Discipline & Event Log Levels](Context-Discipline.md) to control how much of a run's output actually reaches Claude's context.

---
**Next:** [CLI Reference](CLI-Reference.md) · [Concepts](Concepts.md)
[Back to index](README.md)
