# Graph Report - codex in claude  (2026-10-09)

## Corpus Check
- 78 files · ~82,321 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: .jsonl 7, (none) 2)

## Summary
- 1198 nodes · 2494 edges · 74 communities (47 shown, 26 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 43 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4a7fd702`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- events.py
- .finished
- test_batch.py
- cli.py
- codex_cli/__init__.py
- UserDefaultsAndTheirPrecedence
- Result
- result.py
- BridgeCase
- runs.py
- git/__init__.py
- codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를
- clean.py
- test_events.py
- rows.py
- DamagedLines
- test_structure.py
- test_cli_contract.py
- run_e2e.py
- TerminalStates
- WhatReachesCodex
- resolve
- TopLevelValues
- build
- test_catalog.py
- batch/commands.py
- Doctor
- RealCodex
- ExitCodes
- TheSkillTextPointsAtRealThings
- LoginStatus
- codex
- TheNextStep
- Refusal
- engine
- HelpIsTheInterface
- resolve_settings
- AStaleReap
- registry/__init__.py
- StopLadder
- worktrees.py
- runs/__init__.py
- TheLadderOrder
- codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비
- Codex Managed Subagent Skill
- Codex in Claude
- Codex-in-Claude Release History
- Listing
- codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비
- Community Impact Enforcement Ladder
- Private Vulnerability Reporting
- Graph-First Navigation
- JsonArgumentParser
- WaitingForTheResult
- GroupResult
- codex/__init__.py
- EventLines
- codex 스킬 재작성 계획
- wait_until
- Scoped Contribution Workflow
- scenarios.md
- Graphify-First Codebase Navigation
- Tiered Contribution Verification
- .detached_process
- collect.py
- doctor.py
- OneLinePerParagraph
- test_observe.py
- resolve_project
- AStateThatMovesWhileItIsRead
- _check_codex
- ReadOnlyAndTheCodexVersion
- APidAnotherProcessNowHolds

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 79 edges
2. `Refusal` - 45 edges
3. `wait_until()` - 30 edges
4. `Clean` - 28 edges
5. `engine()` - 25 edges
6. `alive()` - 24 edges
7. `resolve_project()` - 21 edges
8. `result()` - 21 edges
9. `group_view()` - 21 edges
10. `find_run()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `build_parser()` --indirect_call--> `batch()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/batch/commands.py
- `build_parser()` --indirect_call--> `clean()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/batch/commands.py
- `build_parser()` --indirect_call--> `log()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/observe/log.py
- `build_parser()` --indirect_call--> `status()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/observe/status.py
- `build_parser()` --indirect_call--> `start()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/runs/commands.py

## Import Cycles
- None detected.

## Communities (74 total, 26 thin omitted)

### Community 0 - "events.py"
Cohesion: 0.15
Nodes (24): changed_paths(), event_lines(), first_thread_id(), _format_item(), head_tail(), _indent(), Path, Reading what a run's Codex wrote: the `codex exec --json` event stream,… (+16 more)

### Community 1 - ".finished"
Cohesion: 0.06
Nodes (13): make_meta(), Clean, Overlaps, `batch --worktree`: which members get a checkout, what the checkout holds, how…, A checkout is `git worktree add` output: tracked files at the base commit and…, This CLI's own call for `words`, written out whole the way the pre-approval…, Run a command a reply handed back, as the caller would: exactly as written,…, A batch that continues each member of an earlier one: a tasks file with one… (+5 more)

### Community 2 - "test_batch.py"
Cohesion: 0.09
Nodes (12): AMalformedRegistry, BatchCase, NextRound, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, A read-only member is a read-only run: it gets the profile that writes scratch,…, A next round is a batch whose tasks resume the earlier members' threads, one…, A batch that continues each member of an earlier one: a tasks file with one… (+4 more)

### Community 3 - "cli.py"
Cohesion: 0.11
Nodes (28): add_common(), add_run_options(), build_parser(), cmd_result(), cmd_resume(), doctor_reply(), group_name(), main() (+20 more)

### Community 4 - "codex_cli/__init__.py"
Cohesion: 0.10
Nodes (28): apply_preamble(), build_argv(), The `codex exec` argv for a run, and the paragraphs put in front of its prompt.…, The caller's uncommitted work is absent from a checkout either way; only the…, Prepend the run-context paragraphs. Not optional., `-c` values are parsed as TOML, so a string value is emitted quoted., A TOML basic string: a path can hold a quote, a backslash or a control…, Read everything, write only TMPDIR and ~/.cache, network off. The run's own… (+20 more)

### Community 5 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.07
Nodes (14): The `-c` entries a read-only run that can write scratch hands Codex, as…, read_only_profile(), FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A read-only run can run tests and builds: it reads anything and writes only…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's… (+6 more)

### Community 6 - "Result"
Cohesion: 0.20
Nodes (3): answer_fixture(), A --schema run's `result`: one JSON document over however many lines, indented…, Result

### Community 7 - "result.py"
Cohesion: 0.15
Nodes (16): The one way a command says no, from anywhere below the command surface:…, GroupWatch, The silent wait `result --wait` makes, and a group as that wait sees it look by…, Ask `ended()` every FOLLOW_INTERVAL until it holds or `timeout` seconds have…, A group as a wait sees it, look by look: its members' rows and the slots no row…, `(members, gaps)` as they stand: members as `(run_dir, meta)`, in start order., `(rows, gaps)` as they stand, each row reaped., wait_until() (+8 more)

### Community 8 - "BridgeCase"
Cohesion: 0.06
Nodes (18): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, its closing line)., Every codex invocation the bridge made, in order (catalog lookups excluded)., The `-c key=value` entries of an argv, as a dict of raw values., A --tasks-file; a bare string is a `{"prompt": ...}` task. (+10 more)

### Community 9 - "runs.py"
Cohesion: 0.15
Nodes (20): flock(), meta_lock(), Path, Cross-process locks on registry files, and the atomic JSON write every registry…, Hold an exclusive lock on `lock` for the body. Failing to take the lock…, Serialise "is this thread free?" with publishing the run that answers it,…, Serialise read-modify-write on one meta.json. The lock file is separate because…, A reader sees the old file or the new one, never half of one. The staging name… (+12 more)

### Community 10 - "git/__init__.py"
Cohesion: 0.13
Nodes (31): The git CLI: repository questions and the worktrees a batch cuts. A git…, _covered_by(), ignored_entries(), is_dirty(), missing_at_base(), Path, What the git CLI says about a repository: its top level, its identity, a…, Files that differ from HEAD in the caller's tree, or None if git would not say… (+23 more)

### Community 11 - "codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를"
Cohesion: 0.12
Nodes (15): codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를, Context, skill-maker 프레임 대조 (완료 판정에 그대로 씀), SKILL.md 섹션 구조 (한 파일, 영어), 검증 (전체), 계획 리뷰 기록, 구현 후 디렉터리 구조, 단계 (PR별, 완료 판정) (+7 more)

### Community 12 - "clean.py"
Cohesion: 0.10
Nodes (46): _check_liftable_guards(), clean_group(), continued_by(), member_checkouts(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The refusals `--force` lifts, in check order; returns what was overridden,…, The `stop` calls that end these runs, each written out whole the way `next` is,… (+38 more)

### Community 13 - "test_events.py"
Cohesion: 0.11
Nodes (8): AHalfWrittenLine, ItemsAndPaths, Reading a run's event stream: damaged lines that are counted rather than…, An event file holding these events built by hand, one JSON line each., `codex.codex_cli`'s readers that hand `status` and `result` the changed paths…, `log` is one look at what a run did: every command with its exit code and…, stream(), WhatLogPrints

### Community 14 - "rows.py"
Cohesion: 0.16
Nodes (17): Watching and collecting runs: `status` and `result` for one run and for a…, log(), `log`: what one run did, read once from its events., group_snapshot(), note_unreadable(), Describing runs and groups: the status row and its summary, the turn-failure…, `(running, done, failed, group_state)` — the one place group state is derived,…, What the default listing shows of a run, from a row built with a 160-character… (+9 more)

### Community 16 - "test_structure.py"
Cohesion: 0.07
Nodes (36): all_violations(), call_name(), declared_all(), dotted(), imported_unit(), imports(), inner_modules(), interface_violations() (+28 more)

### Community 17 - "test_cli_contract.py"
Cohesion: 0.10
Nodes (8): BatchAndCleanAreCommandsOfTheirOwn, OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, Two selectors name different things; honouring one silently drops the other., Flags nothing used, removed from the parser rather than left to accept and do…, RemovedSurface, SelectorsAreExclusive, TheRegistryGoesWhereItIsTold

### Community 18 - "run_e2e.py"
Cohesion: 0.18
Nodes (17): base_cmd(), calls_to_result(), control_text(), digest(), entry(), main(), Path, A session whose stdin stays open, so a finished background task can start… (+9 more)

### Community 21 - "resolve"
Cohesion: 0.15
Nodes (5): Precedence, `codex.runs.settings_for`: one precedence for every setting — the flag, then…, Which read-only a run gets. `scratch` writes TMPDIR and ~/.cache, so tests and…, ReadOnlyMarker, resolve()

### Community 23 - "build"
Cohesion: 0.15
Nodes (5): build(), BuildArgv, Preamble, `codex.codex_cli`'s `build_argv` and `apply_preamble`: the argv a run hands…, ReadOnlyProfile

### Community 24 - "test_catalog.py"
Cohesion: 0.10
Nodes (8): ABrokenLookupNeverBlocksARun, BelowTheIsolationFloor, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…, Every isolated run passes `--ignore-user-config`; a Codex without it fails the…, `codex.codex_cli.support_for`: what a `codex --version` line says this install…, VersionFloors

### Community 25 - "batch/commands.py"
Cohesion: 0.12
Nodes (24): batch(), clean(), `batch` and `clean`, and the `next` a batch's reply names., The group name's rule is the command surface's to refuse, before this is called., Several runs as one group: `batch` and `clean`. A batch is N runs, so it builds…, Spawning a batch: each member's slot recorded before it starts, each member…, Start one member, as `start` or `resume` would. A resume target outside the…, Spawn every task in order. A member that fails keeps its slot with the error,… (+16 more)

### Community 27 - "RealCodex"
Cohesion: 0.18
Nodes (7): skipUnless, is_within(), S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, What the reply's `next` prints once the run has ended — `result --run <id>…, The text of every tool output the rollout recorded, as Codex itself saw it., A turn's permission profile as (entry → access, network)., RealCodex

### Community 28 - "ExitCodes"
Cohesion: 0.22
Nodes (4): ExitCodes, A command or flag 0.11 removed is refused like any command line that must…, 0 success; 2 the command line itself must change, answered as JSON with the…, TheSurfaceRemovedIn011

### Community 29 - "TheSkillTextPointsAtRealThings"
Cohesion: 0.16
Nodes (6): The call SKILL.md teaches, through the link, from a directory unrelated to the…, SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk(), ThroughASymlink, finished()

### Community 31 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 33 - "Refusal"
Cohesion: 0.12
Nodes (26): A command refused, or failed, for a reason the caller can act on. `error` is…, Refusal, ensure_runs_dir(), publish_run(), Run directories `iter_runs` had to skip, so a listing missing them can say so., Publish a new run under its thread's turn lock: `check()` may refuse while the…, Whether this run's Codex process is still going, whatever its state says.…, still_writing() (+18 more)

### Community 34 - "engine"
Cohesion: 0.13
Nodes (15): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import a unit's interface (`"codex.runs"`, `"codex.registry"`, …) from the…, `codex.codex_cli`'s `user_defaults` and `config_summary`: the top-level values…, `doctor`: one line describing the environment a run would start in, exit 2 when…, Installs: the skill reached through a symlink, from a directory that has…, ManyWritersOneMeta, OnePublishPerThreadCheck (+7 more)

### Community 36 - "resolve_settings"
Cohesion: 0.16
Nodes (17): model_catalog(), What this Codex install offers, trimmed to the fields a caller chooses from, or…, codex_home(), config_scalars(), config_summary(), Path, CODEX_HOME and the few top-level values this skill reads from the user's…, CODEX_HOME when set, resolved — sessions, config and auth all move with it —… (+9 more)

### Community 38 - "registry/__init__.py"
Cohesion: 0.15
Nodes (21): group_runs(), The members of `group_view`: `(run_dir, meta)` in start order; refuses an…, The run registry, the one store this skill keeps: `<project>/.codex-…, live_runs(), meta_unreadable(), Path, Merge `fields` only while the run is still in an active state on disk, and…, `(run_dir, meta)` of each run that is live once reaped, oldest first: of… (+13 more)

### Community 40 - "worktrees.py"
Cohesion: 0.21
Nodes (12): plan_worktrees(), reasons_for(), Isolation for a batch: which members get a git checkout of their own, cut from…, Whether `--worktree` would isolate this member: a fresh writer with no cwd of…, Why `--worktree` would pass this member over, in the caller's words, or None., Members that will write, grouped by the directory they will write in, resolved…, Who is about to write into one directory, and — only where it would work — the…, Which members get a checkout, cut from HEAD, and a note when members will share… (+4 more)

### Community 41 - "runs/__init__.py"
Cohesion: 0.20
Nodes (9): Running a turn: what a run will be (settings), building and publishing it…, What a run will be: one precedence for every setting, used by `start`,…, Resolve a run's settings from the caller's flags, the run it continues (`base`,…, settings_for(), end_group(), SIGINT, then SIGTERM, then SIGKILL to a process group, then a SIGKILL sweep,…, Spawn Codex, record what happened, exit. Runs as its own process., supervise() (+1 more)

### Community 43 - "codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비"
Cohesion: 0.12
Nodes (15): cli.py의 계약, codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비, Context, SKILL.md 섹션 구조 (PR ③ 이후, 한 파일), test_structure.py가 확인하는 것, 검증 (전체), 단계 (PR별, 완료 판정), 모듈 이전 표 (현재 → 새 위치) (+7 more)

### Community 44 - "Codex Managed Subagent Skill"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 45 - "Codex in Claude"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 46 - "Codex-in-Claude Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 48 - "codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비"
Cohesion: 0.12
Nodes (15): codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비, Context, skill-maker 프레임 대조 (구현 완료 판정에 그대로 씀), SKILL.md 섹션 구조 (PR ③, 한 파일), test_structure.py v2가 확인하는 것, 검증 (전체), 구현 후 디렉터리 구조, 단계 (PR별, 완료 판정) (+7 more)

### Community 49 - "Community Impact Enforcement Ladder"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 50 - "Private Vulnerability Reporting"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

### Community 57 - "codex 스킬 재작성 계획"
Cohesion: 0.17
Nodes (11): codex 스킬 재작성 계획, Context, --help·에러 메시지 작성 규칙 (PR5), SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하), 검증 (전체 완료 판정), 단계 (PR별, 각 단계의 완료 판정 포함), 참고: 재사용하는 기존 코드, 최종 디렉터리 구조 (+3 more)

### Community 58 - "wait_until"
Cohesion: 0.13
Nodes (5): alive(), wait_until(), AnOrphanThatIsStillWriting, LegacyWaitingRun, Releases before 0.8 could leave a batch member `waiting` on its predecessor.…

### Community 63 - ".detached_process"
Cohesion: 0.27
Nodes (4): writer(), A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, A run that moves while a view reads `path`. Read i of it is a FIFO held open…

### Community 65 - "collect.py"
Cohesion: 0.13
Nodes (22): final_message(), member_result(), read(), overlaps(), Path, Collecting a group: what each member concluded and which paths more than one…, Paths a run wrote, as `(repository, repo-relative path)` pairs. Codex reports…, A run's `-o` file as written, or None when there is none yet. (+14 more)

### Community 66 - "doctor.py"
Cohesion: 0.33
Nodes (7): _check_registry(), _overlapping_writers(), `doctor` and `models`: the environment a run would start in, and the models…, Live runs whose recorded cwds overlap (either inside the other), where at least…, is_within(), Primitives with no knowledge of runs, events or Codex: time, text, paths,…, Whether `path` is `parent` or lives inside it, compared in NFC.

### Community 68 - "test_observe.py"
Cohesion: 0.17
Nodes (4): AnOlderReleasesRegistry, What `status` and `result` say about runs: progress while live, the answer once…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, StatusOfOneRun

### Community 69 - "resolve_project"
Cohesion: 0.25
Nodes (9): doctor(), git_toplevel(), The project a command works on: the git top level of `explicit`, or of the…, resolve_project(), follow_up(), The reply with its `next`: the call that waits for the run it made and prints…, `args.ref` and `args.prompt` arrive split out of `resume REF [PROMPT]` by the…, resume() (+1 more)

### Community 71 - "_check_codex"
Cohesion: 0.40
Nodes (4): login_status(), `codex login status`: whether this install can authenticate, read from how that…, `{ok, cause, detail}`. `cause` is `authenticated`; `unauthenticated`;…, _check_codex()

## Knowledge Gaps
- **68 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+63 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 501 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `.finished`, `test_batch.py`, `UserDefaultsAndTheirPrecedence`, `Result`, `test_events.py`, `DamagedLines`, `test_cli_contract.py`, `TerminalStates`, `WhatReachesCodex`, `test_catalog.py`, `Doctor`, `ExitCodes`, `TheSkillTextPointsAtRealThings`, `TheNextStep`, `engine`, `HelpIsTheInterface`, `StopLadder`, `Listing`, `WaitingForTheResult`, `GroupResult`, `wait_until`, `.detached_process`, `test_observe.py`, `AStateThatMovesWhileItIsRead`, `ReadOnlyAndTheCodexVersion`, `APidAnotherProcessNowHolds`?**
  _High betweenness centrality (0.484) - this node is a cross-community bridge._
- **Why does `check()` connect `Refusal` to `BridgeCase`?**
  _High betweenness centrality (0.296) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Refusal` to `doctor.py`, `cli.py`, `codex_cli/__init__.py`, `resolve_project`, `registry/__init__.py`, `result.py`, `resolve_settings`, `runs.py`, `clean.py`, `batch/commands.py`?**
  _High betweenness centrality (0.196) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _68 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `events.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14666666666666667 - nodes in this community are weakly interconnected._
- **Should `.finished` be split into smaller, more focused modules?**
  _Cohesion score 0.06095481670929241 - nodes in this community are weakly interconnected._