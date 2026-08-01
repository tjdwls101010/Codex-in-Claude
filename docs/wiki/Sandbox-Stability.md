# Sandbox Stability

The measured defect this project exists to fix, in full: what causes it, exactly how it was verified, and how the fix works. For anyone deciding whether to trust this plugin with real filesystem access, or debugging a run that behaved unexpectedly.

## 1. Why `resume` Can't Just Ask for a Sandbox

`codex exec`'s flag surface is not the same across its own subcommands:

| Flag | `exec` | `exec resume` | `exec review` |
|---|---|---|---|
| `-s`/`--sandbox` | ✅ | ❌ | ❌ |
| `-C`/`--cd` | ✅ | ❌ | ❌ |
| `--add-dir` | ✅ | ❌ | ❌ |
| `-i`/`--image` | ✅ | ✅ | ❌ |
| `-m`, `-c`, `--json`, `-o`, `--output-schema`, `--ignore-user-config` | ✅ | ✅ | ✅ |

`-c` (raw config passthrough) is the only mechanism available on all three subcommands, so this plugin always expresses the sandbox as `-c sandbox_mode="<mode>"`, never `-s` — and always sets the working directory on the child process itself, never via `-C`, for the same reason. Applying both uniformly closes the hole below *by construction*, rather than by remembering to special-case `resume` and `review`.

One consequence worth knowing: `--add-dir` is `exec`-only, so extra writable roots can only be added when a thread is created with `start` — they can't be added later on a `resume`.

## 2. The Drift, Measured

Because `resume` has no `-s`, it re-derives the sandbox from whatever config layer is in effect for that specific invocation — not from the thread it's resuming. Which direction it drifts depends entirely on that layer, and **both directions are wrong**.

**Downgrade**, measured on one thread across three turns, isolated throughout:

| Turn | Invocation | `sandbox_policy` | `reasoning_effort` |
|---|---|---|---|
| 1 | `exec -c sandbox_mode="workspace-write" -c model_reasoning_effort="low"` | `workspace-write` | `low` |
| 2 | `exec resume` (no flags) | **`read-only`** — silent downgrade | **`None`** — dropped |
| 3 | `exec resume -c sandbox_mode="workspace-write" -c model_reasoning_effort="high"` | `workspace-write` | `high` |

Turn 3 is also confirmation that `-c` genuinely *constrains* a resumed run rather than merely being accepted: turn 2's resumed agent refused a write with "the workspace is read-only, and permission escalation is disabled," and the target file was never created.

**Escalation**, measured on a `read-only` thread resumed with the user's config loaded:

| Turn | Invocation | `sandbox_policy` | Result |
|---|---|---|---|
| 1 | `exec --ignore-user-config -c sandbox_mode="read-only"` | `read-only` | refused to write |
| 2 | `exec resume` (inherited config, no flags) | **`danger-full-access`**, `file_system: disabled` | **wrote the file** |

Isolation happens to *mask* the escalation direction on a machine whose own `config.toml` defaults to something permissive, because Codex's own built-in `exec` default (with no config at all) is `read-only`. That's not something to rely on: it depends on a Codex default staying put, it disappears the moment `--inherit-config` is used, and it actively breaks legitimate `workspace-write` work in the downgrade direction. The property actually worth having is **stability of a run's settings across turns** — anti-escalation is one consequence of that, not the whole of it.

This was independently re-confirmed against the real Codex CLI (not just a test fixture): a `read-only` thread's `turn_context` read `['read-only', 'read-only']` across both turns when resumed through this plugin, and the resume argv it recorded genuinely contained `sandbox_mode="read-only"`.

## 3. The Cost of Inheriting Config

Isolation (`--ignore-user-config`) is this plugin's default in part *because* inherited config is what re-enables the escalation direction above — but it has a second, independent justification: cost. Measured on the same trivial prompt (`Reply with exactly: OK`), same machine, twice, two weeks apart:

| When | Mode | Input tokens | `error` events |
|---|---|---:|---:|
| design | `--inherit-config` | 46,238 | 24 (plus a plugin advertisement inside the agent's own message) |
| design | `--ignore-user-config` | 15,863 | 0 |
| two weeks later | `--inherit-config` | 17,327 | 8 |
| two weeks later | `--ignore-user-config` | 15,837 | 0 |

Two different things are in that table, and only one is a property you can rely on. **Stable:** the isolated floor (~15.8k tokens, moved by only 26 across two weeks) and the clean stream (0 error events, every time) — that floor is Codex's own base instructions and tool definitions, and isn't removable. **Not stable:** the *ratio* — it moved from 2.92× to 1.09× on the same machine with no deliberate config change, because the inherited cost is whatever the user's config actually loads at that moment, and something as small as one MCP server failing to start changes it. Don't budget from a specific ratio, including this one — if the cost of inheriting matters to a real decision, measure it directly by comparing `turn.completed.usage.input_tokens` both ways.

`--inherit-config` remains available for the one legitimate reason to use it: the run needs a tool that only exists in the user's own config (a specific MCP server, a custom agent role). "To be safe" is not a reason — inheriting is what turns the sandbox fallback back on.

## 4. How the Fix Works

Every setting a run is created with — sandbox mode, model, reasoning effort, isolation, working directory — is written to that run's `meta.json` in the [run registry](Concepts.md#5-the-run-registry) the moment it starts, and re-read and re-injected as explicit `-c` flags on every subsequent `resume` or `review` call against that thread. Nothing is left to whatever the ambient config happens to be at call time. See [Architecture § request flow](Architecture.md#2-request-flow) for exactly where this happens in the code path.

An explicit, deliberate sandbox change on a `resume` call (passing a different `--sandbox` than the thread was created with) is not treated as drift — it's recorded in the registry as `sandbox_changed_from`, and surfaced in `status`, so an intentional change is distinguishable from an accidental one.

## 5. Verifying What a Turn Actually Ran Under

Codex's rollout file (`$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ISO8601>-<thread_id>.jsonl`) appends one `turn_context` line per turn — the authoritative, structured record of what that specific turn ran under:

```json
{"type":"turn_context","payload":{"turn_id":"…","cwd":"…","workspace_roots":["…"],
 "approval_policy":"never","sandbox_policy":{"type":"read-only"},
 "permission_profile":{…},"model":"gpt-5.6-sol",
 "collaboration_mode":{"settings":{"reasoning_effort":null}}}}
```

This is a far more reliable check than grepping the agent's own `<permissions instructions>` developer message — it's one line per turn, machine-readable, and it's what the integration tests use to confirm the fix holds against the real CLI, not just a test fixture.

---
**Next:** [Context Discipline & Event Log Levels](Context-Discipline.md) · [Testing](Testing.md)
[Back to index](README.md)
