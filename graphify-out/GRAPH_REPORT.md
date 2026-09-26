# Graph Report - codex in claude  (2026-09-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 882 nodes · 1861 edges · 54 communities (27 shown, 26 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 152 edges (avg confidence: 0.85)
- Token cost: 33,416 input · 763 output

## Graph Freshness
- Built from commit: `68befc31`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Group Cleaning and Liveness
- Batch Start and Tasks
- Codex Event Log Formatting
- Batch Clean Tests
- CLI Help and Lock Tests
- CLI Parser and Commands
- Batch Resume and Follow Tests
- Event Cursor Tests
- Resume Thread Tests
- Bridge Test Harness
- Orphan Liveness Test Scaffolding
- Status and Result Tests
- Package Structure Tests
- Install and Skill Text Tests
- Git Repository Queries
- End-to-End Scenario Runner
- Codex Invocation Argument Tests
- Codex Config Parsing Tests
- CLI Output Contract Tests
- Argv Building Tests
- Doctor Diagnostics Tests
- Model Catalog Validation
- Real Codex Smoke Tests
- Run Listing Tests
- Exit Code Contract
- Run Terminal States
- Fake Codex Binary
- Next Step Hints
- Stop Signal Ladder
- Exclusive Selector Rules
- Codex Argv Builder
- Codex Skill Guidance
- Codex Bridge Features
- Legacy Registry Compatibility
- Release History
- Legacy Waiting Runs
- Code of Conduct
- Security Policy
- No-Op Flag Refusal
- Detached Start Tests
- Graph Navigation Workflow
- Batch Package
- Codex CLI Package
- Git Package
- Codex Root Package
- Observe Package
- Registry Package
- Runs Package
- Contribution Guidelines
- S6 Scenarios
- Graphify-First Navigation
- Contribution Verification Tiers
- Path Utility

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 69 edges
2. `Refusal` - 51 edges
3. `wait_until()` - 26 edges
4. `Clean` - 23 edges
5. `find_run()` - 23 edges
6. `alive()` - 22 edges
7. `log()` - 19 edges
8. `reap()` - 19 edges
9. `ResumeFrom` - 18 edges
10. `iter_runs()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `main()` --uses--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py
- `log()` --uses--> `CursorOutOfRange`  [INFERRED]
  .claude/skills/codex/scripts/codex/observe/log.py → .claude/skills/codex/scripts/codex/codex_cli/events.py
- `follow_group()` --calls--> `group_tail()`  [INFERRED]
  .claude/skills/codex/scripts/codex/observe/status.py → .claude/skills/codex/scripts/codex/observe/follow.py
- `status()` --calls--> `list_groups()`  [INFERRED]
  .claude/skills/codex/scripts/codex/observe/status.py → .claude/skills/codex/scripts/codex/registry/groups.py
- `result_group()` --calls--> `resolve_group()`  [INFERRED]
  .claude/skills/codex/scripts/codex/observe/result.py → .claude/skills/codex/scripts/codex/registry/groups.py

## Import Cycles
- None detected.

## Communities (54 total, 26 thin omitted)

### Community 0 - "Group Cleaning and Liveness"
Cohesion: 0.06
Nodes (105): _check_liftable_guards(), clean_group(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The `stop` calls that end these runs: the group's when the run is one of its…, Remove a group's worktrees and release its name when nothing is left behind.…, `(live members, members whose meta.json will not parse)` — unknown is kept…, The refusals `--force` lifts, in check order; returns what was overridden,… (+97 more)

### Community 1 - "Batch Start and Tasks"
Cohesion: 0.06
Nodes (51): `batch start` and `batch clean`., A next round: `batch start --resume-from` pairs task i with member i of an…, Spawning a batch: each member's slot recorded before it starts, each member…, check_task_settings(), load_tasks(), What a batch is asked to do: the ordered tasks, each validated before anything…, The ordered task list: `--task` prompts first (as typed), then `--tasks-file`…, A member's options: the group's as defaults, the task's own fields over them. (+43 more)

### Community 2 - "Codex Event Log Formatting"
Cohesion: 0.08
Nodes (49): CursorOutOfRange, find_item(), format_events(), _format_item(), head_tail(), _indent(), Path, read_events() (+41 more)

### Community 3 - "Batch Clean Tests"
Cohesion: 0.08
Nodes (8): Clean, Overlaps, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout, WorktreeCase

### Community 4 - "CLI Help and Lock Tests"
Cohesion: 0.06
Nodes (18): engine(), Import an engine module (`"codex.runs.settings"`, `"codex.codex_cli.argv"`, …)…, HelpIsTheInterface, walk(), AFailureInsideALockIsReportedAsItself, AStaleReap, ManyRunsAtOnce, ManyWritersOneMeta (+10 more)

### Community 5 - "CLI Parser and Commands"
Cohesion: 0.08
Nodes (37): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_batch_start(), cmd_log(), cmd_resume(), cmd_start() (+29 more)

### Community 6 - "Batch Resume and Follow Tests"
Cohesion: 0.09
Nodes (7): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 7 - "Event Cursor Tests"
Cohesion: 0.07
Nodes (8): Cursors, DamagedLines, FormatEvents, Levels, Reading a run's event stream: exact cursors, damaged lines that are counted…, `codex.codex_cli.events.format_events` on events built by hand, one kind at a…, A line that will not parse is kept as `unparsed` and counted, apart from…, Show

### Community 8 - "Resume Thread Tests"
Cohesion: 0.08
Nodes (10): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted (+2 more)

### Community 9 - "Bridge Test Harness"
Cohesion: 0.07
Nodes (14): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded). (+6 more)

### Community 10 - "Orphan Liveness Test Scaffolding"
Cohesion: 0.15
Nodes (8): alive(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, A run recorded `orphaned` whose codex is demonstrably still going: its…, wait_until(), Batches: N runs under one name, validated before anything starts, recorded slot…, AnOrphanThatIsStillWriting, A run's life: detached start, every terminal state, the stop ladder, and what a…, `batch start --worktree`: which members get a checkout, what the checkout…

### Community 11 - "Status and Result Tests"
Cohesion: 0.11
Nodes (5): answer_fixture(), GroupResult, What `status` and `result` say about runs: progress while live, the answer once…, Result, StatusOfOneRun

### Community 12 - "Package Structure Tests"
Cohesion: 0.15
Nodes (12): imports(), package_files(), The skill's tree is an interface read before any file, so its shape is checked…, The top-level name under codex/ a file belongs to., `(line, level, dotted name)` for every import in a file, including those inside…, Lines that change `sys.path`, however it is reached: `sys.path`, `import sys as…, skill_files(), Structure (+4 more)

