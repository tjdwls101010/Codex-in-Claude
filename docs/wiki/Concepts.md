# Concepts

The vocabulary you need to read the rest of this wiki, defined in the order each concept builds on the last. For anyone about to use or extend the plugin.

## 1. Thread

A **thread** is Codex's own unit of conversation, identified by a `thread_id`. It's created the first time `codex exec` runs and is what `codex exec resume <thread_id>` continues. Codex persists a thread's full history as a **rollout file** at `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ISO8601>-<thread_id>.jsonl`, and every `resume` appends to that same file rather than starting a new one. Threads exist independently of this plugin — one can be started directly in the Codex TUI and later picked up through the bridge, or vice versa.

## 2. Run

A **run** is this plugin's unit of work: one invocation of the bridge (`start`, `resume`, or `review`) that spawns exactly one `codex exec` process, identified by a `run_id` (format `<timestamp>-<label-or-'run'>-<4 hex chars>`). A single thread accumulates one run per turn — `start` creates a thread's first run, and each `resume` creates a new run against the same thread. A run's lifecycle state is one of `starting`, `running`, `stalled` (advisory), `completed`, `failed`, `interrupted`, or `orphaned`.

## 3. Sandbox Mode

One of three values Codex enforces for a run: `read-only`, `workspace-write` (this plugin's default), or `danger-full-access`. It governs what a run is allowed to touch on disk. See [Sandbox Stability](Sandbox-Stability.md) for why this concept needs a whole page: `codex exec` only lets you *set* it with `-s`/`--sandbox` on a fresh invocation, never on `resume` or `review`.

## 4. Isolation (`--ignore-user-config`)

Whether a run loads the user's own `$CODEX_HOME/config.toml` — their plugins, MCP servers, custom agent roles, and lifecycle hooks. This plugin isolates by default (`--ignore-user-config`); passing `--inherit-config` opts back in for a single run. Isolation does not affect authentication (`auth.json` is always read) and does not suppress the *project's* `AGENTS.md` (only the user's).

## 5. The Run Registry

The durable record this plugin keeps of every run it starts, at `<project>/.codex-runs/<run_id>/`. This is the mechanism that makes sandbox stability possible at all: since Codex itself doesn't remember a thread's settings across turns, the registry does, storing `meta.json` (settings and lifecycle state), `events.jsonl` (Codex's raw event stream), `stderr.log`, and `last-message.txt`. See [Architecture](Architecture.md) for how it's used and [Session Cleanup Hook](Session-Cleanup-Hook.md) for how it's cleaned up.

## 6. Event / Item

Codex's `codex exec --json` mode emits one JSON object per line to stdout — an **event** — and most events wrap an **item**: a `command_execution`, `file_change`, `agent_message`, `reasoning` step, `error`, `todo_list`, `web_search`, or `mcp_tool_call`. Item ids (`item_0`, `item_1`, …) restart at zero on every invocation, so they only mean something scoped to one run's `events.jsonl`.

## 7. Filter Level

One of `compact` (default), `normal`, `full`, or `raw` — how much of the raw event stream the bridge actually prints when you ask for a run's log. The levels exist because one field, `command_execution`'s `aggregated_output`, can carry a command's entire stdout — including the full contents of any file Codex happened to `cat`. See [Context Discipline & Event Log Levels](Context-Discipline.md) for exactly what each level includes.

## 8. Cursor

A byte offset into a run's `events.jsonl`, returned by `log` as a trailing `# cursor=<n>` line. Passing it back as `--since <n>` on the next call returns only what arrived since — exactly once, with no duplication or gaps, even if you poll mid-write.

---
**Next:** [Architecture](Architecture.md) · [CLI Reference](CLI-Reference.md)
[Back to index](README.md)
