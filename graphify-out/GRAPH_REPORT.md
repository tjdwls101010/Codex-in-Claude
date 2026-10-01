# Graph Report - codex in claude  (2026-10-02)

## Corpus Check
- 78 files · ~71,054 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: .jsonl 6, (none) 2)

## Summary
- 1098 nodes · 2393 edges · 69 communities (45 shown, 23 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 37 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `68d11763`
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
- log.py
- BridgeCase
- create.py
- git/__init__.py
- batch/commands.py
- registry/__init__.py
- ItemsAndPaths
- read_meta
- engine
- test_structure.py
- SelectorsAreExclusive
- run_e2e.py
- wait_until
- Codex Argument Passthrough Tests
- Settings Precedence Tests
- TopLevelValues
- test_argv.py
- Model Catalog Checks
- APidAnotherProcessNowHolds
- Doctor Diagnostics Tests
- Real Codex Smoke Tests
- Exit Code Contract
- Skill Doc Consistency Tests
- Run Terminal States
- Fake Codex Stub
- Next Step Hints
- ThroughASymlink
- StopLadder
- Help Text Tests
- Event Log Cursors
- Stale Run Reaping
- result.py
- CLI Output Frame
- DamagedLines
- status.py
- test_run_lifecycle.py
- codex 스킬: skill-maker 레이아웃 이행과 출력 계약 정비
- Codex Skill Guidance
- Codex in Claude Features
- Release History
- runs.py
- codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비
- Code of Conduct
- Security Policy
- Graph Navigation Workflow
- main
- doctor.py
- test_resume.py
- Codex Package Init
- resolve_project
- codex 스킬 재작성 계획
- Refusal
- Contribution Guidelines
- S6 Scenarios
- Graphify Codebase Navigation
- Contribution Verification Tiers
- model_catalog
- run_row
- LoginStatus
- OneLinePerParagraph
- AnOlderReleasesRegistry

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 73 edges
2. `Refusal` - 52 edges
3. `wait_until()` - 27 edges
4. `find_run()` - 24 edges
5. `resolve_project()` - 23 edges
6. `iter_runs()` - 23 edges
7. `engine()` - 23 edges
8. `alive()` - 23 edges
9. `Clean` - 23 edges
10. `resolve_runs_dir()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `build_parser()` --indirect_call--> `clean()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/batch/commands.py
- `build_parser()` --indirect_call--> `models()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/doctor.py
- `build_parser()` --indirect_call--> `result()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/observe/result.py
- `build_parser()` --indirect_call--> `show()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/observe/show.py
- `build_parser()` --indirect_call--> `stop()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/runs/commands.py

## Import Cycles
- None detected.

## Communities (69 total, 23 thin omitted)

### Community 0 - "events.py"
Cohesion: 0.12
Nodes (29): changed_paths(), CursorOutOfRange, find_item(), format_events(), _format_item(), head_tail(), _indent(), _item() (+21 more)

### Community 1 - ".finished"
Cohesion: 0.08
Nodes (8): Clean, Overlaps, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout, WorktreeCase

### Community 2 - "ResumeFrom"
Cohesion: 0.09
Nodes (7): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 3 - "cli.py"
Cohesion: 0.16
Nodes (19): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_batch_start(), cmd_log(), cmd_resume(), cmd_status() (+11 more)

### Community 4 - "codex_cli/__init__.py"
Cohesion: 0.21
Nodes (12): codex_home(), config_scalars(), config_summary(), pin_codex_home(), Path, CODEX_HOME and the few top-level values this skill reads from the user's…, CODEX_HOME when set, resolved — sessions, config and auth all move with it —…, Pin a relative CODEX_HOME to the directory it named where this command ran: the… (+4 more)

### Community 5 - "UserDefaultsAndTheirPrecedence"
Cohesion: 0.12
Nodes (4): FindingTheThread, An explicit flag, then what a resumed thread recorded, then the user's…, SettingsAreReasserted, UserDefaultsAndTheirPrecedence

### Community 6 - "Result"
Cohesion: 0.09
Nodes (5): answer_fixture(), GroupResult, Listing, `n` finished runs written straight into the registry, all the same shape so…, Result

### Community 7 - "log.py"
Cohesion: 0.18
Nodes (19): event_lines(), The events after byte offset `since` rendered at `level`, paths shown relative…, follow(), The loop every `--follow` runs, and the closing line a group's follow ends on.…, Run `step()` every FOLLOW_INTERVAL until it is done or `timeout` passes,…, log(), dump(), log_group() (+11 more)

### Community 8 - "BridgeCase"
Cohesion: 0.07
Nodes (14): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded). (+6 more)

