# Graph Report - codex in claude  (2026-09-25)

## Corpus Check
- 39 files · ~67,695 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: .jsonl 6, (none) 2)

## Summary
- 682 nodes · 1538 edges · 39 communities (28 shown, 10 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 25 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5db5f497`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _batch.py
- _registry.py
- .finished
- UserDefaultsAndTheirPrecedence
- _run.py
- Codex in Claude
- ResumeFrom
- BridgeCase
- codex_bridge.py
- WhatReachesCodex
- Levels
- wait_until
- test_observe.py
- _events.py
- test_registry_races.py
- reap
- codex 스킬 재작성 계획
- test_catalog.py
- _codex.py
- Doctor
- codex
- StopLadder
- TerminalStates
- ThroughASymlink
- _worktree.py
- test_run_lifecycle.py
- load_tasks
- Graphify-First Codebase Navigation
- Tiered Contribution Verification
- Listing
- Codex Managed Subagent Skill
- Codex-in-Claude Release History
- Bridge Error Type
- Private Vulnerability Reporting
- HidesSuppressedCommands
- Code of Conduct Enforcement
- Graph Navigation Workflow
- Contribution Guidelines

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 65 edges
2. `fail()` - 32 edges
3. `wait_until()` - 27 edges
4. `cmd_batch_clean()` - 25 edges
5. `cmd_batch_start()` - 24 edges
6. `alive()` - 23 edges
7. `Clean` - 23 edges
8. `find_run()` - 22 edges
9. `reap()` - 22 edges
10. `cmd_doctor()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `fail_at()` --calls--> `fail()`  [EXTRACTED]
  .claude/skills/codex/scripts/_batch.py → .claude/skills/codex/scripts/_util.py
- `cmd_batch_start()` --uses--> `BridgeError`  [INFERRED]
  .claude/skills/codex/scripts/_batch.py → .claude/skills/codex/scripts/_util.py
- `build_parser()` --indirect_call--> `cmd_batch_start()`  [INFERRED]
  .claude/skills/codex/scripts/codex_bridge.py → .claude/skills/codex/scripts/_batch.py
- `build_parser()` --indirect_call--> `cmd_batch_clean()`  [INFERRED]
  .claude/skills/codex/scripts/codex_bridge.py → .claude/skills/codex/scripts/_batch.py
- `cmd_log()` --uses--> `CursorOutOfRange`  [INFERRED]
  .claude/skills/codex/scripts/codex_bridge.py → .claude/skills/codex/scripts/_events.py

## Import Cycles
- None detected.

## Communities (39 total, 10 thin omitted)

### Community 0 - "_batch.py"
Cohesion: 0.07
Nodes (66): changed_paths(), claim_group(), cmd_batch_clean(), cmd_batch_start(), cmd_result_group(), derived_groups(), follow_group(), follow_group_log() (+58 more)

### Community 1 - "_registry.py"
Cohesion: 0.14
Nodes (25): claim_run_dir(), ensure_runs_dir(), _flock_path(), _meta_lock(), meta_unreadable(), new_run_id(), Path, The run registry: `<project>/.codex-runs/<run_id>/`. .codex-runs/ ├──… (+17 more)

### Community 2 - ".finished"
Cohesion: 0.08
Nodes (8): Clean, Overlaps, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout, WorktreeCase

### Community 3 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.08
Nodes (10): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted (+2 more)

### Community 4 - "_run.py"
Cohesion: 0.10
Nodes (28): apply_preamble(), build_argv(), model_catalog(), `{model, effort, service_tier}` from the user's `config.toml`. Read fresh…, What this Codex install actually offers, or None if it cannot be read. `codex…, Compose the Codex argv for a run from its recorded settings. Every per-…, The caller's uncommitted work is absent from this checkout either way; only the…, Prepend the run-context paragraphs. Not optional. `--no-preamble` switched all… (+20 more)

### Community 5 - "Codex in Claude"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 6 - "ResumeFrom"
Cohesion: 0.10
Nodes (8): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 7 - "BridgeCase"
Cohesion: 0.08
Nodes (14): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded)., The `-c key=value` entries of an argv, as a dict of raw values. (+6 more)

### Community 8 - "codex_bridge.py"
Cohesion: 0.14
Nodes (40): add_common(), add_heartbeat(), add_run_options(), build_parser(), cmd_log(), cmd_models(), cmd_result(), cmd_resume() (+32 more)

### Community 9 - "WhatReachesCodex"
Cohesion: 0.08
Nodes (9): FlagsThatWouldDecideNothing, OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, The sandbox always travels as `-c sandbox_mode=` and the working directory is…, Two selectors name different things; honouring one silently drops the other., A flag that parses and changes nothing reads as having been obeyed, so each is…, SelectorsAreExclusive, TheRegistryGoesWhereItIsTold (+1 more)

