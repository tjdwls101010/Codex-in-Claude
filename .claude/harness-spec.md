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

### V-01…V-10 results

Measured 2026-07-25 against `codex-cli 0.144.1`, Claude Code 2.1.220, macOS 25.5.0 (APFS), `CODEX_HOME=…/orca/codex-runtime-home/home`. Scratch repo under the session scratchpad. Raw event streams and rollout paths were kept for the run; the durable evidence is quoted inline below.

| ID | Verdict | Evidence |
|---|---|---|
| V-01 | **deferred to M8** | `CLAUDE_PLUGIN_ROOT` is empty in the Bash tool env with no plugin-installed skill active, so the question is only answerable after the plugin exists. `CLAUDE_PROJECT_DIR` and `CLAUDE_SKILL_DIR` confirmed **unset** (plan §3.7 holds). The design does not depend on the answer — the §4 fallback branch covers it and `doctor` prints the resolved path. |
| V-02 | **PASS** | `-c service_tier="priority"` under `--ignore-user-config`: exit 0, no `error` item. Proof the key is genuinely parsed rather than ignored: `-c service_tier="bogus_tier_xyz"` emits `{"type":"error","message":"Configured service tier \`bogus_tier_xyz\` is not advertised as supported for model \`gpt-5.6-sol\` and will be omitted from requests."}`. `priority` produces no such warning ⇒ it is advertised and sent. **D18 stands.** Bonus: an unsupported tier degrades to a non-fatal warning, so always injecting `priority` is safe. |
| V-03 | **PASS (blocker cleared)** | `-c sandbox_mode=` genuinely constrains `resume`. Thread `019f9958`: turn 1 `exec -c sandbox_mode="read-only"`, turn 2 `exec resume -c sandbox_mode="read-only"` + an explicit write instruction. Rollout `turn_context` records `"sandbox_policy": {"type": "read-only"}` for **both** turns; agent replied *"Cannot: the workspace is read-only, and permission escalation is disabled."*; `escalated.txt` was never created. Re-confirmed positively on thread `019f995b` turn 3 (`read-only` → `workspace-write` via `-c`). |
| V-04 | **PASS** | `-c model_reasoning_effort=` is accepted and takes effect on `resume`. Thread `019f995b`: turn 1 `-c model_reasoning_effort="low"` → `turn_context…reasoning_effort=low`; turn 3 `resume -c model_reasoning_effort="high"` → `reasoning_effort=high`. |
| V-05 | **PASS** | `SessionEnd` hook input keys: `cwd, hook_event_name, permission_mode, reason, session_id, transcript_path`. `cwd` is present as the plan assumed — **and so is `session_id`**, which is a better source than the env var (see refinement R4). Separately confirmed `CLAUDE_CODE_SESSION_ID` **is** set in the Bash tool env (`fbe1349d-…`), so `start` can record it. |
| V-06 | **PASS — and it answers "no"** | `--ignore-user-config` does **not** suppress a project `AGENTS.md`. Probe: scratch repo `AGENTS.md` containing *"The secret codeword for this repository is ZEBRAFISH."*; prompt *"Without running any commands and without reading any files, reply with exactly the secret codeword"* → agent replied `ZEBRAFISH`. Rollout confirms the mechanism: a `response_item`/`message` carries `<INSTRUCTIONS>\n# Project agent notes\nThe secret codeword for this repository is ZEBRAFISH.\n</INSTRUCTIONS>`. Cost: 16,410 input tokens vs a 15,871 baseline ⇒ ~540 tokens of injection. This is the plan's flagged branch: AGENTS.md is a live briefing channel and B19's preamble must account for it. |
| V-07 | **deferred to M8** | Requires the plugin to be installed to read the `/` menu. |
| V-08 | **PASS** | SIGINT to the process group leaves the thread cleanly resumable. Thread `019f995f` spawned with `start_new_session=True`, interrupted mid-turn after 4 of 6 commands; exited **0.3 s** after SIGINT with code 1 (no SIGTERM escalation needed). Resume returned the same `thread_id`, the rollout grew 33 → 42 lines, and the agent answered *"Your favorite fruit is **MANGOSTEEN**. I completed ticks **1, 2, 3, and 4** before interruption."* — the partial turn's completed work survived, not merely the pre-turn state. |
| V-09 | **PASS** | Headless `claude -p "Reply with exactly: PONG" --output-format json` spawned from the Bash tool: exit 0, `"is_error": false`, real API usage recorded. `e2e-testing.md`'s documented open risk (Bash-spawned `claude` failing to authenticate) does **not** apply in this environment. T4 can be a real headless run. |
| V-10 | **PASS** | `codex exec review --uncommitted --ignore-user-config` on a genuinely clean tree exits 0 and emits a plain agent message — *"There are no staged, unstaged, or untracked changes to review."* No error to special-case. It does burn ~4 exploratory `command_execution` items first (the model re-verifies the empty diff), which is cost, not failure. |

