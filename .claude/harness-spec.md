# Harness Spec — Codex-in-Claude

## Context

This repository *is* the harness component it ships: a Claude Code plugin (`codex`) containing a single skill (`codex`) that lets Claude drive the OpenAI Codex CLI as a managed subagent. There is no application code to support — the skill, its Python CLI, and its `SessionEnd` hook are the entire product.

- Language / runtime: Python 3.10+, standard library only (no `jq`, no third-party packages).
- External dependency: `codex-cli` (verified against **0.144.1**), authenticated via `CODEX_HOME`.
- Host: Claude Code 2.1.220.
- Distribution: Claude Code plugin, self-marketplace in this repo; dev install via symlink into `~/.claude/skills/codex`.
- Documentation language: **English** for SKILL.md and `references/`; Korean README; Korean trigger keywords inside the skill `description`.
- User proficiency: high. Comfortable with hooks, plugins, skills, and CLI internals; already ships a plugin (`skills-for-repo-wiki`) using this exact packaging pattern. Interview was conducted in Korean at full technical vocabulary.

Full design reasoning, measurements, and implementation order: `docs/plan/codex-skill-implementation-plan.md`.

## Goals

In the user's own words: *"코덱스를 클로드코드의 자체 integrated된 서브에이전트처럼 활용할 수 있는 스킬을 만들고 싶은거지."*

Concretely, Claude should be able to:

1. Hand work to Codex and get a run handle back immediately.
2. Continue an earlier Codex thread rather than starting cold every time.
3. Watch a Codex run's log live and intervene when it goes wrong.
4. Leave Codex running while Claude does something else.

Two constraints the user stated explicitly, and which shape every component below:

- **No use-case rails.** *"그 사용목적을 일일이 스킬에 명시할 필요는 없을거 같아. 이건 일종의 레일이니까."* The skill teaches mechanism, gotchas, and judgment criteria — never a menu of approved tasks.
- **Context discipline is a first-class requirement.** *"코덱스가 접근한 파일의 내용을 전부 클로드에게 그대로 돌려주면 컨텍스트가 낭비될 거 같거든. 이건 일종의 트레이드오프겠지. 이 부분에 대해선 실측을 하며 최적의 전략을 세울 필요가 있을거 같아."* Filter defaults are to be chosen by measurement, not assumption.

## Behavior inventory

| id | behavior/knowledge/constraint | layer | component | status |
|----|-------------------------------|-------|-----------|--------|
| B1 | Start a Codex thread with explicit, recorded sandbox/model/isolation settings; background by default | skill+script | `codex_bridge.py start` | approved |
| B2 | Resume any Codex thread (own runs, `--last`, or a thread created in the Codex TUI) | skill+script | `codex_bridge.py resume` | approved |
| B3 | A resumed or reviewed run must never silently escalate its filesystem sandbox | skill+script | `codex_bridge.py` (`-c sandbox_mode=` re-injection from the registry) | approved |
| B4 | Read a run's event log incrementally at a controlled detail level | skill+script | `codex_bridge.py log --since --level` | approved |
| B5 | File contents and successful commands' stdout never reach Claude's context by default | skill+script | filter levels; `show --item` as the only escape hatch | approved |
| B6 | Inspect one specific event's full output on demand | skill+script | `codex_bridge.py show` | approved |
| B7 | List runs for this project with state, elapsed, idle, tokens; detect stalls without auto-killing | skill+script | `codex_bridge.py status` | approved |
| B8 | Interrupt exactly one run without touching other concurrent runs | skill+script | `codex_bridge.py stop` (process group, never name matching) | approved |
| B9 | Collect a run's final message, usage, and schema-validated JSON when a schema was supplied | skill+script | `codex_bridge.py result`, `start --schema` | approved |
| B10 | Drive `codex exec review`'s distinct flag surface (`--uncommitted`/`--base`/`--commit`/prompt) | skill+script | `codex_bridge.py review` | approved |
| B11 | Attach images to a Codex prompt | skill+script | `start --image` | approved |
| B12 | Diagnose the Codex environment in one command (PATH, version, `CODEX_HOME`, auth, config sandbox, resolved skill dir, runs dir) | skill+script | `codex_bridge.py doctor` | approved |
| B13 | Run isolated from the user's Codex config by default; opt back in per run | skill+script | `--ignore-user-config` default, `--inherit-config` opt-in | approved |
| B14 | Preserve the user's priority service tier despite isolation | skill+script | `-c service_tier="priority"` | approved |
| B15 | Persist run state (thread id, sandbox, pid, session id) durably across Claude context loss | script | `<project>/.codex-runs/<run_id>/meta.json` | approved |
| B16 | The run registry must never pollute the user's git history or `.gitignore` | script | `.codex-runs/.gitignore` containing `*` | approved |
| B17 | Background Codex runs must not outlive the Claude session that started them, unless deliberately detached | hook | `SessionEnd` → `codex_session_cleanup.py`; `start --detach` exempts | approved |
| B18 | Running the bridge must not raise an approval prompt on every poll | permissions | SKILL.md `allowed-tools` (plugin-portable); `settings.json` equivalent documented for symlink installs | approved |
| B19 | Prepend minimal situational facts to every Codex prompt (non-interactive, single turn, nobody to ask) — facts only, no methodology | script | `start`/`resume` preamble, `--no-preamble` disables | approved |
| B20 | Codex-CLI gotchas that cannot be derived from general competence | skill | SKILL.md gotcha section + `references/` | approved |
| B21 | Live-follow a run so each event becomes a notification, including terminal failure states | skill+script | `log --follow`, paired with the Monitor tool | approved |

