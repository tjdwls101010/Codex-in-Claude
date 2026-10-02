# Graph Report - codex in claude  (2026-10-02)

## Corpus Check
- 78 files · ~76,077 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: .jsonl 6, (none) 2)

## Summary
- 1157 nodes · 2514 edges · 70 communities (45 shown, 24 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 46 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `375f82c8`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- events.py
- .finished
- ResumeFrom
- cli.py
- codex_cli/__init__.py
- UserDefaultsAndTheirPrecedence
- Result
- Refusal
- BridgeCase
- registry/__init__.py
- git/__init__.py
- create.py
- clean.py
- ItemsAndPaths
- supervisor.py
- engine
- test_structure.py
- test_cli_contract.py
- run_e2e.py
- alive
- WhatReachesCodex
- Settings Precedence Tests
- TopLevelValues
- test_argv.py
- Model Catalog Checks
- batch/commands.py
- Doctor Diagnostics Tests
- RealCodex
- ExitCodes
- TheSkillTextPointsAtRealThings
- argv.py
- codex
- TheNextStep
- clip
- test_registry_races.py
- HelpIsTheInterface
- Cursors
- Stale Run Reaping
- runs/commands.py
- test_run_lifecycle.py
- DamagedLines
- status.py
- TheLadderOrder
- codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비
- Codex Skill Guidance
- Codex in Claude Features
- Release History
- Listing
- codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비
- Code of Conduct
- Security Policy
- Graph Navigation Workflow
- JsonArgumentParser
- wait_until
- iter_runs
- Codex Package Init
- SelectorsAreExclusive
- codex 스킬 재작성 계획
- AnOrphanThatIsStillWriting
- Contribution Guidelines
- S6 Scenarios
- Graphify Codebase Navigation
- Contribution Verification Tiers
- LegacyWaitingRun
- result.py
- AnOlderReleasesRegistry
- OneLinePerParagraph
- test_observe.py
- APidAnotherProcessNowHolds

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 75 edges
2. `Refusal` - 57 edges
3. `wait_until()` - 32 edges
4. `Clean` - 27 edges
5. `alive()` - 25 edges
6. `resolve_project()` - 23 edges
7. `iter_runs()` - 23 edges
8. `find_run()` - 23 edges
9. `engine()` - 23 edges
10. `WaitingForTheResult` - 22 edges

## Surprising Connections (you probably didn't know these)
- `build_parser()` --indirect_call--> `clean()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/batch/commands.py
- `build_parser()` --indirect_call--> `models()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/doctor.py
- `build_parser()` --indirect_call--> `show()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/observe/show.py
- `build_parser()` --indirect_call--> `start()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/runs/commands.py
- `main()` --uses--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py

## Import Cycles
- None detected.

## Communities (70 total, 24 thin omitted)

### Community 0 - "events.py"
Cohesion: 0.08
Nodes (42): changed_paths(), CursorOutOfRange, find_item(), first_thread_id(), format_events(), _format_item(), head_tail(), _indent() (+34 more)

### Community 1 - ".finished"
Cohesion: 0.06
Nodes (11): Clean, Overlaps, `batch --worktree`: which members get a checkout, what the checkout holds, how…, A checkout is `git worktree add` output: tracked files at the base commit and…, This CLI's own call for `words`, written out whole the way the pre-approval…, Run a command a reply handed back, as the caller would: exactly as written,…, Codex reports absolute paths, and each checkout has its own prefix, so paths…, Append a file_change naming these absolute paths, the shape real events have. (+3 more)

### Community 2 - "ResumeFrom"
Cohesion: 0.09
Nodes (9): AMalformedRegistry, BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting (+1 more)

### Community 3 - "cli.py"
Cohesion: 0.11
Nodes (28): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_batch(), cmd_log(), cmd_result(), cmd_resume() (+20 more)

### Community 4 - "codex_cli/__init__.py"
Cohesion: 0.10
Nodes (32): codex_version(), model_catalog(), This install's model catalog, read from `codex debug models`, and the pre-spawn…, What `codex --version` prints, or None when there is no codex or it prints…, What this Codex install offers, trimmed to the fields a caller chooses from, or…, codex_home(), config_scalars(), config_summary() (+24 more)

### Community 5 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.08
Nodes (10): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted (+2 more)

### Community 6 - "Result"
Cohesion: 0.18
Nodes (3): answer_fixture(), A --schema run's `result`: one JSON document over however many lines, indented…, Result

### Community 7 - "Refusal"
Cohesion: 0.13
Nodes (22): event_lines(), The events after byte offset `since` rendered at `level`, paths shown relative…, The one way a command says no, from anywhere below the command surface:…, A command refused, or failed, for a reason the caller can act on. `error` is…, Refusal, follow(), GroupWatch, The loop every `--follow` runs, the closing line a group's follow ends on, and… (+14 more)

### Community 8 - "BridgeCase"
Cohesion: 0.07
Nodes (15): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded). (+7 more)

