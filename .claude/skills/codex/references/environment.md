# The Codex environment

Open this when an environment question comes up or `doctor` reports something. The numbers here were measured against `codex-cli 0.144.1` and re-verified against `0.146.0`; re-check with `doctor` before trusting any of them, because Codex ships fast.

## `CODEX_HOME`

Codex resolves its home as `${CODEX_HOME:-$HOME/.codex}`. When `CODEX_HOME` is set, **sessions, `config.toml`, auth and the thread database all move with it** — `~/.codex` is then empty or stale, and reading it gives you another installation's state or nothing.

This is not hypothetical: on the machine this skill was built on, `CODEX_HOME` points into an application's own runtime directory. Any instruction that hardcodes `~/.codex` is already wrong there.

`doctor` prints `codex_home` and `codex_home_from_env` so you can tell an override from a default at a glance.

What lives under it:

| Path | Contents |
|---|---|
| `config.toml` | The user's Codex configuration — model, sandbox, approvals, plugins, MCP servers |
| `auth.json` | Credentials. Still used under `--ignore-user-config` |
| `sessions/YYYY/MM/DD/rollout-<ISO8601>-<thread_id>.jsonl` | Per-thread rollout, written live |
| `state_<N>.sqlite` | The `threads` table — every thread Codex knows about |
| `AGENTS.md` | User-level agent instructions (dropped under isolation) |

## Isolation vs inherited config

`--ignore-user-config` is the default. It stops Codex loading `$CODEX_HOME/config.toml`, which means no user plugins, no MCP servers, no custom agent roles, no lifecycle hooks. Authentication is unaffected — it comes from `auth.json`, which is still read.

Measured on the same trivial prompt (`Reply with exactly: OK`), same machine, twice:

