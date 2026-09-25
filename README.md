<div align="center">

<img src="https://github.com/tjdwls101010/tjdwls101010/blob/main/Images/codex%20in%20claude.png?raw=true" alt="Codex in Claude logo" width="180" />

# Codex in Claude

**Run the OpenAI Codex CLI as a managed, resumable background subagent from inside Claude Code.**

[![License: Apache 2.0](https://img.shields.io/github/license/tjdwls101010/Codex-in-Claude)](LICENSE)
[![Latest release](https://img.shields.io/github/v/tag/tjdwls101010/Codex-in-Claude?label=release)](https://github.com/tjdwls101010/Codex-in-Claude/releases)

[Overview](#1-overview) · [Features](#2-features) · [Quick Start](#3-quick-start) · [Usage](#4-usage) · [Project Status](#5-project-status)

</div>

## 1. Overview

The OpenAI [Codex CLI](https://developers.openai.com/codex/cli) is a capable coding agent, but running it from inside another tool exposes a real gap: `codex exec resume` has no `--sandbox` flag. A resumed turn doesn't inherit the sandbox its thread was created with — it silently re-derives one from whatever config layer happens to be active at that moment. Measured directly:

| Turn | Command | `turn_context.sandbox_policy` | Result |
|---|---|---|---|
| 1 | `codex exec --ignore-user-config -c sandbox_mode="read-only"` | `read-only` | write refused |
| 2 | `codex exec resume <id>` (user config inherited, no flag passed) | **`danger-full-access`** | **file written** |

It breaks in the opposite direction too: a `workspace-write` thread resumed under isolation with no flag silently *downgrades* to `read-only`, and its reasoning-effort setting disappears along with it.

**Codex in Claude** is a Claude Code plugin that closes that gap, and in doing so turns the Codex CLI into something Claude can actually delegate real work to: a background subagent whose settings stay stable across turns. It's for anyone using Claude Code who wants a second model (Codex, running on GPT) working in parallel — checked in on through a filtered live log instead of a wall of raw output, stoppable and redirectable mid-task, and resumable later.

It isn't a thin wrapper around the `codex` binary. Every per-invocation setting — sandbox, model, reasoning effort, isolation, working directory — is recorded the moment a run starts and re-injected on every subsequent call. That's what makes "safe to resume" a guarantee instead of a hope.

## 2. Features

- **Detached runs** — `start` returns a `run_id`/`thread_id` immediately instead of blocking, and `log --follow` in a background call tells Claude when the run ends.
- **Sandbox stability across turns** — every `resume` re-asserts the sandbox, model, and reasoning effort its thread was created with.
- **Your Codex defaults survive isolation** — `--ignore-user-config` drops `config.toml` whole, so an isolated run would lose the model, reasoning effort and Fast mode you configured and take the server's defaults instead. Three keys are read back out of the file and re-injected; an explicit flag still wins, and a resumed thread re-asserts what it recorded rather than what the file says now. `sandbox_mode` is deliberately not one of them.
- **A filtered live event log** — four verbosity levels (`compact` by default, `normal`, `full`, `raw`); the default reports each command's output by size, and `show` fetches the one you need.
- **Stop, then redirect** — interrupt a run mid-task and continue it on the same thread with new instructions. `stop` always targets a run's own process group, never a process by name, so concurrent runs never interfere with each other.
- **Resume a thread started elsewhere** — one begun in the Codex TUI continues by its id, with `--sandbox` stating what it may do.
- **Schema-shaped results** — pass `--schema` and Codex shapes its final message to it; `result` hands back the parsed JSON instead of a message you have to eyeball.
- **A deadline you choose** — `--timeout` works in the background and records a state of its own, so "it ran out of the time I gave it" never reads as "Codex failed". The thread stays resumable across it.
- **Run several as one group** — `batch start` launches N runs under one name; `status --group`, `result --group`, and `stop --group` then address all of them at once. Members share your tree by default, the way a fan-out of Claude's own subagents does; `--worktree` gives each writing member its own git checkout when they would edit the same files. Continue every member's thread in a next round with `--resume-from`, once the whole group has finished.
- **Built-in diagnostics** — `doctor` checks your PATH, Codex auth, config, and the run registry in a single call.

## 3. Quick Start

**Prerequisites**

- [Codex CLI](https://developers.openai.com/codex/cli) — verified against `0.156.1`, already authenticated (`codex login`)
- Python 3.10+ — standard library only, no extra packages to install
- Claude Code — verified against `2.1.282`

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

</details>

**Let Claude call it without asking**

The skill pre-approves its own command, but Claude Code applies that only when you invoke the skill yourself (`/codex:codex`, or `/codex` for a symlinked skill). When Claude picks the skill on its own, which is how it is usually used, every call asks for permission, and a headless session simply refuses it. A permission rule in `~/.claude/settings.json` covers both cases. Take the path from `skill_dir` in `doctor`'s output and write it out — `$HOME` is not expanded in a permission rule:

```json
{
  "permissions": {
    "allow": [
      "Skill(codex)",
      "Bash(python3 \"/Users/you/.claude/skills/codex/scripts/cli_codex.py\" *)"
    ]
  }
}
```

The skill rule is separate, and without it a headless session cannot load the skill at all: `Skill(codex)` for a symlinked skill, `Skill(codex:codex)` for the plugin. A plugin install's `skill_dir` contains the plugin's version (`…/plugins/cache/codex-in-claude/codex/0.8.0/…`); replace that segment with `*` so the rule survives an update.

**Upgrading from 0.7.0?** The entrypoint is now `scripts/cli_codex.py`, so a rule naming `…/scripts/codex_bridge.py` no longer matches anything — replace it with the one above.

**First run**

Inside a Claude Code session, just describe the work — the skill triggers automatically on phrasing like "codex", "GPT", or "delegate this to Codex", or you can invoke it explicitly with `/codex:codex`. The commands below are what Claude runs; `<skill dir>` is the skill's directory, which `doctor` reports as `skill_dir`.

As a sanity check, ask Claude to run:

```bash
python3 "<skill dir>/scripts/cli_codex.py" doctor
```

`doctor` exits `0` when Codex is reachable, authenticated, and configured correctly, or `2` with a `blockers` array explaining exactly what to fix.

From there, a typical loop looks like this (`$CODEX` below is shorthand for the full `python3 "<skill dir>/scripts/cli_codex.py"`):

```bash
$CODEX start --label refactor "Refactor the auth module to use the new session store"
# → {"run_id": "...", "thread_id": "...", "state": "running", ...}

$CODEX log --run <run_id> --follow
# → the run's events as they happen; exits when the run ends

$CODEX result --run <run_id>
# → the final message and usage, once it's done
```

`$CODEX --help` lists the commands, and `$CODEX <command> --help` has every flag, default and refusal.

## 4. Usage

| Command | What it does |
|---|---|
| `start` | New thread. Background by default; returns `{run_id, thread_id}` immediately |
| `resume` | Add a turn to an existing thread; every recorded setting is re-asserted |
| `status` | Whether a run is live, how far along, and what it last said; a summary row per run by default |
| `log` | Filtered events, followed live with `--follow` or read incrementally with `--since <cursor>` |
| `show` | One item's full output, fetched on request |
| `stop` | Interrupt by process group — never by matching a process name |
| `result` | Final message and usage, or the parsed JSON alone when `--schema` was used |
| `batch start` | N runs as one named group, sharing your tree unless `--worktree` gives each writing member a checkout |
| `batch clean` | Remove a finished group's worktrees, once you've collected them |
| `models` | The models and reasoning efforts this Codex install offers |
| `doctor` | PATH, version, `CODEX_HOME`, auth, config defaults, registry health, worktrees |

`status`, `result` and `stop` also take `--group <name>` to address a whole batch at once.

Defaults: detached execution, `workspace-write` sandbox, isolated from your own Codex config (`--ignore-user-config`) apart from the three keys above, no hard timeout.

By default, a command's actual output never reaches Claude's context — only its size does:

```
cmd[item_2] exit=0 out=8797B rg -n "" tests . --glob '*.py'
```

Fetch that one command's full output on demand with `show --run <run_id> --item item_2`.

To interrupt a run that's going the wrong way and redirect it without losing its progress:

```bash
$CODEX stop --run <run_id>
$CODEX resume <run_id> "Stop rewriting tests — just fix the failing assertion"
```

To hand three independent pieces of work to three Codex runs at once and collect them as one thing:

```bash
$CODEX batch start --group audit --task "audit the parser" --task "audit the lexer" --task "audit the cache"
$CODEX status --group audit --follow      # ends on a terminal line, never in silence
$CODEX result --group audit               # each message, plus which paths more than one wrote
$CODEX batch clean --group audit          # removes any worktrees and releases the group name
```

Members work in your tree, the way a fan-out of your own subagents does: their changes are there as they make them, with nothing to collect. Add `--worktree` when they would edit the same files, and each writing member gets its own checkout instead.

## 5. Project Status

Codex in Claude is at **v0.8.0** — an early, actively developed release, verified against `codex-cli 0.156.1` and Claude Code `2.1.282`. The suite drives the CLI against a fake `codex`; an opt-in smoke test checks sandbox stability against the real Codex CLI, and an opt-in harness runs real headless Claude sessions with the skill — see [CONTRIBUTING.md](CONTRIBUTING.md#4-tests--checks).

**Upgrading from v0.7.0?** The entrypoint, three flags and some output shapes changed; see the [changelog](CHANGELOG.md#080--2026-09-25).

A few things are deliberately out of scope for now, not overlooked: `codex cloud`, `codex mcp-server`/`app-server` integration, and true mid-turn steering.

## 6. Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up the project, run the test suite, and submit a change, and please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## 7. License

Licensed under the [Apache License 2.0](LICENSE).
