# Graph Report - codex in claude  (2026-10-02)

## Corpus Check
- 78 files · ~74,867 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: .jsonl 6, (none) 2)

## Summary
- 1155 nodes · 2511 edges · 64 communities (46 shown, 17 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 46 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `44ebdcfa`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- codex_cli/__init__.py
- .finished
- ResumeFrom
- Refusal
- doctor.py
- UserDefaultsAndTheirPrecedence
- Result
- read_meta
- BridgeCase
- runs.py
- git/__init__.py
- test_resume.py
- registry/__init__.py
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
- util.py
- Doctor Diagnostics Tests
- Real Codex Smoke Tests
- ExitCodes
- TheSkillTextPointsAtRealThings
- create.py
- codex
- TheNextStep
- clip
- AFailureInsideALockIsReportedAsItself
- HelpIsTheInterface
- Cursors
- Stale Run Reaping
- runs/commands.py
- codex_home
- DamagedLines
- log.py
- TheLadderOrder
- codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비
- Codex Skill Guidance
- Codex in Claude Features
- Release History
- ThroughASymlink
- codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비
- Code of Conduct
- Security Policy
- Graph Navigation Workflow
- JsonArgumentParser
- wait_until
- Codex Package Init
- codex 스킬 재작성 계획
- Contribution Guidelines
- S6 Scenarios
- Graphify Codebase Navigation
- Contribution Verification Tiers
- result.py
- OneLinePerParagraph
- test_observe.py

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
- `build_parser()` --indirect_call--> `stop()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/runs/commands.py

## Import Cycles
- None detected.

## Communities (64 total, 17 thin omitted)

### Community 0 - "codex_cli/__init__.py"
Cohesion: 0.13
Nodes (28): changed_paths(), CursorOutOfRange, event_lines(), find_item(), format_events(), _format_item(), head_tail(), _indent() (+20 more)

### Community 1 - ".finished"
Cohesion: 0.06
Nodes (10): Clean, Overlaps, A checkout is `git worktree add` output: tracked files at the base commit and…, This CLI's own call for `words`, written out whole the way the pre-approval…, Run a command a reply handed back, as the caller would: exactly as written,…, Codex reports absolute paths, and each checkout has its own prefix, so paths…, Append a file_change naming these absolute paths, the shape real events have., WhatACheckoutHolds (+2 more)

### Community 2 - "ResumeFrom"
Cohesion: 0.09
Nodes (7): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 3 - "Refusal"
Cohesion: 0.13
Nodes (27): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_batch(), cmd_log(), cmd_result(), cmd_resume() (+19 more)

### Community 4 - "doctor.py"
Cohesion: 0.12
Nodes (23): codex_version(), model_catalog(), This install's model catalog, read from `codex debug models`, and the pre-spawn…, What `codex --version` prints, or None when there is no codex or it prints…, What this Codex install offers, trimmed to the fields a caller chooses from, or…, `{model, effort, service_tier}` from the user's config.toml, read fresh on…, user_defaults(), login_status() (+15 more)

### Community 5 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.12
Nodes (4): FindingTheThread, An explicit flag, then what a resumed thread recorded, then the user's…, SettingsAreReasserted, UserDefaultsAndTheirPrecedence

### Community 6 - "Result"
Cohesion: 0.09
Nodes (6): answer_fixture(), GroupResult, Listing, `n` finished runs written straight into the registry, all the same shape so…, A --schema run's `result`: one JSON document over however many lines, indented…, Result

### Community 7 - "read_meta"
Cohesion: 0.32
Nodes (6): `(members, gaps)` as they stand: members as `(run_dir, meta)`, in start order., `(rows, gaps)` as they stand, each row reaped., log(), dump(), step(), read_meta()

### Community 8 - "BridgeCase"
Cohesion: 0.06
Nodes (17): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded). (+9 more)

### Community 9 - "runs.py"
Cohesion: 0.15
Nodes (22): A reader sees the old file or the new one, never half of one. The staging name…, write_json_atomic(), claim_run_dir(), ensure_runs_dir(), iter_runs(), live_runs(), new_run_id(), publish_run() (+14 more)

### Community 10 - "git/__init__.py"
Cohesion: 0.09
Nodes (44): plan_worktrees(), reasons_for(), Isolation for a batch: which members get a git checkout of their own, cut from…, Whether `--worktree` would isolate this member: a fresh writer with no cwd of…, Why `--worktree` would pass this member over, in the caller's words, or None., Members that will write, grouped by the directory they will write in, resolved…, Who is about to write into one directory, and — only where it would work — the…, Which members get a checkout, cut from which commit, and a note when members… (+36 more)

### Community 11 - "test_resume.py"
Cohesion: 0.17
Nodes (6): OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, ResumeCase, ThreadsTheRegistryNeverSaw

### Community 12 - "registry/__init__.py"
Cohesion: 0.06
Nodes (74): _check_liftable_guards(), clean_group(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The `stop` calls that end these runs, each written out whole the way `next` is,…, Remove a group's worktrees and release its name when nothing is left behind.…, `(live members, members whose meta.json will not parse)` — unknown is kept…, The refusals `--force` lifts, in check order; returns what was overridden,… (+66 more)

### Community 13 - "ItemsAndPaths"
Cohesion: 0.07
Nodes (8): EventLines, ItemsAndPaths, Levels, An event file holding these events built by hand, one JSON line each., `codex.codex_cli.event_lines` on events built by hand, one kind at a time., `codex.codex_cli`'s readers that hand `show`, `status` and `result` an item,…, Show, stream()

### Community 14 - "supervisor.py"
Cohesion: 0.14
Nodes (19): first_thread_id(), `thread.started` is the first line Codex emits, and a resumed turn repeats the…, Merge `fields` into meta.json under the run's lock., update_meta(), end_group(), Path, The detached supervisor that runs Codex and records its outcome, and the signal…, Start the run's supervisor in a new session, re-executing the entrypoint.… (+11 more)

### Community 15 - "engine"
Cohesion: 0.10
Nodes (18): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import a unit's interface (`"codex.runs"`, `"codex.registry"`, …) from the…, `codex.codex_cli`'s `user_defaults` and `config_summary`: the top-level values…, LoginStatus, `doctor`: one line describing the environment a run would start in, exit 2 when…, `codex.codex_cli.login_status`, asked of the fake codex: the cause says which…, Reading a run's event stream: exact cursors, damaged lines that are counted… (+10 more)

### Community 16 - "test_structure.py"
Cohesion: 0.07
Nodes (36): all_violations(), call_name(), declared_all(), dotted(), imported_unit(), imports(), inner_modules(), interface_violations() (+28 more)

### Community 17 - "test_cli_contract.py"
Cohesion: 0.09
Nodes (9): FlagsThatWouldDecideNothing, OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, Two selectors name different things; honouring one silently drops the other., A flag that parses and changes nothing reads as having been obeyed, so each is…, Flags nothing used, removed from the parser rather than left to accept and do…, RemovedSurface, SelectorsAreExclusive (+1 more)

### Community 18 - "run_e2e.py"
Cohesion: 0.21
Nodes (15): base_cmd(), control_text(), digest(), entry(), main(), Path, A session whose stdin stays open, so a finished background task can start…, Run one S6 scenario against the draft, the control or the v0.8.0 skill,… (+7 more)

### Community 19 - "alive"
Cohesion: 0.06
Nodes (10): alive(), AnOrphanThatIsStillWriting, DetachedStart, LegacyWaitingRun, A run's life: detached start, every terminal state, the stop ladder, and what a…, Signals go to the run's recorded process group, SIGINT first, escalating only…, Releases before 0.8 could leave a batch member `waiting` on its predecessor.…, StopLadder (+2 more)

### Community 21 - "Settings Precedence Tests"
Cohesion: 0.23
Nodes (3): Precedence, `codex.runs.settings_for`: one precedence for every setting — the flag, then…, resolve()

### Community 23 - "test_argv.py"
Cohesion: 0.20
Nodes (4): build(), BuildArgv, Preamble, `codex.codex_cli`'s `build_argv` and `apply_preamble`: the argv a run hands…

### Community 24 - "Model Catalog Checks"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 25 - "util.py"
Cohesion: 0.23
Nodes (11): flock(), meta_lock(), Path, Cross-process locks on registry files, and the atomic JSON write every registry…, Hold an exclusive lock on `lock` for the body. Failing to take the lock…, Serialise "is this thread free?" with publishing the run that answers it,…, Serialise read-modify-write on one meta.json. The lock file is separate because…, thread_turn_lock() (+3 more)

### Community 27 - "Real Codex Smoke Tests"
Cohesion: 0.29
Nodes (4): skipUnless, S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, `result`'s JSON header line and the message after it., RealCodex

### Community 28 - "ExitCodes"
Cohesion: 0.24
Nodes (3): BatchAndCleanAreCommandsOfTheirOwn, ExitCodes, 0 success; 2 the command line itself must change, answered as JSON with the…

### Community 29 - "TheSkillTextPointsAtRealThings"
Cohesion: 0.25
Nodes (3): SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk()

### Community 30 - "create.py"
Cohesion: 0.12
Nodes (21): apply_preamble(), build_argv(), The `codex exec` argv for a run, and the paragraphs put in front of its prompt.…, `-c` values are parsed as TOML, so a string value is emitted quoted., Compose the argv from a run's recorded settings, re-asserting every one on…, The caller's uncommitted work is absent from a checkout either way; only the…, Prepend the run-context paragraphs. Not optional., toml_cfg() (+13 more)

### Community 31 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 33 - "clip"
Cohesion: 0.21
Nodes (12): Run directories `iter_runs` had to skip, so a listing missing them can say so., unreadable_runs(), publish(), check(), make_meta(), Stage 2 — under the thread's turn lock, check the thread is free, claim a run…, The thread a run with an unparseable meta.json was on, recovered from its event…, Refuse a second live turn on one thread — two turns would append to one rollout… (+4 more)

### Community 36 - "Cursors"
Cohesion: 0.24
Nodes (3): Cursors, APidAnotherProcessNowHolds, The system hands an exited process's pid to the next process it starts, so a…

### Community 38 - "runs/commands.py"
Cohesion: 0.15
Nodes (19): The one way a command says no, from anywhere below the command surface:…, The project a command works on: the git top level of `explicit`, or of the…, resolve_project(), Watching and collecting runs: `status`, `log`, `show` and `result`, for one run…, `show`: one run-scoped item in full — a command's output, capped and with the…, show(), implicit_run(), Pick a run nobody named, from `candidates` in `iter_runs` order: the one live… (+11 more)

### Community 39 - "codex_home"
Cohesion: 0.27
Nodes (10): codex_home(), config_scalars(), config_summary(), pin_codex_home(), Path, CODEX_HOME and the few top-level values this skill reads from the user's…, CODEX_HOME when set, resolved — sessions, config and auth all move with it —…, Pin a relative CODEX_HOME to the directory it named where this command ran: the… (+2 more)

### Community 41 - "log.py"
Cohesion: 0.13
Nodes (29): closing_line(), follow(), GroupWatch, The loop every `--follow` runs, the closing line a group's follow ends on, and…, Run `step()` every FOLLOW_INTERVAL until it is done or `timeout` passes,…, A group as a follower or a wait sees it, tick by tick: its members' rows and…, The counts a group's closing line appends when non-zero., The line a group's follow ends on. (+21 more)

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

### Community 47 - "ThroughASymlink"
Cohesion: 0.47
Nodes (3): The call SKILL.md teaches, through the link, from a directory unrelated to the…, ThroughASymlink, finished()

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
Cohesion: 0.12
Nodes (4): wait_until(), `result --wait` waits for the end, then prints exactly what `result` would;…, WaitingForTheResult, ManyRunsAtOnce

### Community 57 - "codex 스킬 재작성 계획"
Cohesion: 0.17
Nodes (11): codex 스킬 재작성 계획, Context, --help·에러 메시지 작성 규칙 (PR5), SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하), 검증 (전체 완료 판정), 단계 (PR별, 각 단계의 완료 판정 포함), 참고: 재사용하는 기존 코드, 최종 디렉터리 구조 (+3 more)

### Community 65 - "result.py"
Cohesion: 0.12
Nodes (30): final_message(), member_result(), overlaps(), Path, Collecting a group: what each member concluded and which paths more than one…, Paths a run wrote, as `(repository, repo-relative path)` pairs. Codex reports…, What a run concluded: its `-o` file decoded as UTF-8 (a byte that is not,…, One member of `result --group`: its row and the part of its message that is… (+22 more)

### Community 68 - "test_observe.py"
Cohesion: 0.17
Nodes (4): AnOlderReleasesRegistry, What `status` and `result` say about runs: progress while live, the answer once…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, StatusOfOneRun

## Knowledge Gaps
- **54 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+49 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 480 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **17 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `.finished`, `ResumeFrom`, `Result`, `test_resume.py`, `ItemsAndPaths`, `engine`, `test_cli_contract.py`, `alive`, `WhatReachesCodex`, `Model Catalog Checks`, `Doctor Diagnostics Tests`, `ExitCodes`, `TheNextStep`, `AFailureInsideALockIsReportedAsItself`, `HelpIsTheInterface`, `Cursors`, `DamagedLines`, `log.py`, `ThroughASymlink`, `wait_until`, `test_observe.py`?**
  _High betweenness centrality (0.499) - this node is a cross-community bridge._
- **Why does `check()` connect `clip` to `log.py`, `Refusal`?**
  _High betweenness centrality (0.267) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Refusal` to `result.py`, `clip`, `doctor.py`, `runs/commands.py`, `read_meta`, `log.py`, `git/__init__.py`, `runs.py`, `registry/__init__.py`, `create.py`?**
  _High betweenness centrality (0.185) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _54 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `codex_cli/__init__.py` be split into smaller, more focused modules?**
  _Cohesion score 0.12873563218390804 - nodes in this community are weakly interconnected._
- **Should `.finished` be split into smaller, more focused modules?**
  _Cohesion score 0.06398809523809523 - nodes in this community are weakly interconnected._