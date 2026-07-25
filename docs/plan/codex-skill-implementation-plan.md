# Implementation Plan — `codex` skill (Codex as a managed subagent for Claude Code)

**Status:** approved, ready to implement. Written 2026-07-25 in a planning-only session.
**Audience:** the next Claude session, which will implement this from scratch.
**Companion file:** `.claude/harness-spec.md` (the spec `audit_harness.py` / `validate_harness.py` diff against). This plan is the *reasoning*; the spec is the *contract*. Keep both in sync.

---

## 0. Read this first

Before generating anything, load these harness-creator references — they are the authoring doctrine this plan assumes and does not repeat:

- `~/.claude/skills/harness-creator/references/skills.md` — before writing SKILL.md or any `references/*.md`
- `~/.claude/skills/harness-creator/references/hooks.md` and `hooks-events.md` — before writing the `SessionEnd` hook
- `~/.claude/skills/harness-creator/references/e2e-testing.md` — before the T4 tier
- `~/.claude/skills/harness-creator/references/claude-md-and-rules.md` — only if a CLAUDE.md ends up being added (not currently planned)

Two doctrines from those files govern everything below, and both were reaffirmed explicitly by the user during the interview:

1. **Conviction over compliance.** Every instruction written into the skill gets a *why* strong enough that the model can re-derive it for a case nobody enumerated. A number without its reason is a rail wearing a digit.
2. **No use-case rails.** The user's exact words: *"클로드가 코덱스를 다양한 목적으로 사용할 수 있겠지. 근데 그 사용목적을 일일이 스킬에 명시할 필요는 없을거 같아. 이건 일종의 레일이니까."* The skill teaches **mechanism + gotchas + judgment criteria**, never a menu of blessed use cases. When you catch yourself writing "Use this skill when the user wants to refactor…", delete it and write the capability instead.

---

## 1. What is being built

A Claude Code **plugin** whose single skill lets Claude drive the OpenAI Codex CLI as a managed subagent:

- **start** Codex work (background by default) and get a run handle back immediately
- **watch** its live event log at a controlled level of detail, incrementally
- **intervene** by stopping a run and resuming the same Codex thread with corrective instructions
- **resume** any prior Codex thread, including ones created outside this skill
- **collect** results, optionally as schema-validated JSON
- **diagnose** the Codex environment when something is wrong

The deliverable is *not* a thin CLI wrapper. It is the orchestration + safety + context-discipline layer that makes an external agent usable from inside Claude Code without wrecking the session's context or the user's filesystem.

### Explicitly out of v1 scope

Record these in `references/troubleshooting.md` (or a short "Out of scope" section of SKILL.md) so a future reader knows they were considered, not overlooked:

- `codex cloud` (remote cloud tasks) — experimental, large surface
- `codex mcp-server` / `codex app-server` (Codex as an MCP/protocol server) — experimental, "may change without notice" per official docs
- **True mid-turn steering.** There is no CLI channel to inject a message into an in-flight `codex exec` turn. The interactive TUI can (Enter injects into the current turn) but needs a TTY. v1's intervention model is stop → resume, which is what the user approved. Note the app-server path in the reference as an unexplored future option, flagged as unverified.

---

## 2. Approved decisions (from the interview — do not re-litigate)

| # | Decision | Value |
|---|---|---|
| D1 | Intervention model | Stop the process, then `resume` the same thread with a corrective prompt. Not mid-turn injection. |
| D2 | Codex config posture | **Isolated by default** (`--ignore-user-config`); `--inherit-config` opts back in per run. |
| D3 | Default filesystem sandbox | `workspace-write` |
| D4 | Layers to build | skill + scripts, **plus** a `SessionEnd` orphan-cleanup hook, **plus** pre-approved tool permissions (delivered via skill `allowed-tools`, see §5.5) |
| D5 | Script language | Python 3, standard library only. No `jq` dependency. |
| D6 | Skill documentation language | **English** for SKILL.md and `references/`; Korean trigger keywords included in `description`. Repo README in Korean. |
| D7 | Log verbosity | Compact summary by default; deep detail only on explicit request. **Never** let file contents or full command stdout flow into Claude's context by default. Default level is chosen by measurement (T3), not by guess. |
| D8 | Run registry location | `<project>/.codex-runs/`, made self-ignoring via `.codex-runs/.gitignore` containing `*`. Never edit the user's own `.gitignore`. |
| D9 | Distribution | Claude Code **plugin** (self-marketplace in this repo), plus a dev symlink for local iteration. |
| D10 | Instruction-injection presets | **Dropped entirely.** No `Prompts/` library, no `<SystemPrompt>` wrapping. Claude writes whatever Codex needs into the prompt itself. |
| D11 | Naming | plugin `codex`, skill `codex`, skill dir `.claude/skills/codex/` |
| D12 | v1 feature scope | includes `--output-schema` structured returns, a `review` path over `codex exec review`, and image attachment (`-i`) |
| D13 | Testing | all four tiers (T1–T4, §7). User: *"목적을 달성하는데 필요한 모든 테스트를 해야해."* |
| D14 | Git flow | feature branch → PR → merge to `main` → tag `v0.1.0` → GitHub release |
| D15 | Session-end policy | Kill this session's running background runs; `--detach` exempts a run. |
| D16 | Default run mode | **Background.** `--foreground` opts out. |
| D17 | Auto-preamble | A minimal *situational facts* preamble only (non-interactive, single turn, nobody to ask). No methodology. `--no-preamble` disables. |
| D18 | `service_tier` | Re-inject `-c service_tier="priority"` under isolation, since isolation would otherwise silently drop the user's priority tier. |
| D19 | Reasoning effort | Do **not** set by default. Inherit Codex's own built-in default so the skill doesn't go stale as Codex versions change. `--effort` overrides. |
| D20 | Background run timeout | No hard timeout. Implement **stall detection** (idle-since-last-event) and surface it in `status`; let Claude judge. |

