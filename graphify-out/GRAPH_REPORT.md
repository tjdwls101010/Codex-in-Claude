# Graph Report - codex in claude  (2026-09-26)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 911 nodes · 1883 edges · 69 communities (34 shown, 34 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 175 edges (avg confidence: 0.85)
- Token cost: 35,134 input · 952 output

## Graph Freshness
- Built from commit: `d00fb5db`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Batch Group Cleanup
- Worktree Clean Tests
- Batch Group Tests
- Resume Thread Tests
- Bridge Test Harness
- Observe and Result Tests
- Result Collection
- Batch Start and Tasks
- Git Repository Queries
- CLI Command Parser
- Codex Catalog and Config
- Event Stream Formatting
- Package Structure Tests
- Run Spawning and Creation
- Shared Test Scaffolding
- End-to-End Scenario Runner
- Orphaned Run Liveness
- Codex Argument Passing Tests
- Settings Precedence Tests
- JSON Argument Parser
- Config TOML Parsing Tests
- Event Stream Tests
- Argv Building Tests
- Model Catalog Tests
- Run Lifecycle Tests
- Command Refusals and Show
- Doctor Diagnostics Tests
- Log Detail Levels
- Real Codex Smoke Tests
- Exit Code Contract
- Skill Text Validation
- Run Terminal States
- Fake Codex Stand-in
- Next Step Follow Hints
- Event Formatting Tests
- Symlink Install Tests
- Stop Signal Ladder
- Help Text Interface
- Selector Exclusivity Rules
- Event Cursor Polling
- Stale Run Reaping
- CLI Output Frame
- Legacy Waiting Runs
- Signal Ladder Order
- One-Line Help Formatter
- Codex Argv Builder
- Codex Skill Guidance
- Skill Feature Overview
- Release History
- Removed CLI Surface
- Registry Lock Failures
- Code of Conduct
- Security Policy
- No-Op Flag Refusals
- Concurrent Run Starts
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
- Graphify Navigation
- Contribution Verification Tiers
- Path Type

## God Nodes (most connected - your core abstractions)
1. `BridgeCase` - 63 edges
2. `Refusal` - 50 edges
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
- `main()` --uses--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/cli.py → .claude/skills/codex/scripts/codex/errors.py
- `spawn_members()` --uses--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/codex/batch/spawn.py → .claude/skills/codex/scripts/codex/errors.py
- `refuse_unresolved_run()` --calls--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/codex/registry/runs.py → .claude/skills/codex/scripts/codex/errors.py
- `resolve_implicit_run()` --calls--> `Refusal`  [INFERRED]
  .claude/skills/codex/scripts/codex/registry/runs.py → .claude/skills/codex/scripts/codex/errors.py

## Import Cycles
- None detected.

## Communities (69 total, 34 thin omitted)

### Community 0 - "Batch Group Cleanup"
Cohesion: 0.05
Nodes (99): _check_liftable_guards(), clean_group(), _member_liveness(), Cleaning a group: removing its worktrees and releasing its name, never taking…, The `stop` calls that end these runs: the group's when the run is one of its…, Remove a group's worktrees and release its name when nothing is left behind.…, `(live members, members whose meta.json will not parse)` — unknown is kept…, The refusals `--force` lifts, in check order; returns what was overridden,… (+91 more)

### Community 1 - "Worktree Clean Tests"
Cohesion: 0.08
Nodes (9): Clean, Overlaps, `batch start --worktree`: which members get a checkout, what the checkout…, A checkout is `git worktree add` output: tracked files at the base commit and…, Append a file_change naming these absolute paths, the shape real events have., Codex reports absolute paths, and each checkout has its own prefix, so paths…, WhatACheckoutHolds, WhoGetsACheckout (+1 more)