### Community 9 - "registry/__init__.py"
Cohesion: 0.18
Nodes (20): The run registry, the one store this skill keeps: `<project>/.codex-…, claim_run_dir(), new_run_id(), publish_run(), Path, Run records: one directory per run, its `meta.json` the run's settings and…, Merge `fields` only while the run is still in an active state on disk, and…, Compare-and-set on `state`: merge only if the state on disk is still one of… (+12 more)

### Community 10 - "git/__init__.py"
Cohesion: 0.08
Nodes (46): plan_worktrees(), reasons_for(), Isolation for a batch: which members get a git checkout of their own, cut from…, Whether `--worktree` would isolate this member: a fresh writer with no cwd of…, Why `--worktree` would pass this member over, in the caller's words, or None., Members that will write, grouped by the directory they will write in, resolved…, Who is about to write into one directory, and — only where it would work — the…, Which members get a checkout, cut from which commit, and a note when members… (+38 more)

### Community 11 - "create.py"
Cohesion: 0.21
Nodes (12): check_model_effort(), Refuse a model or effort this install does not offer. Callers pass only values…, `{model, effort, service_tier}` from the user's config.toml, read fresh on…, user_defaults(), Path, Building a run: `start`, `resume` and every batch member go through…, Stage 1 — what this run will be. Nothing here writes or claims anything, so a…, read_prompt() (+4 more)

### Community 12 - "clean.py"
Cohesion: 0.10
Nodes (47): _check_liftable_guards(), clean_group(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The `stop` calls that end these runs, each written out whole the way `next` is,…, Remove a group's worktrees and release its name when nothing is left behind.…, `(live members, members whose meta.json will not parse)` — unknown is kept…, The refusals `--force` lifts, in check order; returns what was overridden,… (+39 more)

### Community 13 - "ItemsAndPaths"
Cohesion: 0.07
Nodes (8): EventLines, ItemsAndPaths, Levels, An event file holding these events built by hand, one JSON line each., `codex.codex_cli.event_lines` on events built by hand, one kind at a time., `codex.codex_cli`'s readers that hand `show`, `status` and `result` an item,…, Show, stream()

### Community 14 - "supervisor.py"
Cohesion: 0.20
Nodes (12): end_group(), Path, The detached supervisor that runs Codex and records its outcome, and the signal…, Start the run's supervisor in a new session, re-executing the entrypoint.…, SIGINT, then SIGTERM, then SIGKILL to a process group, then a SIGKILL sweep,…, End one run through its process group and record `interrupted` — compare-and-…, Spawn Codex, record what happened, exit. Runs as its own process., spawn_supervised() (+4 more)

### Community 15 - "engine"
Cohesion: 0.16
Nodes (9): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import a unit's interface (`"codex.runs"`, `"codex.registry"`, …) from the…, `codex.codex_cli`'s `user_defaults` and `config_summary`: the top-level values…, LoginStatus, `doctor`: one line describing the environment a run would start in, exit 2 when…, `codex.codex_cli.login_status`, asked of the fake codex: the cause says which…, Reading a run's event stream: exact cursors, damaged lines that are counted… (+1 more)

### Community 16 - "test_structure.py"
Cohesion: 0.07
Nodes (36): all_violations(), call_name(), declared_all(), dotted(), imported_unit(), imports(), inner_modules(), interface_violations() (+28 more)

### Community 17 - "test_cli_contract.py"
Cohesion: 0.12
Nodes (7): FlagsThatWouldDecideNothing, OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, A flag that parses and changes nothing reads as having been obeyed, so each is…, Flags nothing used, removed from the parser rather than left to accept and do…, RemovedSurface, TheRegistryGoesWhereItIsTold

### Community 18 - "run_e2e.py"
Cohesion: 0.18
Nodes (17): base_cmd(), calls_to_result(), control_text(), digest(), entry(), main(), Path, A session whose stdin stays open, so a finished background task can start… (+9 more)

### Community 21 - "Settings Precedence Tests"
Cohesion: 0.23
Nodes (3): Precedence, `codex.runs.settings_for`: one precedence for every setting — the flag, then…, resolve()

### Community 23 - "test_argv.py"
Cohesion: 0.20
Nodes (4): build(), BuildArgv, Preamble, `codex.codex_cli`'s `build_argv` and `apply_preamble`: the argv a run hands…

### Community 24 - "Model Catalog Checks"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 25 - "batch/commands.py"
Cohesion: 0.12
Nodes (23): batch(), `batch` and `clean`, and the `next` a batch's reply names., The group name's rule and `--base` without `--worktree` are the command…, Several runs as one group: `batch` and `clean`. A batch is N runs, so it builds…, Spawning a batch: each member's slot recorded before it starts, each member…, Start one member, as `start` or `resume` would. A resume target outside the…, Spawn every task in order. A member that fails keeps its slot with the error,…, spawn_members() (+15 more)

### Community 27 - "RealCodex"
Cohesion: 0.29
Nodes (4): skipUnless, S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, What the reply's `next` prints once the run has ended — `result --run <id>…, RealCodex

