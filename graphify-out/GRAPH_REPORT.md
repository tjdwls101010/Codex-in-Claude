# Graph Report - codex in claude  (2026-09-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 911 nodes · 1872 edges · 65 communities (35 shown, 29 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 181 edges (avg confidence: 0.85)
- Token cost: 34,788 input · 1,670 output

## Graph Freshness
- Built from commit: `0da57e33`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Codex Event Formatting
- Worktree Cleanup Tests
- Batch Group Tests
- CLI Command Parser
- Doctor and Worktree Planning
- Resume Thread Selection Tests
- Observe View Tests
- Run Log and Liveness
- Bridge Test Harness
- Batch Member Spawning
- Git Repository Queries
- Batch Start and Rounds
- Group Cleanup and Claiming
- Event Formatting Tests
- Run Supervisor Process
- Shared Test Scaffolding
- Package Structure Tests
- CLI Contract Tests
- End-to-End Scenario Runner
- Orphaned Run Liveness
- Codex Argument Passthrough Tests
- Settings Precedence Tests
- TOML Config Parsing Tests
- Argv and Preamble Tests
- Model Catalog Checks
- Run Lifecycle Tests
- Doctor Diagnostics Tests
- Real Codex Smoke Tests
- Exit Code Contract
- Skill Doc Consistency Tests
- Run Terminal States
- Fake Codex Stub
- Next Step Hints
- Symlink Install Tests
- Stop Signal Ladder
- Help Text Tests
- Event Log Cursors
- Stale Run Reaping
- Test Output Readers
- CLI Output Frame
- Damaged Event Lines
- Legacy Waiting Runs
- Signal Ladder Order
- Codex Argv Building
- Codex Skill Guidance
- Codex in Claude Features
- Release History
- Run Directory Claiming
- Registry Lock Failures
- Code of Conduct
- Security Policy
- Graph Navigation Workflow
- Batch Package Init
- Codex CLI Package Init
- Git Package Init
- Codex Package Init
- Observe Package Init
- Registry Package Init
- Runs Package Init
- Contribution Guidelines
- S6 Scenarios
- Graphify Codebase Navigation
- Contribution Verification Tiers
- Path Type

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 63 edges
2. `Refusal` - 48 edges
3. `wait_until()` - 25 edges
4. `find_run()` - 24 edges
5. `Clean` - 23 edges
6. `alive()` - 21 edges
7. `reap()` - 20 edges
8. `log()` - 19 edges
9. `iter_runs()` - 19 edges
10. `ResumeFrom` - 18 edges

## Surprising Connections (you probably didn't know these)
- `log()` --uses--> `CursorOutOfRange`  [INFERRED]
  .claude/skills/codex/scripts/codex/observe/log.py → .claude/skills/codex/scripts/codex/codex_cli/events.py
- `cmd_batch_start()` --calls--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py
- `cmd_log()` --calls--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py
- `cmd_resume()` --calls--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py
- `cmd_status()` --calls--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py

## Import Cycles
- None detected.

## Communities (65 total, 29 thin omitted)

### Community 0 - "Codex Event Formatting"
Cohesion: 0.07
Nodes (56): CursorOutOfRange, find_item(), first_thread_id(), format_events(), _format_item(), head_tail(), _indent(), Path (+48 more)

### Community 1 - "Worktree Cleanup Tests"
Cohesion: 0.08
Nodes (9): Clean, Overlaps, `batch start --worktree`: which members get a checkout, what the checkout…, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout (+1 more)

### Community 2 - "Batch Group Tests"
Cohesion: 0.09
Nodes (8): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 3 - "CLI Command Parser"
Cohesion: 0.08
Nodes (33): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_batch_start(), cmd_log(), cmd_resume(), cmd_start() (+25 more)

### Community 4 - "Doctor and Worktree Planning"
Cohesion: 0.08
Nodes (35): doctor_reply(), The report, with the exit code that says whether a blocker would stop a run., What a batch is asked to do: the ordered tasks, each validated before anything…, plan_worktrees(), reasons_for(), Isolation for a batch: which members get a git checkout of their own, cut from…, Whether `--worktree` would isolate this member: a fresh writer with no cwd of…, Why `--worktree` would pass this member over, in the caller's words, or None. (+27 more)

### Community 5 - "Resume Thread Selection Tests"
Cohesion: 0.08
Nodes (10): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted (+2 more)