### Community 10 - "Levels"
Cohesion: 0.09
Nodes (6): Cursors, DamagedLines, Levels, Reading a run's event stream: exact cursors, damaged lines that are counted…, A line that will not parse is kept as `unparsed` and counted, apart from…, Show

### Community 11 - "wait_until"
Cohesion: 0.20
Nodes (5): alive(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, wait_until(), Installs: the skill reached through a symlink, from a directory that has…, `batch start --worktree`: which members get a checkout, what the checkout…

### Community 12 - "test_observe.py"
Cohesion: 0.13
Nodes (5): answer_fixture(), GroupResult, What `status` and `result` say about runs: progress while live, the answer once…, Result, StatusOfOneRun

### Community 13 - "_events.py"
Cohesion: 0.10
Nodes (30): drain(), dump(), CursorOutOfRange, final_usage(), find_item(), first_thread_id(), format_events(), _format_item() (+22 more)

### Community 14 - "test_registry_races.py"
Cohesion: 0.13
Nodes (10): engine(), AFailureInsideALockIsReportedAsItself, AStaleReap, ManyRunsAtOnce, ManyWritersOneMeta, The registry under real concurrent processes: many writers on one meta.json, a…, A registry that cannot be locked degrades to unlocked access, but an error…, `reap` decides from a snapshot and commits only if the state on disk is still… (+2 more)

### Community 15 - "reap"
Cohesion: 0.33
Nodes (6): Path, SIGINT, then SIGTERM, then SIGKILL — to the process group. SIGINT first because…, signal_run(), A run whose supervisor is gone but whose meta still says `running` was killed…, reap(), pid_alive()

### Community 16 - "codex 스킬 재작성 계획"
Cohesion: 0.17
Nodes (11): codex 스킬 재작성 계획, Context, --help·에러 메시지 작성 규칙 (PR5), SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하), 검증 (전체 완료 판정), 단계 (PR별, 각 단계의 완료 판정 포함), 참고: 재사용하는 기존 코드, 최종 디렉터리 구조 (+3 more)

### Community 17 - "test_catalog.py"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 18 - "_codex.py"
Cohesion: 0.12
Nodes (25): await_predecessor(), cmd_doctor(), config_scalars(), Path, query_threads(), Talking to the Codex CLI: argv composition, spawning, and its thread database.…, Start the run under a supervisor process, in its own session. A background…, Block until the run this one is chained behind reaches a terminal state.… (+17 more)

### Community 20 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 24 - "_worktree.py"
Cohesion: 0.13
Nodes (28): cut_worktree(), Stage 3 — give this run its own checkout, after every refusal has passed.…, add(), _covered_by(), _git(), ignored_entries(), is_dirty(), missing_at_base() (+20 more)

### Community 25 - "test_run_lifecycle.py"
Cohesion: 0.17
Nodes (5): AnOrphanThatIsStillWriting, DetachedStart, LegacyWaitingRun, A run's life: detached start, every terminal state, the stop ladder, and what a…, Releases before 0.8 could leave a batch member `waiting` on its predecessor.…

### Community 26 - "load_tasks"
Cohesion: 0.29
Nodes (7): load_tasks(), defaults_for(), fail_at(), inherits(), Build the ordered task list from `--task` and `--tasks-file`. Both may be…, check_model_effort(), Refuse a model or effort this Codex install does not offer. Only values the…

### Community 60 - "Codex Managed Subagent Skill"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 61 - "Codex-in-Claude Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 99 - "Bridge Error Type"
Cohesion: 0.50
Nodes (3): BridgeError, A `fail()` raised instead of emitted. See `failures_raise`., Exception

### Community 104 - "Private Vulnerability Reporting"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

### Community 113 - "Code of Conduct Enforcement"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

## Knowledge Gaps
- **28 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 285 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `.finished`, `UserDefaultsAndTheirPrecedence`, `ResumeFrom`, `WhatReachesCodex`, `Levels`, `wait_until`, `test_observe.py`, `test_registry_races.py`, `test_catalog.py`, `Doctor`, `StopLadder`, `TerminalStates`, `ThroughASymlink`, `test_run_lifecycle.py`, `load_tasks`, `Listing`?**
  _High betweenness centrality (0.637) - this node is a cross-community bridge._
- **Why does `inherits()` connect `load_tasks` to `codex_bridge.py`?**
  _High betweenness centrality (0.426) - this node is a cross-community bridge._
- **Why does `find_run()` connect `codex_bridge.py` to `_batch.py`, `_registry.py`, `load_tasks`?**
  _High betweenness centrality (0.277) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `cmd_batch_start()` (e.g. with `BridgeError` and `build_parser()`) actually correct?**
  _`cmd_batch_start()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _28 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `_batch.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06829488919041157 - nodes in this community are weakly interconnected._
- **Should `_registry.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14153846153846153 - nodes in this community are weakly interconnected._