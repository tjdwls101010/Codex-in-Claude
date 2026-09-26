# Graph Report - codex in claude  (2026-09-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 768 nodes · 1873 edges · 50 communities (29 shown, 20 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 25 edges (avg confidence: 0.86)
- Token cost: 33,259 input · 1,349 output

## Graph Freshness
- Built from commit: `5e988a30`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Group Cleaning and Reaping
- CLI Command Parser
- Codex Argv and Events
- Clean Command Tests
- Batch Group Tests
- Event Log Cursor Tests
- Resume Thread Selection Tests
- Batch Worktree Isolation
- Result and Listing Tests
- Package Structure Tests
- Orphaned Run Liveness
- Bridge Test Harness
- CLI Contract Tests
- Shared Test Scaffolding
- Codex Invocation Tests
- Settings Precedence Tests
- E2E Scenario Runner
- Skill Text Accuracy Tests
- Argv Builder Tests
- Doctor Diagnostics Tests
- Model Catalog Validation
- Bridge Command Helpers
- Run Lifecycle Tests
- Terminal State Tests
- Real Codex Smoke Tests
- Fake Codex Binary
- Detached Process Fixtures
- Stop Ladder Tests
- Help Text Tests
- Stale Reap Tests
- CLI Output Frame
- Signal Ladder Order
- Codex Skill Guidance
- Core Skill Features
- Legacy Registry Compatibility
- Release History
- Registry Lock Failures
- Code of Conduct
- Security Policy
- Detached Start Tests
- Graph Navigation Workflow
- Codex CLI Package
- Git Package
- Codex Package Root
- Run Registry Package
- Contribution Guidelines
- E2E Scenarios Doc
- Graphify-First Navigation
- Contribution Verification

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 68 edges
2. `Refusal` - 53 edges
3. `find_run()` - 30 edges
4. `wait_until()` - 27 edges
5. `reap()` - 25 edges
6. `Clean` - 23 edges
7. `alive()` - 23 edges
8. `resolve_project()` - 22 edges
9. `iter_runs()` - 22 edges
10. `is_live()` - 20 edges

## Surprising Connections (you probably didn't know these)
- `spawn_members()` --uses--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/codex/batch/spawn.py → .claude/skills/codex/scripts/codex/errors.py
- `build_parser()` --indirect_call--> `show()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/observe/show.py
- `log()` --uses--> `CursorOutOfRange`  [INFERRED]
  .claude/skills/codex/scripts/codex/observe/log.py → .claude/skills/codex/scripts/codex/codex_cli/events.py
- `main()` --uses--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py
- `_check_liftable_guards()` --calls--> `Refusal`  [EXTRACTED]
  .claude/skills/codex/scripts/codex/batch/clean.py → .claude/skills/codex/scripts/codex/errors.py

## Import Cycles
- None detected.

## Communities (50 total, 20 thin omitted)

### Community 0 - "Group Cleaning and Reaping"
Cohesion: 0.08
Nodes (92): _check_liftable_guards(), clean_group(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, _remove_worktrees(), stop_commands(), clean(), start() (+84 more)

### Community 1 - "CLI Command Parser"
Cohesion: 0.08
Nodes (42): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_log(), cmd_result(), cmd_resume(), cmd_status() (+34 more)

### Community 2 - "Codex Argv and Events"
Cohesion: 0.09
Nodes (46): load_tasks(), _task_from_line(), apply_preamble(), build_argv(), toml_cfg(), uncommitted_clause(), find_item(), first_thread_id() (+38 more)

### Community 3 - "Clean Command Tests"
Cohesion: 0.08
Nodes (8): Clean, Overlaps, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout, WorktreeCase

### Community 4 - "Batch Group Tests"
Cohesion: 0.10
Nodes (8): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 5 - "Event Log Cursor Tests"
Cohesion: 0.07
Nodes (8): Cursors, DamagedLines, FormatEvents, Levels, Reading a run's event stream: exact cursors, damaged lines that are counted…, `codex.codex_cli.events.format_events` on events built by hand, one kind at a…, A line that will not parse is kept as `unparsed` and counted, apart from…, Show

### Community 6 - "Resume Thread Selection Tests"
Cohesion: 0.08
Nodes (9): FindingTheThread, OneTurnPerThread, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted, ThreadsTheRegistryNeverSaw (+1 more)

### Community 7 - "Batch Worktree Isolation"
Cohesion: 0.17
Nodes (26): task_args(), plan_worktrees(), reasons_for(), Isolation for a batch: which members get a git checkout of their own, cut from…, sharing_note(), wants_worktree(), why_not_isolated(), worktree_report() (+18 more)

### Community 8 - "Result and Listing Tests"
Cohesion: 0.10
Nodes (6): answer_fixture(), GroupResult, Listing, What `status` and `result` say about runs: progress while live, the answer once…, Result, StatusOfOneRun

### Community 9 - "Package Structure Tests"
Cohesion: 0.15
Nodes (12): imports(), package_files(), The skill's tree is an interface read before any file, so its shape is checked…, The top-level name under codex/ a file belongs to., `(line, level, dotted name)` for every import in a file, including those inside…, Lines that change `sys.path`, however it is reached: `sys.path`, `import sys as…, skill_files(), Structure (+4 more)

