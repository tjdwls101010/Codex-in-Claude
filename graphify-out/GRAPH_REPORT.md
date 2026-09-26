# Graph Report - codex in claude  (2026-09-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 878 nodes · 1861 edges · 61 communities (31 shown, 29 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 149 edges (avg confidence: 0.85)
- Token cost: 34,461 input · 852 output

## Graph Freshness
- Built from commit: `c90d60c7`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Run Registry and Reaping
- Batch Clean Tests
- Batch Member Spawning
- CLI Command Parser
- Bridge Test Harness
- Batch Group Lifecycle Tests
- Group Result Collection
- Group Worktree Cleanup
- Orphaned Run Liveness
- Group Results and Listing Tests
- Test Scaffolding and Config
- Thread Resume Resolution
- Event Log Formatting
- Package Structure Rules
- Git Repository Queries
- Codex Invocation Arguments
- Settings Precedence Tests
- End-to-End Scenario Runner
- TOML Config Parsing
- Argv and Preamble Building
- Model Catalog Validation
- Status and Legacy Registry
- Detached Run Terminal States
- Doctor Diagnostics
- Real Codex Smoke Tests
- CLI Exit Codes
- Skill Doc Consistency
- Fake Codex Binary
- Next-Step Follow Hints
- Help Text Interface
- Exclusive Selector Rules
- Log Cursor Polling
- Stale Run Reaping
- Unknown Thread Resume
- One Turn Per Thread
- JSON Output Frame
- Damaged Log Lines
- Symlinked Skill Invocation
- Process Signal Ladder
- Codex Argv Builder
- Codex Skill Guidance
- Skill Feature Overview
- Release History
- Removed CLI Flags
- Registry Lock Failures
- Code of Conduct
- Security Policy
- Concurrent Run Starts
- Graph Navigation Workflow
- Batch Package
- Codex CLI Formats Package
- Git Package
- Codex Package Root
- Observe Package
- Registry Package
- Runs Package
- Contribution Guidelines
- S6 Scenarios
- Graphify Navigation
- Contribution Verification Tiers

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 71 edges
2. `Refusal` - 51 edges
3. `wait_until()` - 27 edges
4. `Clean` - 23 edges
5. `find_run()` - 23 edges
6. `alive()` - 23 edges
7. `log()` - 19 edges
8. `reap()` - 19 edges
9. `ResumeFrom` - 18 edges
10. `iter_runs()` - 18 edges

## Surprising Connections (you probably didn't know these)
- `main()` --uses--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py
- `spawn_members()` --uses--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/codex/batch/spawn.py → .claude/skills/codex/scripts/codex/errors.py
- `progress()` --calls--> `scan_progress()`  [INFERRED]
  .claude/skills/codex/scripts/codex/observe/rows.py → .claude/skills/codex/scripts/codex/codex_cli/events.py
- `build_parser()` --calls--> `supervise()`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/runs/supervisor.py
- `_task_from_line()` --calls--> `clip()`  [INFERRED]
  .claude/skills/codex/scripts/codex/batch/tasks.py → .claude/skills/codex/scripts/codex/util.py

## Import Cycles
- None detected.

## Communities (61 total, 29 thin omitted)

### Community 0 - "Run Registry and Reaping"
Cohesion: 0.06
Nodes (96): _member_liveness(), `(live members, members whose meta.json will not parse)` — unknown is kept…, A next round: `batch start --resume-from` pairs task i with member i of an…, CursorOutOfRange, find_item(), first_thread_id(), format_events(), _format_item() (+88 more)

### Community 1 - "Batch Clean Tests"
Cohesion: 0.08
Nodes (8): Clean, Overlaps, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout, WorktreeCase

### Community 2 - "Batch Member Spawning"
Cohesion: 0.07
Nodes (44): Spawning a batch: each member's slot recorded before it starts, each member…, spawn_members(), spawn_task(), check_task_settings(), load_tasks(), What a batch is asked to do: the ordered tasks, each validated before anything…, The ordered task list: `--task` prompts first (as typed), then `--tasks-file`…, A member's options: the group's as defaults, the task's own fields over them. (+36 more)

### Community 3 - "CLI Command Parser"
Cohesion: 0.08
Nodes (35): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_batch_start(), cmd_log(), cmd_resume(), cmd_start() (+27 more)

### Community 4 - "Bridge Test Harness"
Cohesion: 0.07
Nodes (15): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded). (+7 more)

