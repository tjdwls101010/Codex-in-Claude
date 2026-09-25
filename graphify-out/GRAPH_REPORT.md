# Graph Report - codex in claude  (2026-09-25)

## Corpus Check
- 56 files · ~50,687 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: .jsonl 6, (none) 2)

## Summary
- 810 nodes · 1825 edges · 47 communities (33 shown, 13 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 26 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `886afa49`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- groups.py
- registry.py
- .finished
- UserDefaultsAndTheirPrecedence
- batch.py
- Codex in Claude
- ResumeFrom
- BridgeCase
- fail
- test_cli_contract.py
- Levels
- wait_until
- test_observe.py
- cmd_log
- engine
- cli/observe.py
- codex 스킬 재작성 계획
- test_catalog.py
- diagnose.py
- Doctor
- codex
- core/runs.py
- WhatReachesCodex
- resolve_group
- worktree.py
- StopLadder
- Precedence
- Graphify-First Codebase Navigation
- Tiered Contribution Verification
- cli/__init__.py
- Layering
- test_events.py
- result_group
- TerminalStates
- codex/__init__.py
- HelpIsTheInterface
- TheLadderOrder
- OneLinePerParagraph
- meta_unreadable
- DetachedStart
- Codex Managed Subagent Skill
- Codex-in-Claude Release History
- Private Vulnerability Reporting
- Code of Conduct Enforcement
- Graph Navigation Workflow
- Contribution Guidelines

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 68 edges
2. `fail()` - 38 edges
3. `wait_until()` - 27 edges
4. `reap()` - 24 edges
5. `cmd_log()` - 23 edges
6. `find_run()` - 23 edges
7. `alive()` - 23 edges
8. `Clean` - 23 edges
9. `iter_runs()` - 21 edges
10. `cmd_status()` - 20 edges

## Surprising Connections (you probably didn't know these)
- `build_parser()` --indirect_call--> `cmd_batch_start()`  [INFERRED]
  .claude/skills/codex/scripts/cli/parser.py → .claude/skills/codex/scripts/cli/batch.py
- `build_parser()` --indirect_call--> `cmd_log()`  [INFERRED]
  .claude/skills/codex/scripts/cli/parser.py → .claude/skills/codex/scripts/cli/observe.py
- `main()` --calls--> `build_parser()`  [EXTRACTED]
  .claude/skills/codex/scripts/cli/__init__.py → .claude/skills/codex/scripts/cli/parser.py
- `main()` --calls--> `fail()`  [EXTRACTED]
  .claude/skills/codex/scripts/cli/__init__.py → .claude/skills/codex/scripts/util.py
- `cmd_batch_start()` --calls--> `claim_group()`  [EXTRACTED]
  .claude/skills/codex/scripts/cli/batch.py → .claude/skills/codex/scripts/core/groups.py

## Import Cycles
- None detected.

## Communities (47 total, 13 thin omitted)

### Community 0 - "groups.py"
Cohesion: 0.08
Nodes (28): load_tasks(), reasons_for(), Groups: `<runs_dir>/.groups/<name>.json`, the set of runs one `batch start`…, The ordered task list: `--task` prompts first (as typed), then `--tasks-file`…, A member's options: the group's as defaults, the task's own fields over them., Whether `--worktree` would isolate this member: a fresh writer with no cwd of…, Why `--worktree` would pass this member over, in the caller's words, or None., Members that will write, grouped by the directory they will write in, resolved… (+20 more)

### Community 1 - "registry.py"
Cohesion: 0.13
Nodes (26): _flock_path(), _meta_lock(), Path, The run registry: `<project>/.codex-runs/<run_id>/`. .codex-runs/ ├──…, Serialise read-modify-write on one meta.json. The lock file is separate because…, A reader sees the old file or the new one, never half of one. The staging name…, Merge `fields` into meta.json under the run's lock., Compare-and-set on `state`: merge only if the state on disk is still one of… (+18 more)

### Community 2 - ".finished"
Cohesion: 0.08
Nodes (9): Clean, Overlaps, `batch start --worktree`: which members get a checkout, what the checkout…, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout (+1 more)

### Community 3 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.08
Nodes (10): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted (+2 more)

### Community 4 - "batch.py"
Cohesion: 0.25
Nodes (10): cmd_batch_start(), `batch start` and `batch clean`., check_task_settings(), plan_worktrees(), Refuse a model or effort any task would adopt, before the group name is claimed…, Which members get a checkout, cut from which commit, and a note when members…, A group name becomes a filename, so no separator and no leading dot., valid_name() (+2 more)

### Community 5 - "Codex in Claude"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 6 - "ResumeFrom"
Cohesion: 0.10
Nodes (8): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 7 - "BridgeCase"
Cohesion: 0.07
Nodes (14): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded)., The `-c key=value` entries of an argv, as a dict of raw values. (+6 more)

