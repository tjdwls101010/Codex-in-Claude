---
name: codex
description: >-
  Run OpenAI Codex (the `codex` CLI, GPT models) as a managed subagent from Claude Code —
  start work in the background and get a run handle back immediately, watch its live event
  log at a controlled level of detail, interrupt and redirect a run, resume any earlier
  Codex thread including ones started in the Codex TUI, and collect results as text or
  schema-validated JSON. Use whenever work is being handed to Codex or GPT, when a second
  independent model should look at something, when an external agent should keep working
  while Claude does something else, or when an earlier Codex session needs continuing.
  Also covers Codex CLI setup, auth, sandbox and config diagnosis. Triggers include: codex,
  코덱스, 코덱스로, 코덱스한테, 코덱스에게, GPT, GPT한테, GPT에게 시켜, delegate to codex,
  run with codex, ask GPT, resume codex. Not for Claude's own subagents, the Task tool, or
  background Bash — those are Claude doing the work itself. Not for Codex Cloud or
  `codex mcp-server` / `app-server`.
allowed-tools:
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/.claude/skills/codex/scripts/codex_bridge.py" *)
---

# Codex as a managed subagent

One CLI wraps the whole surface. Your context already carries a line reading **`Base directory for this skill: <dir>`** — the bridge is `<dir>/scripts/codex_bridge.py`. Use that absolute path, double-quoted, in every call:

```bash
python3 "<base directory>/scripts/codex_bridge.py" status
```

**Do not build the path from an environment variable.** `$CLAUDE_PLUGIN_ROOT` and `$CLAUDE_SKILL_DIR` are both empty in the Bash environment, even for a plugin install (measured — `$CLAUDE_PLUGIN_ROOT` is expanded in permission rules, which is a different layer from the process environment). And because this skill's pre-approved permission pattern matches the command *text*, a command written as `python3 "$SOMEVAR/..."` is not covered by it and raises an approval prompt on every poll — which is exactly what makes background work unusable.

If a call fails with "No such file or directory", the path is wrong and `doctor` cannot help you find it — it is the same script. Locate the file first: the `Base directory for this skill:` line above is the answer, and `ls "<base directory>/scripts/"` confirms it. Once a call runs at all, `doctor` diagnoses everything else about the environment.

Every subcommand prints **one line of JSON**, except `log`, which prints text plus a trailing `# cursor=<n>`. Below, `$CODEX` is shorthand for that literal `python3 "<base directory>/scripts/codex_bridge.py"` — write it out in full when you run it.

| Command | What it does |
|---|---|
| `start [opts] "<prompt>"` | New thread. Background by default; returns `{run_id, thread_id, state, …}` |
| `resume <ref\|--last> [opts] "<prompt>"` | Another turn on an existing thread. `<ref>` is a run id, thread id, or thread name |
| `review [opts] --uncommitted \| --base <ref> \| --commit <sha> \| "<prompt>"` | `codex exec review`'s separate flag surface |
| `batch start --group <name> --task "…" [--task "…"]…` | N runs as one addressable group. Also `--tasks-file <jsonl>`, `--resume-from <group>` |
| `batch clean --group <name> [--force]` | Remove that group's worktrees once you have collected them |
| `status [--run <id>] [--group <name> [--follow]] [--all] [--include-external]` | State, elapsed, `idle_seconds`, usage, last message, in-progress item |
| `log --run <id> [--since <n>] [--level …] [--follow]` | Filtered events, incrementally |
| `show --run <id> --item <item_id> [--max-bytes N]` | One item's full output |
| `stop --run <id>… \| --group <name> \| --all` | Interrupt by process group |
| `result --run <id> \| --group <name>` | Final message, usage, parsed JSON when `--schema` was used |
| `doctor` | PATH, version, `CODEX_HOME`, auth, config sandbox, resolved paths, runs dir, worktrees |

Common `start`/`resume`/`review` options: `--sandbox {read-only,workspace-write,danger-full-access}` (default `workspace-write`), `--model`, `--effort`, `--label`, `--schema <file>`, `--inherit-config`, `--timeout <sec>`, `--foreground`, `--no-preamble`, `--config k=v`. `start` also takes `--cwd`, `--add-dir`, `--image`; `resume` takes `--image`.

`--timeout` works in the background too: at the deadline the run's process group gets SIGINT and the run is recorded `timed_out` — a state of its own, distinct from `interrupted` (you stopped it) and `failed` (Codex did), because only the third is answered by raising the timeout. The thread stays resumable across it, with the pre-timeout turn's context intact.