### Community 5 - "Batch Group Lifecycle Tests"
Cohesion: 0.09
Nodes (7): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 6 - "Group Result Collection"
Cohesion: 0.11
Nodes (33): changed_paths(), final_message(), member_result(), overlaps(), Path, Collecting a group: what each member concluded and which paths more than one…, Paths a run wrote, as `(repository, repo-relative path)` pairs. Codex reports…, What a run concluded: its `-o` file decoded as UTF-8 (a byte that is not,… (+25 more)

### Community 7 - "Group Worktree Cleanup"
Cohesion: 0.15
Nodes (32): _check_liftable_guards(), clean_group(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The `stop` calls that end these runs: the group's when the run is one of its…, Remove a group's worktrees and release its name when nothing is left behind.…, The refusals `--force` lifts, in check order; returns what was overridden,…, _remove_worktrees(), stop_commands() (+24 more)

### Community 8 - "Orphaned Run Liveness"
Cohesion: 0.10
Nodes (10): alive(), wait_until(), Batches: N runs under one name, validated before anything starts, recorded slot…, AnOrphanThatIsStillWriting, LegacyWaitingRun, A run's life: detached start, every terminal state, the stop ladder, and what a…, Signals go to the run's recorded process group, SIGINT first, escalating only…, Releases before 0.8 could leave a batch member `waiting` on its predecessor.… (+2 more)

### Community 9 - "Group Results and Listing Tests"
Cohesion: 0.09
Nodes (5): answer_fixture(), GroupResult, Listing, `n` finished runs written straight into the registry, all the same shape so…, Result

### Community 10 - "Test Scaffolding and Config"
Cohesion: 0.11
Nodes (15): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import an engine module (`"codex.runs.settings"`, `"codex.codex_cli.argv"`, …)…, FlagsThatWouldDecideNothing, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, A flag that parses and changes nothing reads as having been obeyed, so each is…, TheRegistryGoesWhereItIsTold, `codex.codex_cli.config`: the top-level values this skill reads from the user's… (+7 more)

### Community 11 - "Thread Resume Resolution"
Cohesion: 0.12
Nodes (4): FindingTheThread, An explicit flag, then what a resumed thread recorded, then the user's…, SettingsAreReasserted, UserDefaultsAndTheirPrecedence

### Community 12 - "Event Log Formatting"
Cohesion: 0.11
Nodes (4): FormatEvents, Levels, `codex.codex_cli.events.format_events` on events built by hand, one kind at a…, Show

### Community 13 - "Package Structure Rules"
Cohesion: 0.15
Nodes (12): imports(), package_files(), The skill's tree is an interface read before any file, so its shape is checked…, The top-level name under codex/ a file belongs to., `(line, level, dotted name)` for every import in a file, including those inside…, Lines that change `sys.path`, however it is reached: `sys.path`, `import sys as…, skill_files(), Structure (+4 more)

### Community 14 - "Git Repository Queries"
Cohesion: 0.26
Nodes (17): _covered_by(), git_toplevel(), ignored_entries(), is_dirty(), missing_at_base(), Path, What the git CLI says about a repository: its top level, its identity, a…, repo_identity() (+9 more)

### Community 16 - "Settings Precedence Tests"
Cohesion: 0.23
Nodes (3): Precedence, `codex.runs.settings.resolve`: one precedence for every setting — the flag,…, resolve()

### Community 17 - "End-to-End Scenario Runner"
Cohesion: 0.23
Nodes (13): base_cmd(), control_text(), digest(), main(), Path, Run one S6 scenario against the draft or the control SKILL.md, isolated, and…, The draft's frontmatter and its call paragraph, without any judgement text., Detached runs outlive the session that started them; stop them so none keeps… (+5 more)

### Community 19 - "Argv and Preamble Building"
Cohesion: 0.22
Nodes (4): build(), BuildArgv, Preamble, `codex.codex_cli.argv`: the argv a run hands Codex, and the paragraphs in front…

### Community 20 - "Model Catalog Validation"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 21 - "Status and Legacy Registry"
Cohesion: 0.18
Nodes (4): AnOlderReleasesRegistry, What `status` and `result` say about runs: progress while live, the answer once…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, StatusOfOneRun

### Community 24 - "Real Codex Smoke Tests"
Cohesion: 0.29
Nodes (4): skipUnless, S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, `result`'s JSON header line and the message after it., RealCodex

### Community 26 - "Skill Doc Consistency"
Cohesion: 0.25
Nodes (3): SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk()

### Community 27 - "Fake Codex Binary"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 33 - "Unknown Thread Resume"
Cohesion: 0.33
Nodes (4): Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, ResumeCase, ThreadsTheRegistryNeverSaw

### Community 37 - "Symlinked Skill Invocation"
Cohesion: 0.47
Nodes (3): The call SKILL.md teaches, through the link, from a directory unrelated to the…, ThroughASymlink, finished()

### Community 39 - "Codex Argv Builder"
Cohesion: 0.60
Nodes (4): apply_preamble(), build_argv(), toml_cfg(), uncommitted_clause()

### Community 40 - "Codex Skill Guidance"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 41 - "Skill Feature Overview"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 42 - "Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 45 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 46 - "Security Policy"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

## Knowledge Gaps
- **19 isolated node(s):** `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline`, `Codex Delegation Mode Selection`, `Codex Operational Gotchas` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 315 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `Bridge Test Harness` to `Batch Clean Tests`, `Batch Group Lifecycle Tests`, `Orphaned Run Liveness`, `Group Results and Listing Tests`, `Test Scaffolding and Config`, `Event Log Formatting`, `Codex Invocation Arguments`, `Model Catalog Validation`, `Status and Legacy Registry`, `Detached Run Terminal States`, `Doctor Diagnostics`, `CLI Exit Codes`, `Next-Step Follow Hints`, `Help Text Interface`, `Exclusive Selector Rules`, `Log Cursor Polling`, `Unknown Thread Resume`, `JSON Output Frame`, `Damaged Log Lines`, `Symlinked Skill Invocation`, `Removed CLI Flags`, `Registry Lock Failures`, `Concurrent Run Starts`?**
  _High betweenness centrality (0.209) - this node is a cross-community bridge._
- **Why does `WorktreeCase` connect `Batch Clean Tests` to `Orphaned Run Liveness`, `Bridge Test Harness`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Run Registry and Reaping` to `Batch Member Spawning`, `CLI Command Parser`, `Group Result Collection`, `Group Worktree Cleanup`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `find_run()` (e.g. with `_member_liveness()` and `_remove_worktrees()`) actually correct?**
  _`find_run()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Run Registry and Reaping` be split into smaller, more focused modules?**
  _Cohesion score 0.057764186204553175 - nodes in this community are weakly interconnected._