## Component specs

### `.claude/skills/codex/scripts/codex_bridge.py`

Single Python 3.10+ stdlib CLI. Subcommands: `start`, `resume`, `status`, `log`, `show`, `stop`, `result`, `review`, `doctor`. All emit one line of JSON except `log`, which emits compact text plus a trailing `# cursor=<n>`.

Two invariants that unify the implementation, both forced by §3.8 of the plan (flag availability differs per subcommand):

- Sandbox is **always** expressed as `-c sandbox_mode="<mode>"`, never `-s`. `-s` does not exist on `resume` or `review`.
- Working directory is **always** set on the child process, never via `-C`. `-C` does not exist on `resume` or `review`.

Defaults: background, `workspace-write`, isolated (`--ignore-user-config`), `service_tier=priority` re-injected, no model pinned, no reasoning effort pinned, no hard timeout.

### `.claude/skills/codex/SKILL.md`

`name: codex`. `description` is the sole trigger signal — written to lean toward firing, naming intent rather than keywords alone, carrying Korean triggers (`코덱스`, `GPT에게 시켜`, …) and explicit near-misses (not Claude's own subagents/Task tool; not Codex Cloud or Codex-as-MCP-server). `allowed-tools` pre-approves the bridge script.

Body holds only what every invocation needs: path resolution, the CLI surface, the core loop (start → poll → judge → stop+resume → result), the context-discipline principle with its reason, the gotchas, background/parallel patterns, structured output, and cost/judgment inputs. No use-case list, no delegation methodology.

### `.claude/skills/codex/references/`

Split by the branch the model takes, not by volume:

- `environment.md` — `CODEX_HOME` resolution, isolation vs inherit with measured numbers, auth, sandbox semantics and the escalation story, `service_tier`, reading `doctor` output.
- `event-stream.md` — both event schemas (stdout API and rollout file), filter levels with the measured calibration table, cursor/polling, Monitor pairing, `show`.
- `troubleshooting.md` — symptom → cause → fix, plus the out-of-scope list.

Launch/watch/interrupt/resume/collect deliberately stay in SKILL.md: a single invocation needs them together, so splitting them would add a routing decision with no payoff.

### `hooks/codex_session_cleanup.py` + `hooks/hooks.json`

`SessionEnd`, **1.5 s default timeout**. Immediate `exit 0` when `<project>/.codex-runs` is absent (the common case in every project that never uses Codex). Otherwise signals the process groups of runs matching `state == running AND claude_session_id == $CLAUDE_CODE_SESSION_ID AND NOT detached` (SIGINT then SIGTERM), records the outcome, and returns without waiting. Fires on `/clear` and `/resume` as well as real termination; the kill-unless-detached policy is deliberate (an unwatched background run keeps writing to the repo and burning tokens, and a killed run is resumable from its rollout).

Not considered generated until `test_hook.py` passes against it.

## Design rationale

**Why a run registry exists at all.** `codex exec resume` has no `-s/--sandbox` flag, so it falls back to `config.toml`'s `sandbox_mode`. Measured on this machine: a thread created `read-only` was resumed at `danger-full-access` and wrote a file its original policy forbade. The only way to hold a sandbox across turns is to remember the mode and re-assert it, which requires durable per-run state. Everything else the registry does (parallel-safe stop, stall detection, session-scoped cleanup) is a bonus on top of that one non-negotiable.

**Why isolation is the default.** Measured: an inherited-config run spent 46,238 input tokens on a one-line task and leaked 24 config-error events plus an unrelated plugin advertisement into the agent's own message; the isolated equivalent spent 15,863 with a clean four-line stream. Rejected alternative: always inherit (fidelity to the user's MCP/plugin setup, but ~3× the input cost on every call). Rejected alternative: a dedicated `CODEX_HOME` profile (cleanest isolation, but it severs continuity with threads created in the Codex TUI, which B2 requires). `--inherit-config` keeps the rejected option available per run.