### Community 28 - "ExitCodes"
Cohesion: 0.24
Nodes (3): BatchAndCleanAreCommandsOfTheirOwn, ExitCodes, 0 success; 2 the command line itself must change, answered as JSON with the…

### Community 29 - "TheSkillTextPointsAtRealThings"
Cohesion: 0.16
Nodes (6): The call SKILL.md teaches, through the link, from a directory unrelated to the…, SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk(), ThroughASymlink, finished()

### Community 30 - "argv.py"
Cohesion: 0.24
Nodes (9): apply_preamble(), build_argv(), The `codex exec` argv for a run, and the paragraphs put in front of its prompt.…, `-c` values are parsed as TOML, so a string value is emitted quoted., Compose the argv from a run's recorded settings, re-asserting every one on…, The caller's uncommitted work is absent from a checkout either way; only the…, Prepend the run-context paragraphs. Not optional., toml_cfg() (+1 more)

### Community 31 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 33 - "clip"
Cohesion: 0.19
Nodes (14): Run directories `iter_runs` had to skip, so a listing missing them can say so., unreadable_runs(), publish(), check(), make_meta(), Stage 2 — under the thread's turn lock, check the thread is free, claim a run…, The thread a run with an unparseable meta.json was on, recovered from its event…, Refuse a second live turn on one thread — two turns would append to one rollout… (+6 more)

### Community 34 - "test_registry_races.py"
Cohesion: 0.13
Nodes (12): AFailureInsideALockIsReportedAsItself, ManyRunsAtOnce, ManyWritersOneMeta, OnePublishPerThreadCheck, _publish_on_one_thread(), check(), The registry under real concurrent processes: many writers on one meta.json, a…, One contender: publish a run on thread `t` unless one is already there — the… (+4 more)

### Community 38 - "runs/commands.py"
Cohesion: 0.23
Nodes (12): clean(), The project a command works on: the git top level of `explicit`, or of the…, resolve_project(), `show`: one run-scoped item in full — a command's output, capped and with the…, show(), resolve_runs_dir(), follow_up(), `start`, `resume` and `stop`, and the `next` a started run's reply names. (+4 more)

### Community 39 - "test_run_lifecycle.py"
Cohesion: 0.15
Nodes (4): DetachedStart, A run's life: detached start, every terminal state, the stop ladder, and what a…, Signals go to the run's recorded process group, SIGINT first, escalating only…, StopLadder

### Community 41 - "status.py"
Cohesion: 0.17
Nodes (20): closing_line(), The counts a group's closing line appends when non-zero., The line a group's follow ends on., tail(), step(), take(), group_snapshot(), note_unreadable() (+12 more)

