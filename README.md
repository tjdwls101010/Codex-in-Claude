<div align="center">

<img src="https://github.com/tjdwls101010/tjdwls101010/blob/main/Images/codex%20in%20claude.png?raw=true" alt="Codex in Claude logo" width="180" />

# Codex in Claude

**Run the OpenAI Codex CLI as a managed, resumable background subagent from inside Claude Code.**

[![License: Apache 2.0](https://img.shields.io/github/license/tjdwls101010/Codex-in-Claude)](LICENSE)
[![Latest release](https://img.shields.io/github/v/tag/tjdwls101010/Codex-in-Claude?label=release)](https://github.com/tjdwls101010/Codex-in-Claude/releases)

[Overview](#1-overview) · [Features](#2-features) · [Quick Start](#3-quick-start) · [Usage](#4-usage) · [Documentation](#5-documentation)

</div>

## 1. Overview

The OpenAI [Codex CLI](https://developers.openai.com/codex/cli) is a capable coding agent, but running it from inside another tool exposes a real gap: `codex exec resume` has no `--sandbox` flag. A resumed turn doesn't inherit the sandbox its thread was created with — it silently re-derives one from whatever config layer happens to be active at that moment. Measured directly:

| Turn | Command | `turn_context.sandbox_policy` | Result |
|---|---|---|---|
| 1 | `codex exec --ignore-user-config -c sandbox_mode="read-only"` | `read-only` | write refused |
| 2 | `codex exec resume <id>` (user config inherited, no flag passed) | **`danger-full-access`** | **file written** |

It breaks in the opposite direction too: a `workspace-write` thread resumed under isolation with no flag silently *downgrades* to `read-only`, and its reasoning-effort setting disappears along with it. The full measurement, including that downgrade, is in [Sandbox Stability](docs/wiki/Sandbox-Stability.md).

**Codex in Claude** is a Claude Code plugin that closes that gap, and in doing so turns the Codex CLI into something Claude can actually delegate real work to: a background subagent whose settings stay stable across turns. It's for anyone using Claude Code who wants a second model (Codex, running on GPT) working in parallel — checked in on through a filtered live log instead of a wall of raw output, stoppable and redirectable mid-task, and resumable later, including threads that were started directly in the Codex TUI.

It isn't a thin wrapper around the `codex` binary. Every per-invocation setting — sandbox, model, reasoning effort, isolation, working directory — is recorded the moment a run starts and re-injected on every subsequent call. That's what makes "safe to resume" a guarantee instead of a hope.

## 2. Features

- **Background by default** — `start` returns a `run_id`/`thread_id` immediately instead of blocking; check back in whenever it's convenient.
- **Sandbox stability across turns** — every `resume` re-asserts the sandbox, model, and reasoning effort its thread was created with. See [Sandbox Stability](docs/wiki/Sandbox-Stability.md).
- **A filtered live event log** — four verbosity levels (`compact` by default, `normal`, `full`, `raw`), with the default chosen from real measurements rather than a guess. See [Context Discipline & Event Log Levels](docs/wiki/Context-Discipline.md).
- **Stop, then redirect** — interrupt a run mid-task and continue it on the same thread with new instructions. `stop` always targets a run's own process group, never a process by name, so concurrent runs never interfere with each other.
- **Resume any thread** — including ones started outside this plugin, directly in the Codex TUI.
- **Schema-validated results** — pass `--schema` and get back parsed, validated JSON instead of a message you have to eyeball.
- **Automatic cleanup** — a `SessionEnd` hook stops a Claude session's own background runs when that session ends (`/clear` and `/resume` included), unless the run was started with `--detach`. See [Session Cleanup Hook](docs/wiki/Session-Cleanup-Hook.md).
- **Built-in diagnostics** — `doctor` checks your PATH, Codex auth, config, and the run registry in a single call.

## 3. Quick Start

**Prerequisites**

- [Codex CLI](https://developers.openai.com/codex/cli) — verified against `0.144.1`, already authenticated (`codex login`)
- Python 3.10+ — standard library only, no extra packages to install
- Claude Code 2.1.220 or later

**Install the plugin**

```bash
claude plugin marketplace add tjdwls101010/Codex-in-Claude
claude plugin install codex@codex-in-claude
```

Confirm it's active — `claude plugin list` should show `codex` with `Status: ✔ enabled`.

<details>
<summary>Installing from a local checkout, or without the plugin marketplace</summary>

```bash
claude plugin marketplace add /path/to/Codex-in-Claude
claude plugin install codex@codex-in-claude
```

Or, for development, symlink the skill directly:

```bash
ln -s /path/to/Codex-in-Claude/.claude/skills/codex ~/.claude/skills/codex
```

A symlinked skill doesn't get the plugin's pre-approved `allowed-tools`, so every poll prompts for approval. Add this to `~/.claude/settings.json` to get the same effect manually:

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 \"$HOME/.claude/skills/codex/scripts/codex_bridge.py\" *)"
    ]
  }
}
```

</details>

**First run**

Inside a Claude Code session, just describe the work — the skill triggers automatically on phrasing like "codex", "GPT", or "delegate this to Codex", or you can invoke it explicitly with `/codex:codex`. The first time it loads, Claude's context will include a line like `Base directory for this skill: <dir>` — that's the path to use for every command below.

As a sanity check, ask Claude to run:

```bash
python3 "<base directory>/scripts/codex_bridge.py" doctor
```

`doctor` exits `0` when Codex is reachable, authenticated, and configured correctly, or `2` with a `blockers` array explaining exactly what to fix.

From there, a typical loop looks like this (`$CODEX` below is shorthand for the full `python3 "<base directory>/scripts/codex_bridge.py"`):

```bash
$CODEX start --label refactor "Refactor the auth module to use the new session store"
# → {"run_id": "...", "thread_id": "...", "state": "running", ...}

$CODEX status --run <run_id>
# → elapsed/idle time, usage, and the last thing the agent said

$CODEX result --run <run_id>
# → the final message and usage, once it's done
```

See [Getting Started](docs/wiki/Getting-Started.md) for a fuller walkthrough, and [CLI Reference](docs/wiki/CLI-Reference.md) for every subcommand and flag.

## 4. Usage

| Command | What it does |
|---|---|
| `start` | New thread. Background by default; returns `{run_id, thread_id}` immediately |
| `resume` | Add a turn to an existing thread; every recorded setting is re-asserted |
| `review` | `codex exec review`'s separate flag surface |
| `status` | State, elapsed/idle time, usage, last message, in-progress item |
| `log` | Filtered events, delivered incrementally via `--since <cursor>` |
| `show` | One item's full output, fetched on request |
| `stop` | Interrupt by process group — never by matching a process name |
| `result` | Final message, usage, and parsed JSON when `--schema` was used |
| `doctor` | PATH, version, `CODEX_HOME`, auth, config sandbox, registry health |

Defaults: background execution, `workspace-write` sandbox, isolated from your own Codex config (`--ignore-user-config`), no fixed model or reasoning effort, no hard timeout.

By default, a command's actual output never reaches Claude's context — only its size does:

```
cmd[item_2] exit=0 out=8797B rg -n "" tests . --glob '*.py'
```

Fetch that one command's full output on demand with `show --item item_2`. See [Context Discipline & Event Log Levels](docs/wiki/Context-Discipline.md) for the reasoning and the measurements behind it.

To interrupt a run that's going the wrong way and redirect it without losing its progress:

```bash
$CODEX stop --run <run_id>
$CODEX resume <run_id> "Stop rewriting tests — just fix the failing assertion"
```

Full command and flag reference: [CLI Reference](docs/wiki/CLI-Reference.md).

## 5. Documentation

This README gets you running. Everything else lives in [`docs/wiki/`](docs/wiki/README.md):

- **[Overview](docs/wiki/Overview.md)** — the problem in full, the value this delivers, and what it deliberately doesn't do
- **[Getting Started](docs/wiki/Getting-Started.md)** — installation, requirements, and a full first-run walkthrough
- **[Architecture](docs/wiki/Architecture.md)** — how the bridge, the run registry, and the event filter fit together
- **[Concepts](docs/wiki/Concepts.md)** — the vocabulary: runs, threads, sandbox modes, isolation, filter levels
- **[CLI Reference](docs/wiki/CLI-Reference.md)** — every subcommand and flag, in full
- **[Sandbox Stability](docs/wiki/Sandbox-Stability.md)** — the measured defect this project exists to fix
- **[Context Discipline & Event Log Levels](docs/wiki/Context-Discipline.md)** — the filtering system and its measurements
- **[Session Cleanup Hook](docs/wiki/Session-Cleanup-Hook.md)** — what happens to background runs when a session ends
- **[Testing](docs/wiki/Testing.md)** — the three test tiers and how to run each one
- **[Troubleshooting](docs/wiki/Troubleshooting.md)** — known failure modes and their fixes

## 6. Project Status

Codex in Claude is at **v0.1.0** — an early, actively developed release, verified against `codex-cli 0.144.1` and Claude Code `2.1.220+`. Its documented behaviors (background execution, sandbox stability, context filtering, session cleanup, and more) are validated against real Codex runs, not just the fake test shim — see [Testing](docs/wiki/Testing.md) for how.

A few things are deliberately out of scope for now, not overlooked: `codex cloud`, `codex mcp-server`/`app-server` integration, and true mid-turn steering. See [Overview → Non-Goals](docs/wiki/Overview.md#5-non-goals) for why.

## 7. Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up the project, run the test suite, and submit a change, and please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## 8. License

Licensed under the [Apache License 2.0](LICENSE).