### Community 6 - "Observe View Tests"
Cohesion: 0.07
Nodes (9): AnOlderReleasesRegistry, answer_fixture(), GroupResult, Listing, What `status` and `result` say about runs: progress while live, the answer once…, `n` finished runs written straight into the registry, all the same shape so…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, Result (+1 more)

### Community 7 - "Run Log and Liveness"
Cohesion: 0.12
Nodes (36): _member_liveness(), `(live members, members whose meta.json will not parse)` — unknown is kept…, _overlapping_writers(), Live runs whose recorded cwds overlap (either inside the other), where at least…, log(), dump(), step(), `log`: a run's or a group's events, filtered to a level, from a byte cursor,… (+28 more)

### Community 8 - "Bridge Test Harness"
Cohesion: 0.08
Nodes (12): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded)., The `-c key=value` entries of an argv, as a dict of raw values., A --tasks-file; a bare string is a `{"prompt": ...}` task. (+4 more)

### Community 9 - "Batch Member Spawning"
Cohesion: 0.11
Nodes (28): clean(), Spawning a batch: each member's slot recorded before it starts, each member…, spawn_members(), spawn_task(), A member's options: the group's as defaults, the task's own fields over them., task_args(), The project a command works on: the git top level of `explicit`, or of the…, resolve_project() (+20 more)

### Community 10 - "Git Repository Queries"
Cohesion: 0.14
Nodes (27): _covered_by(), ignored_entries(), is_dirty(), missing_at_base(), Path, What the git CLI says about a repository: its top level, its identity, a…, repo_identity(), resolve_base() (+19 more)

### Community 11 - "Batch Start and Rounds"
Cohesion: 0.13
Nodes (19): Cleaning a group: removing its worktrees and releasing its name, never taking…, `batch start` and `batch clean`., The group name's rule and `--base` without `--worktree` are the command…, start(), A next round: `batch start --resume-from` pairs task i with member i of an…, check_task_settings(), load_tasks(), The ordered task list: `--task` prompts first (as typed), then `--tasks-file`… (+11 more)

### Community 12 - "Group Cleanup and Claiming"
Cohesion: 0.23
Nodes (24): _check_liftable_guards(), clean_group(), The `stop` calls that end these runs: the group's when the run is one of its…, Remove a group's worktrees and release its name when nothing is left behind.…, The refusals `--force` lifts, in check order; returns what was overridden,…, _remove_worktrees(), stop_commands(), pair_with_previous() (+16 more)

### Community 13 - "Event Formatting Tests"
Cohesion: 0.11
Nodes (4): FormatEvents, Levels, `codex.codex_cli.events.format_events` on events built by hand, one kind at a…, Show

### Community 14 - "Run Supervisor Process"
Cohesion: 0.13
Nodes (19): _check_registry(), Merge `fields` into meta.json under the run's lock., update_meta(), end_group(), Path, The detached supervisor that runs Codex and records its outcome, and the signal…, Start the run's supervisor in a new session, re-executing the entrypoint.…, SIGINT, then SIGTERM, then SIGKILL to a process group, then a SIGKILL sweep,… (+11 more)

### Community 15 - "Shared Test Scaffolding"
Cohesion: 0.14
Nodes (11): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import an engine module (`"codex.runs.settings"`, `"codex.codex_cli.argv"`, …)…, `codex.codex_cli.config`: the top-level values this skill reads from the user's…, `doctor`: one line describing the environment a run would start in, exit 2 when…, Reading a run's event stream: exact cursors, damaged lines that are counted…, ManyRunsAtOnce, ManyWritersOneMeta (+3 more)

### Community 16 - "Package Structure Tests"
Cohesion: 0.15
Nodes (12): imports(), package_files(), The skill's tree is an interface read before any file, so its shape is checked…, The top-level name under codex/ a file belongs to., `(line, level, dotted name)` for every import in a file, including those inside…, Lines that change `sys.path`, however it is reached: `sys.path`, `import sys as…, skill_files(), Structure (+4 more)

### Community 17 - "CLI Contract Tests"
Cohesion: 0.12
Nodes (8): FlagsThatWouldDecideNothing, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, Two selectors name different things; honouring one silently drops the other., A flag that parses and changes nothing reads as having been obeyed, so each is…, Flags nothing used, removed from the parser rather than left to accept and do…, RemovedSurface, SelectorsAreExclusive, TheRegistryGoesWhereItIsTold

