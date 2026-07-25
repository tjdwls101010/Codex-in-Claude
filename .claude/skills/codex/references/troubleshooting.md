# Troubleshooting

Run `$CODEX doctor` first. It exits **0** when healthy and **2** when there is a blocker,
and it separates blockers (the run cannot work) from warnings (it will work, but something
is worth knowing). Most of the table below is faster to reach through it.

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---|---|---|
| `python3: can't open file '/scripts/codex_bridge.py'` | `${CLAUDE_SKILL_DIR}` does not exist in the Bash environment and expanded to nothing | Use the resolution snippet in SKILL.md. `doctor`'s `bridge_path` shows what actually resolved |
| `no such file or directory` on the bridge, plugin install | `CLAUDE_PLUGIN_ROOT` not set in this context | The snippet's fallback covers the symlink install; check `doctor`'s `plugin_root_env` to see which branch you are on |
| Every bridge call raises a permission prompt | The `allowed-tools` pattern is not matching — commonly a symlink install, where `CLAUDE_PLUGIN_ROOT` is empty | Add the `settings.json` equivalent from the README |
| `codex` is not on PATH | Codex not installed, or installed for a different shell | Install it; `doctor` reports `codex_path` and `codex_version` |
| `codex login status` exits non-zero | Not authenticated | `codex login`. Nothing else is worth debugging until this is clean — an unauthenticated run fails in ways that look like other problems |
| Auth works in the terminal but not from the skill | `CODEX_HOME` differs between the two environments | Compare `doctor`'s `codex_home` against `echo $CODEX_HOME` in the shell where it works |
| Run went to `failed` with `exit_code: 127` | `codex` was not found when the run spawned | Same as PATH above; the run's `stderr.log` has the detail |
| A resumed turn did something the sandbox should have prevented | A bare `codex exec resume` typed by hand, not through the bridge | `resume` has no `-s` flag and falls back to `config.toml`. Use the bridge, which re-asserts `-c sandbox_mode=` every time. See `environment.md` |
| A resumed turn refuses something the first turn could do | Same mechanism, opposite direction — the sandbox drifted *down* | The bridge prevents this too. If you changed it deliberately, `status` shows `sandbox_changed_from` |
| Codex behaves oddly in a way the prompt does not explain | The project's `AGENTS.md` is injected into every run, even under isolation | Read it. `doctor` reports `project_agents_md` |
| Huge input token counts on a simple task | `--inherit-config`, loading the user's plugins, MCP servers and agent roles | Drop it — measured 46,238 vs 15,863 input tokens for the same trivial prompt |
| Many `error` events about duplicate agent roles | Inherited config with a malformed user config | Informational, not fatal. Isolation removes them |
| `usage` is `null` on a review run | Review runs genuinely report zero usage | Not a bug and not free — the tokens were spent, Codex just does not report them |
| `status` shows `orphaned` | The supervisor was killed without recording an outcome — often a machine sleep or a hard kill | The thread survives; `resume` it. `events.jsonl` up to that point is intact |
| `status` shows `stalled` | No events for a while. Advisory only | Check `in_progress_item`: with one, it is inside a long command; without one, investigate |
| A run vanished when the session ended | Session-end cleanup, which is the intended default | `resume` it — a SIGINT-stopped thread is resumable. Use `--detach` next time if it should outlive the session |
| A background run is still going and nothing knows about it | A `--detach`ed run outliving its session | `status --all` finds it; `stop --run <id>`. `doctor` lists them under `detached_running` |
| `stop` reports `no process group recorded` | The run never got far enough to spawn, or its meta predates the pgid | Check `state` and `stderr.log`; nothing is running to stop |
| `resume --last` says no thread found | Empty registry and no Codex thread recorded for this cwd | Pass a thread id explicitly. `status --include-external` lists threads Codex knows about for this directory |
| `--include-external` returns nothing, `doctor` says `thread_db_readable: false` | A Codex upgrade changed the version-stamped sqlite schema | Degraded, not broken: only `--include-external` and a registry-less `--last` use it. Resume by explicit thread id |
| `review` says there is nothing to review | The tree genuinely is clean | Not an error; it exits 0 with a plain message. Check `git status` |
| `result` fails with "not valid JSON" | `--schema` was used but the model's final message is not JSON | Deliberate — a malformed object handed back as if it had the schema's shape is worse. The error carries a preview; re-run with a clearer prompt |
| stderr contains `Reading additional input from stdin...` | Codex writes this on every non-TTY run | Normal output, not failure. `status` filters this line and shows the rest |
| A run in a Korean or spaced path behaves strangely | APFS returns NFD while argv carries NFC | The bridge normalises at every boundary. If you see it elsewhere, that is a bug worth reporting |
| Two runs seem to interfere | They should not — each has its own process group and its own event log | Never kill by process name; `pgrep -f "codex exec"` matches everyone's runs |

## Things that are not broken

- **`error` items in the stream.** Informational config warnings. Shown at every filter
  level on purpose, because the one time an `error` is not routine you need to see it.
- **A silent run.** A single `command_execution` can be legitimately silent for minutes.
  `idle_seconds` plus `in_progress_item` is how you tell that apart from a stuck one.
- **`thread_id: null` from `start`.** The thread id had not appeared within the wait
  window. `status` backfills it from the first line of `events.jsonl`.
- **`compact` output that omits command stdout.** That is the entire point; the size marker
  and `show --item` are how you get it when you want it.

## Out of scope for v1

Recorded here so a future reader knows these were considered rather than overlooked.

**`codex cloud`** — remote cloud tasks. Experimental, and a large surface that would need
its own state model (remote task ids, polling, artifact retrieval) with little shared with
the local path.

**`codex mcp-server` / `codex app-server`** — Codex as an MCP or protocol server. Both
documented as primarily for development and debugging and *"may change without notice"*.

**True mid-turn steering.** There is no CLI channel to inject a message into an in-flight
`codex exec` turn: it is one non-interactive turn with no input once started. The
interactive TUI can do it — Enter injects into the current turn — but it needs a TTY that
Claude cannot drive. v1's model is stop → resume, which works because SIGINT leaves the
thread resumable with the interrupted turn's completed work intact.

`codex app-server` is the one plausible route to real steering, since a protocol client
could hold an open channel to a running turn. **This is unverified** — it has not been
tested, and the documented instability is a real reason not to build on it yet. Recorded as
unexplored, not as impossible.

## Reporting something that looks wrong

Include: `doctor` output (it is one JSON line and carries the whole environment), the run's
`meta.json` (which records the exact argv), and the tail of `events.jsonl`. Those three
reproduce almost anything, and `meta.json`'s `argv` in particular settles "what did it
actually run" without guessing.