---

## 3. Verified environment findings

Everything in this section was **measured on this machine** during the planning session against `codex-cli 0.144.1` and Claude Code 2.1.220. Treat it as ground truth, but re-run §6's checks before relying on any of it — Codex ships fast.

### 3.1 CRITICAL — resume silently escalates the sandbox

A session created with `codex exec -s read-only` was resumed with `codex exec resume <id>` and the second turn ran with **`danger-full-access`**, then successfully created a file the original policy forbade.

Evidence, from the rollout file's injected `<permissions instructions>` developer messages:

| Turn | Command | Injected policy | Result |
|---|---|---|---|
| 1 | `codex exec --json -s read-only …` | ``sandbox_mode`` is `read-only` | read only |
| 2 | `codex exec resume <id> --json …` | ``sandbox_mode`` is **`danger-full-access`** | **wrote `b.txt`** |

Root cause: `codex exec resume` has **no `-s/--sandbox` flag**, so it falls back to `config.toml`'s `sandbox_mode`, which on this machine is `danger-full-access`. The legacy skill has this hole wide open.

**Design consequence (non-negotiable):** the wrapper records the sandbox mode at run creation and re-asserts it on every subsequent invocation via `-c sandbox_mode="<mode>"`. This is why a run registry is mandatory rather than a convenience. T1 carries a dedicated regression test for it; T2 re-verifies it against the real CLI.

### 3.2 `CODEX_HOME` is overridden on this machine

`CODEX_HOME=/Users/seongjin/Library/Application Support/orca/codex-runtime-home/home` (set by Orca). Sessions, config, and auth all live there — `~/.codex` is **not** the effective home. The legacy skill's instruction to read `~/.codex/sessions` is already wrong here.

**Design consequence:** never hardcode `~/.codex`. Resolve `${CODEX_HOME:-$HOME/.codex}` everywhere, and have `doctor` print the resolved value.

### 3.3 Isolation is worth ~66% of input tokens

| Mode | Prompt | Input tokens | Noise |
|---|---|---|---|
| Inherit user config | "Read a.txt and reply with its contents in one word." | **46,238** | 24 `item.completed`/`error` events for duplicate agent-role definitions; an unrelated "LazyCodex 4.19.1 is installing…" sentence inside the agent's own message |
| `--ignore-user-config` | "Reply with exactly: OK" | **15,863** | none — a clean 4-line event stream |

The ~15.8k floor is Codex's own base instructions and tool definitions; it is not removable. The delta is the user's plugins, MCP servers, agent roles, and hooks. Auth still works under `--ignore-user-config` (documented, and confirmed: exit 0).

### 3.4 Resume replays the whole thread

A three-word resume turn cost **31,743 input tokens** (28,160 cached). Resume is not free and gets more expensive as a thread grows.

**Design consequence:** SKILL.md must state this as a judgment input — a fresh thread is sometimes cheaper than resuming a long one, and Claude should decide deliberately rather than resuming reflexively. Do not turn this into a rule with a threshold; give the model the cost model and let it judge.

### 3.5 `codex exec --json` event stream (0.144.1)

```jsonl
{"type":"thread.started","thread_id":"019f9930-…"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"item_25","type":"command_execution","command":"…","aggregated_output":"","exit_code":null,"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_25","type":"command_execution","command":"/bin/zsh -lc \"…\"","aggregated_output":"…FULL STDOUT…","exit_code":0,"status":"completed"}}
{"type":"item.completed","item":{"id":"item_26","type":"agent_message","text":"…"}}
{"type":"item.completed","item":{"id":"item_25","type":"file_change","changes":[{"path":"/abs/path/b.txt","kind":"add"}],"status":"completed"}}
{"type":"item.completed","item":{"id":"item_0","type":"error","message":"…"}}
{"type":"turn.completed","usage":{"input_tokens":46238,"cached_input_tokens":22272,"output_tokens":179,"reasoning_output_tokens":0}}
```

Observed facts that matter:

- `thread.started` is the **first** line and carries the thread id — including on `resume`, where it repeats the *same* id.
- `file_change` events carry **paths and kind only, never file contents**. The context risk is `command_execution.aggregated_output`, which contains full stdout (including whole file bodies when Codex `cat`s something).
- **`item.id` restarts at `item_0` on every invocation.** It is per-invocation, not per-thread. Key items by `(run_id, item_id)`; never treat an item id as thread-unique.
- Commands are wrapped: `/bin/zsh -lc "…"`. Strip the wrapper for display (the legacy `strip_wrapper` logic is worth porting).
- `error` items are informational config warnings, not fatal.

### 3.6 Rollout files and the thread database

