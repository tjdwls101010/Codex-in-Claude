# Troubleshooting

Known failure modes and their fixes. For anyone hitting something that doesn't look right — run `$CODEX doctor` first regardless of what you're chasing; it exits `0` when healthy and `2` with a `blockers` array otherwise, and most of the table below is faster to reach through it than by reading logs directly.

## 1. Path & Permission Issues

| Symptom | Cause | Fix |
|---|---|---|
| `python3: can't open file '/scripts/codex_bridge.py'` | The path was built from an environment variable (`${CLAUDE_SKILL_DIR}`, etc.) that doesn't exist in the Bash tool's environment and expanded to nothing | Use the literal `Base directory for this skill: <dir>` line from context instead — see [Getting Started § finding the bridge script's path](Getting-Started.md#3-finding-the-bridge-scripts-path). `doctor`'s `bridge_path` field shows what actually resolved |
| `no such file or directory` on the bridge, plugin install | `$CLAUDE_PLUGIN_ROOT` isn't set in this context either | The same fallback applies; check `doctor`'s `plugin_root_env` field to see which case you're in |
| Every bridge call raises a permission prompt | The `allowed-tools` pattern isn't matching — commonly a symlink install, where `$CLAUDE_PLUGIN_ROOT` is empty | Add the `settings.json` snippet from [Getting Started § installation](Getting-Started.md#2-installation) |

## 2. Auth & PATH Issues

| Symptom | Cause | Fix |
|---|---|---|
| `codex` is not on `PATH` | Codex isn't installed, or is installed for a different shell | Install it; `doctor` reports `codex_path` and `codex_version` |
| `codex login status` exits non-zero | Not authenticated | Run `codex login`. Nothing else is worth debugging until this is clean — an unauthenticated run fails in ways that look like unrelated problems |
| Auth works in a terminal but not from the skill | `$CODEX_HOME` differs between the two environments | Compare `doctor`'s `codex_home` field against `echo $CODEX_HOME` in the shell where it does work |
| A run went to `failed` with `exit_code: 127` | `codex` wasn't found when the run spawned | Same as the PATH issue above; the run's `stderr.log` has the detail |

## 3. Sandbox Drift

| Symptom | Cause | Fix |
|---|---|---|
| A resumed turn did something its sandbox should have prevented | A bare `codex exec resume` was typed by hand, bypassing the bridge | `resume` has no `-s` flag and falls back to `config.toml`. Use the bridge, which re-asserts `-c sandbox_mode=` on every call — see [Sandbox Stability](Sandbox-Stability.md) |
| A resumed turn refuses something the first turn could do | The same mechanism, drifting the other direction | The bridge prevents this too. If you changed the sandbox deliberately, `status` shows it as `sandbox_changed_from` rather than silent drift |
| Codex behaves oddly in a way the prompt doesn't explain | The project's `AGENTS.md` is injected into every run, even under isolation | Read it — `doctor` reports `project_agents_md` if one exists |
| Huge input token counts on a simple task | `--inherit-config` is loading the user's plugins, MCP servers, and agent roles | Drop it — measured 46,238 vs. 15,863 input tokens for the identical trivial prompt. See [Sandbox Stability § the cost of inheriting config](Sandbox-Stability.md#3-the-cost-of-inheriting-config) |
| Many `error` events about duplicate agent roles | Inherited config with a malformed user configuration | Informational, not fatal — isolation removes these entirely |

## 4. Run State & Lifecycle

| Symptom | Cause | Fix |
|---|---|---|
| `status` shows `orphaned` | The supervisor process was killed without recording an outcome — often a machine sleep or a hard kill | The thread itself survives; `resume` it. `events.jsonl` up to that point is intact |
| `status` shows `stalled` | No events for a while past an advisory threshold | Check `in_progress_item`: present means it's inside a long-running command (normal); absent means it's worth investigating |
| A background run from an earlier session is still going and nothing knows about it | Nothing stops a run automatically — the skill holds capability, not cost or cleanup policy | `status --all` finds it; `stop --run <id>` when you're done with it |
| `stop` reports no process group recorded | The run never got far enough to spawn one, or its `meta.json` predates that field | Check `state` and `stderr.log` — there's nothing running to stop |
| `resume --last` says no thread was found | The registry is empty and Codex has no recorded thread for this working directory either | Pass a thread id explicitly. `status --include-external` lists threads Codex itself knows about for this directory |
| `--include-external` returns nothing, and `doctor` reports `thread_db_readable: false` | A Codex CLI upgrade changed the version-stamped sqlite schema | Degraded, not broken — only `--include-external` and a registry-less `--last` depend on it. Resume by explicit thread id instead |

## 5. Review, Results, and Encoding

| Symptom | Cause | Fix |
|---|---|---|
| `review` says there's nothing to review | The tree is genuinely clean | Not an error — it exits `0` with a plain message. Confirm with `git status` |
| `usage` is `null` on a review run | Review runs consistently report zero usage from the underlying CLI | Not a bug, and not free — the tokens were spent, Codex just doesn't report them for this subcommand |
| `result` fails with "not valid JSON" | `--schema` was used, but the model's final message isn't valid JSON | Deliberate — handing back a malformed object shaped like the schema would be worse than failing loudly. The error includes a preview; re-run with a clearer prompt |
| stderr contains `Reading additional input from stdin...` | Codex prints this on every non-TTY invocation | Normal output, not a failure — `status` filters this specific line out of `stderr_tail` |
| A run in a Korean or space-containing path behaves strangely | APFS returns NFD-normalized paths while argv/JSON carry NFC | The bridge normalizes at every boundary where a path becomes a string. If you see drift anywhere else, that's a real bug worth reporting |
| Two runs seem to interfere with each other | They shouldn't — each has its own process group and its own event log | Never kill Codex processes by name; `pgrep -f "codex exec"` matches *every* run's processes, not just one |

## 6. Things That Are Not Broken

- **`error` items in the event stream.** These are informational config warnings, shown at every filter level on purpose — the one time an `error` isn't routine, you need to see it.
- **A silent run.** A single `command_execution` can legitimately produce no events for minutes. `idle_seconds` plus `in_progress_item` is how you tell that apart from a genuinely stuck run.
- **`thread_id: null` from `start`.** The thread id simply hadn't appeared within the wait window yet. `status` backfills it from the first line of `events.jsonl` once it does.
- **`compact` output that omits command stdout.** That's the entire point of the default level — the size marker and `show --item` are how you retrieve it when you actually want it.

## 7. Deliberately Out of Scope

Recorded here so it's clear these were considered and rejected, not overlooked. See [Overview § non-goals](Overview.md#5-non-goals) for the fuller reasoning.

- **`codex cloud`** — experimental, and a large enough surface to need its own state model.
- **`codex mcp-server` / `codex app-server`** — both documented upstream as primarily for development and debugging, and explicitly subject to change without notice.
- **True mid-turn steering** — `codex exec` has no channel to inject a message into an already-running turn. `codex app-server` is the one plausible future route to real steering, and is recorded as unexplored rather than impossible.

## 8. Reporting Something That Looks Wrong

Include three things and almost anything becomes reproducible: `doctor`'s output (one JSON line, carries the whole environment), the affected run's `meta.json` (records the exact argv it ran), and the tail of that run's `events.jsonl`. `meta.json`'s `argv` field in particular settles "what did it actually run" without anyone needing to guess.

---
**Next:** [Getting Started](Getting-Started.md) · [Sandbox Stability](Sandbox-Stability.md)
[Back to index](README.md)