`status` truncates. Without `--all` it reports the non-terminal runs plus `total_runs`, and sets `runs_truncated` when it withheld some; `threads` groups runs that share one. The list is capped at 20 rows in every mode. A group's own summary reports `running`, `done`, `failed` and a `group_state` of `running`, `completed` or `partial`.

## The loop

```bash
$CODEX start --label refactor "…"            # → run_id, thread_id, immediately
$CODEX log --run <id> --since 0              # → events + "# cursor=4213"
$CODEX log --run <id> --since 4213           # → only what is new
$CODEX stop --run <id>                       # if it is going wrong
$CODEX resume <id> "Stop rewriting tests — …" # correct it, same thread
$CODEX result --run <id>                     # final message + usage
```

There is no way to inject a message into a turn that is already running. `codex exec` is one non-interactive turn with no input channel once started, so intervention is **stop then resume**, and a stopped run stays resumable: SIGINT lets Codex flush its rollout, and the resumed turn still knows what the interrupted one had finished.

## Context discipline

`file_change` events carry paths and a kind, never file contents. **The entire context risk is one field: `command_execution.aggregated_output`**, which holds a command's full stdout — so a run that `cat`s a 2,000-line file puts that whole file in there.

The default level therefore never carries command output. Instead each command line reports its size:

```
cmd[item_2] exit=0 out=8797B rg -n "" tests . --glob '*.py'
```

That byte count is there so fetching output is a decision, not a guess: `show --run <id> --item item_2` returns exactly that one command's output, and nothing else's.

This works because **the agent's own messages are never filtered at any level**. Codex states what it found and what it did, so raw output is usually a second copy of a summary you already have. Reach for `show` when you need to check the summary rather than read it — a claim looks wrong, or the run stopped before it explained itself.

Levels: `compact` (default) · `normal` adds output for **failed** commands only · `full` adds capped output for every item · `raw` passes events through. Measured costs and the reason `compact` is the default are in `references/event-stream.md`. Raise to `normal` when a command failed and the agent's account of it is not enough to act on — that is the one case where the withheld bytes are the diagnosis rather than a copy of it.

## Gotchas

These are the traps that cost a real failure to learn. Everything else about driving a CLI you already know.

**A resumed run inherits none of its thread's settings.** `codex exec resume` has no `-s/--sandbox` flag, so the sandbox comes from whatever config layer is in effect, not from the thread. Measured: a `read-only` thread resumed under the user's config ran as `danger-full-access` and wrote a file its original policy forbade; the same thread resumed under isolation silently dropped to `read-only` and lost its reasoning effort. This wrapper re-asserts sandbox, model, effort, isolation and cwd **from the registry** — so the protection reaches exactly as far as the registry does. Resuming a run this skill started is covered. Resuming a thread it has never seen, by thread id or by name from the Codex TUI, has nothing to re-assert from and falls back to the defaults: **pass `--sandbox` explicitly the first time you pick up an outside thread**, and it is recorded from then on. A bare `codex` command you type yourself has no protection at all.

**`item.id` restarts at `item_0` on every invocation.** It is per-invocation, not per-thread, so two runs on one thread both have an `item_0`. Always pass `--run` with `--item`; an item id alone identifies nothing.

**`resume` replays the entire thread.** Measured on one thread: 15.9k input tokens fresh → 31.8k after one turn → 47.8k after two → 86.1k after an interrupted multi-command turn. Resuming is not free and gets worse as a thread grows, so a fresh thread is sometimes the cheaper choice. Judge it; there is no threshold worth memorising.

**A project's `AGENTS.md` is loaded even under isolation.** `--ignore-user-config` drops the user's config, plugins and MCP servers, but the repository's own `AGENTS.md` is still injected verbatim as a developer instruction (measured). That makes it a briefing channel that survives isolation — and equally, means whatever is in it is in every run you start there, whether you intended it or not. `doctor` reports whether the project has one.

**stderr is normal output.** Codex writes `Reading additional input from stdin...` to stderr on every non-TTY run. Never treat stderr content as failure; `status` already filters that line out and shows you the rest.

**`review` reports zero token usage.** Measured on every review run: `turn.completed` comes back all zeros after real work. `status` and `result` report usage as `null` for review runs — that means unavailable, not free.

**Never kill Codex by process name.** `stop` signals one run's recorded process group. Matching `codex exec` by name kills every Codex on the machine, including runs started by another session or another person.

