# Graph Report - codex in claude  (2026-10-09)

## Corpus Check
- 80 files · ~85,225 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: .jsonl 7, (none) 2)

## Summary
- 1248 nodes · 2687 edges · 68 communities (43 shown, 24 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 47 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `876ba3c2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- events.py
- .finished
- ResumeFrom
- Refusal
- codex_cli/__init__.py
- UserDefaultsAndTheirPrecedence
- Result
- GroupWatch
- BridgeCase
- runs.py
- git/__init__.py
- codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를
- registry/__init__.py
- ItemsAndPaths
- status.py
- harness.py
- test_structure.py
- test_cli_contract.py
- run_e2e.py
- alive
- WhatReachesCodex
- resolve
- TopLevelValues
- build
- test_catalog.py
- nfc
- Doctor
- RealCodex
- ExitCodes
- TheSkillTextPointsAtRealThings
- LoginStatus
- codex
- TheNextStep
- create.py
- engine
- HelpIsTheInterface
- Cursors
- AStaleReap
- runs/commands.py
- StopLadder
- VersionFloors
- log.py
- test_run_lifecycle.py
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
- SelectorsAreExclusive
- codex 스킬 재작성 계획
- wait_until
- Scoped Contribution Workflow
- scenarios.md
- Graphify-First Codebase Navigation
- Tiered Contribution Verification
- LegacyWaitingRun
- result.py
- OneLinePerParagraph
- test_observe.py

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 77 edges
2. `Refusal` - 59 edges
3. `wait_until()` - 32 edges
4. `Clean` - 27 edges
5. `engine()` - 25 edges
6. `alive()` - 25 edges
7. `resolve_project()` - 23 edges
8. `iter_runs()` - 23 edges
9. `find_run()` - 23 edges
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

## Communities (68 total, 24 thin omitted)

### Community 0 - "events.py"
Cohesion: 0.12
Nodes (29): changed_paths(), CursorOutOfRange, event_lines(), find_item(), format_events(), _format_item(), head_tail(), _indent() (+21 more)

### Community 1 - ".finished"
Cohesion: 0.06
Nodes (11): Clean, Overlaps, `batch --worktree`: which members get a checkout, what the checkout holds, how…, A checkout is `git worktree add` output: tracked files at the base commit and…, This CLI's own call for `words`, written out whole the way the pre-approval…, Run a command a reply handed back, as the caller would: exactly as written,…, Codex reports absolute paths, and each checkout has its own prefix, so paths…, Append a file_change naming these absolute paths, the shape real events have. (+3 more)

### Community 2 - "ResumeFrom"
Cohesion: 0.08
Nodes (11): AMalformedRegistry, BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, A read-only member is a read-only run: it gets the profile that writes scratch,…, Phase two pairs task i with member i of phase one, in start order, and refuses…, ReadOnlyMembers (+3 more)

### Community 3 - "Refusal"
Cohesion: 0.11
Nodes (31): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_batch(), cmd_log(), cmd_result(), cmd_resume() (+23 more)

### Community 4 - "codex_cli/__init__.py"
Cohesion: 0.06
Nodes (56): The `codex exec` argv for a run, and the paragraphs put in front of its prompt.…, The caller's uncommitted work is absent from a checkout either way; only the…, `-c` values are parsed as TOML, so a string value is emitted quoted., A TOML basic string: a path can hold a quote, a backslash or a control…, Read everything, write only TMPDIR and ~/.cache, network off. The run's own…, Why a read-only run in `cwd` cannot write scratch on this install, as the note…, read_only_blocker(), read_only_profile() (+48 more)

### Community 5 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.06
Nodes (14): The `-c` entries a read-only run that can write scratch hands Codex, as…, read_only_profile(), FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A read-only run can run tests and builds: it reads anything and writes only…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's… (+6 more)

### Community 6 - "Result"
Cohesion: 0.18
Nodes (3): answer_fixture(), A --schema run's `result`: one JSON document over however many lines, indented…, Result

### Community 7 - "GroupWatch"
Cohesion: 0.33
Nodes (4): GroupWatch, A group as a follower or a wait sees it, tick by tick: its members' rows and…, `(members, gaps)` as they stand: members as `(run_dir, meta)`, in start order., `(rows, gaps)` as they stand, each row reaped.

### Community 8 - "BridgeCase"
Cohesion: 0.07
Nodes (15): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded). (+7 more)

### Community 9 - "runs.py"
Cohesion: 0.11
Nodes (37): log(), dump(), step(), ended(), A reader sees the old file or the new one, never half of one. The staging name…, write_json_atomic(), claim_run_dir(), ensure_runs_dir() (+29 more)

### Community 10 - "git/__init__.py"
Cohesion: 0.06
Nodes (65): batch(), clean(), `batch` and `clean`, and the `next` a batch's reply names., The group name's rule and `--base` without `--worktree` are the command…, Several runs as one group: `batch` and `clean`. A batch is N runs, so it builds…, Spawn every task in order. A member that fails keeps its slot with the error,…, spawn_members(), check_task_settings() (+57 more)

### Community 11 - "codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를"
Cohesion: 0.12
Nodes (15): codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를, Context, skill-maker 프레임 대조 (완료 판정에 그대로 씀), SKILL.md 섹션 구조 (한 파일, 영어), 검증 (전체), 계획 리뷰 기록, 구현 후 디렉터리 구조, 단계 (PR별, 완료 판정) (+7 more)

### Community 12 - "registry/__init__.py"
Cohesion: 0.12
Nodes (44): _check_liftable_guards(), clean_group(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The `stop` calls that end these runs, each written out whole the way `next` is,…, Remove a group's worktrees and release its name when nothing is left behind.…, `(live members, members whose meta.json will not parse)` — unknown is kept…, The refusals `--force` lifts, in check order; returns what was overridden,… (+36 more)

### Community 13 - "ItemsAndPaths"
Cohesion: 0.07
Nodes (8): EventLines, ItemsAndPaths, Levels, An event file holding these events built by hand, one JSON line each., `codex.codex_cli.event_lines` on events built by hand, one kind at a time., `codex.codex_cli`'s readers that hand `show`, `status` and `result` an item,…, Show, stream()

### Community 14 - "status.py"
Cohesion: 0.20
Nodes (12): note_unreadable(), Path, What the default listing shows of a run, from a row built with a 160-character…, Name runs whose meta.json will not parse, so a listing they are missing from…, `is_live` for a row: its state is not terminal, or its Codex still writes., The row `status` prints for one run, reaped first so a dead supervisor is never…, row_is_live(), run_row() (+4 more)

### Community 15 - "harness.py"
Cohesion: 0.16
Nodes (6): Scaffolding shared by every test: a throwaway git project, the fake `codex`…, `codex.codex_cli`'s `user_defaults` and `config_summary`: the top-level values…, DamagedLines, Reading a run's event stream: exact cursors, damaged lines that are counted…, A line that will not parse is kept as `unparsed` and counted, apart from…, Installs: the skill reached through a symlink, from a directory that has…

### Community 16 - "test_structure.py"
Cohesion: 0.07
Nodes (36): all_violations(), call_name(), declared_all(), dotted(), imported_unit(), imports(), inner_modules(), interface_violations() (+28 more)

### Community 17 - "test_cli_contract.py"
Cohesion: 0.12
Nodes (7): FlagsThatWouldDecideNothing, OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, A flag that parses and changes nothing reads as having been obeyed, so each is…, Flags nothing used, removed from the parser rather than left to accept and do…, RemovedSurface, TheRegistryGoesWhereItIsTold

### Community 18 - "run_e2e.py"
Cohesion: 0.18
Nodes (17): base_cmd(), calls_to_result(), control_text(), digest(), entry(), main(), Path, A session whose stdin stays open, so a finished background task can start… (+9 more)

### Community 21 - "resolve"
Cohesion: 0.14
Nodes (5): Precedence, `codex.runs.settings_for`: one precedence for every setting — the flag, then…, Which read-only a run gets. `scratch` writes TMPDIR and ~/.cache, so tests and…, ReadOnlyMarker, resolve()

### Community 23 - "build"
Cohesion: 0.15
Nodes (5): build(), BuildArgv, Preamble, `codex.codex_cli`'s `build_argv` and `apply_preamble`: the argv a run hands…, ReadOnlyProfile

### Community 24 - "test_catalog.py"
Cohesion: 0.12
Nodes (6): ABrokenLookupNeverBlocksARun, BelowTheIsolationFloor, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…, Every isolated run passes `--ignore-user-config`; a Codex without it fails the…

### Community 25 - "nfc"
Cohesion: 0.27
Nodes (10): flock(), meta_lock(), Path, Cross-process locks on registry files, and the atomic JSON write every registry…, Hold an exclusive lock on `lock` for the body. Failing to take the lock…, Serialise "is this thread free?" with publishing the run that answers it,…, Serialise read-modify-write on one meta.json. The lock file is separate because…, thread_turn_lock() (+2 more)

### Community 26 - "Doctor"
Cohesion: 0.11
Nodes (4): Doctor, `doctor`: one line describing the environment a run would start in, exit 2 when…, What a read-only run started here would get, and the Codex below which no…, ReadOnlyAndTheCodexVersion

### Community 27 - "RealCodex"
Cohesion: 0.18
Nodes (7): skipUnless, is_within(), S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, What the reply's `next` prints once the run has ended — `result --run <id>…, The text of every tool output the rollout recorded, as Codex itself saw it., A turn's permission profile as (entry → access, network)., RealCodex

### Community 28 - "ExitCodes"
Cohesion: 0.24
Nodes (3): BatchAndCleanAreCommandsOfTheirOwn, ExitCodes, 0 success; 2 the command line itself must change, answered as JSON with the…

### Community 29 - "TheSkillTextPointsAtRealThings"
Cohesion: 0.16
Nodes (6): The call SKILL.md teaches, through the link, from a directory unrelated to the…, SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk(), ThroughASymlink, finished()

### Community 31 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 33 - "create.py"
Cohesion: 0.07
Nodes (36): apply_preamble(), build_argv(), Prepend the run-context paragraphs. Not optional., Compose the argv from a run's recorded settings, re-asserting every one on…, first_thread_id(), `thread.started` is the first line Codex emits, and a resumed turn repeats the…, Run directories `iter_runs` had to skip, so a listing missing them can say so., Whether this run's Codex process is still going, whatever its state says.… (+28 more)

### Community 34 - "engine"
Cohesion: 0.13
Nodes (14): engine(), Import a unit's interface (`"codex.runs"`, `"codex.registry"`, …) from the…, AFailureInsideALockIsReportedAsItself, ManyRunsAtOnce, ManyWritersOneMeta, OnePublishPerThreadCheck, _publish_on_one_thread(), check() (+6 more)

### Community 38 - "runs/commands.py"
Cohesion: 0.11
Nodes (27): Spawning a batch: each member's slot recorded before it starts, each member…, Start one member, as `start` or `resume` would. A resume target outside the…, spawn_task(), The one way a command says no, from anywhere below the command surface:…, `show`: one run-scoped item in full — a command's output, capped and with the…, show(), find_run(), Resolve a run id, a thread id, or a run-id prefix; newest wins. Returns… (+19 more)

### Community 41 - "log.py"
Cohesion: 0.20
Nodes (18): closing_line(), follow(), The loop every `--follow` runs, the closing line a group's follow ends on, and…, Run `step()` every FOLLOW_INTERVAL until it is done or `timeout` passes,…, The counts a group's closing line appends when non-zero., The line a group's follow ends on., tail(), log_group() (+10 more)

### Community 42 - "test_run_lifecycle.py"
Cohesion: 0.17
Nodes (6): APidAnotherProcessNowHolds, DetachedStart, A run's life: detached start, every terminal state, the stop ladder, and what a…, `codex.runs.end_group`'s order of signals, observed where they are delivered —…, The system hands an exited process's pid to the next process it starts, so a…, TheLadderOrder

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

### Community 65 - "result.py"
Cohesion: 0.16
Nodes (21): final_message(), member_result(), overlaps(), Path, Collecting a group: what each member concluded and which paths more than one…, Paths a run wrote, as `(repository, repo-relative path)` pairs. Codex reports…, What a run concluded: its `-o` file decoded as UTF-8 (a byte that is not,…, One member of `result --group`: its row and the part of its message that is… (+13 more)

### Community 68 - "test_observe.py"
Cohesion: 0.17
Nodes (4): AnOlderReleasesRegistry, What `status` and `result` say about runs: progress while live, the answer once…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, StatusOfOneRun

## Knowledge Gaps
- **68 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+63 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 519 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `.finished`, `ResumeFrom`, `UserDefaultsAndTheirPrecedence`, `Result`, `ItemsAndPaths`, `harness.py`, `test_cli_contract.py`, `alive`, `WhatReachesCodex`, `test_catalog.py`, `Doctor`, `ExitCodes`, `TheSkillTextPointsAtRealThings`, `TheNextStep`, `engine`, `HelpIsTheInterface`, `Cursors`, `StopLadder`, `test_run_lifecycle.py`, `Listing`, `WaitingForTheResult`, `GroupResult`, `SelectorsAreExclusive`, `wait_until`, `LegacyWaitingRun`, `test_observe.py`?**
  _High betweenness centrality (0.482) - this node is a cross-community bridge._
- **Why does `check()` connect `create.py` to `engine`, `Refusal`?**
  _High betweenness centrality (0.265) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Refusal` to `result.py`, `create.py`, `codex_cli/__init__.py`, `runs/commands.py`, `GroupWatch`, `log.py`, `git/__init__.py`, `runs.py`, `registry/__init__.py`?**
  _High betweenness centrality (0.202) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _68 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `events.py` be split into smaller, more focused modules?**
  _Cohesion score 0.12183908045977011 - nodes in this community are weakly interconnected._
- **Should `.finished` be split into smaller, more focused modules?**
  _Cohesion score 0.06293706293706294 - nodes in this community are weakly interconnected._