| When | Mode | Input tokens | `error` events |
|---|---|---:|---:|
| design | `--inherit-config` | 46,238 | 24 (plus a plugin advertisement inside the agent's own message) |
| design | `--ignore-user-config` | 15,863 | 0 |
| two weeks later | `--inherit-config` | 17,327 | 8 |
| two weeks later | `--ignore-user-config` | 15,837 | 0 |

Two different things are in that table, and only one of them is a property you can rely on.

**Stable:** the isolated floor (~15.8k, moved by 26 tokens across two weeks) and the clean stream (0 error events, every time). The floor is Codex's own base instructions and tool definitions and is not removable.

**Not stable:** the saving. It went from 2.92× to 1.09× on the same machine with no deliberate config change, because the delta is whatever the user's config actually *loads at that moment* — and an MCP server that fails to start contributes nothing to the prompt.

So do not budget from a ratio someone else measured, including this one. If the cost of inheriting matters to a decision, measure it: run the same prompt both ways and compare `turn.completed.usage.input_tokens`. What you can rely on without measuring is the clean stream.

**When to inherit anyway:** when the run needs a tool that only exists in the user's config — a specific MCP server, a custom agent role. That is a real reason. "To be safe" is not: inheriting also re-enables the `config.toml` sandbox fallback described below, which is the thing that escalates a resumed run.

### `service_tier`

Isolation would otherwise silently drop a user's priority tier, so the wrapper re-injects `-c service_tier="priority"` whenever it is isolating. `--no-priority` turns that off.

Confirmed that the key is genuinely parsed rather than ignored: passing a bogus value produces an explicit event —

```json
{"type":"error","message":"Configured service tier `bogus_tier_xyz` is not advertised as supported for model `gpt-5.6-sol` and will be omitted from requests."}
```

— and `priority` produces no such warning, so it is advertised and being sent. Note the failure mode is graceful: an unsupported tier degrades to a warning and the run proceeds, which is why injecting it unconditionally is safe.

## Sandbox: the whole story

Three modes: `read-only`, `workspace-write` (the default), `danger-full-access`.

### Why the wrapper never uses `-s`

Flag availability differs per subcommand, and this is the fact everything else follows from:

| Flag | `exec` | `exec resume` | `exec review` |
|---|---|---|---|
| `-s`/`--sandbox` | ✅ | ❌ | ❌ |
| `-C`/`--cd` | ✅ | ❌ | ❌ |
| `--add-dir` | ✅ | ❌ | ❌ |
| `-i`/`--image` | ✅ | ✅ | ❌ |
| `-m`, `-c`, `--json`, `-o`, `--output-schema`, `--ignore-user-config` | ✅ | ✅ | ✅ |

`-c` is the only mechanism available on all three, so the sandbox always travels as `-c sandbox_mode="<mode>"`. Working directory is always set on the child process instead of `-C`, for the same reason. Applying both uniformly closes the hole below *by construction* rather than by remembering to special-case two subcommands.

`--add-dir` is `exec`-only, so extra writable roots cannot be added to a resumed or review run. Decide them at `start`.

### The drift, measured

Because `resume` has no `-s`, it re-derives the sandbox from the config layer in effect — not from the thread. Which direction it drifts depends on that layer, and **both directions are wrong**.

One thread, three turns, isolated throughout (`turn_context` from the rollout):

| Turn | Invocation | `sandbox_policy` | `reasoning_effort` |
|---|---|---|---|
| 1 | `exec -c sandbox_mode="workspace-write" -c model_reasoning_effort="low"` | `workspace-write` | `low` |
| 2 | `exec resume` (no flags) | **`read-only`** — silent downgrade | **`None`** — dropped |
| 3 | `exec resume -c sandbox_mode="workspace-write" -c model_reasoning_effort="high"` | `workspace-write` | `high` |

And in the other direction, a `read-only` thread resumed with the user's config loaded:

| Turn | Invocation | `sandbox_policy` | Result |
|---|---|---|---|
| 1 | `exec --ignore-user-config -c sandbox_mode="read-only"` | `read-only` | refused to write |
| 2 | `exec resume` (inherited config, no flags) | **`danger-full-access`**, `file_system: disabled` | **wrote the file** |

Isolation happens to mask the escalation on a machine whose `config.toml` says `danger-full-access`, because Codex's own built-in `exec` default is `read-only`. Do not rely on that. It depends on a Codex default staying put, it collapses the moment `--inherit-config` is used, and it breaks legitimate `workspace-write` work in the other direction.

The property the wrapper buys is **stability of a run's settings across turns**. Anti-escalation is one consequence of it, not the whole of it.

Turn 3 is also the confirmation that `-c` genuinely constrains a resumed run, not merely that it is accepted: the resumed turn refused a write with *"the workspace is read-only, and permission escalation is disabled"* and the file was never created.

### Verifying what a turn actually ran under

The rollout file appends one `turn_context` line per turn:

```json
{"type":"turn_context","payload":{"turn_id":"…","cwd":"…","workspace_roots":["…"],
 "approval_policy":"never","sandbox_policy":{"type":"read-only"},
 "permission_profile":{…},"model":"gpt-5.6-sol",
 "collaboration_mode":{"settings":{"reasoning_effort":null}}}}
```

This is the authoritative per-turn record — structured, one line per turn, and far better than grepping the `<permissions instructions>` developer message. Find the rollout via `$CODEX_HOME/sessions/**/rollout-*-<thread_id>.jsonl`; `codex exec resume` appends to the same file rather than starting a new one.

## `AGENTS.md` survives isolation

`--ignore-user-config` drops the *user's* `AGENTS.md`, but the **project's** `AGENTS.md` is still loaded. Measured: a scratch repo whose `AGENTS.md` said *"The secret codeword for this repository is ZEBRAFISH"* produced `ZEBRAFISH` from a run explicitly told not to read any files, and the rollout shows it injected verbatim:

```
<INSTRUCTIONS>
# Project agent notes
The secret codeword for this repository is ZEBRAFISH.
</INSTRUCTIONS>
```

Two consequences, and the second is easy to miss:

- It is a **briefing channel that works under isolation** — the one way to give an isolated run project-specific standing instructions without pasting them into every prompt.
- It is **uncontrolled input**. Whatever the repo's `AGENTS.md` says is in every run started there. If a run behaves in a way the prompt does not explain, read it. `doctor` reports whether the project has one.

Cost was ~540 input tokens for a two-line file.

## Auth

`codex login status` is what `doctor` runs. It works under isolation because credentials come from `auth.json`, not `config.toml`.

A failing login is reported as a **blocker** and `doctor` exits 2 — every other symptom is worth investigating only after this one is clean, because an unauthenticated run fails in ways that look like something else.

## Model and reasoning effort

Neither is pinned by default. Codex picks its own defaults, and inheriting them is what keeps this skill from going stale as Codex versions change — a hardcoded model name is a guaranteed future bug.

`--model` and `--effort` override per run and are then re-asserted on every subsequent turn of that run's thread, because effort drifts on resume exactly like the sandbox does.

## Reading `doctor`

`doctor` exits 0 when healthy and **2** when there is a blocker, so it is usable in a conditional. It separates two categories deliberately:

- **blockers** — the run will not work: no `codex` on PATH, not authenticated, missing `CODEX_HOME`, unwritable runs dir, Python below 3.10.
- **warnings** — the run will work but something is worth knowing: `config.toml` set to `danger-full-access`, a project `AGENTS.md`, a thread database it could not read.

`thread_db_readable: false` with a `thread_db` path present means the sqlite schema changed under a Codex upgrade. Only `--include-external` and a registry-less `resume --last` depend on it; everything else keeps working. That degradation is deliberate — the filename is version-stamped (`state_5.sqlite`), so the schema *will* change, and a Codex upgrade must never break the skill outright.