### Community 9 - "create.py"
Cohesion: 0.10
Nodes (33): apply_preamble(), build_argv(), The `codex exec` argv for a run, and the paragraphs put in front of its prompt.…, `-c` values are parsed as TOML, so a string value is emitted quoted., Compose the argv from a run's recorded settings, re-asserting every one on…, The caller's uncommitted work is absent from a checkout either way; only the…, Prepend the run-context paragraphs. Not optional., toml_cfg() (+25 more)

### Community 10 - "git/__init__.py"
Cohesion: 0.09
Nodes (44): plan_worktrees(), reasons_for(), Isolation for a batch: which members get a git checkout of their own, cut from…, Whether `--worktree` would isolate this member: a fresh writer with no cwd of…, Why `--worktree` would pass this member over, in the caller's words, or None., Members that will write, grouped by the directory they will write in, resolved…, Who is about to write into one directory, and — only where it would work — the…, Which members get a checkout, cut from which commit, and a note when members… (+36 more)

### Community 11 - "batch/commands.py"
Cohesion: 0.11
Nodes (26): batch(), clean(), `batch start` and `batch clean`, and the `next` a batch's reply names., The group name's rule and `--base` without `--worktree` are the command…, Several runs as one group: `batch start` and `batch clean`. A batch is N runs,…, Spawning a batch: each member's slot recorded before it starts, each member…, Start one member, as `start` or `resume` would. A resume target outside the…, Spawn every task in order. A member that fails keeps its slot with the error,… (+18 more)