**Process groups isolate signals, not files.** Each run gets its own group, so stopping one never touches another — that is the whole of what the separation buys. Two runs in the same directory still edit the same files, and neither can tell another agent's change from its own. That is what worktrees are for, and why `batch start` assigns them when two or more members can write.

**The preamble is a paragraph this wrapper prepends to your prompt**, telling Codex facts it cannot observe from inside a non-interactive turn: that nobody is watching, so a clarifying question ends the turn with the work not done; that its final message is what the caller receives, so the answer belongs there and not only in files it touched. Batch runs additionally get the group size and, when isolated, their worktree's path and base. `--no-preamble` removes all of it at once — reach for it only when you are briefing Codex yourself, and note that `result` depends on the "put the answer in your final message" instruction.

**`CODEX_HOME` may be overridden**, so `~/.codex` is not reliably where sessions, config and auth live. `doctor` prints the resolved value.

## Background work and parallelism

Runs are backgrounded by default and several can run at once — each gets its own process group, so stopping one does not touch the others. Start work, do something else, come back with `log --since`.

To be notified as events arrive rather than polling, pair `--follow` with the **Monitor** tool:

```bash
$CODEX log --run <id> --follow --level compact
```

`--follow` emits a terminal line (`run.completed` / `run.failed` / `run.interrupted` with the exit code) before exiting, so a crashed run never looks like a quiet one.

**Silence is not failure.** A run producing no events for minutes may be inside one long `command_execution` — legitimately silent. `status` gives you `idle_seconds` *and* `in_progress_item`; silence with an in-progress item is work, silence with none is a problem worth investigating. The `stalled` state is advisory and nothing is ever auto-killed.

### When a group is worth it

`batch start` buys one thing: N runs become one thing you can name. `status --group` is a single call instead of N, `--follow` tells you when the *group* finishes rather than when each member does, `result --group` returns capped messages plus `overlaps` — the paths more than one member wrote — and `stop --group` ends all of it. Reach for it when you would otherwise be tracking several run ids by hand.

The costs are real and neither is a threshold. Each run pays the isolation floor separately, so N parallel runs pay N floors where N turns on one thread pay one floor plus a growing replay. And N runs writing in one directory corrupt each other, which is why two or more writing members get worktrees — results then live outside your tree until you collect them, and `batch clean --group` is what removes them.

`references/orchestration.md` has the mechanics: group lifetimes, the `--resume-from` pairing rule, the worktree traps, and how to pair `--follow` with Monitor.

## Structured output

`--schema <file>` passes a JSON Schema to Codex and `result` returns the parsed object as `json`. If the final message is not valid JSON, `result` fails loudly rather than handing back something malformed. Worth the extra file when you are going to branch on the answer; not worth it when you are going to read the answer.

## Cost and configuration

Runs are **isolated by default** (`--ignore-user-config`), which drops the user's `config.toml`: their MCP servers, plugins, agent roles and hooks. Auth is unaffected.

What isolation reliably buys is a **clean stream**. An inherited-config run on this machine emits 8 config-error events about malformed agent roles before it does any work, and has been observed leaking an unrelated plugin advertisement into the agent's own message; the isolated equivalent emits none.

What it saves in tokens is **not a fixed number, and do not quote one**. The same one-line prompt on the same machine measured 46,238 input tokens inherited during design and 17,327 inherited two weeks later — against a stable ~15.8k isolated floor, that is 2.9× and then 1.09×. The floor is Codex's own base instructions and does not move; the delta is whatever the user's config happens to load at that moment, and an MCP server that fails to start contributes nothing. So: reach for `--inherit-config` when the run genuinely needs a tool that only exists in the user's config, and measure your own delta rather than budgeting from a number measured somewhere else.

## Out of scope

`codex cloud`, and `codex mcp-server` / `codex app-server` — all experimental and documented as subject to change without notice. `app-server` is the only plausible route to true mid-turn steering and is recorded in `references/troubleshooting.md` as unexplored, not as impossible.

## References

- `references/environment.md` — `CODEX_HOME`, isolation vs inherit with the numbers, auth, the full sandbox story, `service_tier`, reading `doctor` output.
- `references/event-stream.md` — both event schemas, the filter levels with the measured calibration table, cursors and polling, Monitor pairing, `show`.
- `references/orchestration.md` — running several Codex runs as one group: the batch commands, worktrees, `--resume-from`, how cost multiplies.
- `references/troubleshooting.md` — symptom → cause → fix.