- Rollout: `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ISO8601>-<thread_id>.jsonl`, written live. Different schema from the stdout stream: `{"timestamp", "type": "session_meta"|"event_msg"|"response_item"|"turn_context"|"world_state", "payload": {...}}`. **`codex exec resume` appends to the same rollout file** — confirmed.
- `$CODEX_HOME/state_5.sqlite` has a `threads` table with `id, rollout_path, cwd, title, source ('exec'|'cli'|subagent JSON), model, reasoning_effort, sandbox_policy, approval_mode, cli_version, updated_at, …`. This is the best source for *"which Codex threads exist for this project, including ones I didn't start"*.
- `$CODEX_HOME/session_index.jsonl` maps `{id, thread_name, updated_at}` — and `codex exec resume` accepts a **thread name** as well as a UUID.

**Design consequence:** the sqlite filename is version-stamped (`state_5`), so its schema *will* change. Query it defensively — introspect `PRAGMA table_info(threads)`, select only columns that exist, and fall back to globbing rollout files if the table or DB is missing. Never let a Codex upgrade break the skill outright.

### 3.7 `${CLAUDE_SKILL_DIR}` does not exist in the Bash environment

Checked directly: `CLAUDE_SKILL_DIR` and `CLAUDE_PROJECT_DIR` are both **unset** in the Bash tool's environment, even while a skill is active. The legacy skill's `"${CLAUDE_SKILL_DIR}/Scripts/run-codex.sh"` therefore expands to `/Scripts/run-codex.sh` — every script invocation in it is broken.

`${CLAUDE_PLUGIN_ROOT}` is the documented plugin convention and is used in production by the official `claude-security` plugin, in both a skill's `allowed-tools` frontmatter and its body. Whether it is live in the *Bash tool's* environment for a plugin-installed skill is **V-01** in §6 — the design must not depend on it being true.

### 3.8 Flag availability is inconsistent across subcommands

| Flag | `exec` | `exec resume` | `exec review` |
|---|---|---|---|
| `-s/--sandbox` | ✅ | ❌ | ❌ |
| `-C/--cd` | ✅ | ❌ | ❌ |
| `--add-dir` | ✅ | ❌ | ❌ |
| `-i/--image` | ✅ | ✅ | ❌ |
| `-m/--model` | ✅ | ✅ | ✅ |
| `--json`, `-o`, `--output-schema` | ✅ | ✅ | ✅ |
| `--ignore-user-config`, `--ephemeral`, `--skip-git-repo-check` | ✅ | ✅ | ✅ |
| `-c/--config` | ✅ | ✅ | ✅ |

**Design consequences — these two rules unify the whole implementation:**

1. **Sandbox is always expressed as `-c sandbox_mode="<mode>"`, never `-s`.** `-c` is the only mechanism available on all three subcommands, so using it uniformly closes §3.1's escalation hole by construction rather than by remembering to special-case resume. (V-03 confirms `-c` genuinely constrains.)
2. **Working directory is always set on the child process** (`subprocess(cwd=…)`), never via `-C`. Same reason: `-C` doesn't exist on two of the three subcommands.

`--add-dir` remains `exec`-only; document that extra writable roots can't be added to a resumed or review run.

### 3.9 stdin, stderr, and process hygiene