### Community 8 - "fail"
Cohesion: 0.14
Nodes (34): cmd_batch_clean(), cmd_doctor(), cmd_models(), The catalog is asked of Codex rather than written down: which efforts a model…, note_unreadable(), Refusals several commands share: competing selectors, a run that cannot be…, Two selectors name different things, and honouring one would silently drop the…, Cannot read that run" and "no such run" are different answers: the first still… (+26 more)

### Community 9 - "test_cli_contract.py"
Cohesion: 0.09
Nodes (9): FlagsThatWouldDecideNothing, OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, Flags nothing used, removed from the parser rather than left to accept and do…, Two selectors name different things; honouring one silently drops the other., A flag that parses and changes nothing reads as having been obeyed, so each is…, RemovedSurface, SelectorsAreExclusive (+1 more)

### Community 10 - "Levels"
Cohesion: 0.11
Nodes (4): FormatEvents, Levels, `codex.events.format_events` on events built by hand, one kind at a time., Show

### Community 11 - "wait_until"
Cohesion: 0.12
Nodes (10): alive(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, A run recorded `orphaned` whose codex is demonstrably still going: its…, wait_until(), Installs: the skill reached through a symlink, from a directory that has…, ThroughASymlink, AnOrphanThatIsStillWriting, LegacyWaitingRun (+2 more)

### Community 12 - "test_observe.py"
Cohesion: 0.08
Nodes (8): AnOlderReleasesRegistry, answer_fixture(), GroupResult, Listing, What `status` and `result` say about runs: progress while live, the answer once…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, Result, StatusOfOneRun

### Community 13 - "cmd_log"
Cohesion: 0.08
Nodes (48): cmd_log(), dump(), step(), follow(), follow_group(), step(), group_tail(), log_group() (+40 more)

### Community 14 - "engine"
Cohesion: 0.12
Nodes (11): engine(), Import an engine module (`"core.settings"`, `"codex.argv"`, …) from the scripts…, AFailureInsideALockIsReportedAsItself, AStaleReap, ManyRunsAtOnce, ManyWritersOneMeta, The registry under real concurrent processes: many writers on one meta.json, a…, A registry that cannot be locked degrades to unlocked access, but an error… (+3 more)

### Community 15 - "cli/observe.py"
Cohesion: 0.13
Nodes (21): `status`, `log`, `show` and `result`, for one run and for a group. A follower…, What the default listing shows of a run, from a row built with a 160-character…, summary_row(), Describing runs and groups: the status row, the turn-failure excerpt, and…, `is_live` for a row: its state is not terminal, or its Codex still writes., row_is_live(), turn_failed_excerpt(), is_live() (+13 more)

### Community 16 - "codex 스킬 재작성 계획"
Cohesion: 0.17
Nodes (11): codex 스킬 재작성 계획, Context, --help·에러 메시지 작성 규칙 (PR5), SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하), 검증 (전체 완료 판정), 단계 (PR별, 각 단계의 완료 판정 포함), 참고: 재사용하는 기존 코드, 최종 디렉터리 구조 (+3 more)

### Community 17 - "test_catalog.py"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 18 - "diagnose.py"
Cohesion: 0.15
Nodes (17): _check_registry(), _overlapping_writers(), `doctor` and `models`., Live runs whose recorded cwds overlap (either inside the other), where at least…, codex_version(), model_catalog(), This install's model catalog, read from `codex debug models`, and the pre-spawn…, What this Codex install offers, trimmed to the fields a caller chooses from, or… (+9 more)