### Community 12 - "registry/__init__.py"
Cohesion: 0.11
Nodes (48): _check_liftable_guards(), clean_group(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The `stop` calls that end these runs: the group's when the run is one of its…, Remove a group's worktrees and release its name when nothing is left behind.…, `(live members, members whose meta.json will not parse)` — unknown is kept…, The refusals `--force` lifts, in check order; returns what was overridden,… (+40 more)

### Community 13 - "ItemsAndPaths"
Cohesion: 0.07
Nodes (8): EventLines, ItemsAndPaths, Levels, An event file holding these events built by hand, one JSON line each., `codex.codex_cli.event_lines` on events built by hand, one kind at a time., `codex.codex_cli`'s readers that hand `show`, `status` and `result` an item,…, Show, stream()

### Community 14 - "read_meta"
Cohesion: 0.11
Nodes (26): first_thread_id(), `thread.started` is the first line Codex emits, and a resumed turn repeats the…, Run directories `iter_runs` had to skip, so a listing missing them can say so., Merge `fields` into meta.json under the run's lock., read_meta(), unreadable_runs(), update_meta(), publish() (+18 more)

### Community 15 - "engine"
Cohesion: 0.07
Nodes (23): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import a unit's interface (`"codex.runs"`, `"codex.registry"`, …) from the…, FlagsThatWouldDecideNothing, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, A flag that parses and changes nothing reads as having been obeyed, so each is…, Flags nothing used, removed from the parser rather than left to accept and do…, RemovedSurface (+15 more)

### Community 16 - "test_structure.py"
Cohesion: 0.07
Nodes (36): all_violations(), call_name(), declared_all(), dotted(), imported_unit(), imports(), inner_modules(), interface_violations() (+28 more)

### Community 18 - "run_e2e.py"
Cohesion: 0.21
Nodes (15): base_cmd(), control_text(), digest(), entry(), main(), Path, A session whose stdin stays open, so a finished background task can start…, Run one S6 scenario against the draft, the control or the v0.8.0 skill,… (+7 more)

### Community 19 - "wait_until"
Cohesion: 0.10
Nodes (10): alive(), A run recorded `orphaned` whose codex is demonstrably still going: its…, wait_until(), AMalformedRegistry, Batches: N runs under one name, validated before anything starts, recorded slot…, Installs: the skill reached through a symlink, from a directory that has…, What `status` and `result` say about runs: progress while live, the answer once…, StatusOfOneRun (+2 more)

### Community 21 - "Settings Precedence Tests"
Cohesion: 0.23
Nodes (3): Precedence, `codex.runs.settings_for`: one precedence for every setting — the flag, then…, resolve()

### Community 23 - "test_argv.py"
Cohesion: 0.20
Nodes (4): build(), BuildArgv, Preamble, `codex.codex_cli`'s `build_argv` and `apply_preamble`: the argv a run hands…

### Community 24 - "Model Catalog Checks"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 27 - "Real Codex Smoke Tests"
Cohesion: 0.29
Nodes (4): skipUnless, S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, `result`'s JSON header line and the message after it., RealCodex

### Community 29 - "Skill Doc Consistency Tests"
Cohesion: 0.25
Nodes (3): SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk()

### Community 31 - "Fake Codex Stub"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 33 - "ThroughASymlink"
Cohesion: 0.47
Nodes (3): The call SKILL.md teaches, through the link, from a directory unrelated to the…, ThroughASymlink, finished()

### Community 38 - "result.py"
Cohesion: 0.20
Nodes (17): final_message(), member_result(), overlaps(), Path, Collecting a group: what each member concluded and which paths more than one…, Paths a run wrote, as `(repository, repo-relative path)` pairs. Codex reports…, What a run concluded: its `-o` file decoded as UTF-8 (a byte that is not,…, One member of `result --group`: its row and the part of its message that is… (+9 more)

### Community 41 - "status.py"
Cohesion: 0.21
Nodes (16): group_tail(), The counts a group's closing line appends when non-zero., group_snapshot(), note_unreadable(), `(running, done, failed, group_state)` — the one place group state is derived,…, What the default listing shows of a run, from a row built with a 160-character…, Name runs whose meta.json will not parse, so a listing they are missing from…, `is_live` for a row: its state is not terminal, or its Codex still writes. (+8 more)

### Community 42 - "test_run_lifecycle.py"
Cohesion: 0.13
Nodes (7): AnOrphanThatIsStillWriting, DetachedStart, LegacyWaitingRun, A run's life: detached start, every terminal state, the stop ladder, and what a…, `codex.runs.end_group`'s order of signals, observed where they are delivered —…, Releases before 0.8 could leave a batch member `waiting` on its predecessor.…, TheLadderOrder

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

### Community 47 - "runs.py"
Cohesion: 0.12
Nodes (27): flock(), meta_lock(), Path, Cross-process locks on registry files, and the atomic JSON write every registry…, Hold an exclusive lock on `lock` for the body. Failing to take the lock…, Serialise "is this thread free?" with publishing the run that answers it,…, Serialise read-modify-write on one meta.json. The lock file is separate because…, A reader sees the old file or the new one, never half of one. The staging name… (+19 more)

### Community 48 - "codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비"
Cohesion: 0.12
Nodes (15): codex 스킬: skill-maker v0.3.0 코드 규칙 이행과 기다림·회수·help 계약 정비, Context, skill-maker 프레임 대조 (구현 완료 판정에 그대로 씀), SKILL.md 섹션 구조 (PR ③, 한 파일), test_structure.py v2가 확인하는 것, 검증 (전체), 구현 후 디렉터리 구조, 단계 (PR별, 완료 판정) (+7 more)

### Community 49 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 50 - "Security Policy"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

### Community 52 - "main"
Cohesion: 0.20
Nodes (11): command_words(), JsonArgumentParser, main(), Print one line of JSON and exit., A command's answer: a dict is one line of JSON, a `(dict, exit code)` pair the…, The words that name the command a namespace came from: `status`, or `batch…, A command line that does not parse is answered like any other that must change:…, render() (+3 more)

### Community 53 - "doctor.py"
Cohesion: 0.23
Nodes (13): `{model, effort, service_tier}` from the user's config.toml, read fresh on…, user_defaults(), login_status(), `{ok, cause, detail}`. `cause` is `authenticated`; `unauthenticated`;…, _check_codex(), _check_config(), _check_registry(), doctor() (+5 more)

### Community 54 - "test_resume.py"
Cohesion: 0.19
Nodes (6): OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, ResumeCase, ThreadsTheRegistryNeverSaw

### Community 56 - "resolve_project"
Cohesion: 0.38
Nodes (5): The project a command works on: the git top level of `explicit`, or of the…, resolve_project(), Watching and collecting runs: `status`, `log`, `show` and `result`, for one run…, `show`: one run-scoped item in full — a command's output, capped and with the…, show()

### Community 57 - "codex 스킬 재작성 계획"
Cohesion: 0.17
Nodes (11): codex 스킬 재작성 계획, Context, --help·에러 메시지 작성 규칙 (PR5), SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하), 검증 (전체 완료 판정), 단계 (PR별, 각 단계의 완료 판정 포함), 참고: 재사용하는 기존 코드, 최종 디렉터리 구조 (+3 more)

### Community 58 - "Refusal"
Cohesion: 0.23
Nodes (10): The one way a command says no, from anywhere below the command surface:…, A command refused, or failed, for a reason the caller can act on. `error` is…, Refusal, cut_worktree(), Path, Stage 3 — the run's own checkout at `<run_dir>/wt`, recorded in meta.json at…, Stage 1 — what this run will be. Nothing here writes or claims anything, so a…, read_prompt() (+2 more)

### Community 63 - "model_catalog"
Cohesion: 0.29
Nodes (7): codex_version(), model_catalog(), This install's model catalog, read from `codex debug models`, and the pre-spawn…, What `codex --version` prints, or None when there is no codex or it prints…, What this Codex install offers, trimmed to the fields a caller chooses from, or…, models(), The catalog is asked of Codex rather than written down: which efforts a model…

### Community 65 - "run_row"
Cohesion: 0.33
Nodes (5): progress(), Path, The event-stream summary for a reaped run. A trailing fragment counts as…, The row `status` prints for one run, reaped first so a dead supervisor is never…, run_row()

## Knowledge Gaps
- **54 isolated node(s):** `Context`, `합의 장부`, `최종 디렉터리 구조`, `SKILL.md 섹션 구조 (한 파일, 목표 약 130줄 이하)`, `--help·에러 메시지 작성 규칙 (PR5)` (+49 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 458 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `BridgeCase` to `.finished`, `ResumeFrom`, `Result`, `ItemsAndPaths`, `engine`, `SelectorsAreExclusive`, `wait_until`, `Codex Argument Passthrough Tests`, `Model Catalog Checks`, `APidAnotherProcessNowHolds`, `Doctor Diagnostics Tests`, `Exit Code Contract`, `Run Terminal States`, `Next Step Hints`, `ThroughASymlink`, `StopLadder`, `Help Text Tests`, `Event Log Cursors`, `CLI Output Frame`, `DamagedLines`, `test_run_lifecycle.py`, `test_resume.py`, `AnOlderReleasesRegistry`?**
  _High betweenness centrality (0.500) - this node is a cross-community bridge._
- **Why does `check()` connect `read_meta` to `create.py`, `Refusal`, `engine`?**
  _High betweenness centrality (0.329) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Refusal` to `cli.py`, `result.py`, `log.py`, `create.py`, `git/__init__.py`, `batch/commands.py`, `registry/__init__.py`, `read_meta`, `runs.py`, `main`, `doctor.py`, `resolve_project`, `model_catalog`?**
  _High betweenness centrality (0.218) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Context`, `합의 장부`, `최종 디렉터리 구조` to the rest of the system?**
  _54 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `events.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11954022988505747 - nodes in this community are weakly interconnected._
- **Should `.finished` be split into smaller, more focused modules?**
  _Cohesion score 0.07764876632801161 - nodes in this community are weakly interconnected._