- `codex exec` prints `Reading additional input from stdin...` to **stderr** when stdin is not a TTY. Harmless, but always pass `stdin=DEVNULL` to avoid any chance of a block, and never treat stderr content as failure.
- **Never `2>/dev/null`.** The legacy script does, which hides auth failures and crashes. Capture stderr to `stderr.log` per run and surface it in `status` / `doctor`.
- The legacy `--cancel` uses `pgrep -f "codex exec"` and kills **every** codex process. That is a direct conflict with parallel runs. Stop must target a recorded PID/process group for one run; `--all-mine` (this Claude session's runs) must be an explicit opt-in.

### 3.10 Effective Codex config on this machine (for context)

`model = "gpt-5.6-sol"`, `model_reasoning_effort = "high"`, `service_tier = "priority"`, `approval_policy = "never"`, `sandbox_mode = "danger-full-access"`, plus the `omo@sisyphuslabs` (LazyCodex) plugin with many lifecycle hooks, several MCP servers, and duplicate agent-role definitions.

Under `--ignore-user-config` the run still selected `gpt-5.6-sol` (Codex's own built-in default) and `approval_mode` `never`, which is why D19 says not to pin a model or effort.

---

## 4. Repository and plugin layout

```
codex in claude/                          # repo root == plugin root
├── .claude-plugin/
│   ├── plugin.json                       # name: codex, skills: ["./.claude/skills/"]
│   └── marketplace.json                  # self-marketplace, plugins[0].source: "./"
├── .claude/
│   ├── harness-spec.md                   # the contract; audit/validate diff against this
│   └── skills/
│       └── codex/
│           ├── SKILL.md
│           ├── references/
│           │   ├── environment.md
│           │   ├── event-stream.md
│           │   └── troubleshooting.md
│           └── scripts/
│               └── codex_bridge.py       # the single CLI
├── hooks/
│   ├── hooks.json                        # SessionEnd registration
│   └── codex_session_cleanup.py
├── tests/
│   ├── fake_codex/codex                  # executable shim placed first on PATH
│   ├── fixtures/*.jsonl                  # recorded real event streams
│   ├── test_*.py                         # T1 unit tests (stdlib unittest)
│   └── integration/                      # T2 scripts (real Codex, opt-in via env flag)
├── docs/
│   ├── plan/codex-skill-implementation-plan.md   # this file
│   └── measurements/filter-calibration.md        # T3 output
├── README.md                             # Korean
├── CHANGELOG.md
└── LICENSE
```

Mirror `skills-for-repo-wiki`, which the user already ships this way: `.claude-plugin/{plugin.json,marketplace.json}` at repo root, skill under `.claude/skills/<name>/`, installed into `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.

**Script path resolution** must work in both installation modes. Canonical expression, used verbatim in SKILL.md:

```bash
CODEX_SKILL="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/.claude/skills/codex}"
CODEX_SKILL="${CODEX_SKILL:-$HOME/.claude/skills/codex}"
python3 "$CODEX_SKILL/scripts/codex_bridge.py" …
```

If V-01 shows `CLAUDE_PLUGIN_ROOT` is not in the Bash environment, the fallback branch already covers the symlink install, and `doctor` prints the resolved path so a broken resolution is diagnosable in one command instead of being a mystery.

---

## 5. Component design

### 5.1 `scripts/codex_bridge.py` — the single CLI

Python 3.10+, stdlib only. One script with subcommands so a single `allowed-tools` entry covers everything. Every subcommand emits **one line of JSON** on stdout except `log`, which emits compact text (JSON framing per event would itself be a meaningful fraction of the context cost).

Global options: `--runs-dir <dir>` (default: git toplevel of cwd, else cwd, + `/.codex-runs`), `--project <dir>`.

#### `start`

Creates a new Codex thread.

| Option | Default | Notes |
|---|---|---|
| prompt (positional) / `--prompt-file` / `-` | required | |
| `--label <slug>` | none | human-readable component of the run id |
| `--cwd <dir>` | current project dir | applied as the child's cwd (§3.8) |
| `--add-dir <dir>` (repeatable) | none | `exec`-only |
| `--sandbox {read-only,workspace-write,danger-full-access}` | `workspace-write` | emitted as `-c sandbox_mode=` |
| `--model <m>` | unset | |
| `--effort <e>` | unset (D19) | `-c model_reasoning_effort=` |
| `--inherit-config` | off | off ⇒ `--ignore-user-config` |
| `--priority / --no-priority` | on when isolated | `-c service_tier="priority"` |
| `--schema <file>` | none | `--output-schema` |
| `--image <f>` (repeatable) | none | `-i` |
| `--foreground` | off (D16) | with `--timeout <sec>` |
| `--detach` | off | exempt from `SessionEnd` cleanup |
| `--config k=v` (repeatable) | none | raw `-c` passthrough escape hatch |
| `--no-preamble` | off | |

Behavior: build argv, spawn in its own **process group** (`start_new_session=True`) with `stdin=DEVNULL`, stream stdout to `<run>/events.jsonl` and stderr to `<run>/stderr.log`, write `<run>/meta.json`, then wait up to ~15 s for the `thread.started` line to capture `thread_id` (it is the first line and arrives fast). Return `{"run_id","thread_id","state","events","project"}`. If the thread id hasn't appeared in time, return it as `null` — `status` backfills it later. Never block the caller past that window in background mode.

#### `resume`

`resume <run_id|thread_id|thread_name> | --last` plus a prompt.

Re-applies the **recorded** sandbox, model, effort, priority, isolation flag, and cwd from the original run's `meta.json`. This is the §3.1 fix. Changing the sandbox on resume requires an explicit `--sandbox`, and the change is recorded — it must never happen silently in either direction.

Creates a **new run_id** pointing at the **same thread_id**, so each turn gets its own event log while the thread stays linked. `status` groups runs by thread.

`--last` resolves to the most recent run in this project's registry; if the registry is empty, fall back to the `threads` table filtered by `cwd` (this is what lets Claude continue a session the user started in the Codex TUI).

#### `status`

`[--run <id>] [--thread <id>] [--all] [--include-external]`

Per run: `run_id, thread_id, label, state, pid, started_at, elapsed, idle_seconds, tokens, sandbox, model, isolated, detached, last_agent_message (truncated), stderr_tail (only if non-empty)`.

States: `running | completed | failed | interrupted | stalled | orphaned`.

**Stall detection (D20):** `idle_seconds` = now − mtime of the last event line. Report it; never auto-kill. SKILL.md tells Claude that a run producing no events for a long time is a judgment call, with the reasoning (a long single `command_execution` is legitimately silent, so silence alone is not failure — but silence plus no in-progress item is).

`--include-external` merges rows from the `threads` table whose `cwd` matches the project but which have no registry entry.

#### `log`

`--run <id> [--since <cursor>] [--level {compact,normal,full}] [--follow]`

Emits filtered text lines, then a final `# cursor=<n>` line so the next poll is incremental. Levels are specified in §5.3.

`--follow` streams as events arrive and is the intended pairing with the **Monitor** tool (each stdout line becomes a notification). Per Monitor's own doctrine, `--follow` must also emit terminal-state lines — completion, failure, and non-zero exits — so that silence never looks like success. Without that, a crashed Codex run and a working one produce identical output: nothing.

#### `show`

`--run <id> --item <item_id> [--max-bytes N]`

The escape hatch: full `aggregated_output` for one `command_execution`, or the full change list for one `file_change`. This is the *only* way full command output reaches Claude, and it is always an explicit, per-item request. Truncate at `--max-bytes` (default ~20 000) with an explicit truncation notice — a silently truncated blob is worse than a loud one.

#### `stop`

`--run <id>` or `--all-mine` (this Claude session only; must be typed explicitly). Sends SIGINT to the process group first so Codex can flush its rollout and stay resumable, then SIGTERM after a short grace, then SIGKILL. Marks the run `interrupted`. **Never** matches processes by name.

#### `result`

`--run <id>` → final agent message (from the `-o` file), token usage, exit code, and — when `--schema` was used — the parsed JSON object. Fail loudly if the output doesn't validate against the schema rather than handing Claude something malformed.

#### `review`

Wraps `codex exec review`. Exactly one of `--uncommitted | --base <ref> | --commit <sha> | --prompt <text>` (the CLI rejects combinations). `--title` is only valid with `--commit`. Same registry, background, and filtering semantics as `start`; no `-i`, no `--add-dir`, cwd set on the child.

Frame this in SKILL.md as *a different CLI surface with different flags*, not as a blessed use case (D-rails). The reason it exists as a subcommand is that `codex exec review` takes arguments `exec` does not — not that "reviewing is what you should use Codex for".

#### `doctor`

Prints and exits non-zero on any blocker: `codex` on PATH + version; resolved `CODEX_HOME`; `codex login status`; effective `config.toml` `sandbox_mode`/`approval_policy` **with a warning when it is `danger-full-access`** (explaining that this is why the wrapper always passes `-c sandbox_mode=`); resolved skill dir and whether `CLAUDE_PLUGIN_ROOT` was set; runs dir and its writability; Python version; count of config-error events under inherit mode. This is the single command SKILL.md points at for "something is wrong".

### 5.2 Run registry — `<project>/.codex-runs/`

```
.codex-runs/
├── .gitignore                 # contains exactly:  *
└── <run_id>/
    ├── meta.json
    ├── events.jsonl           # raw codex --json stdout, durable source of truth
    ├── stderr.log
    └── last-message.txt       # from -o
```

`run_id` = `<YYYYmmdd-HHMMSS>-<label-or-"run">-<4 hex>` — sortable, human-readable, collision-free under parallel starts.

`meta.json` fields: `run_id, thread_id, parent_run_id, label, prompt_preview, cwd, project, sandbox, model, effort, isolated, priority, schema_path, images, argv, pid, pgid, claude_session_id, detached, started_at, ended_at, exit_code, state`.

`claude_session_id` comes from `CLAUDE_CODE_SESSION_ID` and is what lets the `SessionEnd` hook kill only its own session's runs.

The `.gitignore` containing `*` makes the directory self-ignoring — no edit to the user's own `.gitignore`, and no chance of it landing in a commit by accident (D8).

### 5.3 Event filter levels

These are **candidates**; the default is decided by the T3 measurement (§7.3), not here. Whatever wins, `references/event-stream.md` must carry the measured table next to the choice so a future reader can see the reasoning, not just the verdict.

| Level | Includes | Excludes |
|---|---|---|
| `compact` | thread/turn lifecycle, agent messages (full), command line + exit code, changed file paths + kind, errors, token usage | all `aggregated_output`, all file contents |
| `normal` | compact + head/tail of output **for non-zero-exit commands only** | successful commands' output |
| `full` | every event with per-item output capped | nothing structural, but still capped |
| `raw` | pass-through | — |

The load-bearing principle, and the user's own framing: `file_change` events already carry only paths, so **the entire context risk is `command_execution.aggregated_output`** — that is where a `cat` of a 2 000-line file lands. Failed commands are the case where the output is what Claude actually needs, which is why `normal` splits on exit code rather than on size. Write that reasoning into the reference; a level table without it is a rail.

### 5.4 `SessionEnd` cleanup hook

`hooks/hooks.json` registering `hooks/codex_session_cleanup.py` on `SessionEnd`.

**The binding constraint is a 1.5 second default timeout** — the shortest of any hook event by nearly two orders of magnitude. The hook must therefore be structured to do nothing expensive:

1. Resolve the project dir from the hook input's `cwd` (V-05). If `<project>/.codex-runs` doesn't exist, `exit 0` immediately — this is the common case for every project that never uses Codex, and it must cost effectively nothing.
2. Read `meta.json` files; select `state == running AND claude_session_id == $CLAUDE_CODE_SESSION_ID AND NOT detached`.
3. Signal each process group (SIGINT, then SIGTERM) and record the outcome in `meta.json`. **Do not wait for exit** — signal and return.

`SessionEnd` fires on `/clear` and `/resume` as well as real termination. The user chose the simple policy deliberately (D15): kill everything not `--detach`ed. The reasoning to write into the hook and the skill: a background Codex run that nobody is watching keeps writing to the repo and burning tokens, and that is the worse failure than losing a run that can be resumed from its rollout anyway.

The hook is not "done" until `test_hook.py` passes against it (harness-creator hard line #2).

### 5.5 Permissions

Deliver via SKILL.md `allowed-tools`, following the official `claude-security` plugin's pattern:

```yaml
allowed-tools:
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/.claude/skills/codex/scripts/codex_bridge.py" *)
```

This travels with the plugin and never touches the user's `settings.json` — strictly better than the `permissions.allow` entry the user asked for, and it satisfies the same requirement (D4). Also document the `settings.json` equivalent in the README for people installing by symlink, where `CLAUDE_PLUGIN_ROOT` won't be set.

Without this, every start / poll / stop raises an approval prompt, which makes "leave it running in the background and go do something else" unusable in practice.

### 5.6 SKILL.md

**Frontmatter.** `name: codex`. The `description` is the only trigger signal — the body cannot influence triggering because it loads only after the trigger decision is already made. Write it to lean toward firing (current models under-trigger, and a skill that stays dark costs the entire skill), name the *intent* not just the keyword, include Korean triggers, and state the near-misses so it doesn't steal from neighbors. Working draft:

> Run OpenAI Codex (GPT) as a managed subagent from Claude Code — start work in the background, watch its live log, interrupt and redirect it, resume earlier Codex threads, and collect results as text or schema-validated JSON. Use whenever work should be handed to Codex or GPT, when a second independent model should check something, when an external agent needs to keep running while Claude does other work, or when a previous Codex session needs continuing. Also covers Codex CLI setup, auth, and sandbox diagnosis. Triggers: codex, 코덱스, GPT, 코덱스로, GPT에게 시켜, delegate to codex, resume codex. Not for Claude's own subagents or the Task tool, and not for Codex Cloud or Codex-as-MCP-server.

**Body contents** — everything every invocation needs, and nothing else:

1. The path-resolution snippet (§4) and the CLI surface table.
2. The core loop: start → poll `log --since` → judge → (`stop` + `resume` with correction) → `result`.
3. **Context discipline**, stated as a principle with its reason: Codex's command output can contain whole file bodies, so the default log level never carries it; use `show --item` when a specific command's output actually matters. A model that understands *why* will also get the cases this sentence doesn't enumerate.
4. The gotchas that cannot be derived from general competence (§5.7).
5. Background/parallel patterns, including the `log --follow` + Monitor pairing.
6. Structured output: when a schema is worth writing and what `result` returns.
7. Judgment inputs, not rules: resume cost grows with thread length (§3.4); isolation costs the user's MCP/plugin tools but saves ~66% of input tokens (§3.3); silence is not necessarily failure (§5.1).

**What must not be in the body:** a list of tasks Codex is good at, a methodology for delegation, or anything a capable model already knows about working with a CLI. D10 and the no-rails principle apply to SKILL.md most of all.

### 5.7 The gotchas (the skill's actual reason to exist)

These are the domain traps that are only learnable by being burned. They belong in SKILL.md or the reference that owns them, each with its reason:

1. **`resume` and `review` have no `-s` flag**, so sandbox must travel as `-c sandbox_mode=` — otherwise a read-only session escalates to whatever the user's config says (§3.1, measured).
2. **`CODEX_HOME` may be overridden**; `~/.codex` is not reliably the Codex home (§3.2, true on this machine right now).
3. **`item.id` restarts per invocation**, so it is not a thread-wide key (§3.5).
4. **`file_change` gives paths only; `command_execution.aggregated_output` is the context bomb** (§5.3).
5. **`resume` replays the whole thread**, so its cost scales with thread length (§3.4).
6. **`${CLAUDE_SKILL_DIR}` doesn't exist**; use the §4 resolution (§3.7).
7. **stderr is normal output, not failure** — Codex writes `Reading additional input from stdin...` there routinely (§3.9).
8. **Killing by process name kills other people's runs** (§3.9).

### 5.8 References split

Three files, split by the branch the model actually takes — not by volume:

| File | Opened when | Contents |
|---|---|---|
| `environment.md` | An environment question or `doctor` failure | `CODEX_HOME` resolution, isolation vs inherit with the measured numbers, auth, sandbox semantics and the full escalation story, `service_tier`, how to read `doctor` output |
| `event-stream.md` | Claude needs to reason about raw events or tune detail | Both event schemas (stdout API and rollout), the filter levels with the T3 measured table, cursor/polling, Monitor pairing, `show` |
| `troubleshooting.md` | Something is broken | Symptom → cause → fix, plus the out-of-scope list |

Launch, watch, interrupt, resume, and collect stay in SKILL.md because a single invocation needs them *together* — splitting them would create a routing decision with no payoff, which is the exact failure mode `skills.md` warns about. If SKILL.md ends up long, cut content rather than splitting for length.

---

## 6. Verification items — do these FIRST

Each can invalidate part of the design, so run them before writing much code. Record every outcome in `.claude/harness-spec.md`'s Validation section.

| ID | Question | How to check | If it fails |
|---|---|---|---|
| V-01 | Is `CLAUDE_PLUGIN_ROOT` in the **Bash tool's** environment for a plugin-installed skill? | Install this repo locally (`/plugin marketplace add ./`), start a fresh session, invoke the skill, run `echo "$CLAUDE_PLUGIN_ROOT"` | Fallback branch in §4 already covers it; make `doctor` print the resolved path and document the symlink install as primary |
| V-02 | Is `-c service_tier="priority"` accepted under `--ignore-user-config`, and honored by the account? | Run twice with and without; compare wall-clock and check for a config error event | Drop D18, note it in the reference |
| V-03 | Does `-c sandbox_mode=` actually constrain a `resume` / `review` run? | Resume with `-c sandbox_mode="read-only"`, then read the rollout's `<permissions instructions>` developer message for that turn; also attempt a write and confirm refusal | **Blocker.** Escalate: consider always starting a fresh thread instead of resuming when the sandbox must be tightened |
| V-04 | Is `-c model_reasoning_effort=` accepted on `resume`? | Same technique, check `threads.reasoning_effort` | Document that effort is fixed at thread creation |
| V-05 | What does the `SessionEnd` hook input carry — is `cwd` there? | `test_hook.py --event SessionEnd`, inspect the payload | Fall back to `CLAUDE_PROJECT_DIR`, then to the hook's own cwd |
| V-06 | Does `--ignore-user-config` also suppress project `AGENTS.md` and project `.codex/hooks.json`? | Create a scratch repo with a distinctive `AGENTS.md`, run isolated, check the rollout for its text | If `AGENTS.md` still loads, say so in the reference — it is a *useful* channel for Claude to brief Codex, and materially changes what the preamble needs to say |
| V-07 | How is a plugin skill invoked — `/codex` or `/codex:codex`? | Install and check the `/` menu | Cosmetic; record the real answer in the README |
| V-08 | Does SIGINT leave the thread cleanly resumable? | Start a long run, SIGINT mid-turn, resume, confirm the rollout appended and context survived | Escalate the signal ladder, or document that interruption loses the partial turn |
| V-09 | Does headless `claude -p` authenticate when spawned from Bash? | One `run_e2e.py` scenario | Documented open risk in `e2e-testing.md`; if it fails, T4 becomes manual interactive dogfooding and must be reported as such, not quietly skipped |
| V-10 | Does `codex exec review` behave under `--ignore-user-config` in a repo with no changes? | `review --uncommitted` on a clean tree | Handle the empty case explicitly rather than surfacing a confusing error |

---

## 7. Test plan

All four tiers (D13). Tiers 1 and 3 are where the real quality safety-net lives; tiers 2 and 4 cost real tokens.

### 7.1 T1 — unit tests against a fake `codex` (free, deterministic, repeatable)

`tests/fake_codex/codex` is an executable shim placed first on `PATH`. It records the argv it received and replays a fixture JSONL stream (captured from real runs) at a controllable pace. This makes every behavior below testable at zero token cost — which is precisely why it is the primary safety net rather than an afterthought.

Cases:

- **argv matrix**: start/resume/review × isolated/inherit × each sandbox × model/effort/priority/schema/image/add-dir. Assert exact flag composition.
- **§3.1 regression (the most important test in the suite)**: start with `read-only`, resume, assert the resume argv contains `-c sandbox_mode="read-only"`. Assert an explicit `--sandbox` on resume both changes it *and* records the change.
- **no `-s` / no `-C` ever emitted** for `resume` and `review` (§3.8).
- registry: creation, `.gitignore` content is exactly `*`, two concurrent starts get distinct run ids and don't interleave writes.
- `stop --run` signals only that run's process group; a second concurrent run keeps running. `stop` never uses name matching.
- filter levels: given a fixture containing a large `aggregated_output` and a `file_change`, assert `compact` output contains **no** `aggregated_output` substring; assert `normal` includes output for a non-zero exit and excludes it for a zero exit.
- `log --since` is exact: no duplicated and no skipped lines across consecutive polls; the emitted cursor round-trips.
- `show --item` returns full output and reports truncation loudly at the byte cap.
- unicode: run the whole flow in a project path containing Korean characters **and** a space, on APFS (NFD vs NFC). The legacy script needed explicit normalization for exactly this; assert relative paths render correctly.
- stall detection: fabricate an old last-event mtime, assert `idle_seconds` and the `stalled` state.
- `doctor` under: `codex` absent from PATH, `codex login status` non-zero, `CODEX_HOME` overridden, runs dir unwritable.
- `result` with a schema: valid JSON passes; malformed JSON fails loudly rather than returning garbage.
- hook: instant `exit 0` when no runs dir; kills only same-session, non-detached, running entries (use `sleep` processes, never a real Codex).

### 7.2 T2 — real Codex integration (costs Codex tokens)

Against a scratch git repo, gated behind an env flag so it never runs by accident.

- I1 background start → `thread_id` captured → `events.jsonl` grows → `result` returns the final message
- I2 stop mid-run → `resume` with a correction → **same `thread_id`**, rollout appended
- I3 two parallel runs → `stop` one → the other completes unaffected
- I4 **sandbox regression against the real CLI**: start `read-only`, resume, read the rollout's permissions instruction for the resumed turn, assert `read-only`, assert a write attempt is refused
- I5 `--schema` returns JSON that validates
- I6 `review --uncommitted` on a repo with a real change produces findings
- I7 isolate vs inherit reproduces the §3.3 token delta (assert a large ratio, not exact numbers — Codex config drifts)
- I8 `--image` attaches successfully

### 7.3 T3 — filter calibration (the measurement the user asked for)

The user's framing: *"코덱스가 접근한 파일의 내용을 전부 클로드에게 그대로 돌려주면 컨텍스트가 낭비될 거 같거든. 이건 일종의 트레이드오프겠지. 이 부분에 대해선 실측을 하며 최적의 전략을 세울 필요가 있을거 같아."*

Three representative workloads in a scratch repo, each measured at every filter level:

| Workload | Why it's in the set |
|---|---|
| Read-heavy: "explain this repo's architecture" | Maximizes `aggregated_output` from file reads — the worst case for context bloat |
| Write-heavy: "add a module with tests" | Maximizes `file_change` volume and build/test output |
| Review: `review --uncommitted` | The realistic mixed case |

For each cell record: raw bytes, filtered bytes, approximate tokens (bytes ÷ 4 — **state the approximation explicitly**, there is no local tokenizer), and a qualitative judgment of whether every decision point Claude would need is still visible.

Output goes to `docs/measurements/filter-calibration.md` and the summary table into `references/event-stream.md`. The default level is then chosen **from the table**, with the rule stated next to it. A number in a shipped skill without its measurement is exactly the rail this project is trying to avoid.

### 7.4 T4 — harness e2e (headless Claude sessions; costs Claude + Codex tokens)

Compose the run/grade/report workflow on the spot per `e2e-testing.md` — do not ship a fixed e2e workflow file. Grading requires cited transcript evidence; surface-level compliance is a FAIL.

| ID | Prompt | Expected |
|---|---|---|
| E1 | "이건 코덱스한테 시켜줘: …" | skill triggers; a run starts; `run_id` reported |
| E2 | "GPT한테 이 diff 검토받아줘" | skill triggers; the `review` path is used |
| E3 | **near-miss** "이 함수 좀 리뷰해줘" (no Codex/GPT mention) | skill must **NOT** trigger — the correct evidence is the *absence* of the event |
| E4 | "아까 그 코덱스 세션 이어서 …" | `resume` path with the recorded thread |
| E5 | "코덱스에 긴 작업 맡기고, 그동안 README 정리해줘" | background start, then unrelated work, then a poll |

Carry `e2e-testing.md`'s documented caveat forward to the user before the first real run: headless `-p` permission and auth handling is a reasoned best guess, not a confirmed fact (V-09). Say so plainly; don't let a clean report imply more than it proves.

### 7.5 Structural validation

`python3 ~/.claude/skills/harness-creator/scripts/validate_harness.py --path .` must exit 0 (errors) before the work is called done, and again at wrap-up. `test_hook.py` must pass against the `SessionEnd` hook. Neither is optional, and nothing mechanically checks that `test_hook.py` was actually run — that one rests on you.

---

## 8. Milestones

Ordered so that anything which could invalidate the design happens first.

| M | Work | Done when |
|---|---|---|
| M0 | §6 verification sweep (V-01…V-10) | Every V has a recorded outcome in the spec; blockers resolved |
| M1 | Registry + `start` / `status` / `log` / `stop`, with T1 tests written alongside | Fake-codex tests green; a real background run is visible in `status` |
| M2 | `resume` with sandbox re-injection | The §3.1 regression test passes at both T1 and T2 (I4) |
| M3 | `show` / `result` / `review` / `--schema` / `--image` | T1 covers each; I5, I6, I8 pass |
| M4 | `doctor` | Produces a correct diagnosis for each of the four failure modes in T1 |
| M5 | `SessionEnd` hook + `hooks.json` | `test_hook.py` passes; the no-runs-dir path exits well inside 1.5 s |
| M6 | T3 calibration → choose and document the default level | `docs/measurements/filter-calibration.md` exists; the default is justified by its own table |
| M7 | SKILL.md + three references (load `skills.md` first; re-read the `description` against its near-miss guidance afterward) | `validate_harness.py` clean; description reviewed for over- and under-triggering |
| M8 | Plugin packaging (`plugin.json`, `marketplace.json`), dev symlink, README (Korean), CHANGELOG, LICENSE | Local install works; V-01 and V-07 answered for real |
| M9 | T2 integration + T4 e2e | Results recorded in the spec's Validation section, failures included |
| M10 | PR → merge → `v0.1.0` tag → GitHub release | Release published |

---

## 9. Delivery

Repo: `github.com/tjdwls101010/Codex-in-Claude` (public, currently one commit, no license file).

- Branch `feat/codex-skill`; commits scoped to milestones so the PR is reviewable.
- PR body: the decision table (§2), the measured findings (§3) — the sandbox escalation especially, since it is the clearest justification for the whole design — and the test results.
- Merge to `main`, tag `v0.1.0` (matching `plugin.json`'s `version`), publish a GitHub release with `gh release create`.
- Add `LICENSE` (Apache-2.0, matching the user's `repo-wiki` repo) and a Korean `README.md` covering: what it is, plugin install, symlink dev install, the `settings.json` permissions equivalent for symlink users, and the out-of-scope list.
- Set the repo description and topics while there (it is currently empty).

The `repo-wiki` skill is installed and covers exactly this documentation-and-release shape — use it for M10 rather than hand-rolling the release.

---

## 10. Standing risks

- **Codex ships fast.** 0.144.1 today; flag availability differs per subcommand already (§3.8) and the thread DB filename is version-stamped. Everything version-dependent must degrade to a clear diagnostic from `doctor`, never to a silent wrong behavior.
- **The user's Codex config is unusually heavy** (plugins, MCP servers, agent roles, lifecycle hooks, duplicate role definitions). Isolation is the default for good measured reasons, but `--inherit-config` will be noticeably slower, noisier, and more expensive — say so where the flag is documented, with the numbers.
- **The interview itself can never be e2e-tested** — `AskUserQuestion` doesn't exist in headless or subagent contexts. A clean T4 report validates the *generated skill*, not the process that produced it.
- **`--detach` is a footgun by design.** It exempts a run from cleanup, which is the point, but it means an abandoned run can outlive every session that knows about it. `status --all` must be able to find it, and `doctor` should mention orphans it can see.
