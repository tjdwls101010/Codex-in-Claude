# Overview

The full picture of what Codex in Claude is, why it exists, and what it deliberately does not do — for anyone deciding whether it fits what they're trying to build.

## 1. What This Solves

The OpenAI [Codex CLI](https://developers.openai.com/codex/cli) exposes its work through `codex exec`, and that command's flag surface is uneven across its own subcommands:

| Flag | `exec` | `exec resume` | `exec review` |
|---|---|---|---|
| `-s`/`--sandbox` | ✅ | ❌ | ❌ |
| `-C`/`--cd` | ✅ | ❌ | ❌ |
| `--add-dir` | ✅ | ❌ | ❌ |
| `-i`/`--image` | ✅ | ✅ | ❌ |
| `-m`, `-c`, `--json`, `-o`, `--output-schema`, `--ignore-user-config` | ✅ | ✅ | ✅ |

`exec resume` has no `-s`/`--sandbox` flag at all. Because of that, a resumed turn doesn't inherit the sandbox its thread was created with — it re-derives one from whatever configuration layer happens to be active at that moment. Measured on one thread across three turns, isolated throughout:

| Turn | Invocation | `sandbox_policy` | `reasoning_effort` |
|---|---|---|---|
| 1 | `exec -c sandbox_mode="workspace-write" -c model_reasoning_effort="low"` | `workspace-write` | `low` |
| 2 | `exec resume` (no flags) | **`read-only`** — silent downgrade | **`None`** — dropped |
| 3 | `exec resume -c sandbox_mode="workspace-write" -c model_reasoning_effort="high"` | `workspace-write` | `high` |

And measured in the opposite direction, a `read-only` thread resumed with the user's own config loaded:

| Turn | Invocation | `sandbox_policy` | Result |
|---|---|---|---|
| 1 | `exec --ignore-user-config -c sandbox_mode="read-only"` | `read-only` | refused to write |
| 2 | `exec resume` (inherited config, no flags) | **`danger-full-access`** | **wrote the file** |

Both directions are wrong, and which one you get depends on an unrelated config layer, not on anything about the thread itself. The full write-up, including how this was verified against the real CLI, is in [Sandbox Stability](Sandbox-Stability.md).

## 2. What It Delivers

Codex in Claude is a Claude Code plugin — one skill (`codex`) backed by a Python standard-library bridge script (`codex_bridge.py`) — that records every per-invocation setting (sandbox, model, reasoning effort, isolation, working directory) the moment a run starts, in a durable run registry, and re-injects all of it on every subsequent call for that thread. That's the fix for the defect above, and it's also the foundation for everything else the plugin does:

- Background execution with a durable handle (`run_id`/`thread_id`) that survives even if Claude's own context is lost or cleared.
- A live event log filtered to a useful default, chosen by measuring real workloads rather than guessing.
- Interrupt-and-redirect on a running task, without losing the work already done.
- Resuming any thread, including ones started outside this plugin entirely, in the Codex TUI.
- Schema-validated structured results.
- Automatic cleanup of orphaned background runs when a Claude session ends.

The property being sold is **stability of a run's settings across turns**. Preventing sandbox escalation is one visible consequence of that; it is not the whole of what stability buys.

## 3. Where It Sits

**Versus calling `codex` directly from a terminal.** Nothing stops you from running the Codex CLI by hand — but then every `resume` you type carries the same settings-amnesia bug, and there's no structured, filtered channel for another agent (Claude) to watch progress and decide when to intervene. This plugin exists specifically to make Codex safe and legible to *drive from Claude*.

**Versus Claude's own subagents (the `Task` tool).** Those are Claude orchestrating more instances of itself. This is Claude delegating to a genuinely different model (whatever Codex/GPT model is configured) running as an independent CLI process, with its own sandbox, its own thread history, and its own event stream to reconcile.

**Versus `codex mcp-server` / `codex app-server`.** Codex's own protocol-server surfaces could in principle offer tighter integration (including real mid-turn steering), but OpenAI's own documentation states both "may change without notice." This project stays on the stable, documented `codex exec` surface and works around its gaps explicitly instead.

## 4. Capabilities at a Glance

| Capability | Where to read more |
|---|---|
| Start and resume Codex threads, background by default | [CLI Reference](CLI-Reference.md), [Getting Started](Getting-Started.md) |
| Sandbox/model/effort held stable across every turn | [Sandbox Stability](Sandbox-Stability.md) |
| Filtered live event log, four verbosity levels | [Context Discipline & Event Log Levels](Context-Discipline.md) |
| Interrupt a run and redirect it on the same thread | [CLI Reference § stop](CLI-Reference.md#8-stop) |
| Resume a thread started in the Codex TUI | [CLI Reference § resume](CLI-Reference.md#3-resume) |
| Schema-validated JSON results | [CLI Reference § result](CLI-Reference.md#9-result) |
| One-command environment diagnostics | [CLI Reference § doctor](CLI-Reference.md#10-doctor) |

## 5. Non-Goals

Considered and deliberately left out of v1 — not overlooked:

- **`codex cloud`.** Remote cloud tasks are experimental and would need their own state model (remote task ids, polling, artifact retrieval) with little shared with the local execution path this plugin manages.
- **`codex mcp-server` / `codex app-server` integration.** Both are documented upstream as primarily for development and debugging, and explicitly "may change without notice." Building on either now would mean building on a surface OpenAI itself doesn't consider stable.
- **True mid-turn steering.** `codex exec` is a single non-interactive turn with no input channel once it starts running — there is no CLI mechanism to inject a message into a turn already in flight. The interactive TUI can do this (Enter injects into the current turn), but that needs a TTY that Claude cannot drive. The v1 intervention model is **stop, then resume**: SIGINT leaves a thread cleanly resumable, with the interrupted turn's completed work intact. `codex app-server` is the one plausible future route to real steering — a protocol client could in principle hold an open channel to a running turn — but this is recorded as **unexplored, not impossible**, pending that surface stabilizing.

---
**Next:** [Getting Started](Getting-Started.md) · [Architecture](Architecture.md)
[Back to index](README.md)
