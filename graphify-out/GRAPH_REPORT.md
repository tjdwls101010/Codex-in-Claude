# Graph Report - codex in claude  (2026-09-25)

## Corpus Check
- 39 files · ~66,348 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: .jsonl 6, (none) 2)

## Summary
- 656 nodes · 1482 edges · 38 communities (25 shown, 12 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 25 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c89e0a82`
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
- _codex.py
- test_registry_races.py
- reap
- codex 스킬 재작성 계획
- test_catalog.py
- _util.py
- Doctor
- codex
- StopLadder
- TerminalStates
- ThroughASymlink
- ManyRunsAtOnce
- DetachedStart
- test_doctor.py
- Graphify-First Codebase Navigation
- Tiered Contribution Verification
- Codex Managed Subagent Skill
- Codex-in-Claude Release History
- Bridge Error Type
- Private Vulnerability Reporting
- Suppressed Command Help Hiding
- Code of Conduct Enforcement
- Graph Navigation Workflow
- Contribution Guidelines

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 64 edges
2. `fail()` - 32 edges
3. `cmd_batch_start()` - 24 edges
4. `cmd_batch_clean()` - 24 edges
5. `wait_until()` - 23 edges
6. `find_run()` - 22 edges
7. `reap()` - 22 edges
8. `cmd_doctor()` - 22 edges
9. `cmd_status()` - 21 edges
10. `create_run()` - 20 edges

## Surprising Connections (you probably didn't know these)
- `cmd_batch_start()` --uses--> `BridgeError`  [INFERRED]
  .claude/skills/codex/scripts/_batch.py → .claude/skills/codex/scripts/_util.py
- `build_parser()` --indirect_call--> `cmd_batch_start()`  [INFERRED]
  .claude/skills/codex/scripts/codex_bridge.py → .claude/skills/codex/scripts/_batch.py
- `build_parser()` --indirect_call--> `cmd_batch_clean()`  [INFERRED]
  .claude/skills/codex/scripts/codex_bridge.py → .claude/skills/codex/scripts/_batch.py
- `cmd_doctor()` --calls--> `list_groups()`  [EXTRACTED]
  .claude/skills/codex/scripts/codex_bridge.py → .claude/skills/codex/scripts/_batch.py
- `cmd_status()` --calls--> `list_groups()`  [EXTRACTED]
  .claude/skills/codex/scripts/codex_bridge.py → .claude/skills/codex/scripts/_batch.py

## Import Cycles
- None detected.

## Communities (38 total, 12 thin omitted)

### Community 0 - "_batch.py"
Cohesion: 0.06
Nodes (77): changed_paths(), claim_group(), cmd_batch_clean(), cmd_batch_start(), derived_groups(), group_path(), group_unreadable(), groups_dir() (+69 more)

### Community 1 - "_registry.py"
Cohesion: 0.17
Nodes (20): claim_run_dir(), ensure_runs_dir(), _flock_path(), _meta_lock(), new_run_id(), Path, The run registry: `<project>/.codex-runs/<run_id>/`. .codex-runs/ ├──…, Generate a run id and take exclusive ownership of its directory. `mkdir`… (+12 more)

### Community 2 - ".finished"
Cohesion: 0.09
Nodes (9): Clean, Overlaps, `batch start --worktree`: which members get a checkout, what the checkout…, A checkout is `git worktree add` output: tracked files at the base commit and…, Codex reports absolute paths, and each checkout has its own prefix, so paths…, Append a file_change naming these absolute paths, the shape real events have., WhatACheckoutHolds, WhoGetsACheckout (+1 more)

### Community 3 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.08
Nodes (10): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted (+2 more)

### Community 4 - "_run.py"
Cohesion: 0.13
Nodes (24): apply_preamble(), check_model_effort(), model_catalog(), What this Codex install actually offers, or None if it cannot be read. `codex…, Refuse a model or effort this Codex install does not offer. Only values the…, Prepend the run-context paragraphs. Not optional. `--no-preamble` switched all…, create_run(), cut_worktree() (+16 more)

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
Cohesion: 0.06
Nodes (89): cmd_result_group(), follow_group(), follow_group_log(), drain(), group_snapshot(), heartbeat_due(), load_tasks(), defaults_for() (+81 more)

### Community 9 - "WhatReachesCodex"
Cohesion: 0.08
Nodes (9): FlagsThatWouldDecideNothing, OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, The sandbox always travels as `-c sandbox_mode=` and the working directory is…, Two selectors name different things; honouring one silently drops the other., A flag that parses and changes nothing reads as having been obeyed, so each is…, SelectorsAreExclusive, TheRegistryGoesWhereItIsTold (+1 more)

### Community 10 - "Levels"
Cohesion: 0.09
Nodes (6): Cursors, DamagedLines, Levels, Reading a run's event stream: exact cursors, damaged lines that are counted…, A line that will not parse is kept as `unparsed` and counted, apart from…, Show

### Community 11 - "wait_until"
Cohesion: 0.14
Nodes (8): alive(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, wait_until(), Installs: the skill reached through a symlink, from a directory that has…, AnOrphanThatIsStillWriting, LegacyWaitingRun, A run's life: detached start, every terminal state, the stop ladder, and what a…, Releases before 0.8 could leave a batch member `waiting` on its predecessor.…

### Community 12 - "test_observe.py"
Cohesion: 0.10
Nodes (6): answer_fixture(), GroupResult, Listing, What `status` and `result` say about runs: progress while live, the answer once…, Result, StatusOfOneRun

### Community 13 - "_codex.py"
Cohesion: 0.12
Nodes (20): build_argv(), config_scalars(), Path, Talking to the Codex CLI: argv composition, spawning, and its thread database.…, `{model, effort, service_tier}` from the user's `config.toml`. Read fresh…, Compose the Codex argv for a run from its recorded settings. Every per-…, The caller's uncommitted work is absent from this checkout either way; only the…, Start the run under a supervisor process, in its own session. A background… (+12 more)

### Community 14 - "test_registry_races.py"
Cohesion: 0.22
Nodes (7): engine(), AStaleReap, ManyWritersOneMeta, The registry under real concurrent processes: many writers on one meta.json, a…, `reap` decides from a snapshot and commits only if the state on disk is still…, _read(), _write_own_key()

### Community 15 - "reap"
Cohesion: 0.21
Nodes (13): await_predecessor(), SIGINT, then SIGTERM, then SIGKILL — to the process group. SIGINT first because…, signal_run(), Block until the run this one is chained behind reaches a terminal state.…, A run whose supervisor is gone but whose meta still says `running` was killed…, Whether this run's Codex process is still going, whatever its state says.…, reap(), still_writing() (+5 more)

### Community 16 - "codex 스킬 재작성 계획"
Cohesion: 0.17
Nodes (11): codex 스킬 재작성 계획, Context, --help·에러 메시지 작성 규칙 (PR5), SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하), 검증 (전체 완료 판정), 단계 (PR별, 각 단계의 완료 판정 포함), 참고: 재사용하는 기존 코드, 최종 디렉터리 구조 (+3 more)

### Community 17 - "test_catalog.py"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 18 - "_util.py"
Cohesion: 0.29
Nodes (9): codex_home(), git_toplevel(), is_within(), nfc(), Path, Primitives shared by every module in the bridge. Nothing here knows about runs,…, Never hardcode ~/.codex: CODEX_HOME is overridden on some machines and then…, Whether `path` is `parent` or lives inside it. NFC-normalised on both sides,… (+1 more)

### Community 20 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

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
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 276 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `.finished`, `UserDefaultsAndTheirPrecedence`, `ResumeFrom`, `codex_bridge.py`, `WhatReachesCodex`, `Levels`, `wait_until`, `test_observe.py`, `test_registry_races.py`, `test_catalog.py`, `Doctor`, `StopLadder`, `TerminalStates`, `ThroughASymlink`, `ManyRunsAtOnce`, `DetachedStart`, `test_doctor.py`?**
  _High betweenness centrality (0.630) - this node is a cross-community bridge._
- **Why does `find_run()` connect `codex_bridge.py` to `_batch.py`, `_registry.py`?**
  _High betweenness centrality (0.277) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `cmd_batch_start()` (e.g. with `BridgeError` and `build_parser()`) actually correct?**
  _`cmd_batch_start()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _28 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `_batch.py` be split into smaller, more focused modules?**
  _Cohesion score 0.058747160012982795 - nodes in this community are weakly interconnected._
- **Should `.finished` be split into smaller, more focused modules?**
  _Cohesion score 0.09191919191919191 - nodes in this community are weakly interconnected._
- **Should `UserDefaultsAndTheirPrecedence` be split into smaller, more focused modules?**
  _Cohesion score 0.08205128205128205 - nodes in this community are weakly interconnected._