### Community 20 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 21 - "core/runs.py"
Cohesion: 0.10
Nodes (29): apply_preamble(), build_argv(), The `codex exec` argv for a run, and the paragraphs put in front of its prompt.…, `-c` values are parsed as TOML, so a string value is emitted quoted., Compose the argv from a run's recorded settings, re-asserting every one on…, The caller's uncommitted work is absent from a checkout either way; only the…, Prepend the run-context paragraphs. Not optional., toml_cfg() (+21 more)

### Community 23 - "resolve_group"
Cohesion: 0.16
Nodes (28): _check_liftable_guards(), claim_group(), clean_group(), derived_groups(), group_path(), group_unreadable(), groups_dir(), list_groups() (+20 more)

### Community 24 - "worktree.py"
Cohesion: 0.14
Nodes (28): What the caller cannot see from anywhere else about the checkouts just cut:…, worktree_report(), add(), _covered_by(), _git(), ignored_entries(), is_dirty(), missing_at_base() (+20 more)

### Community 26 - "Precedence"
Cohesion: 0.11
Nodes (7): build(), BuildArgv, Preamble, `codex.argv`: the argv a run hands Codex, and the paragraphs in front of its…, Precedence, `core.settings.resolve`: one precedence for every setting — the flag, then what…, resolve()

### Community 30 - "cli/__init__.py"
Cohesion: 0.19
Nodes (13): Drive the OpenAI Codex CLI as a managed subagent. Entrypoint and the…, _check_codex(), _check_config(), main(), The command-line surface: parse, dispatch, and answer in the output contract —…, codex_home(), config_scalars(), Path (+5 more)

### Community 31 - "Layering"
Cohesion: 0.33
Nodes (4): internal_imports(), layer(), Layering, The scripts' structure: imports point one way (cli → core → codex/worktree →…

### Community 32 - "test_events.py"
Cohesion: 0.19
Nodes (4): Cursors, DamagedLines, Reading a run's event stream: exact cursors, damaged lines that are counted…, A line that will not parse is kept as `unparsed` and counted, apart from…

### Community 33 - "result_group"
Cohesion: 0.18
Nodes (12): result_group(), status_group(), changed_paths(), member_result(), overlaps(), Slots that never became runs, including tasks a killed `batch start` never…, Members the manifest names that no longer resolve — a directory removed by…, Paths a run wrote, as `(repository, repo-relative path)` pairs. Codex reports… (+4 more)

### Community 39 - "meta_unreadable"
Cohesion: 0.50
Nodes (4): _member_liveness(), `(live members, members whose meta.json will not parse)` — unknown is kept…, meta_unreadable(), Present but will not parse, as distinct from absent: `read_meta` answers None…

### Community 60 - "Codex Managed Subagent Skill"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 61 - "Codex-in-Claude Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 104 - "Private Vulnerability Reporting"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

### Community 113 - "Code of Conduct Enforcement"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

## Knowledge Gaps
- **28 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 329 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `test_events.py`, `TerminalStates`, `UserDefaultsAndTheirPrecedence`, `HelpIsTheInterface`, `.finished`, `ResumeFrom`, `DetachedStart`, `test_cli_contract.py`, `Levels`, `wait_until`, `test_observe.py`, `engine`, `test_catalog.py`, `Doctor`, `WhatReachesCodex`, `StopLadder`?**
  _High betweenness centrality (0.188) - this node is a cross-community bridge._
- **Why does `WorktreeCase` connect `.finished` to `BridgeCase`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Why does `wait_until()` connect `wait_until` to `.finished`, `UserDefaultsAndTheirPrecedence`, `ResumeFrom`, `BridgeCase`, `test_observe.py`, `engine`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `cmd_log()` (e.g. with `step()` and `CursorOutOfRange`) actually correct?**
  _`cmd_log()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _28 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `groups.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07862903225806452 - nodes in this community are weakly interconnected._
- **Should `registry.py` be split into smaller, more focused modules?**
  _Cohesion score 0.12873563218390804 - nodes in this community are weakly interconnected._