### Community 13 - "Install and Skill Text Tests"
Cohesion: 0.14
Nodes (8): BridgeCase, Installs: the skill reached through a symlink, from a directory that has…, The call SKILL.md teaches, through the link, from a directory unrelated to the…, SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk(), ThroughASymlink, finished()

### Community 14 - "Git Repository Queries"
Cohesion: 0.29
Nodes (15): _covered_by(), ignored_entries(), is_dirty(), missing_at_base(), Path, What the git CLI says about a repository: its top level, its identity, a…, resolve_base(), run_git() (+7 more)

### Community 15 - "End-to-End Scenario Runner"
Cohesion: 0.21
Nodes (15): Path, base_cmd(), control_text(), digest(), entry(), main(), A session whose stdin stays open, so a finished background task can start…, Run one S6 scenario against the draft, the control or the v0.8.0 skill,… (+7 more)

### Community 18 - "CLI Output Contract Tests"
Cohesion: 0.14
Nodes (5): OutputFrame, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, Flags nothing used, removed from the parser rather than left to accept and do…, RemovedSurface, TheRegistryGoesWhereItIsTold

### Community 19 - "Argv Building Tests"
Cohesion: 0.22
Nodes (4): build(), BuildArgv, Preamble, `codex.codex_cli.argv`: the argv a run hands Codex, and the paragraphs in front…

### Community 21 - "Model Catalog Validation"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 22 - "Real Codex Smoke Tests"
Cohesion: 0.29
Nodes (4): skipUnless, S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, `result`'s JSON header line and the message after it., RealCodex

### Community 26 - "Fake Codex Binary"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 30 - "Codex Argv Builder"
Cohesion: 0.60
Nodes (4): apply_preamble(), build_argv(), toml_cfg(), uncommitted_clause()

### Community 31 - "Codex Skill Guidance"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 32 - "Codex Bridge Features"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 34 - "Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 36 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 37 - "Security Policy"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

## Knowledge Gaps
- **19 isolated node(s):** `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline`, `Codex Delegation Mode Selection`, `Codex Operational Gotchas` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 318 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `Bridge Test Harness` to `Batch Clean Tests`, `CLI Help and Lock Tests`, `Batch Resume and Follow Tests`, `Event Cursor Tests`, `Resume Thread Tests`, `Orphan Liveness Test Scaffolding`, `Status and Result Tests`, `Codex Invocation Argument Tests`, `CLI Output Contract Tests`, `Doctor Diagnostics Tests`, `Model Catalog Validation`, `Run Listing Tests`, `Exit Code Contract`, `Run Terminal States`, `Next Step Hints`, `Stop Signal Ladder`, `Exclusive Selector Rules`, `Legacy Registry Compatibility`, `Legacy Waiting Runs`, `No-Op Flag Refusal`, `Detached Start Tests`?**
  _High betweenness centrality (0.200) - this node is a cross-community bridge._
- **Why does `WorktreeCase` connect `Batch Clean Tests` to `Bridge Test Harness`, `Orphan Liveness Test Scaffolding`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Group Cleaning and Liveness` to `Batch Start and Tasks`, `Codex Event Log Formatting`, `CLI Parser and Commands`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `find_run()` (e.g. with `_member_liveness()` and `_remove_worktrees()`) actually correct?**
  _`find_run()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Group Cleaning and Liveness` be split into smaller, more focused modules?**
  _Cohesion score 0.0592396109637489 - nodes in this community are weakly interconnected._