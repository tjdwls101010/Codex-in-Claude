# Troubleshooting

Run `$CODEX doctor` first. It exits **0** when healthy and **2** when there is a blocker, and it separates blockers (the run cannot work) from warnings (it will work, but something is worth knowing).

**What belongs in the table below, and what does not.** A row earns its place when the tool cannot explain the symptom at the moment it happens: the failure is outside the bridge, or it is a state you read rather than an error you are handed. Everything the CLI already refuses with a reason is left to the refusal — the message arrives when you need it, names your specific case, and cannot fall out of date the way a row can. This file used to restate a dozen of them, including three rows whose entire content was a description of the error text.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| `python3: can't open file '/scripts/codex_bridge.py'` | A path was built from `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PLUGIN_ROOT}`, which are empty in the Bash environment and expanded to nothing | Never build the path from a variable. Use the literal directory from the `Base directory for this skill:` line in your context, double-quoted |
| `no such file or directory` on the bridge | The base directory is wrong. `doctor` cannot diagnose this — it is the same script | `ls "<base directory>/scripts/"` to confirm where the file is. Once any call runs, `doctor`'s `bridge_path` and `plugin_root_env` describe the install |
| Every bridge call raises a permission prompt | The `allowed-tools` pattern is not matching — commonly a symlink install, where `CLAUDE_PLUGIN_ROOT` is empty | Add the `settings.json` equivalent from the README |
| `codex login status` exits non-zero | Not authenticated | `codex login`. Nothing else is worth debugging until this is clean — an unauthenticated run fails in ways that look like other problems |
| Auth works in the terminal but not from the skill | `CODEX_HOME` differs between the two environments | Compare `doctor`'s `codex_home` against `echo $CODEX_HOME` in the shell where it works |
| A run went to `failed` with `exit_code: 127` | `codex` was not found when the run spawned — a PATH that differs from the one `doctor` sees | The run's `stderr.log` has the detail; `doctor` reports `codex_path` |
| A resumed turn did something the sandbox should have prevented, or refuses something the first turn could do | The sandbox drifted, in one direction or the other: `codex exec resume` has no `-s` and falls back to whatever config layer is in effect | Not reachable through the bridge, which re-asserts `-c sandbox_mode=` every time — so this is a bare `codex exec resume` typed by hand. See `environment.md`. If you changed it deliberately, `status` shows `sandbox_changed_from` |
| Codex behaves oddly in a way the prompt does not explain | The project's `AGENTS.md` is injected into every run, even under isolation | Read it. `doctor` reports `project_agents_md` |
| Huge input token counts on a simple task | `--inherit-config`, loading the user's plugins, MCP servers and agent roles | Drop it. The size of the delta is whatever the user's config happens to load and is not a stable number — measure your own rather than quoting one (see `environment.md`) |
| Many `error` events about duplicate agent roles | Inherited config with a malformed user config | Informational, not fatal. Isolation removes them |
| `status` shows `orphaned` | The supervisor was killed without recording an outcome — often a machine sleep or a hard kill | The thread survives; `resume` it. `events.jsonl` up to that point is intact |
| `status` shows `stalled` | No events for a while. Advisory only, and nothing is ever auto-killed | Check `in_progress_item`: with one, it is inside a long command; without one, investigate. [Reading liveness](event-stream.md#reading-liveness) |
| A background run is still going from an earlier session and nothing knows about it | Nothing stops a run on its own — the skill holds capability, not cleanup policy | `status --all` finds it; `stop --run <id>` when you are done with it |
| `stop` reports `no process group recorded` | The run never got far enough to spawn, or its meta predates the pgid | Check `state` and `stderr.log`; nothing is running to stop |
| `resume --last` says no thread found | Empty registry and no Codex thread recorded for this cwd | `status --include-external` lists threads Codex knows about for this directory; resume one by explicit id |
| `review` says there is nothing to review | The tree genuinely is clean | Not an error; it exits 0 with a plain message. Check `git status` |
| `result` refuses a `--schema` run whose message is not JSON | Deliberate | A malformed object handed back as if it had the schema's shape is worse than a loud failure. The error carries a preview; re-run with a clearer prompt |
| A run in a Korean or spaced path behaves strangely | APFS returns NFD while argv carries NFC | The bridge normalises at every boundary. If you see it elsewhere, that is a bug worth reporting |

## Things that are not broken

- **`error` items in the stream.** Informational config warnings, shown at every filter level on purpose — see [Two different schemas](event-stream.md#two-different-schemas).
- **A silent run.** A single `command_execution` can be legitimately silent for minutes. Telling that apart from a stuck one is [Reading liveness](event-stream.md#reading-liveness).
- **`thread_id: null` from `start`.** The thread id had not appeared within the wait window. `status` backfills it from the first line of `events.jsonl`.

## Out of scope for v1

Recorded here so a future reader knows these were considered rather than overlooked.

**`codex cloud`** — remote cloud tasks. Experimental, and a large surface that would need its own state model (remote task ids, polling, artifact retrieval) with little shared with the local path.

**`codex mcp-server` / `codex app-server`** — Codex as an MCP or protocol server. Both documented as primarily for development and debugging and *"may change without notice"*.

**True mid-turn steering.** There is no CLI channel to inject a message into an in-flight `codex exec` turn: it is one non-interactive turn with no input once started. The interactive TUI can do it — Enter injects into the current turn — but it needs a TTY that Claude cannot drive. v1's model is stop → resume, which works because SIGINT leaves the thread resumable with the interrupted turn's completed work intact.

`codex app-server` is the one plausible route to real steering, since a protocol client could hold an open channel to a running turn. **This is unverified** — it has not been tested, and the documented instability is a real reason not to build on it yet. Recorded as unexplored, not as impossible.

## Reporting something that looks wrong

Include: `doctor` output (it is one JSON line and carries the whole environment), the run's `meta.json` (which records the exact argv), and the tail of `events.jsonl`. Those three reproduce almost anything, and `meta.json`'s `argv` in particular settles "what did it actually run" without guessing.