### Community 43 - "codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비"
Cohesion: 0.12
Nodes (15): cli.py의 계약, codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비, Context, SKILL.md 섹션 구조 (PR ③ 이후, 한 파일), test_structure.py가 확인하는 것, 검증 (전체), 단계 (PR별, 완료 판정), 모듈 이전 표 (현재 → 새 위치) (+7 more)

### Community 44 - "Codex Skill Guidance"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 45 - "Codex in Claude Features"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 46 - "Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 48 - "codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비"
Cohesion: 0.12
Nodes (15): codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비, Context, skill-maker 프레임 대조 (구현 완료 판정에 그대로 씀), SKILL.md 섹션 구조 (PR ③, 한 파일), test_structure.py v2가 확인하는 것, 검증 (전체), 구현 후 디렉터리 구조, 단계 (PR별, 완료 판정) (+7 more)

### Community 49 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 50 - "Security Policy"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

### Community 53 - "wait_until"
Cohesion: 0.13
Nodes (3): wait_until(), `result --wait` waits for the end, then prints exactly what `result` would;…, WaitingForTheResult

### Community 54 - "iter_runs"
Cohesion: 0.29
Nodes (8): iter_runs(), live_runs(), Oldest to newest by `started_at` (millisecond resolution), the run id only…, Yield (run_dir, meta) oldest first, skipping runs whose meta.json will not…, `(run_dir, meta)` of each run that is live once reaped, oldest first: of…, run_sort_key(), concurrent_writers(), Other live runs that can write in or around this directory — reported, never…

### Community 57 - "codex 스킬 재작성 계획"
Cohesion: 0.17
Nodes (11): codex 스킬 재작성 계획, Context, --help·에러 메시지 작성 규칙 (PR5), SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하), 검증 (전체 완료 판정), 단계 (PR별, 각 단계의 완료 판정 포함), 참고: 재사용하는 기존 코드, 최종 디렉터리 구조 (+3 more)

### Community 65 - "result.py"
Cohesion: 0.13
Nodes (28): final_message(), member_result(), overlaps(), Collecting a group: what each member concluded and which paths more than one…, What a run concluded: its `-o` file decoded as UTF-8 (a byte that is not,…, One member of `result --group`: its row and the part of its message that is…, Paths more than one run wrote, reported by path alone. Keyed by run, never by…, Ask `ended()` every FOLLOW_INTERVAL until it holds or `timeout` seconds have… (+20 more)

### Community 68 - "test_observe.py"
Cohesion: 0.14
Nodes (3): GroupResult, What `status` and `result` say about runs: progress while live, the answer once…, StatusOfOneRun

## Knowledge Gaps
- **54 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+49 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 481 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `.finished`, `ResumeFrom`, `UserDefaultsAndTheirPrecedence`, `Result`, `ItemsAndPaths`, `engine`, `test_cli_contract.py`, `alive`, `WhatReachesCodex`, `Model Catalog Checks`, `Doctor Diagnostics Tests`, `ExitCodes`, `TheSkillTextPointsAtRealThings`, `TheNextStep`, `test_registry_races.py`, `HelpIsTheInterface`, `Cursors`, `test_run_lifecycle.py`, `DamagedLines`, `status.py`, `Listing`, `wait_until`, `SelectorsAreExclusive`, `AnOrphanThatIsStillWriting`, `LegacyWaitingRun`, `AnOlderReleasesRegistry`, `test_observe.py`, `APidAnotherProcessNowHolds`?**
  _High betweenness centrality (0.479) - this node is a cross-community bridge._
- **Why does `check()` connect `clip` to `status.py`, `Refusal`?**
  _High betweenness centrality (0.263) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Refusal` to `result.py`, `clip`, `cli.py`, `codex_cli/__init__.py`, `runs/commands.py`, `registry/__init__.py`, `git/__init__.py`, `create.py`, `clean.py`, `batch/commands.py`?**
  _High betweenness centrality (0.182) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _54 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `events.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07505285412262157 - nodes in this community are weakly interconnected._
- **Should `.finished` be split into smaller, more focused modules?**
  _Cohesion score 0.06293706293706294 - nodes in this community are weakly interconnected._