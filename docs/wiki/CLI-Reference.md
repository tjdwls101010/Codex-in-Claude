# CLI Reference

Every subcommand and flag of `codex_bridge.py`, in full. For anyone who needs a specific flag's exact behavior rather than the common-case walkthrough in [Getting Started](Getting-Started.md).

Every subcommand prints exactly **one line of JSON** on stdout, except the two that stream: `log`, which prints formatted text plus a trailing `# cursor=<n>` line, and `status --group --follow`, which prints a line per member state change and then a terminal `group.<state>` line. `$CODEX` below is shorthand for `python3 "<base directory>/scripts/codex_bridge.py"` — see [Getting Started § finding the bridge script's path](Getting-Started.md#3-finding-the-bridge-scripts-path).

## 1. Common Flags & Defaults

Every subcommand accepts:

| Flag | Meaning |
|---|---|
| `--runs-dir <path>` | Override the run registry location (default `<project>/.codex-runs`) |
| `--project <path>` | Override the project root (default: the git top level of the current directory) |

`start`, `resume`, and `review` additionally share:

| Flag | Meaning |
|---|---|
| `--label <str>` | A short name folded into the `run_id` for readability |
| `--sandbox {read-only,workspace-write,danger-full-access}` | Sandbox mode; default `workspace-write` |
| `--model <str>` | Override the model for this run |
| `--effort <str>` | Reasoning effort, passed through as `model_reasoning_effort` |
| `--inherit-config` | Load the user's own `$CODEX_HOME/config.toml` instead of isolating |
| `--isolate` | Force isolation even if something else would disable it |
| `--priority` / `--no-priority` | Force `service_tier="priority"` re-injection on or off (default: on exactly when isolating) |
| `--schema <path>` | Path to a JSON schema file; the run's final message must validate against it |
| `--config k=v` | Append a raw `-c k="v"` passthrough (repeatable) |
| `--foreground` | Block until the run finishes instead of returning immediately |
| `--timeout <seconds>` | Give the run this long, then SIGINT its process group and record `timed_out`. Works in the background too |
| `--no-preamble` | Disable the short situational preamble normally prepended to the prompt |

A `start` or `resume` that can write to a directory another live writing run already occupies returns `concurrent_writers` naming them. Reported, never refused — sharing a directory is sometimes what you meant, but it is not something you can otherwise see. Runs in their own worktrees never appear there.

Defaults across all of them: **background**, `workspace-write`, isolated from the user's own Codex config, `service_tier=priority` re-injected under isolation, no model or reasoning effort pinned, no hard timeout.

## 2. `start`

```bash
$CODEX start [common flags] [--cwd <path>] [--add-dir <path>]... [--image <path>]... [--prompt-file <path>] "<prompt>"
```

Starts a brand-new thread. The prompt can come from the positional argument, `--prompt-file`, or stdin (if the positional is `-` or omitted while stdin isn't a TTY) — an empty prompt is rejected. `start`-only flags:

| Flag | Meaning |
|---|---|
| `--cwd <path>` | Working directory for the spawned `codex` process |
| `--add-dir <path>` | An extra writable root, beyond `--cwd` (repeatable). Only available on a fresh `start` — `resume`/`review` can't add one later |
| `--image <path>` | Attach an image (repeatable) |
| `--prompt-file <path>` | Read the prompt from a file instead of the command line |

**Output** (background): `run_id`, `thread_id`, `state`, `events` (path to `events.jsonl`), `project`, `sandbox`, `isolated`, and `sandbox_changed_from` if the sandbox differs from a prior run on the same thread.

**Output** (`--foreground`): the above plus `exit_code`, `last_agent_message`, `usage`.

## 3. `resume`

```bash
$CODEX resume <ref|--last> [common flags] [--image <path>]... "<prompt>"
```

Adds a turn to an existing thread, re-asserting every recorded setting. `<ref>` can be a run id, a thread id, or a thread name — if it isn't recognized, it's passed straight through to `codex exec resume` as a thread name. `--last` resumes the most recently active thread instead of naming one explicitly; if the registry is empty, it falls back to querying Codex's own thread database for the most recent thread whose recorded working directory matches the current project — which is what lets this pick up a thread that was started directly in the Codex TUI.

Because `codex exec resume` accepts two optional positionals (`[SESSION_ID] [PROMPT]`) that plain argument parsing can't disambiguate on its own, the bridge special-cases this subcommand's parsing internally; from the outside, just write the ref (if any) followed by the prompt, with flags wherever you like:

```bash
$CODEX resume <run_id> --sandbox read-only "Now double-check the edge cases"
$CODEX resume --last "Continue where you left off"
```

**Output:** the same shape as `start`'s non-foreground output.

## 4. `review`

```bash
$CODEX review [common flags] (--uncommitted | --base <ref> | --commit <sha> [--title <str>] | "<prompt>") [--cwd <path>]
```

Drives `codex exec review`'s own distinct flag surface. Exactly one of `--uncommitted`, `--base <ref>`, `--commit <sha>`, or a free-form prompt is required — combining them is rejected, since the underlying CLI itself rejects the combination. `--title` is only valid alongside `--commit`.

**Output:** the same shape as `start`'s non-foreground output. Note: review runs consistently report all-zero token usage from the underlying CLI — see [`status`](#5-status) and [`result`](#9-result) below for how that's surfaced.

## 5. `status`

```bash
$CODEX status [--run <ref>] [--thread <thread_id>] [--group <name>]
              [--follow [--interval <sec>] [--follow-timeout <sec>]]
              [--all] [--include-external]
```

Lists runs for the project. The default view — no `--run`, `--group` or `--all` — keeps every non-terminal run plus a tail of recent ones, capped at 20 rows, and reports `total_runs` with `runs_truncated` saying how many it withheld. `--group` never truncates: a group you started is bounded by definition, so `runs_truncated` is always `0` there.

| Flag | Meaning |
|---|---|
| `--run <ref>` | Show just one run (by id, prefix, or thread id) |
| `--thread <thread_id>` | Filter to runs on one thread |
| `--group <name>` | Show one batch group's members, with a `group_state` of `running`, `completed`, or `partial` |
| `--follow` | With `--group`: print one line per tick until the group ends, then a terminal `group.completed` / `group.partial` / `group.still-running` line. Pair with the Monitor tool |
| `--all` | Include terminal runs too |
| `--include-external` | Also list threads Codex knows about for this directory that have no registry entry (e.g. started in the TUI) |

**Per-run fields:** `run_id`, `thread_id`, `parent_run_id`, `kind`, `label`, `state` (recomputed to `stalled` if idle time exceeds 300 seconds while still `running`), `codex_pid`, `pgid`, `started_at`, `ended_at`, `elapsed_seconds`, `idle_seconds`, `exit_code`, `sandbox`, `model`, `effort`, `isolated`, `cwd`, `usage` (`null` with a `usage_note` for review runs), `turns_completed`, `commands`, `files_changed`, `config_error_events`, `in_progress_item`, `last_agent_message` (clipped to 400 characters), `events`; conditionally `sandbox_changed_from`, `stderr_tail`, `error`.

**Top level:** `project`, `runs_dir`, `runs`, `threads` (thread id → run ids), `groups` (every batch group in this project), `running` (currently `running`/`stalled` run ids); with `--include-external`: `external_threads` and an explanatory `external_note`. A run that belongs to a group carries `group`, and one with a worktree carries `worktree` — together these are what let a session find and address a batch it did not start.

## 6. `log`

```bash
$CODEX log --run <ref> [--since <n>] [--level {compact,normal,full,raw}] [--follow] [--interval <sec>] [--follow-timeout <sec>]
```

Prints a run's event log, filtered to `--level` (default `compact` — see [Context Discipline & Event Log Levels](Context-Discipline.md)), starting from byte offset `--since` (default `0`). Ends with `# cursor=<n>` — pass that number back as `--since` on the next call to get only new events.

`--follow` polls every `--interval` seconds (default `1.0`) and streams new events as they arrive, printing a terminal line (`run.completed`, `run.failed`, `run.interrupted`, or `run.orphaned`, each with the exit code) once the run reaches a terminal state, or `run.still-running` if `--follow-timeout` elapses first.

## 7. `show`

```bash
$CODEX show --run <ref> --item <item_id> [--max-bytes <n>]
```

Returns one item's complete, unfiltered content — the only path by which full command output reaches you. For a `command_execution` item: `command`, `exit_code`, `total_bytes`, `truncated`, and `output` (truncated to `--max-bytes`, default `20000`, with a loud `truncation_notice` if so). For a `file_change` item: the full, untruncated `changes` list. An unrecognized `--item` fails with a list of available `id:type` pairs.

## 8. `stop`

```bash
$CODEX stop (--run <ref>... | --group <name> | --all) [--grace <sec>]
```

Interrupts a run by signaling its recorded process group directly (SIGINT → SIGTERM after `--grace` seconds, default `5.0` → SIGKILL shortly after) — never by matching a process name, so concurrent runs never interfere with each other. `--run` is repeatable. `--all` stops every non-terminal run in this project's registry — scope is whatever's visible in the registry, not the invisible `claude_session_id` a subagent's runs may not even share with the top-level session. There's no default target, so one of `--run`/`--group`/`--all` is required. `--group` resolves a group's manifest to run ids and signals each one's pgid, same as `--run`.

**Output:** `stopped` (a list of `{run_id, pgid, signalled, signals_sent, state, thread_id, ...}`) and `claude_session_id`.

## 9. `result`

```bash
$CODEX result (--run <ref> | --group <name>)
```

Returns a run's final message and usage. With `--group`, returns every member's message capped at 4,000 bytes with the true size stated, plus `overlaps` — the paths more than one member wrote, keyed by run. Under worktree isolation an overlap is a merge conflict ahead rather than damage already done; without worktrees it is damage already done. If `state` isn't terminal yet, the output includes a `note` saying the result is partial. If the run used `--schema`, the output includes `schema_path` and a parsed `json` field — and fails loudly if the final message isn't valid JSON, rather than returning a malformed object shaped like the schema.

## 10. `batch start`

```bash
$CODEX batch start --group <name> (--task "<prompt>"... | --tasks-file <jsonl>)
                   [--resume-from <group> [--as-ready]] [--worktree | --no-worktree]
                   [--base <ref>] [--force]
                   [any start/resume/review flag as a group-wide default]
```

Starts N runs as one addressable group and returns every handle at once.

| Flag | Meaning |
|---|---|
| `--group <name>` | The group's name. **Single-use per project** — a second `batch start` with the same name fails rather than adding to it |
| `--task "<prompt>"` | One member, always `kind: start`. Repeatable |
| `--tasks-file <path>` | JSONL, one task object per line. Fields: `prompt`, `kind`, `label`, `model`, `effort`, `sandbox`, `schema`, `image`, `cwd`, `resume`, `review` |
| `--resume-from <group>` | Task *i* continues member *i* of that group, in its recorded start order. Refuses while any member of that group is still live |
| `--as-ready` | With `--resume-from`: start each member the moment the member it continues reaches a terminal state, instead of waiting for the slowest of them. Any terminal state releases, a failure included; `--timeout` bounds only the Codex turn and never the wait, and `stop --group` is what ends a wait |
| `--worktree` / `--no-worktree` | Force worktree isolation on for a lone writer, or off entirely |
| `--base <ref>` | Commit the worktrees are cut from (default `HEAD`) |
| `--force` | Let a resume task start a second turn on a thread that already has one live. Not combinable with `--as-ready`, which is the opposite instruction |

Group-level flags are **defaults**, not constraints; a per-item field overrides them. An unknown field name or a wrongly-typed value fails the command before anything starts. One member failing to spawn does not take the batch with it — the failure is recorded in that member's slot.

**Worktrees** are assigned when two or more members can write (`workspace-write` or `danger-full-access`), one per member at `.codex-runs/<run_id>/wt`, detached. `read-only` members, `kind: review` members, `kind: resume` members, and any member with an explicit `cwd` never get one. See [Orchestration](Orchestration.md) for why each exclusion exists.

**Output:** `group`, `runs` (one entry per task, in order, each with `run_id`/`thread_id`/`cwd`/`sandbox` or an `error`), `spawned`, `requested`, `projected_cost`, `manifest`; plus `worktrees` when any were cut (or a `note` saying why none were), and `resumed_from` under `--resume-from`.

A member that never spawned keeps its slot with an `error` and no `run_id`. It stays visible in every later view of the group as `unstarted`, and makes the group `partial` rather than `completed` — a group asked for three and given two never reports success.

## 11. `batch clean`

```bash
$CODEX batch clean --group <name> [--force]
```

Removes a group's worktrees and, if nothing is left behind, releases the group name for reuse. There is no automatic cleanup — a worktree holds the only copy of what its run produced.

Refuses without `--force` when the group still has running members, when another run is still working inside one of the worktrees, when a group derived from this one exists, or when a worktree holds uncommitted changes (that last one is git's own refusal, reported back). **`--force` lifts all four at once**; the result's `forced_past` says what it overrode, and none of it is recoverable.

**Output:** `removed`, `kept` (each with the reason and whether it was dirty), `name_released`, and `forced_past` when `--force` overrode something.

## 12. `doctor`

```bash
$CODEX doctor
```

Diagnoses the environment in one call, including what batches leave behind — registry size and run count, the project's groups, residual worktrees, and any set of live runs sharing one directory where at least one can write. It also covers: Python version, whether `codex` is on `PATH` and its version, `CODEX_HOME` resolution, login status, the config file's sandbox/approval settings, the resolved skill and bridge paths, whether the project has an `AGENTS.md`, whether the runs directory is writable, and whether Codex's thread database is readable.

Exits `0` when healthy, `2` when there's a **blocker** (missing `codex`, failed auth, missing `CODEX_HOME`, unwritable runs dir, Python below 3.10) — which makes it usable directly in a shell conditional. Non-fatal issues are reported separately as **warnings** (e.g. `config.toml` set to `danger-full-access`, a project `AGENTS.md` present, an unreadable thread database).

---
**Next:** [Sandbox Stability](Sandbox-Stability.md) · [Context Discipline & Event Log Levels](Context-Discipline.md)
[Back to index](README.md)