### Community 18 - "End-to-End Scenario Runner"
Cohesion: 0.21
Nodes (15): Path, base_cmd(), control_text(), digest(), entry(), main(), A session whose stdin stays open, so a finished background task can start…, Run one S6 scenario against the draft, the control or the v0.8.0 skill,… (+7 more)

### Community 19 - "Orphaned Run Liveness"
Cohesion: 0.22
Nodes (4): alive(), A run recorded `orphaned` whose codex is demonstrably still going: its…, wait_until(), AnOrphanThatIsStillWriting

### Community 21 - "Settings Precedence Tests"
Cohesion: 0.23
Nodes (3): Precedence, `codex.runs.settings.resolve`: one precedence for every setting — the flag,…, resolve()

### Community 23 - "Argv and Preamble Tests"
Cohesion: 0.22
Nodes (4): build(), BuildArgv, Preamble, `codex.codex_cli.argv`: the argv a run hands Codex, and the paragraphs in front…

### Community 24 - "Model Catalog Checks"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 25 - "Run Lifecycle Tests"
Cohesion: 0.24
Nodes (5): BridgeCase, APidAnotherProcessNowHolds, DetachedStart, A run's life: detached start, every terminal state, the stop ladder, and what a…, The system hands an exited process's pid to the next process it starts, so a…

### Community 27 - "Real Codex Smoke Tests"
Cohesion: 0.29
Nodes (4): skipUnless, S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, `result`'s JSON header line and the message after it., RealCodex

### Community 29 - "Skill Doc Consistency Tests"
Cohesion: 0.25
Nodes (3): SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk()

### Community 31 - "Fake Codex Stub"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 33 - "Symlink Install Tests"
Cohesion: 0.32
Nodes (4): Installs: the skill reached through a symlink, from a directory that has…, The call SKILL.md teaches, through the link, from a directory unrelated to the…, ThroughASymlink, finished()

### Community 43 - "Codex Argv Building"
Cohesion: 0.60
Nodes (4): apply_preamble(), build_argv(), toml_cfg(), uncommitted_clause()

### Community 44 - "Codex Skill Guidance"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 45 - "Codex in Claude Features"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 46 - "Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 47 - "Run Directory Claiming"
Cohesion: 0.50
Nodes (4): claim_run_dir(), new_run_id(), Sortable and human-readable. Same-second, same-label ids collide about once in…, Take exclusive ownership of a fresh run directory: `mkdir` without `exist_ok`…

### Community 49 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 50 - "Security Policy"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

## Knowledge Gaps
- **19 isolated node(s):** `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline`, `Codex Delegation Mode Selection`, `Codex Operational Gotchas` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 342 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `Bridge Test Harness` to `Worktree Cleanup Tests`, `Batch Group Tests`, `Resume Thread Selection Tests`, `Observe View Tests`, `Event Formatting Tests`, `Shared Test Scaffolding`, `CLI Contract Tests`, `Orphaned Run Liveness`, `Codex Argument Passthrough Tests`, `Model Catalog Checks`, `Doctor Diagnostics Tests`, `Exit Code Contract`, `Next Step Hints`, `Help Text Tests`, `Event Log Cursors`, `Test Output Readers`, `CLI Output Frame`, `Damaged Event Lines`, `Registry Lock Failures`?**
  _High betweenness centrality (0.167) - this node is a cross-community bridge._
- **Why does `wait_until()` connect `Orphaned Run Liveness` to `Symlink Install Tests`, `Batch Group Tests`, `Worktree Cleanup Tests`, `Resume Thread Selection Tests`, `Observe View Tests`, `Bridge Test Harness`, `Legacy Waiting Runs`, `Shared Test Scaffolding`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Why does `WorktreeCase` connect `Worktree Cleanup Tests` to `Bridge Test Harness`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `Refusal` (e.g. with `cmd_batch_start()` and `cmd_log()`) actually correct?**
  _`Refusal` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `wait_until()` (e.g. with `.test_a_run_started_through_the_link_is_finished_by_its_detached_supervisor()` and `.test_once_its_codex_is_gone_the_follower_ends_on_orphaned()`) actually correct?**
  _`wait_until()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `find_run()` (e.g. with `_member_liveness()` and `_remove_worktrees()`) actually correct?**
  _`find_run()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._