### Community 2 - "Batch Group Tests"
Cohesion: 0.09
Nodes (8): BatchCase, FollowingAGroup, OneMemberFailingDoesNotTakeTheOthers, Batches: N runs under one name, validated before anything starts, recorded slot…, Phase two pairs task i with member i of phase one, in start order, and refuses…, ResumeFrom, Starting, TasksAreValidatedBeforeAnythingStarts

### Community 3 - "Resume Thread Tests"
Cohesion: 0.08
Nodes (10): FindingTheThread, OneTurnPerThread, Resuming a thread: its settings stay what they were, it is found by the ref the…, A thread started outside this skill has no recorded sandbox, so the caller has…, Two turns on one thread append to one rollout file. The check and the new run's…, An explicit flag, then what a resumed thread recorded, then the user's…, ResumeCase, SettingsAreReasserted (+2 more)

### Community 4 - "Bridge Test Harness"
Cohesion: 0.07
Nodes (14): BridgeCase, Run a command that answers with one line of JSON, and parse it., Start the CLI without waiting, for races and for killing it midway., `result` read the way its `--help` says to: one JSON header line, then bodies…, `log` output split into (event lines, cursor)., A live process in a process group of its own that is not this test's child, so…, Copy the registry an older release left behind into this project, and give its…, Every codex invocation the bridge made, in order (catalog lookups excluded). (+6 more)

### Community 5 - "Observe and Result Tests"
Cohesion: 0.07
Nodes (9): AnOlderReleasesRegistry, answer_fixture(), GroupResult, Listing, What `status` and `result` say about runs: progress while live, the answer once…, `n` finished runs written straight into the registry, all the same shape so…, A registry written by 0.4–0.7 — a `review` run, a boolean `priority`, a batch…, Result (+1 more)

