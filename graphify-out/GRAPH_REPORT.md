# Graph Report - codex in claude  (2026-10-09)

## Corpus Check
- 79 files · ~83,837 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: .jsonl 7, (none) 2)

## Summary
- 1239 nodes · 2590 edges · 67 communities (45 shown, 21 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 43 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a53e26a8`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- events.py
- .finished
- read_only_profile
- cli.py
- codex_cli/__init__.py
- test_resume.py
- Result
- follow.py
- BridgeCase
- git
- git/__init__.py
- codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를
- registry/__init__.py
- EventLines
- rows.py
- DamagedLines
- test_structure.py
- test_cli_contract.py
- run_e2e.py
- UserDefaultsAndTheirPrecedence
- WhatReachesCodex
- resolve
- TopLevelValues
- build
- test_catalog.py
- Refusal
- Doctor
- RealCodex
- ExitCodes
- TheSkillTextPointsAtRealThings
- test_doctor.py
- codex
- TheNextStep
- create.py
- engine
- HelpIsTheInterface
- test_install.py
- AStaleReap
- runs.py
- StopLadder
- batch/commands.py
- runs/commands.py
- TheLadderOrder
- codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비
- Codex Managed Subagent Skill
- Codex in Claude
- Codex-in-Claude Release History
- read_only_profile
- codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비
- Community Impact Enforcement Ladder
- Private Vulnerability Reporting
- Graph-First Navigation
- VersionFloors
- WaitingForTheResult
- codex/__init__.py
- codex 스킬 재작성 계획
- wait_until
- Scoped Contribution Workflow
- scenarios.md
- Graphify-First Codebase Navigation
- Tiered Contribution Verification
- result.py
- OneLinePerParagraph
- test_observe.py
- AStateThatMovesWhileItIsRead
- APidAnotherProcessNowHolds

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 83 edges
2. `Refusal` - 45 edges
3. `wait_until()` - 30 edges
4. `engine()` - 28 edges
5. `Clean` - 28 edges
6. `main_checkout()` - 24 edges
7. `alive()` - 24 edges
8. `result()` - 22 edges
9. `resolve_project()` - 21 edges
10. `group_view()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `build_parser()` --indirect_call--> `batch()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/batch/commands.py
- `build_parser()` --indirect_call--> `clean()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/batch/commands.py
- `build_parser()` --indirect_call--> `models()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/doctor.py
- `build_parser()` --indirect_call--> `log()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/observe/log.py
- `build_parser()` --indirect_call--> `status()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/observe/status.py

## Import Cycles
- None detected.

## Communities (67 total, 21 thin omitted)

### Community 0 - "events.py"
Cohesion: 0.10
Nodes (33): changed_paths(), event_lines(), _format_item(), head_tail(), _indent(), Path, Reading what a run's Codex wrote: the `codex exec --json` event stream,…, A run's events as `log` prints them, paths shown relative to `rel_to`. A line… (+25 more)

### Community 1 - ".finished"
Cohesion: 0.06
Nodes (11): Clean, Overlaps, A checkout is `git worktree add` output: tracked files at the base commit and…, This CLI's own call for `words`, written out whole the way the pre-approval…, Run a command a reply handed back, as the caller would: exactly as written,…, A batch that continues each member of an earlier one: a tasks file with one…, Codex reports absolute paths, and each checkout has its own prefix, so paths…, Append a file_change naming these absolute paths, the shape real events have. (+3 more)

### Community 2 - "read_only_profile"
Cohesion: 0.06
Nodes (18): The `-c` entries a read-only run that can write scratch hands Codex, as…, read_only_profile(), AMalformedRegistry, BatchCase, NextRound, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, A read-only member is a read-only run: it gets the profile that writes scratch,… (+10 more)

### Community 3 - "cli.py"
Cohesion: 0.10
Nodes (27): add_common(), add_run_options(), build_parser(), cmd_result(), cmd_resume(), doctor_reply(), group_name(), JsonArgumentParser (+19 more)

### Community 4 - "codex_cli/__init__.py"
Cohesion: 0.08
Nodes (44): check_task_settings(), Refuse what would refuse a member — a Codex too old for an isolated member, a…, apply_preamble(), The `codex exec` argv for a run, and the paragraphs put in front of its prompt.…, The caller's uncommitted work is absent from a checkout either way; only the…, Prepend the run-context paragraphs. Not optional., Why a read-only run in `cwd` cannot write scratch on this install, as the note…, read_only_blocker() (+36 more)

### Community 5 - "test_resume.py"
Cohesion: 0.14
Nodes (6): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, Two turns on one thread append to one rollout file. The check and the new run's…, ResumeCase, SettingsAreReasserted

### Community 6 - "Result"
Cohesion: 0.09
Nodes (6): answer_fixture(), GroupResult, Listing, `n` finished runs written straight into the registry, all the same shape so…, A --schema run's `result`: one JSON document over however many lines, indented…, Result

### Community 7 - "follow.py"
Cohesion: 0.20
Nodes (7): GroupWatch, The silent wait `result --wait` makes, and a group as that wait sees it look by…, Ask `ended()` every FOLLOW_INTERVAL until it holds or `timeout` seconds have…, A group as a wait sees it, look by look: its members' rows and the slots no row…, `(members, gaps)` as they stand: members as `(run_dir, meta)`, in start order., `(rows, gaps)` as they stand, each row reaped., wait_until()

### Community 8 - "BridgeCase"
Cohesion: 0.06
Nodes (18): BridgeCase, writer(), Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, its closing line)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its… (+10 more)

### Community 9 - "git"
Cohesion: 0.09
Nodes (11): CleaningAfterTheCheckoutIsGone, git(), MainCheckout, OneRegistryPerRepository, Path, git could not say" is unknown, never a no: nothing is deleted by hand, and a…, A batch cut from a linked worktree records that worktree as the repository its…, A git repository with one commit, resolved the way the skill records paths. (+3 more)

### Community 10 - "git/__init__.py"
Cohesion: 0.12
Nodes (31): The git CLI: repository questions and the worktrees a batch cuts. A git…, _covered_by(), ignored_entries(), is_dirty(), missing_at_base(), Path, What the git CLI says about a repository: its top level, its identity, a…, Every path the base commit tracks, from one `git ls-tree`. (+23 more)

### Community 11 - "codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를"
Cohesion: 0.12
Nodes (15): codex 스킬 0.11.0: read-only가 실행할 수 있게, 안 쓰는 표면은 빼고, worktree에서도 같은 레지스트리를, Context, skill-maker 프레임 대조 (완료 판정에 그대로 씀), SKILL.md 섹션 구조 (한 파일, 영어), 검증 (전체), 계획 리뷰 기록, 구현 후 디렉터리 구조, 단계 (PR별, 완료 판정) (+7 more)

### Community 12 - "registry/__init__.py"
Cohesion: 0.09
Nodes (52): _check_liftable_guards(), clean_group(), continued_by(), member_checkouts(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The refusals `--force` lifts, in check order; returns what was overridden,…, The `stop` calls that end these runs, each written out whole the way `next` is,… (+44 more)

### Community 13 - "EventLines"
Cohesion: 0.09
Nodes (8): EventLines, ItemsAndPaths, An event file holding these events built by hand, one JSON line each., `codex.codex_cli.event_lines` on events built by hand, one kind at a time., `codex.codex_cli`'s readers that hand `status` and `result` the changed paths…, `log` is one look at what a run did: every command with its exit code and…, stream(), WhatLogPrints

### Community 14 - "rows.py"
Cohesion: 0.18
Nodes (16): The last `limit` characters of a run's stderr without blank lines or the notice…, stderr_tail(), group_snapshot(), note_unreadable(), Describing runs and groups: the status row and its summary, the turn-failure…, `(running, done, failed, group_state)` — the one place group state is derived,…, What the default listing shows of a run, from a row built with a 160-character…, Name runs whose meta.json will not parse, so a listing they are missing from… (+8 more)

### Community 16 - "test_structure.py"
Cohesion: 0.07
Nodes (36): all_violations(), call_name(), declared_all(), dotted(), imported_unit(), imports(), inner_modules(), interface_violations() (+28 more)

### Community 17 - "test_cli_contract.py"
Cohesion: 0.12
Nodes (7): OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, Two selectors name different things; honouring one silently drops the other., Flags nothing used, removed from the parser rather than left to accept and do…, RemovedSurface, SelectorsAreExclusive, TheRegistryGoesWhereItIsTold

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
Cohesion: 0.12
Nodes (6): ABrokenLookupNeverBlocksARun, BelowTheIsolationFloor, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…, Every isolated run passes `--ignore-user-config`; a Codex without it fails the…

### Community 25 - "Refusal"
Cohesion: 0.15
Nodes (17): Spawning a batch: each member's slot recorded before it starts, each member…, Start one member, as `start` or `resume` would. A resume target outside the…, Spawn every task in order. A member that fails keeps its slot with the error,…, spawn_members(), spawn_task(), load_tasks(), What a batch is asked to do: the ordered tasks, each validated before anything…, The ordered task list: `--task` prompts first (as typed), then `--tasks-file`… (+9 more)

### Community 27 - "RealCodex"
Cohesion: 0.18
Nodes (7): skipUnless, is_within(), S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, What the reply's `next` prints once the run has ended — `result --run <id>…, The text of every tool output the rollout recorded, as Codex itself saw it., A turn's permission profile as (entry → access, network)., RealCodex

### Community 28 - "ExitCodes"
Cohesion: 0.16
Nodes (5): BatchAndCleanAreCommandsOfTheirOwn, ExitCodes, A command or flag 0.11 removed is refused like any command line that must…, 0 success; 2 the command line itself must change, answered as JSON with the…, TheSurfaceRemovedIn011

### Community 29 - "TheSkillTextPointsAtRealThings"
Cohesion: 0.25
Nodes (3): SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk()

### Community 30 - "test_doctor.py"
Cohesion: 0.18
Nodes (5): LoginStatus, `doctor`: one line describing the environment a run would start in, exit 2 when…, What a read-only run started here would get, and the Codex below which no…, `codex.codex_cli.login_status`, asked of the fake codex: the cause says which…, ReadOnlyAndTheCodexVersion

### Community 31 - "codex"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 33 - "create.py"
Cohesion: 0.11
Nodes (29): build_argv(), Compose the argv from a run's recorded settings, re-asserting every one on…, first_thread_id(), `thread.started` is the first line Codex emits, and a resumed turn repeats the…, ensure_runs_dir(), Run directories `iter_runs` had to skip, so a listing missing them can say so., Whether this run's Codex process is still going, whatever its state says.…, still_writing() (+21 more)

### Community 34 - "engine"
Cohesion: 0.08
Nodes (19): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import a unit's interface (`"codex.runs"`, `"codex.registry"`, …) from the…, `codex.codex_cli`'s `user_defaults` and `config_summary`: the top-level values…, AHalfWrittenLine, Reading a run's event stream: damaged lines that are counted rather than…, Where the registry is: one per repository, in its main checkout's `.codex-…, AFailureInsideALockIsReportedAsItself (+11 more)

### Community 36 - "test_install.py"
Cohesion: 0.32
Nodes (4): Installs: the skill reached through a symlink, from a directory that has…, The call SKILL.md teaches, through the link, from a directory unrelated to the…, ThroughASymlink, finished()

### Community 38 - "runs.py"
Cohesion: 0.09
Nodes (39): claim_run_dir(), find_run(), iter_runs(), live_runs(), new_run_id(), publish_run(), Path, Run records: one directory per run, its `meta.json` the run's settings and… (+31 more)

### Community 40 - "batch/commands.py"
Cohesion: 0.11
Nodes (28): batch(), clean(), `batch` and `clean`, and the `next` a batch's reply names., The group name's rule is the command surface's to refuse, before this is called., Several runs as one group: `batch` and `clean`. A batch is N runs, so it builds…, plan_worktrees(), reasons_for(), Isolation for a batch: which members get a git checkout of their own, cut from… (+20 more)

### Community 41 - "runs/commands.py"
Cohesion: 0.17
Nodes (14): follow_up(), `start`, `resume` and `stop`, and the `next` a started run's reply names., The reply with its `next`: the call that waits for the run it made and prints…, `args.ref` and `args.prompt` arrive split out of `resume REF [PROMPT]` by the…, Exactly one of `--run` or `--group` is set; the command surface refuses the…, resume(), start(), stop() (+6 more)

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

### Community 47 - "read_only_profile"
Cohesion: 0.33
Nodes (6): `-c` values are parsed as TOML, so a string value is emitted quoted., A TOML basic string: a path can hold a quote, a backslash or a control…, Read everything, write only TMPDIR and ~/.cache, network off. The run's own…, read_only_profile(), toml_cfg(), toml_string()

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
Cohesion: 0.11
Nodes (8): alive(), wait_until(), AnOrphanThatIsStillWriting, LegacyWaitingRun, A run's life: detached start, every terminal state, the stop ladder, and what a…, Releases before 0.8 could leave a batch member `waiting` on its predecessor.…, TerminalStates, `batch --worktree`: which members get a checkout, what the checkout holds, how…

### Community 65 - "result.py"
Cohesion: 0.15
Nodes (26): final_message(), member_result(), read(), overlaps(), Collecting a group: what each member concluded and which paths more than one…, A run's `-o` file as written, or None when there is none yet., What a run concluded: its `-o` file (`raw`, from `read_final`) decoded as UTF-8…, One member of `result --group`: its row, the part of its message that is shown,… (+18 more)

### Community 68 - "test_observe.py"
Cohesion: 0.17
Nodes (4): AnOlderReleasesRegistry, What `status` and `result` say about runs: progress while live, the answer once…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, StatusOfOneRun

## Knowledge Gaps
- **68 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+63 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 515 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `.finished`, `read_only_profile`, `test_resume.py`, `Result`, `git`, `EventLines`, `DamagedLines`, `test_cli_contract.py`, `WhatReachesCodex`, `test_catalog.py`, `Doctor`, `ExitCodes`, `test_doctor.py`, `TheNextStep`, `engine`, `HelpIsTheInterface`, `test_install.py`, `StopLadder`, `WaitingForTheResult`, `wait_until`, `test_observe.py`, `AStateThatMovesWhileItIsRead`, `APidAnotherProcessNowHolds`?**
  _High betweenness centrality (0.475) - this node is a cross-community bridge._
- **Why does `check()` connect `create.py` to `Refusal`, `engine`?**
  _High betweenness centrality (0.283) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Refusal` to `result.py`, `create.py`, `cli.py`, `codex_cli/__init__.py`, `runs.py`, `follow.py`, `runs/commands.py`, `registry/__init__.py`?**
  _High betweenness centrality (0.186) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _68 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `events.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09915966386554621 - nodes in this community are weakly interconnected._
- **Should `.finished` be split into smaller, more focused modules?**
  _Cohesion score 0.06340326340326341 - nodes in this community are weakly interconnected._