### Community 10 - "Orphaned Run Liveness"
Cohesion: 0.20
Nodes (5): alive(), A run recorded `orphaned` whose codex is demonstrably still going: its…, wait_until(), Resuming a thread: its settings stay what they were, it is found by the ref the…, `batch start --worktree`: which members get a checkout, what the checkout…

### Community 11 - "Bridge Test Harness"
Cohesion: 0.13
Nodes (6): BridgeCase, Start the CLI without waiting, for races and for killing it midway., Every codex invocation the bridge made, in order (catalog lookups excluded)., The `-c key=value` entries of an argv, as a dict of raw values., A --tasks-file; a bare string is a `{"prompt": ...}` task., One temp project per test. `self.project` is a git repository with one commit,…

### Community 12 - "CLI Contract Tests"
Cohesion: 0.11
Nodes (8): FlagsThatWouldDecideNothing, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, A flag that parses and changes nothing reads as having been obeyed, so each is…, Flags nothing used, removed from the parser rather than left to accept and do…, Two selectors name different things; honouring one silently drops the other., RemovedSurface, SelectorsAreExclusive, TheRegistryGoesWhereItIsTold

### Community 13 - "Shared Test Scaffolding"
Cohesion: 0.18
Nodes (9): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import an engine module (`"codex.runs.settings"`, `"codex.codex_cli.argv"`, …)…, Installs: the skill reached through a symlink, from a directory that has…, ManyRunsAtOnce, ManyWritersOneMeta, The registry under real concurrent processes: many writers on one meta.json, a…, _read() (+1 more)

### Community 15 - "Settings Precedence Tests"
Cohesion: 0.23
Nodes (3): Precedence, `codex.runs.settings.resolve`: one precedence for every setting — the flag,…, resolve()

### Community 16 - "E2E Scenario Runner"
Cohesion: 0.23
Nodes (13): base_cmd(), control_text(), digest(), main(), Path, Run one S6 scenario against the draft or the control SKILL.md, isolated, and…, The draft's frontmatter and its call paragraph, without any judgement text., Detached runs outlive the session that started them; stop them so none keeps… (+5 more)

### Community 17 - "Skill Text Accuracy Tests"
Cohesion: 0.15
Nodes (5): The call SKILL.md teaches, through the link, from a directory unrelated to the…, SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, ThroughASymlink, finished()

### Community 18 - "Argv Builder Tests"
Cohesion: 0.22
Nodes (4): build(), BuildArgv, Preamble, `codex.codex_cli.argv`: the argv a run hands Codex, and the paragraphs in front…

### Community 20 - "Model Catalog Validation"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 21 - "Bridge Command Helpers"
Cohesion: 0.20
Nodes (4): Run a command that answers with one line of JSON, and parse it., `log` output split into (event lines, cursor)., Poll `status --run` (which reaps) until the run is in one of `states`., Wait for every spawned member of a `batch start` reply.

### Community 22 - "Run Lifecycle Tests"
Cohesion: 0.20
Nodes (4): AnOrphanThatIsStillWriting, LegacyWaitingRun, A run's life: detached start, every terminal state, the stop ladder, and what a…, Releases before 0.8 could leave a batch member `waiting` on its predecessor.…

### Community 24 - "Real Codex Smoke Tests"
Cohesion: 0.32
Nodes (3): skipUnless, S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, RealCodex

### Community 25 - "Fake Codex Binary"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 26 - "Detached Process Fixtures"
Cohesion: 0.25
Nodes (3): A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Start a run that stays in its turn, and return (reply, meta) once both pids are…

### Community 32 - "Codex Skill Guidance"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 33 - "Core Skill Features"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 35 - "Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 37 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 38 - "Security Policy"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

## Knowledge Gaps
- **19 isolated node(s):** `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline`, `Codex Delegation Mode Selection`, `Codex Operational Gotchas` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 253 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `Bridge Test Harness` to `Clean Command Tests`, `Batch Group Tests`, `Event Log Cursor Tests`, `Resume Thread Selection Tests`, `Result and Listing Tests`, `Orphaned Run Liveness`, `CLI Contract Tests`, `Shared Test Scaffolding`, `Codex Invocation Tests`, `Skill Text Accuracy Tests`, `Doctor Diagnostics Tests`, `Model Catalog Validation`, `Bridge Command Helpers`, `Run Lifecycle Tests`, `Terminal State Tests`, `Detached Process Fixtures`, `Stop Ladder Tests`, `Help Text Tests`, `CLI Output Frame`, `Legacy Registry Compatibility`, `Registry Lock Failures`, `Detached Start Tests`?**
  _High betweenness centrality (0.225) - this node is a cross-community bridge._
- **Why does `WorktreeCase` connect `Clean Command Tests` to `Orphaned Run Liveness`, `Bridge Test Harness`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Why does `wait_until()` connect `Orphaned Run Liveness` to `Clean Command Tests`, `Batch Group Tests`, `Result and Listing Tests`, `Shared Test Scaffolding`, `Skill Text Accuracy Tests`, `Bridge Command Helpers`, `Run Lifecycle Tests`, `Detached Process Fixtures`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Group Cleaning and Reaping` be split into smaller, more focused modules?**
  _Cohesion score 0.08199612061364839 - nodes in this community are weakly interconnected._
- **Should `CLI Command Parser` be split into smaller, more focused modules?**
  _Cohesion score 0.08116883116883117 - nodes in this community are weakly interconnected._