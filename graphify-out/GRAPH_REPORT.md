# Graph Report - codex in claude  (2026-09-25)

## Corpus Check
- 58 files · ~50,630 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: .jsonl 6, (none) 2)

## Summary
- 835 nodes · 1861 edges · 50 communities (37 shown, 12 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 27 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ec408a09`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- check_task_settings
- read_meta
- .finished
- UserDefaultsAndTheirPrecedence
- plan_worktrees
- Codex in Claude
- ResumeFrom
- BridgeCase
- fail
- test_cli_contract.py
- Levels
- wait_until
- test_observe.py
- cli/observe.py
- harness.py
- run_e2e.py
- codex 스킬 재작성 계획
- test_catalog.py
- registry.py
- Doctor
- codex
- core/runs.py
- WhatReachesCodex
- batch.py
- worktree.py
- test_argv.py
- Precedence
- Graphify-First Codebase Navigation
- Tiered Contribution Verification
- diagnose.py
- Layering
- TheSkillTextPointsAtRealThings
- result_group
- TerminalStates
- codex/__init__.py
- Path
- TheLadderOrder
- OneLinePerParagraph
- groups.py
- AStaleReap
- publish_run
- BridgeError
- scenarios.md
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
- `spawn_members()` --uses--> `BridgeError`  [INFERRED]
  .claude/skills/codex/scripts/core/groups.py → .claude/skills/codex/scripts/util.py
- `main()` --calls--> `build_parser()`  [EXTRACTED]
  .claude/skills/codex/scripts/cli/__init__.py → .claude/skills/codex/scripts/cli/parser.py
- `main()` --calls--> `fail()`  [EXTRACTED]
  .claude/skills/codex/scripts/cli/__init__.py → .claude/skills/codex/scripts/util.py

## Import Cycles
- None detected.

## Communities (50 total, 12 thin omitted)

### Community 0 - "check_task_settings"
Cohesion: 0.22
Nodes (9): check_task_settings(), A member's options: the group's as defaults, the task's own fields over them., Refuse a model or effort any task would adopt, before the group name is claimed…, Members that will write, grouped by the directory they will write in, resolved…, task_args(), writers_by_directory(), What a run will be: one precedence for every setting, used by `start`,…, Resolve a run's settings from the caller's flags, the run it continues (`base`,… (+1 more)

### Community 1 - "read_meta"
Cohesion: 0.14
Nodes (20): first_thread_id(), `thread.started` is the first line Codex emits, and a resumed turn repeats the…, Merge `fields` into meta.json under the run's lock., read_meta(), update_meta(), The thread a run with an unparseable meta.json was on, recovered from its event…, thread_of_unreadable(), end_group() (+12 more)

### Community 2 - ".finished"
Cohesion: 0.08
Nodes (8): Clean, Overlaps, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout, WorktreeCase

### Community 3 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.08
Nodes (10): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted (+2 more)

### Community 4 - "plan_worktrees"
Cohesion: 0.22
Nodes (9): plan_worktrees(), reasons_for(), Whether `--worktree` would isolate this member: a fresh writer with no cwd of…, Why `--worktree` would pass this member over, in the caller's words, or None., Who is about to write into one directory, and — only where it would work — the…, Which members get a checkout, cut from which commit, and a note when members…, sharing_note(), wants_worktree() (+1 more)

### Community 5 - "Codex in Claude"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 6 - "ResumeFrom"
Cohesion: 0.10
Nodes (8): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 7 - "BridgeCase"
Cohesion: 0.07
Nodes (15): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded)., The `-c key=value` entries of an argv, as a dict of raw values. (+7 more)

### Community 8 - "fail"
Cohesion: 0.18
Nodes (29): cmd_batch_clean(), cmd_doctor(), cmd_models(), The catalog is asked of Codex rather than written down: which efforts a model…, Two selectors name different things, and honouring one would silently drop the…, Cannot read that run" and "no such run" are different answers: the first still…, refuse_competing_selectors(), refuse_unresolved_run() (+21 more)

### Community 9 - "test_cli_contract.py"
Cohesion: 0.08
Nodes (11): FlagsThatWouldDecideNothing, HelpIsTheInterface, walk(), OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, Flags nothing used, removed from the parser rather than left to accept and do…, Two selectors name different things; honouring one silently drops the other., A flag that parses and changes nothing reads as having been obeyed, so each is… (+3 more)

### Community 10 - "Levels"
Cohesion: 0.07
Nodes (8): Cursors, DamagedLines, FormatEvents, Levels, Reading a run's event stream: exact cursors, damaged lines that are counted…, `codex.events.format_events` on events built by hand, one kind at a time., A line that will not parse is kept as `unparsed` and counted, apart from…, Show

### Community 11 - "wait_until"
Cohesion: 0.11
Nodes (9): alive(), wait_until(), AnOrphanThatIsStillWriting, LegacyWaitingRun, A run's life: detached start, every terminal state, the stop ladder, and what a…, Signals go to the run's recorded process group, SIGINT first, escalating only…, Releases before 0.8 could leave a batch member `waiting` on its predecessor.…, StopLadder (+1 more)

### Community 12 - "test_observe.py"
Cohesion: 0.08
Nodes (8): AnOlderReleasesRegistry, answer_fixture(), GroupResult, Listing, What `status` and `result` say about runs: progress while live, the answer once…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, Result, StatusOfOneRun

### Community 13 - "cli/observe.py"
Cohesion: 0.06
Nodes (71): _check_registry(), _overlapping_writers(), Live runs whose recorded cwds overlap (either inside the other), where at least…, `--follow-timeout` and `--heartbeat` only mean something to a follower, at a…, refuse_unusable_follow_options(), cmd_log(), dump(), step() (+63 more)

### Community 14 - "harness.py"
Cohesion: 0.14
Nodes (11): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import an engine module (`"core.settings"`, `"codex.argv"`, …) from the scripts…, Installs: the skill reached through a symlink, from a directory that has…, AFailureInsideALockIsReportedAsItself, ManyRunsAtOnce, ManyWritersOneMeta, The registry under real concurrent processes: many writers on one meta.json, a… (+3 more)

### Community 15 - "run_e2e.py"
Cohesion: 0.23
Nodes (13): base_cmd(), control_text(), digest(), main(), Path, Run one S6 scenario against the draft or the control SKILL.md, isolated, and…, The draft's frontmatter and its call paragraph, without any judgement text., Detached runs outlive the session that started them; stop them so none keeps… (+5 more)

### Community 16 - "codex 스킬 재작성 계획"
Cohesion: 0.17
Nodes (11): codex 스킬 재작성 계획, Context, --help·에러 메시지 작성 규칙 (PR5), SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하), 검증 (전체 완료 판정), 단계 (PR별, 각 단계의 완료 판정 포함), 참고: 재사용하는 기존 코드, 최종 디렉터리 구조 (+3 more)

### Community 17 - "test_catalog.py"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 18 - "registry.py"
Cohesion: 0.13
Nodes (20): note_unreadable(), Refusals several commands share: competing selectors, a run that cannot be…, Name runs whose meta.json will not parse, so a listing they are missing from…, meta_unreadable(), The run registry: `<project>/.codex-runs/<run_id>/`. .codex-runs/ ├──…, Serialise "is this thread free?" with publishing the run that answers it,…, Present but will not parse, as distinct from absent: `read_meta` answers None…, Oldest to newest by `started_at` (millisecond resolution), the run id only… (+12 more)

### Community 20 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 21 - "core/runs.py"
Cohesion: 0.13
Nodes (21): apply_preamble(), build_argv(), The `codex exec` argv for a run, and the paragraphs put in front of its prompt.…, `-c` values are parsed as TOML, so a string value is emitted quoted., Compose the argv from a run's recorded settings, re-asserting every one on…, The caller's uncommitted work is absent from a checkout either way; only the…, Prepend the run-context paragraphs. Not optional., toml_cfg() (+13 more)

### Community 23 - "batch.py"
Cohesion: 0.17
Nodes (24): cmd_batch_start(), `batch start` and `batch clean`., claim_group(), derived_groups(), group_path(), group_unreadable(), groups_dir(), list_groups() (+16 more)

### Community 24 - "worktree.py"
Cohesion: 0.14
Nodes (28): What the caller cannot see from anywhere else about the checkouts just cut:…, worktree_report(), add(), _covered_by(), _git(), ignored_entries(), is_dirty(), missing_at_base() (+20 more)

### Community 25 - "test_argv.py"
Cohesion: 0.22
Nodes (4): build(), BuildArgv, Preamble, `codex.argv`: the argv a run hands Codex, and the paragraphs in front of its…

### Community 26 - "Precedence"
Cohesion: 0.23
Nodes (3): Precedence, `core.settings.resolve`: one precedence for every setting — the flag, then what…, resolve()

### Community 30 - "diagnose.py"
Cohesion: 0.15
Nodes (18): Drive the OpenAI Codex CLI as a managed subagent. Entrypoint and the…, _check_codex(), _check_config(), `doctor` and `models`., main(), The command-line surface: parse, dispatch, and answer in the output contract —…, codex_version(), model_catalog() (+10 more)

### Community 31 - "Layering"
Cohesion: 0.33
Nodes (4): internal_imports(), layer(), Layering, The scripts' structure: imports point one way (cli → core → codex/worktree →…

### Community 32 - "TheSkillTextPointsAtRealThings"
Cohesion: 0.17
Nodes (4): SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk(), ThroughASymlink

### Community 33 - "result_group"
Cohesion: 0.22
Nodes (10): result_group(), status_group(), changed_paths(), overlaps(), Slots that never became runs, including tasks a killed `batch start` never…, Members the manifest names that no longer resolve — a directory removed by…, Paths a run wrote, as `(repository, repo-relative path)` pairs. Codex reports…, Paths more than one run wrote, reported by path alone. Keyed by run, never by… (+2 more)

### Community 36 - "Path"
Cohesion: 0.29
Nodes (10): _flock_path(), _meta_lock(), Path, Serialise read-modify-write on one meta.json. The lock file is separate because…, A reader sees the old file or the new one, never half of one. The staging name…, Compare-and-set on `state`: merge only if the state on disk is still one of…, Hold an exclusive lock on `lock` for the body. Failing to take the lock…, update_meta_if() (+2 more)

### Community 39 - "groups.py"
Cohesion: 0.15
Nodes (20): _check_liftable_guards(), clean_group(), _member_liveness(), member_run_ids(), owned_run_ids(), Groups: `<runs_dir>/.groups/<name>.json`, the set of runs one `batch start`…, Run ids in start order, skipping slots that never spawned; `[]` for an…, Every run that says it belongs to this group, manifest order first, then runs… (+12 more)

### Community 41 - "publish_run"
Cohesion: 0.33
Nodes (6): claim_run_dir(), new_run_id(), Sortable and human-readable. Same-second, same-label ids collide about once in…, Take exclusive ownership of a fresh run directory: `mkdir` without `exist_ok`…, publish_run(), Stage 2 — under the thread's turn lock, check the thread is free, claim a run…

### Community 42 - "BridgeError"
Cohesion: 0.67
Nodes (3): BridgeError, A `fail()` raised instead of emitted. See `failures_raise`., Exception

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
- **29 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+24 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 341 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `TheSkillTextPointsAtRealThings`, `TerminalStates`, `UserDefaultsAndTheirPrecedence`, `.finished`, `ResumeFrom`, `test_cli_contract.py`, `Levels`, `wait_until`, `test_observe.py`, `harness.py`, `test_catalog.py`, `Doctor`, `WhatReachesCodex`?**
  _High betweenness centrality (0.181) - this node is a cross-community bridge._
- **Why does `WorktreeCase` connect `.finished` to `wait_until`, `BridgeCase`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `wait_until()` connect `wait_until` to `TheSkillTextPointsAtRealThings`, `.finished`, `UserDefaultsAndTheirPrecedence`, `ResumeFrom`, `BridgeCase`, `test_observe.py`, `harness.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `cmd_log()` (e.g. with `step()` and `CursorOutOfRange`) actually correct?**
  _`cmd_log()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _29 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `read_meta` be split into smaller, more focused modules?**
  _Cohesion score 0.13852813852813853 - nodes in this community are weakly interconnected._
- **Should `.finished` be split into smaller, more focused modules?**
  _Cohesion score 0.07918552036199095 - nodes in this community are weakly interconnected._