### Community 6 - "Result Collection"
Cohesion: 0.11
Nodes (32): final_message(), member_result(), overlaps(), Collecting a group: what each member concluded and which paths more than one…, What a run concluded: its `-o` file decoded as UTF-8 (a byte that is not,…, One member of `result --group`: its row and the part of its message that is…, Paths more than one run wrote, reported by path alone. Keyed by run, never by…, step() (+24 more)

### Community 7 - "Batch Start and Tasks"
Cohesion: 0.11
Nodes (26): `batch start` and `batch clean`., The group name's rule and `--base` without `--worktree` are the command…, start(), check_task_settings(), load_tasks(), What a batch is asked to do: the ordered tasks, each validated before anything…, The ordered task list: `--task` prompts first (as typed), then `--tasks-file`…, Refuse a model or effort any task would adopt, before the group name is claimed… (+18 more)

### Community 8 - "Git Repository Queries"
Cohesion: 0.14
Nodes (27): _covered_by(), ignored_entries(), is_dirty(), missing_at_base(), Path, What the git CLI says about a repository: its top level, its identity, a…, repo_identity(), resolve_base() (+19 more)

### Community 9 - "CLI Command Parser"
Cohesion: 0.13
Nodes (23): add_common(), add_follow_options(), add_run_options(), build_parser(), cmd_batch_start(), cmd_log(), cmd_resume(), cmd_start() (+15 more)

### Community 10 - "Codex Catalog and Config"
Cohesion: 0.18
Nodes (18): codex_version(), model_catalog(), This install's model catalog, read from `codex debug models`, and the pre-spawn…, What this Codex install offers, trimmed to the fields a caller chooses from, or…, codex_home(), config_scalars(), Path, CODEX_HOME and the few top-level values this skill reads from the user's… (+10 more)

### Community 11 - "Event Stream Formatting"
Cohesion: 0.20
Nodes (19): CursorOutOfRange, find_item(), first_thread_id(), format_events(), _format_item(), head_tail(), _indent(), Path (+11 more)

### Community 12 - "Package Structure Tests"
Cohesion: 0.15
Nodes (12): imports(), package_files(), The skill's tree is an interface read before any file, so its shape is checked…, The top-level name under codex/ a file belongs to., `(line, level, dotted name)` for every import in a file, including those inside…, Lines that change `sys.path`, however it is reached: `sys.path`, `import sys as…, skill_files(), Structure (+4 more)

### Community 13 - "Run Spawning and Creation"
Cohesion: 0.18
Nodes (17): Spawning a batch: each member's slot recorded before it starts, each member…, spawn_members(), spawn_task(), A member's options: the group's as defaults, the task's own fields over them., task_args(), git_toplevel(), write_meta(), create_run() (+9 more)

### Community 14 - "Shared Test Scaffolding"
Cohesion: 0.15
Nodes (11): engine(), Scaffolding shared by every test: a throwaway git project, the fake `codex`…, Import an engine module (`"codex.runs.settings"`, `"codex.codex_cli.argv"`, …)…, The CLI's output frame, its selector rules, and what reaches `codex`. Callers…, TheRegistryGoesWhereItIsTold, `codex.codex_cli.config`: the top-level values this skill reads from the user's…, `doctor`: one line describing the environment a run would start in, exit 2 when…, ManyWritersOneMeta (+3 more)

### Community 15 - "End-to-End Scenario Runner"
Cohesion: 0.21
Nodes (15): Path, base_cmd(), control_text(), digest(), entry(), main(), A session whose stdin stays open, so a finished background task can start…, Run one S6 scenario against the draft, the control or the v0.8.0 skill,… (+7 more)

### Community 16 - "Orphaned Run Liveness"
Cohesion: 0.22
Nodes (4): alive(), A run recorded `orphaned` whose codex is demonstrably still going: its…, wait_until(), AnOrphanThatIsStillWriting

### Community 18 - "Settings Precedence Tests"
Cohesion: 0.23
Nodes (3): Precedence, `codex.runs.settings.resolve`: one precedence for every setting — the flag,…, resolve()

### Community 19 - "JSON Argument Parser"
Cohesion: 0.20
Nodes (11): command_words(), invocation(), JsonArgumentParser, main(), This CLI called again the way SKILL.md calls it: `uv run "<this file, as the…, A command line that does not parse is answered like any other that must change:…, Print one line of JSON and exit., A command's answer: a dict is one line of JSON, a `(dict, exit code)` pair the… (+3 more)

### Community 21 - "Event Stream Tests"
Cohesion: 0.16
Nodes (4): DamagedLines, Reading a run's event stream: exact cursors, damaged lines that are counted…, A line that will not parse is kept as `unparsed` and counted, apart from…, Show

### Community 22 - "Argv Building Tests"
Cohesion: 0.22
Nodes (4): build(), BuildArgv, Preamble, `codex.codex_cli.argv`: the argv a run hands Codex, and the paragraphs in front…

### Community 23 - "Model Catalog Tests"
Cohesion: 0.17
Nodes (4): ABrokenLookupNeverBlocksARun, ChecksBeforeSpawning, Models, The model catalog: read from `codex debug models`, trimmed to what a caller…

### Community 24 - "Run Lifecycle Tests"
Cohesion: 0.24
Nodes (5): BridgeCase, APidAnotherProcessNowHolds, DetachedStart, A run's life: detached start, every terminal state, the stop ladder, and what a…, The system hands an exited process's pid to the next process it starts, so a…

### Community 25 - "Command Refusals and Show"
Cohesion: 0.25
Nodes (7): A next round: `batch start --resume-from` pairs task i with member i of an…, The one way a command says no, from anywhere below the command surface:…, A command refused, or failed, for a reason the caller can act on. `error` is…, Refusal, `show`: one run-scoped item in full — a command's output, capped and with the…, show(), Exception

### Community 28 - "Real Codex Smoke Tests"
Cohesion: 0.29
Nodes (4): skipUnless, S5: the real Codex CLI, end to end. Opt-in because it spends tokens:…, `result`'s JSON header line and the message after it., RealCodex

### Community 30 - "Skill Text Validation"
Cohesion: 0.25
Nodes (3): SKILL.md may name commands, flags and reply fields; each has to exist, and the…, TheSkillTextPointsAtRealThings, walk()

### Community 32 - "Fake Codex Stand-in"
Cohesion: 0.36
Nodes (6): main(), positionals(), prompt_of(), Stand-in for the `codex` binary, first on PATH during the suite. It records…, A fresh `exec` opens a new thread; `exec resume <ref>` reports that ref back., thread_for()

### Community 35 - "Symlink Install Tests"
Cohesion: 0.32
Nodes (4): Installs: the skill reached through a symlink, from a directory that has…, The call SKILL.md teaches, through the link, from a directory unrelated to the…, ThroughASymlink, finished()

### Community 45 - "Codex Argv Builder"
Cohesion: 0.60
Nodes (4): apply_preamble(), build_argv(), toml_cfg(), uncommitted_clause()

### Community 46 - "Codex Skill Guidance"
Cohesion: 0.40
Nodes (5): Arming a Codex Wait, Codex Managed Subagent Skill, Codex Context Discipline, Codex Delegation Mode Selection, Codex Operational Gotchas

### Community 47 - "Skill Feature Overview"
Cohesion: 0.40
Nodes (5): Managed Background Subagent, Batch Orchestration, Codex in Claude, Filtered Live Event Log, Sandbox Stability

### Community 48 - "Release History"
Cohesion: 0.50
Nodes (4): Codex-in-Claude Release History, v0.5.0 Interface Over Document Rewrite, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal

### Community 51 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 52 - "Security Policy"
Cohesion: 0.67
Nodes (3): Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

## Knowledge Gaps
- **19 isolated node(s):** `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline`, `Codex Delegation Mode Selection`, `Codex Operational Gotchas` (+14 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 342 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **34 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `Bridge Test Harness` to `Worktree Clean Tests`, `Batch Group Tests`, `Resume Thread Tests`, `Observe and Result Tests`, `Shared Test Scaffolding`, `Orphaned Run Liveness`, `Codex Argument Passing Tests`, `Event Stream Tests`, `Model Catalog Tests`, `Doctor Diagnostics Tests`, `Log Detail Levels`, `Exit Code Contract`, `Next Step Follow Hints`, `Help Text Interface`, `Selector Exclusivity Rules`, `Event Cursor Polling`, `CLI Output Frame`, `Removed CLI Surface`, `Registry Lock Failures`, `No-Op Flag Refusals`, `Concurrent Run Starts`?**
  _High betweenness centrality (0.167) - this node is a cross-community bridge._
- **Why does `Refusal` connect `Command Refusals and Show` to `Batch Group Cleanup`, `Result Collection`, `Batch Start and Tasks`, `CLI Command Parser`, `Codex Catalog and Config`, `Event Stream Formatting`, `Run Spawning and Creation`, `JSON Argument Parser`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `wait_until()` connect `Orphaned Run Liveness` to `Worktree Clean Tests`, `Batch Group Tests`, `Symlink Install Tests`, `Bridge Test Harness`, `Observe and Result Tests`, `Resume Thread Tests`, `Legacy Waiting Runs`, `Shared Test Scaffolding`, `Concurrent Run Starts`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Refusal` (e.g. with `main()` and `spawn_members()`) actually correct?**
  _`Refusal` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `wait_until()` (e.g. with `.test_a_run_started_through_the_link_is_finished_by_its_detached_supervisor()` and `.test_once_its_codex_is_gone_the_follower_ends_on_orphaned()`) actually correct?**
  _`wait_until()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `find_run()` (e.g. with `_member_liveness()` and `_remove_worktrees()`) actually correct?**
  _`find_run()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `S6 scenarios`, `Arming a Codex Wait`, `Codex Context Discipline` to the rest of the system?**
  _19 weakly-connected nodes found - possible documentation gaps or missing edges._