**Why stop+resume rather than mid-turn steering.** `codex exec` is a single non-interactive turn with no input channel once running. The TUI's Enter-injection needs a TTY that Claude cannot drive. `codex app-server` could in principle support real steering but is documented as subject to change without notice. Stop+resume was chosen with that tradeoff stated; the app-server path is recorded as unexplored, not as impossible.

**Why no instruction-injection presets.** The legacy skill wrapped methodology files in `<SystemPrompt>` tags. Dropped on the user's reasoning: Claude is the caller and can write whatever Codex needs directly into the prompt, so a preset library is a rail that accumulates unused files. Only a minimal situational-facts preamble survives (B19), because Codex asking a clarifying question in a non-interactive turn wastes the entire turn.

**Why the filter default is deferred to measurement.** `file_change` events carry paths only; the whole context risk is `command_execution.aggregated_output`, which contains full stdout including file bodies Codex has `cat`ed. Picking a default without measuring would be exactly the unjustified-number rail this project avoids, so T3 measures three workloads across four levels and the default cites its own table.

**Why no agent and no workflow.** An agent was considered and rejected: the main thread is what needs to watch the log and decide when to intervene, subagents cannot ask the user anything, and Claude's own background Bash plus Monitor already provide the parallelism. A pre-defined workflow was rejected under the same D12 logic that governs e2e — the shape of "delegate something to Codex" varies every time, so freezing it would be a flexibility tax.

## Validation

Four tiers, all approved (*"목적을 달성하는데 필요한 모든 테스트를 해야해"*). Full case lists in the plan, §7.

- **T1** — unit tests against a fake `codex` shim on `PATH` replaying recorded fixtures. Free and repeatable; this is the primary safety net. Carries the sandbox-escalation regression, the parallel-stop isolation test, the filter-leak assertions, and the Korean-path/NFD case.
- **T2** — real Codex integration against a scratch repo, env-gated. Re-verifies the sandbox regression against the actual CLI.
- **T3** — filter calibration measurement across read-heavy / write-heavy / review workloads; output to `docs/measurements/filter-calibration.md`, summary into `references/event-stream.md`, and the shipped default cites it.
- **T4** — headless Claude e2e including a deliberate near-miss prompt that must **not** trigger the skill. Composed on the spot per `e2e-testing.md`; evidence-cited grading, surface compliance is a FAIL.

Plus `validate_harness.py` clean and `test_hook.py` passing.

**Open verification items (V-01…V-10)** are listed in the plan §6 with a check recipe and a fallback each. V-03 (does `-c sandbox_mode=` genuinely constrain a resumed run?) is a blocker; the rest have documented degradations. Record every outcome here as it is resolved.

**Results:** none yet — nothing has been generated. This spec was written in a planning-only session on 2026-07-25.

## Change history

| Date | Mode | Summary |
|---|---|---|
| 2026-07-25 | new (plan only) | Interviewed across five AskUserQuestion rounds; verified the Codex environment empirically (including a reproduced sandbox-escalation defect); recorded 20 decisions; wrote `docs/plan/codex-skill-implementation-plan.md` and this spec. All inventory rows are at `approved` — no files generated yet, so an audit on re-entry should report every row as awaiting generation. |