### Refinements forced by the sweep

Recorded here and applied to `docs/plan/codex-skill-implementation-plan.md`. None of them change a component's design — each strengthens or corrects the *rationale* the design already rests on.

- **R1 — §3.1 is per-turn setting amnesia, not merely escalation.** `resume` inherits *no* per-invocation setting from the thread; it re-derives every one from whatever config is in effect for that invocation. Measured on thread `019f995b`, one thread, three turns:

  | Turn | Invocation | `turn_context.sandbox_policy` | `reasoning_effort` |
  |---|---|---|---|
  | 1 | `exec --ignore-user-config -c sandbox_mode="workspace-write" -c model_reasoning_effort="low"` | `workspace-write` | `low` |
  | 2 | `exec resume --ignore-user-config` (no flags) | **`read-only`** — silent *downgrade* | **`None`** — dropped |
  | 3 | `exec resume --ignore-user-config -c sandbox_mode="workspace-write" -c model_reasoning_effort="high"` | `workspace-write` | `high` |

  The escalation direction reproduces too, exactly as the plan recorded it: thread `019f9959` created `read-only`, resumed **with inherited config** and no sandbox flag, got `"sandbox_policy": {"type": "danger-full-access"}` with `permission_profile.file_system: {"type": "disabled"}`, and wrote `escalated_inherit.txt` containing `ESCALATED`.

  Which direction you get is decided by the config layer in effect, not by the thread: inherited config on this machine escalates to `danger-full-access`; isolation downgrades to `read-only`. Isolation therefore *masks* the escalation here purely by coincidence — Codex's own built-in `exec` default happens to be `read-only`. Relying on that would be a bug: it depends on a Codex default staying put, it collapses the moment `--inherit-config` is used, and it silently breaks legitimate `workspace-write` work in the other direction. Re-injection from the registry is what makes the sandbox *stable*, and stability is the property worth stating — anti-escalation is one consequence of it.

- **R2 — `turn_context` is the verification channel, not the `<permissions instructions>` text.** Each turn appends a `{"type":"turn_context","payload":{…}}` line to the rollout carrying `sandbox_policy`, `permission_profile`, `model`, `cwd`, `workspace_roots`, and `collaboration_mode.settings.reasoning_effort`. It is structured, one line per turn, and unambiguous — strictly better than grepping a developer message. T2/I4 uses it.

- **R3 — `review` reports zero token usage.** Both V-10 runs ended `{"usage":{"input_tokens":0,"cached_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0}}` despite doing real work. `result` and `status` must not present that as a real measurement for review runs; report usage as unavailable rather than as zero.

- **R4 — the `SessionEnd` hook should match on the input's `session_id` first.** Plan §5.4 assumed `$CLAUDE_CODE_SESSION_ID` in the hook's environment. The hook *input* carries `session_id` directly (V-05), which is authoritative. The hook matches a recorded run if its `claude_session_id` equals **either** the input's `session_id` or the hook process's `CLAUDE_CODE_SESSION_ID` — either source alone is a single point of failure, and disagreement between them would otherwise mean killing nothing (benign) or everything (not).

- **R5 — measured resume cost curve** (isolated, same machine, `gpt-5.6-sol`), which is the concrete form of plan §3.4:

  | Invocation | Input tokens | Cached |
  |---|---|---|
  | fresh `exec`, trivial prompt | 15,871 | 13,056 |
  | fresh `exec`, trivial prompt, repo has a 2-line `AGENTS.md` | 16,410 | 0 |
  | `resume`, 1 prior turn | 31,780 | 28,160 |
  | `resume`, 2 prior turns | 47,774 | 43,264 |
  | `resume`, after an interrupted 6-command turn | 86,142 | 75,520 |

**Results:** M0 verification sweep complete except V-01/V-07 (deferred to M8 by construction — they require an installed plugin). The V-03 blocker is cleared, so the design proceeds unchanged.

## Change history

| Date | Mode | Summary |
|---|---|---|
| 2026-07-25 | new (plan only) | Interviewed across five AskUserQuestion rounds; verified the Codex environment empirically (including a reproduced sandbox-escalation defect); recorded 20 decisions; wrote `docs/plan/codex-skill-implementation-plan.md` and this spec. All inventory rows are at `approved` — no files generated yet, so an audit on re-entry should report every row as awaiting generation. |
