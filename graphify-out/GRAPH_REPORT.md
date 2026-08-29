# Graph Report - codex in claude  (2026-08-30)

## Corpus Check
- 102 files · ~187,725 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1860 nodes · 3237 edges · 118 communities (103 shown, 15 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 103 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Batch CLI Pipeline
- Run Registry Utilities
- Soak Test Oracles
- Behavior Contract Tests
- Integration Test Runner
- Run Lifecycle Registry
- Architecture and Orchestration
- CLI Documentation Tests
- As Ready Pipeline
- Output Contract Tests
- Bridge CLI Commands
- Lifecycle Mode Tests
- Live Writing Safety
- Model Validation Tests
- Event Stream Formatting
- Test Suite Integrity
- Registry Concurrency Tests
- Worktree Git Utilities
- JSON Contract Helpers
- Worktree Isolation Tests
- Worktree Overlap Tests
- Review Removal Contract
- Batch Behavior Tests
- Resume Pairing Tests
- Unreadable Group Safety
- Help Source Tests
- Doctor Diagnostics Tests
- Argument Default Tests
- Status Payload Tests
- Wait Chain Safety
- Inventory Block Parsing
- Unreadable Run Safety
- Argument Composition Tests
- Report Timing Tests
- Worktree Cleanup Safety
- Bridge Test Helpers
- Help Fact Ownership
- Waiting Arm Contract
- Fault Injection Tests
- Output Filter Levels
- Group Follow Filtering
- Help Anchor Validation
- Sandbox Resume Tests
- Registry Ownership Faults
- Log Cursor End-to-End
- Registry Resolution Tests
- Thread Database Queries
- Worktree Cost Diagnostics
- Concurrent Writer Safety
- Batch Mode Constraints
- Selector Conflict Tests
- Legacy Bridge Helpers
- Help Audit Manifest
- Batch Task Validation
- Cursor Filtering Tests
- Run State Reporting
- Orphan Liveness Safety
- Worktree Honesty Tests
- Skill Spec Agreement
- Batch Preamble Isolation
- Managed Subagent Design
- Delegation Evolution Plans
- As Ready Status
- Turn Clock Tests
- Unparsed Event Handling
- Documentation Ownership Tests
- CLI Flag Coverage
- Batch Start Semantics
- Batch Orchestration History
- Package Pointer Tests
- Codex Shell Wrapper
- Pure Argument Units
- Group Selector Semantics
- Metadata Fault Diagnostics
- Git Worktree Faults
- Worktree Exclusion Notes
- Multi-Hop Wait Chains
- Corrupt Run Isolation
- Retired Flag Tests
- Group Result Tests
- Registry Layout Tests
- Skill Rewrite Planning
- Batch Isolation Planner
- Operational CLI Commands
- Abandoned Waiter Safety
- Inventory Coverage Tests
- Partial Process Death
- Follow Heartbeat Tests
- Malformed Model Catalog
- Armed Waiting Design
- Waiting State Visibility
- Partial Batch Startup
- As Ready Refusals
- Projected Cost Tests
- Spawn Interruption Cleanup
- Model Lookup Failures
- Validation and PR Contract
- Plan Archive Structure
- Bridge Error Type
- Fast Mode Help Audit
- Event Cursor Concepts
- Security Disclosure Process
- Group Cost Measurement
- Registry Scale Measurement
- Registry Write Faults
- Concurrent Resume Safety
- Unknown Thread Resume
- Final Usage Parsing
- Utility Failure Tests
- Hidden Subcommand Filtering
- Code of Conduct
- Core Run Commands
- Installation and Diagnosis
- Concurrency Measurement
- Graph Navigation Workflow
- Contribution Scope Rules
- Configuration Isolation Concept
- Version One Non-Goals

## God Nodes (most connected - your core abstractions)
1. `BridgeTestCase` - 74 edges
2. `BridgeCase` - 48 edges
3. `fail()` - 31 edges
4. `AsReadyBase` - 30 edges
5. `FaultTestCase` - 27 edges
6. `cmd_batch_start()` - 25 edges
7. `cmd_batch_clean()` - 24 edges
8. `reap()` - 24 edges
9. `read_meta()` - 23 edges
10. `cmd_doctor()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `WhenACursorComesFromAnotherRun` --uses--> `CursorOutOfRange`  [INFERRED]
  tests/legacy/test_faults.py → .claude/skills/codex/scripts/_events.py
- `main()` --calls--> `resolve_runs_dir()`  [INFERRED]
  tests/legacy/measure_filter_calibration.py → .claude/skills/codex/scripts/_registry.py
- `main()` --calls--> `iter_runs()`  [INFERRED]
  tests/legacy/measure_filter_calibration.py → .claude/skills/codex/scripts/_registry.py
- `rollout_path()` --calls--> `codex_home()`  [INFERRED]
  tests/legacy/integration/run_integration.py → .claude/skills/codex/scripts/_util.py
- `Graphify-First Codebase Navigation` --conceptually_related_to--> `Managed Codex Subagent Harness`  [INFERRED]
  AGENTS.md → .claude/harness-spec.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Managed Subagent Safety and Context Contract** — claude_harness_spec_managed_subagent_harness, claude_plans_260725_codex_skill_implementation_plan_sandbox_reassertion, claude_plans_260725_codex_skill_implementation_plan_context_discipline, claude_skills_codex_skill_codex_managed_subagent [INFERRED 0.95]
- **Documentation Ownership Rewrite** — claude_plans_260823_260823_interface_owns_facts, claude_plans_260823_help_audit_manifest_machine_visible_finish_line, claude_plans_260823_skill_rewrite_inventory_ownership_classes, changelog_v050_interface_over_document [EXTRACTED 1.00]
- **Native Delegation Parity Measurement** — claude_plans_260826_valiant_inventing_hopper_native_parity_plan, claude_plans_260826_valiant_inventing_hopper_four_invariants, claude_plans_260826_valiant_inventing_hopper_delegation_shape_axes, claude_harness_spec_native_delegation_invariants, changelog_v060_native_parity [EXTRACTED 1.00]
- **Managed Run Request Flow** — docs_wiki_architecture_bridge_cli, docs_wiki_architecture_run_registry, docs_wiki_architecture_argv_reassertion, docs_wiki_architecture_event_filtering, docs_wiki_architecture_process_group_control [EXTRACTED 1.00]
- **Run Observability Model** — docs_wiki_concepts_run, docs_wiki_concepts_run_registry, docs_wiki_concepts_event_item, docs_wiki_concepts_filter_level, docs_wiki_concepts_cursor [EXTRACTED 1.00]
- **Four-Tier Verification Strategy** — docs_wiki_testing_t1_fake_codex, docs_wiki_testing_t2_real_integration, docs_wiki_testing_t3_filter_calibration, docs_wiki_testing_t4_headless_e2e [EXTRACTED 1.00]

## Communities (118 total, 15 thin omitted)

### Community 0 - "Batch CLI Pipeline"
Cohesion: 0.08
Nodes (57): changed_paths(), claim_group(), cmd_batch_clean(), cmd_batch_start(), cmd_result_group(), derived_groups(), follow_group(), follow_group_log() (+49 more)

### Community 1 - "Run Registry Utilities"
Cohesion: 0.08
Nodes (50): await_predecessor(), cmd_doctor(), config_scalars(), Path, query_threads(), Talking to the Codex CLI: argv composition, spawning, and its thread database.…, `{model, effort, service_tier}` from the user's `config.toml`. Read fresh…, Block until the run this one is chained behind reaches a terminal state.… (+42 more)

### Community 2 - "Soak Test Oracles"
Cohesion: 0.07
Nodes (19): Event, plan(), Path, A concurrency soak driver, and the record that makes its failures re-runnable.…, The one line of JSON, or None. Never raises — deciding whether an unparseable…, Drive the plan, then poll meta.json throughout to catch torn writes., Oracle 2's evidence. A reader that only looks after the writers are done can…, Wait for every supervisor to record an outcome, so oracle 3 measures runs that… (+11 more)

### Community 3 - "Behavior Contract Tests"
Cohesion: 0.06
Nodes (20): BatchStartHasNoForegroundFlag, ContradictoryPriorityFlagsAreRefused, ProjectedCostStatesNoSampleStory, BridgeCase, Seam 6 — the six places where honest help would have had to be a warning. The…, `--include-external` lists threads with no registry entry; a group is a…, 4. `codex exec resume` has no `-s`, so this wrapper re-asserts the sandbox from…, 5. `--priority` and `--no-priority` share a dest, so the last one on the line… (+12 more)

### Community 4 - "Integration Test Runner"
Cohesion: 0.10
Nodes (46): bridge(), bridge_text(), case(), I1(), I10(), I11(), I12(), I13() (+38 more)

### Community 5 - "Run Lifecycle Registry"
Cohesion: 0.07
Nodes (42): load_tasks(), Build the ordered task list from `--task` and `--tasks-file`. Both may be…, apply_preamble(), build_argv(), check_model_effort(), model_catalog(), What this Codex install actually offers, or None if it cannot be read. `codex…, Refuse a model or effort this Codex install does not offer. Only values the… (+34 more)

### Community 6 - "Architecture and Orchestration"
Cohesion: 0.05
Nodes (43): Tiered Contribution Verification, Recorded Settings Reassertion, Bridge CLI Entry Point, Default Configuration Isolation, Cursor-Based Event Filtering, Process Group Control, Run Registry, Run (+35 more)

### Community 7 - "CLI Documentation Tests"
Cohesion: 0.07
Nodes (24): CitationsResolve, cli_surface(), documented_commands(), DocumentedFlagsAreFindable, DocumentedFlagsExist, _flags(), PollingIsPreApproved, B20 and B18 — the two rows the suite never touched. B20 is "the gotchas a… (+16 more)

### Community 8 - "As Ready Pipeline"
Cohesion: 0.10
Nodes (19): ADeadWaiterIsNoticed, AFailedPredecessorStillReleases, AsReadyBase, MutualExclusionClosesBehindAWaiter, PipelineOrdering, BridgeCase, B31 — `batch start --resume-from --as-ready` starts each member as its own…, `create_run` polls up to THREAD_ID_WAIT for a thread id and breaks only on that… (+11 more)

### Community 9 - "Output Contract Tests"
Cohesion: 0.07
Nodes (18): BridgeCase, Scaffolding for the 260814 round. Same seam as the earlier rounds, and the same…, Block until a run stops moving., A throwaway git project with the fake `codex` first on PATH., Run the bridge and parse its one line of JSON., contract_claims(), FollowingAGroupPrintsText, BridgeCase (+10 more)

### Community 10 - "Bridge CLI Commands"
Cohesion: 0.15
Nodes (36): add_common(), add_heartbeat(), add_run_options(), build_parser(), cmd_log(), cmd_models(), cmd_result(), cmd_resume() (+28 more)

### Community 11 - "Lifecycle Mode Tests"
Cohesion: 0.06
Nodes (13): BackgroundTimeout, ForegroundMode, PromptSources, T1 — stopping runs without collateral damage, and collecting results., The legacy wrapper's `--cancel` ran `pgrep -f "codex exec"` and killed every…, Handing back a malformed object as if it had the schema's shape is worse than…, `timed_out` is its own terminal state so a caller can tell "I stopped it" from…, D26. `--timeout` used to be accepted in the background, recorded nowhere, and… (+5 more)

### Community 12 - "Live Writing Safety"
Cohesion: 0.09
Nodes (17): alive(), CleanDoesNotDeleteLiveWork, BridgeCase, A terminal state answers "is anyone recording this?", never "is anything still…, F2. `batch clean`'s own comment says the first thing that stops a clean is "a…, F4. Every surface that answers "is this done" said yes., F3. `concurrent_writers` and `doctor` are the only surfaces that can show two…, F5 and F6 — two messages that stated something other than what happened. (+9 more)

### Community 13 - "Model Validation Tests"
Cohesion: 0.08
Nodes (17): BatchPreflightsTheConfigsOwnDefaults, BatchValidatesBeforeSpawning, DoctorReportsModelCatalogHealth, EffortValidityIsPerModel, Models, T1 — model and effort validation: the catalog lookup, and everything it must…, The single most important case here: fake-big and fake-small do not agree on…, B3: a resumed run must never silently change its sandbox — or its effort.… (+9 more)

### Community 14 - "Event Stream Formatting"
Cohesion: 0.11
Nodes (29): CursorOutOfRange, final_usage(), find_item(), first_thread_id(), format_events(), _format_item(), head_tail(), _indent() (+21 more)

### Community 15 - "Test Suite Integrity"
Cohesion: 0.11
Nodes (18): AST, discover(), documented_commands(), DocumentedCommands, PathConstants, _PathExpr, Path, Slice 1 — the suite has to fail loudly when it is not there. Moving `tests/` to… (+10 more)

### Community 16 - "Registry Concurrency Tests"
Cohesion: 0.08
Nodes (16): _hammer_read(), _hammer_write(), T1 — the registry under concurrent writers. Every one of these reproduces a…, F2 — `reap()` decided from the caller's stale snapshot and committed through…, The fix must not disarm reap: a run whose supervisor is gone and whose meta…, The primitive F2's fix rests on., F15 — a collision was an uncaught FileExistsError. Batch start makes same-…, Write our own key over and over. Any exception is the bug. (+8 more)

### Community 17 - "Worktree Git Utilities"
Cohesion: 0.13
Nodes (27): add(), _covered_by(), _git(), ignored_entries(), is_dirty(), missing_at_base(), prune(), Path (+19 more)

### Community 18 - "JSON Contract Helpers"
Cohesion: 0.09
Nodes (11): BridgeTestCase, Shared scaffolding for the T1 suite. Tests drive `codex_bridge.py` as a…, Run the bridge and parse its one line of JSON., Run `log` and split into (content lines, cursor)., Assert `flag value` appear adjacent in argv., A temp git project, the fake `codex` first on PATH, an argv log., `doctor` exits 2 when it has blockers and 0 when it does not; a test that cares…, The user's `config.toml`, in the CODEX_HOME this case pinned. (+3 more)

### Community 19 - "Worktree Isolation Tests"
Cohesion: 0.11
Nodes (11): Assignment, One writer collides with nobody, so the shared-tree note would be a line about…, It negated a default that no longer exists. Left in the parser it would accept…, The worktree is cut after every check that can still refuse the run. Cutting it…, A typo'd --base answered with a degrade note would produce the one outcome the…, `--base` names the commit a checkout is cut from, and after C-A no checkout is…, V-14: project instructions do reach a worktree run, but only from a base where…, The field is a claim about what a checkout does not have, and a `--base` older… (+3 more)

### Community 20 - "Worktree Overlap Tests"
Cohesion: 0.11
Nodes (13): OverlapsAdversarial, OverlapsUnderIsolation, D35 is per member, not per batch: a read-only member has nothing to isolate,…, Codex reports ABSOLUTE paths, and under worktree isolation every member has a…, Making paths relative fixed the worktree case and broke this one: a per-task…, The mirror of the case above, and the one relativising to each run's own cwd…, `../../elsewhere` compares no better than the absolute path and reads worse, so…, `overlaps` has been wrong three times, and the third design had never been… (+5 more)

### Community 21 - "Review Removal Contract"
Cohesion: 0.09
Nodes (15): BridgeCase, help_text(), Path, Scaffolding for the 260828 round. A copy of the earlier rounds' rather than an…, The real rewrapped `--help` a caller reads, not the parser's `help=`., A throwaway git project to run the bridge inside., Run the bridge and parse its one line of JSON., BridgeCase (+7 more)

### Community 22 - "Batch Behavior Tests"
Cohesion: 0.08
Nodes (14): AGroupIsDiscoverableFromStatus, BatchFailureIsolation, ContradictionsAndGaps, ExternalThreadsStayDeduped, GroupManifestAtomicity, ManifestSurvivesAHalfFinishedBatch, T1 — batch groups: starting one, addressing one, and collecting one. The…, D11: one member failing to spawn does not take the batch with it, and it does… (+6 more)

### Community 23 - "Resume Pairing Tests"
Cohesion: 0.11
Nodes (11): M4c. Phase 2 continues phase 1 member for member, keeping each thread and the…, C-A made this the ordinary shape and left it unwarned. The note was keyed off…, `--worktree` here answered "no member writes to the tree", which is false of…, A resume inherits its sandbox from its thread, so a phase continuing read-only…, Pairing a short list lands a phase-2 task on the wrong phase-1 thread, and…, Explicit beats inferred, the same rule that governs a per-item cwd., Neither reading is safe to pick silently: honouring it leaves the paired member…, --resume-from supplies the target positionally, so under it an unnamed `kind:… (+3 more)

### Community 24 - "Unreadable Group Safety"
Cohesion: 0.13
Nodes (9): ALiveMemberKeepsItsGroupName, BridgeCase, D6 — a group manifest that will not parse must not be a permanent dead end.…, The whole point of checking the group before any member resumes: refusing per…, M3 — `batch clean --force` released the name while a live member still claimed…, D5's second location — `pair_with_previous`'s live-member check. It resolves…, Two members, both finished, then one made unreadable. Both terminal on purpose:…, UnreadableManifest (+1 more)

### Community 25 - "Help Source Tests"
Cohesion: 0.11
Nodes (16): AStatedDefaultIsTheRealDefault, _comparable(), EveryFlagExplainsItself, option_surface(), The CLI's own signature is the source of truth for its option surface. Every…, The pointer is only honest if what it points at is complete., (matches, ) for a stated default against argparse's, or None to skip. Skipping…, Presence is not truth, and this is the part of truth a machine can check. That… (+8 more)

### Community 26 - "Doctor Diagnostics Tests"
Cohesion: 0.14
Nodes (7): Doctor, T1 — `doctor` must produce a correct, specific diagnosis for each failure mode.…, AGENTS.md survives --ignore-user-config, so it is in every run's context…, CLAUDE_SKILL_DIR does not exist and CLAUDE_PLUGIN_ROOT may or may not; doctor…, The DB filename is version-stamped, so its schema will change; a Codex upgrade…, ~/.codex is not reliably the Codex home; the legacy skill's instruction to read…, A diagnostic that changes what it diagnoses is a bad diagnostic.

### Community 27 - "Argument Default Tests"
Cohesion: 0.09
Nodes (11): C10 — isolation drops the user's `config.toml`, and three of its keys go back…, Measured against codex-cli 0.149.1 by V-02's own method: `fast` and `priority`…, B3's rule, applied to one more setting. A thread's settings are stable across…, The fourth key this wrapper owns, and the one it will not read. A config the…, Under `--inherit-config` Codex reads the file itself, so putting the same three…, D40 unchanged: the skill has no defaults of its own. With nothing to respect,…, The field changed name and type in the same commit, and a resume reads whatever…, The reason the record is read rather than defaulted: `--no-priority` is a… (+3 more)

### Community 28 - "Status Payload Tests"
Cohesion: 0.10
Nodes (12): ExternalThreadTitles, FollowNeedsAGroup, _iso(), T1 — what `status` and `result` report (audit findings F3, F8). F3:…, `--follow` is registered on `status` as a whole but only the `--group` branch…, The first guard only asked whether `--group` was present, so `--run X --group g…, Codex stores the whole prompt as a thread's title, preamble included, and this…, The guard itself, at the boundary. A test in this tier cannot reach the… (+4 more)

### Community 29 - "Wait Chain Safety"
Cohesion: 0.11
Nodes (12): ACyclicChainFailsRatherThanHanging, ANamedTargetWaitsToo, AWaitingRunProtectsItsThread, BridgeCase, What the Codex review found in the wait chain, and two tests it found wanting.…, Nothing can watch a ref this project has never seen reach a terminal state, so…, `waits_for` is a field on disk, so a hand-edited or half-written cycle is…, `batch start --as-ready` returns without blocking. The round's original test… (+4 more)

### Community 30 - "Inventory Block Parsing"
Cohesion: 0.18
Nodes (16): digest(), is_prose(), normalize(), original(), original_blocks(), One mechanical definition of "a prose block", shared by the inventory and its…, (block_id, source, text) for every prose block the rewrite is replacing., Whitespace-insensitive form. Re-wrapping a paragraph is not a new block. (+8 more)

### Community 31 - "Unreadable Run Safety"
Cohesion: 0.17
Nodes (8): BridgeCase, D5 and D7 — a run whose meta.json will not parse is not a run that is absent.…, The two answers must stay different in both directions., Leave the directory and the event stream, break only the metadata., A run that is still live when we come back to it., The guard refuses on 'I cannot tell', so the escape hatch has to stay — the…, The refusal must come from 'unreadable', not from 'any run exists'., UnreadableMeta

### Community 32 - "Argument Composition Tests"
Cohesion: 0.10
Nodes (6): ArgvComposition, `codex exec`'s `-i/--image <FILE>...` takes MULTIPLE values and greedily eats…, Codex reads stdin when it is not a TTY; a live stdin risks a block., The wrapper never silently disables a Codex guard where it applies., D19 — inherit Codex's own defaults so the skill does not go stale., Invariant 2: -C does not exist on resume, so it is never used.

### Community 33 - "Report Timing Tests"
Cohesion: 0.14
Nodes (8): ATruncatedTailIsNotSilence, ElapsedMustNotCountTheWait, BridgeCase, Three reporting defects the second adversarial round found. All three are the…, `elapsed_seconds` is measured from `started_at`, which is when the run object…, `read_events` drops a trailing line with no newline, on the reasoning that the…, `uncommitted_clause` special-cased "unknown" and left zero reading as a double…, TheCleanTreeSentence

### Community 34 - "Worktree Cleanup Safety"
Cohesion: 0.17
Nodes (6): Clean, derived_of(), D06. Not a check this code performs — `git worktree remove` refuses a dirty…, One flag lifts all three protections, and a caller usually reaches for it to…, Asked of the registry, not of the group graph. `derived_from` is one hop and…, A phase-2 member works inside its phase-1 predecessor's worktree, so cleaning…

### Community 35 - "Bridge Test Helpers"
Cohesion: 0.15
Nodes (6): BridgeCase, Scaffolding for the 260813 round. Same seam as the legacy suite — the bridge is…, Run the bridge and parse its one line of JSON., Every argv the bridge actually handed to `codex`., Block until a run stops moving, and hand back its final meta., A throwaway git project with the fake `codex` first on PATH.

### Community 36 - "Help Fact Ownership"
Cohesion: 0.16
Nodes (9): help_text(), HelpCarriesTheMigratedFacts, BridgeCase, Seam 1 — each fact the rewrite moved out of prose is in the surface that owns…, `status`'s epilog is where a caller learns what the words mean. A state name…, The list above is a specification; this drives the CLI until it says those…, The real rendered help for one command path., TheStateVocabularyIsReal (+1 more)

### Community 37 - "Waiting Arm Contract"
Cohesion: 0.17
Nodes (10): MonitorIsNeverAdvisedAtItsDefaultLifetime, Seam 3 — the waiting doctrine reaches a single run, and never advises a watcher…, The other hole: knowing to block does not say *when*, and a session that…, Waiting guidance filed under a batch heading is guidance a single run never…, (heading, body) pairs, split on markdown headings. A section rather than a…, A Monitor left at its default stops watching after five minutes. Codex runs go…, C7 — the exception said "run the follow in the foreground" and named only the…, sections() (+2 more)

### Community 38 - "Fault Injection Tests"
Cohesion: 0.12
Nodes (10): T1 — what the registry says after something dies. Most of this project's…, Publishing a run before cutting its worktree made it visible to `reap` before…, `start_new_session` was set only when `--timeout` was also given, so a plain…, `codex login status` also fails when it cannot load config at all, with a…, `status` learned that `--run` and `--group` are different questions. `stop` and…, WhenAForegroundRunRecordsItsProcessGroup, WhenAGroupManifestCannotBeParsed, WhenARunIsStillBeingBuilt (+2 more)

### Community 39 - "Output Filter Levels"
Cohesion: 0.17
Nodes (3): LevelsPure, Filtering is a pure function; test it directly against a real stream., The byte count is what turns `show --item` into a decision rather than a guess.

### Community 40 - "Group Follow Filtering"
Cohesion: 0.24
Nodes (6): AGroupsMidRunSignal, C9 — `log --run --follow` gives one run its events as they arrive; a group had…, The prefix has to be short enough to read at a glance and still lead back to a…, This is a line-oriented protocol and the label is caller text. A label holding…, The same line `status --group --follow` ends on, because a watcher armed on…, Every member has its own byte offset into its own file. One integer cannot…

### Community 41 - "Help Anchor Validation"
Cohesion: 0.22
Nodes (8): Counter, EveryOwnerAnchorResolves, headings(), parser_for(), GitHub-style anchors for every heading, so a `SKILL.md#…` row resolves., `batch start --as-ready` → ("batch start", "--as-ready"). The command half is…, The subparser a command path names, or None., split_help_anchor()

### Community 42 - "Sandbox Resume Tests"
Cohesion: 0.19
Nodes (5): `codex exec resume` inherits no per-invocation setting from the thread.…, THE regression test: the sandbox recorded at creation is in the resume argv,…, `codex exec resume` accepts a thread name, so an id we have never seen is a…, The other half of that change: no invented default., SandboxDriftRegression

### Community 43 - "Registry Ownership Faults"
Cohesion: 0.21
Nodes (6): `batch clean` skipped a member whose meta would not parse when deciding whether…, `batch clean` can release a name whose manifest has been claimed but has no…, `--since` was only refused when it pointed past the end of the file. An offset…, WhenACursorComesFromAnotherRun, WhenAGroupNameIsReclaimedMidSpawn, WhenAMembersMetaCannotBeParsed

### Community 44 - "Log Cursor End-to-End"
Cohesion: 0.14
Nodes (5): LogAndShowEndToEnd, F11: a bare `# cursor=<n>` is indistinguishable between two runs in flight, so…, F11: the old guard (`since >= size`) accepted an out-of-range `--since`…, `item.id` restarts at item_0 on every invocation, so the same id in two runs on…, Silence must never look like success: --follow has to say how it ended, or a…

### Community 45 - "Registry Resolution Tests"
Cohesion: 0.18
Nodes (5): ImplicitTargetResolution, T1 — the run registry: layout, isolation between runs, and state reporting., The legacy script needed explicit normalisation for exactly this: APFS hands…, F4: `resume --last` used to pick `runs[-1]` project-wide, no filter on cwd,…, UnicodePaths

### Community 46 - "Thread Database Queries"
Cohesion: 0.18
Nodes (8): make_threads_db(), Path, QueryThreadsCwdFilter, T1 — F10: `query_threads` must filter cwd in SQL, not over-fetch and filter in…, rows: list of dicts with at least id/cwd/updated_at., query_threads() resolves its db from CODEX_HOME (via state_db_path()), so…, limit=1 (the resume --last / doctor path) must not miss a thread for this cwd…, macOS stores non-ASCII filenames as NFD; argv/JSON carry NFC.

### Community 47 - "Worktree Cost Diagnostics"
Cohesion: 0.16
Nodes (8): DoctorReportsTheCost, T1 — per-member worktree assignment, and taking them away again. The three…, §13. The place that creates the cost is the place that reports it — facts only,…, A project with a commit, so HEAD resolves and a worktree can be cut., `--worktree` passes a member over for three different reasons, and the sharing…, The other true answer, and the one a `--worktree` over a fan-out of readers…, TheNoteNamesTheRealExclusion, WorktreeTestCase

### Community 48 - "Concurrent Writer Safety"
Cohesion: 0.21
Nodes (6): ConcurrentWritersAreNamedWhereTheMistakeHappens, Reported, never refused (D17) — concurrency in one directory is sometimes what…, The note used to prescribe `batch start --worktree --resume-from`. Measured:…, The measured failure was on the resume path, not the start path: a session…, The warning must not fire on the arrangement that makes it safe., The commit that reaped `concurrent_writers` claimed doctor too and did not do…

### Community 49 - "Batch Mode Constraints"
Cohesion: 0.15
Nodes (7): ForegroundIsNotABatchMode, BridgeCase, D1 — `batch start --foreground` runs the batch one member at a time.…, A refusal a caller meets after typing the flag is worse than a listing that…, Removing the only obvious way to block is a dead end unless the working one is…, Refused above `claim_group`, for the reason the `--worktree` / `--no-worktree`…, The flag means something on `start`; only `batch start` is refused.

### Community 50 - "Selector Conflict Tests"
Cohesion: 0.21
Nodes (6): CompetingSelectors, BridgeCase, D3 — a second selector flag must be refused, not silently dropped.…, R28's original case, kept so generalizing does not lose it., The refusal must fire on a second selector, not on any --all., `--all` on `status` lifts a row-count cap; it selects nothing. Refusing this…

### Community 51 - "Legacy Bridge Helpers"
Cohesion: 0.19
Nodes (5): BridgeCase, Scaffolding for the 260823 round. Same seam as the earlier rounds, and the same…, Run the bridge and parse its one line of JSON., Block until a run stops moving., A throwaway git project with the fake `codex` first on PATH.

### Community 52 - "Help Audit Manifest"
Cohesion: 0.23
Nodes (8): EveryArgumentWasAudited, manifest_rows(), public_surface(), Seam 5 — the help audit has a finish line a machine can see. "Audit the help…, {(command, argument): verdict} for every audited argument., Every (command, argument) a caller can pass, hidden commands skipped.…, A `remove` row is a claim about the tree, not a plan., A manifest of nothing but `keep` is an audit that was not run.

### Community 53 - "Batch Task Validation"
Cohesion: 0.24
Nodes (4): Silently ignoring a field means the run quietly used the group default instead…, Checking field names caught `sandox` but not `{"prompt": 123}`, which reached…, Group options are defaults, not constraints: a batch is usually the same thing…, TasksFile

### Community 54 - "Cursor Filtering Tests"
Cohesion: 0.17
Nodes (4): CursorExactness, load(), T1 — event filtering, incremental cursors, and the `show` escape hatch. These…, The file is appended to live, so a half-written line must not be consumed as…

### Community 55 - "Run State Reporting"
Cohesion: 0.15
Nodes (3): Codex always writes `Reading additional input from stdin...` to stderr when…, Silence alone is not failure; silence with no in-progress item is., StateReporting

### Community 56 - "Orphan Liveness Safety"
Cohesion: 0.24
Nodes (7): alive(), AnOrphanCanStillBeWriting, BridgeCase, M1 — a run whose supervisor died but whose Codex is still working is alive.…, `orphaned` keeps its meaning — the legacy suite pins it deliberately, and…, The same fact from the waiter's side, which is where it corrupts., TheChainDoesNotReleaseOntoALiveTurn

### Community 57 - "Worktree Honesty Tests"
Cohesion: 0.27
Nodes (5): BridgeCase, D2 — the worktree preamble must not assert a count it never read.…, The prompt the bridge actually handed to `codex`., `status` fails; `rev-parse` and `worktree add` keep working., UncommittedCount

### Community 58 - "Skill Spec Agreement"
Cohesion: 0.26
Nodes (8): number(), The numbers SKILL.md quotes are the numbers `harness-spec.md` measured. This is…, The one paragraph in SKILL.md that carries the moved claim. Found by its own…, Guards. Without these, a spec rewrite turns this file into a check that passes…, spec_numbers(), stopping_rule_paragraph(), TheNumbersAgree, TheSpecStillStatesWhatIsBeingCheckedAgainst

### Community 59 - "Batch Preamble Isolation"
Cohesion: 0.24
Nodes (4): Preamble, V-15 is the whole reason this exclusion exists: a fresh detached worktree has…, §4.4 / D20. Facts Codex cannot observe from inside its own turn, and which it…, `--no-preamble` is gone. V-18 measured the batch paragraph correcting a…

### Community 60 - "Managed Subagent Design"
Cohesion: 0.20
Nodes (11): Graphify-First Codebase Navigation, Managed Codex Subagent Harness, Native Delegation Invariants, Filtered Event Context Discipline, Four-Tier Validation, Sandbox Reassertion Across Resume, Codex Skill v0.1 Implementation Plan, Four Native-Parity Invariants (+3 more)

### Community 61 - "Delegation Evolution Plans"
Cohesion: 0.20
Nodes (11): Codex-in-Claude Release History, v0.6.0 Native Parity Improvements, v0.7.0 Review Removal, Config Defaults Preservation, Delegation Shape Axes, Native Delegation Parity Plan, Shared Tree Batch Default, Finite Verification Predicate (+3 more)

### Community 62 - "As Ready Status"
Cohesion: 0.24
Nodes (5): DoctorDoesNotInventACollision, What the adversarial round found in `--as-ready` after it passed its own tests.…, `ACTIVE_STATES` replaced six hand-written tuples and missed a seventh:…, `doctor` grouped a waiting member with the predecessor it is queued behind and…, TheSeventhStateTuple

### Community 63 - "Turn Clock Tests"
Cohesion: 0.24
Nodes (5): Why the one-turn-per-thread check reads `codex_started_at`, not `started_at`.…, A phase-2 member built while its predecessor is still running., Documenting the trap, so nobody re-points the check back., The new field is not `--as-ready`-only; every run has a turn., TwoClocks

### Community 64 - "Unparsed Event Handling"
Cohesion: 0.24
Nodes (4): BridgeCase, A line of the event stream that will not parse has to be counted somewhere.…, `config_error_events` is Codex reporting a problem with the work. A line the…, UnparsedEventLines

### Community 65 - "Documentation Ownership Tests"
Cohesion: 0.24
Nodes (7): Every markdown file inside the skill package. A glob rather than a list: this…, skill_docs(), ProseDoesNotRestateWhatHelpOwns, Seam 2 — a fact the tool states is not stated again in prose. Seam 1 says the…, The other direction of seam 1, phrase by phrase. A needle seam 1 requires in…, Naming one state to make a point is fine; listing the set is the copy. Four or…, TheMigratedFactsAreGoneFromProse

### Community 66 - "CLI Flag Coverage"
Cohesion: 0.18
Nodes (5): FlagsNothingElseCovers, Four flags had zero test coverage under any spelling, found by diffing the…, `--isolate` used to state this explicitly. It is the default, so the flag only…, `test_filters.py` calls `format_events` directly, so the flag that selects a…, `--run-dir` (singular) is `__supervise`'s internal flag and not part of the…

### Community 67 - "Batch Start Semantics"
Cohesion: 0.20
Nodes (3): BatchStart, D36. Reusing a name would make 'the members of p1' ambiguous — six runs, not…, A duplicate name must cost nothing, so the claim happens before the first Codex…

### Community 68 - "Batch Orchestration History"
Cohesion: 0.22
Nodes (10): Adversarial Audit Method, Concurrent Run Failure Modes, Preserve Correct Mechanisms, Adaptive Phase Boundaries, Batch Orchestration Plan, Named Batch Primitives, Capability Without Cost Policy, Per-Member Git Worktree Isolation (+2 more)

### Community 69 - "Package Pointer Tests"
Cohesion: 0.29
Nodes (6): EveryPointerResolvesInsideThePackage, package_files(), Seam 4 — every `.md` pointer inside the skill package resolves, and none leaves…, Every markdown path the text points at, however it is written., Every file the skill package ships, as the caller would reach them., scan()

### Community 70 - "Codex Shell Wrapper"
Cohesion: 0.31
Nodes (9): find_prompt(), invocation_thread_id(), load_stream(), log_invocation(), main(), parse_positionals(), Approximate clap's parse enough to find the prompt the way Codex would., `resume` is `[SESSION_ID] [PROMPT]`; everything else is just `[PROMPT]`. (+1 more)

### Community 71 - "Pure Argument Units"
Cohesion: 0.31
Nodes (4): PureArgvUnits, build_argv in isolation, for cases awkward to reach end-to-end., `-c` values parse as TOML, so a string value is quoted; an unquoted bare word…, `--` before the prompt, and it is required rather than tidy: `codex exec`'s…

### Community 72 - "Group Selector Semantics"
Cohesion: 0.33
Nodes (3): GroupSelectors, The group version of StopIsolation. --group resolves a recorded id to run ids…, Without a terminal line a quiet group and a dead follower look identical — the…

### Community 73 - "Metadata Fault Diagnostics"
Cohesion: 0.20
Nodes (7): doctor_rc(), Kept as a function because this module's call sites read that way; the…, `read_meta` swallows a parse error and `iter_runs` drops the run, so a corrupt…, `concurrent_writers`, at run creation, has always treated `/p` and `/p/sub` as…, WhenAMetaFileCannotBeParsed, WhenAWorktreeIsRemovedFromUnderALiveRun, WhenLiveWritersOverlapWithoutMatchingExactly

### Community 74 - "Git Worktree Faults"
Cohesion: 0.27
Nodes (6): FaultTestCase, A project with a commit, so worktrees can be cut from HEAD., `git worktree add` holds a lock for the duration of the checkout, so a `batch…, `registered()` is `git worktree list` for the whole repository. Reporting…, WhenGitHasLockedAWorktree, WhenTheUserHasTheirOwnWorktree

### Community 75 - "Worktree Exclusion Notes"
Cohesion: 0.27
Nodes (5): C8 — a checkout is `git worktree add` output, so it holds tracked files at the…, Plain porcelain C-quotes anything non-ASCII, so the field would hand back an…, A field reporting an empty list on every batch is a field that stops being read., Nothing is cut, so nothing is missing — and after C-A this is the default,…, WhatAWorktreeDoesNotHave

### Community 76 - "Multi-Hop Wait Chains"
Cohesion: 0.31
Nodes (4): AChainLongerThanOneHop, `refuse_concurrent_turn` exempted exactly one run id — the direct predecessor —…, The exemption follows the caller's own wait chain. A run on the same thread…, A waiter is not a free pass for someone else. Phase 2 is given its own hang so…

### Community 77 - "Corrupt Run Isolation"
Cohesion: 0.28
Nodes (4): OneCorruptRunMustNotKillTheFeature, The unreadable-run guard appended every unparseable run in the project, with no…, Its events stream is where the thread id is recovered from. With that gone too,…, The message claimed a live turn on the thread. When an unreadable run is what…

### Community 78 - "Retired Flag Tests"
Cohesion: 0.22
Nodes (5): T1 — argv composition, and the sandbox-drift regression. The most important…, Five flags left in the 260826 round, and a flag that is gone has to be gone…, argparse refuses before anything is claimed, which is what makes a retirement…, The invariant's second guard was argv ordering. With no way to supply a raw…, RetiredFlags

### Community 79 - "Group Result Tests"
Cohesion: 0.22
Nodes (4): GroupResults, D07. The cap makes fetching the full text a decision rather than a guess:…, Slicing characters while reporting bytes made a 3,000-character Korean message…, D30. A full path list per run inverts the context discipline the skill exists…

### Community 80 - "Registry Layout Tests"
Cohesion: 0.22
Nodes (4): `.codex-runs/.gitignore` containing `*` is what keeps the registry out of the…, Four runs in one second share a run-id timestamp, so ordering cannot come from…, Two runs started at once must each own a complete, separate log., RegistryLayout

### Community 81 - "Skill Rewrite Planning"
Cohesion: 0.39
Nodes (8): v0.5.0 Interface Over Document Rewrite, Interface Owns Tool Facts, Codex Skill Rewrite Plan, Zero References Target, Help Audit Manifest, Prose Ownership Classes, Reference Verdict Zero, Skill Rewrite Inventory

### Community 82 - "Batch Isolation Planner"
Cohesion: 0.25
Nodes (8): plan_worktrees(), Whether this member is one `--worktree` would isolate. D35 assigns per member,…, Which members will write, grouped by the directory they will write in. Resolved…, Who is about to write into one directory, and what can be done about it. The…, Decide isolation for the batch, then report why in the same breath. Returns…, sharing_note(), wants_worktree(), writers_by_directory()

### Community 83 - "Operational CLI Commands"
Cohesion: 0.25
Nodes (8): batch clean Command, batch start Command, doctor Command, log Command, result Command, show Command, status Command, Doctor-First Diagnosis

### Community 84 - "Abandoned Waiter Safety"
Cohesion: 0.36
Nodes (4): AnAbandonedWaiterMustNotReleaseTheChain, The premise — otherwise there is no invariant to violate., The fix must not turn every chain into a permanent wait., The chain exemption promised something the wait loop did not keep.…

### Community 85 - "Inventory Coverage Tests"
Cohesion: 0.32
Nodes (4): inventory_rows(), The blocks come out of a commit. A bad ref yields zero rows and every check…, (block_id, hash, class, [anchors]) for every row of the table., TheInventoryCoversEveryBlock

### Community 86 - "Partial Process Death"
Cohesion: 0.32
Nodes (3): A background run is two processes — the supervisor and Codex itself — and…, A background run whose Codex will not exit on its own., WhenOnlyOneHalfOfARunDies

### Community 87 - "Follow Heartbeat Tests"
Cohesion: 0.25
Nodes (3): AHeartbeatSeparatesABusyRunFromADeadFollower, `follow_group` already prints `running -> stalled` after 300 idle seconds, so a…, A flag that parses and decides nothing reads as having been obeyed, which is…

### Community 88 - "Malformed Model Catalog"
Cohesion: 0.39
Nodes (3): MalformedCatalogStillFailsOpen, Valid JSON of the wrong shape is a separate failure mode from the three above,…, Not a second copy of the case above — a string IS iterable, so it never raised.…

### Community 89 - "Armed Waiting Design"
Cohesion: 0.29
Nodes (7): Measured Friction Inventory, Help Round-Trip Cost, Result After Follow Redundancy, Armed Waiting, Background Follow Notification, One-Turn Wait Exception, Arming a Codex Wait

### Community 93 - "Projected Cost Tests"
Cohesion: 0.33
Nodes (3): ProjectedCost, D37. Computed from this project's own history rather than a constant, because a…, projected_cost reads meta, not events — it needs the number for several past…

### Community 94 - "Spawn Interruption Cleanup"
Cohesion: 0.40
Nodes (3): ABatchKilledWhileSpawning, A batch of three with worktrees, killed between members. The existing coverage…, Killed *inside* the window, not merely somewhere near it. Waiting for "two…

### Community 96 - "Validation and PR Contract"
Cohesion: 0.40
Nodes (5): Validated Behavior Inventory, Measurement-Driven Refinement, Adversarial Validation Backlog, Post-v0.2 Unknowns, Korean Pull Request Contract

### Community 97 - "Plan Archive Structure"
Cohesion: 0.50
Nodes (5): Dated Plan Folder Convention, Plan History Relocation, Plan Reference Rewrite, Dated Design Rounds, Design Plan Archive

### Community 98 - "Bridge Error Type"
Cohesion: 0.40
Nodes (3): BridgeError, A `fail()` raised instead of emitted. See `failures_raise`., Exception

### Community 99 - "Fast Mode Help Audit"
Cohesion: 0.50
Nodes (4): Machine-Visible Help Audit Finish Line, Fast Mode Discoverability, Help Claim Verification, Priority Tier Status Reporting

### Community 100 - "Event Cursor Concepts"
Cohesion: 0.50
Nodes (4): Event Cursor, Event and Item, Filter Level, Cursor-Exact Polling

### Community 101 - "Security Disclosure Process"
Cohesion: 0.50
Nodes (4): Reproduction Evidence Bundle, Coordinated Disclosure, Private Vulnerability Reporting, Security Issue Scope

### Community 102 - "Group Cost Measurement"
Cohesion: 0.67
Nodes (3): bridge(), U-08 — what collecting a group costs, applying T3's method to `result --group`.…, run()

### Community 103 - "Registry Scale Measurement"
Cohesion: 0.67
Nodes (3): bridge(), U-07 — what the registry costs once a project has been used for a while.…, timed()

### Community 110 - "Code of Conduct"
Cohesion: 0.67
Nodes (3): Community Impact Enforcement Ladder, Inclusive Community, Private Conduct Reporting

### Community 111 - "Core Run Commands"
Cohesion: 0.67
Nodes (3): resume Command, start Command, stop Command

### Community 112 - "Installation and Diagnosis"
Cohesion: 0.67
Nodes (3): Environment Diagnosis, First Run Loop, Plugin Installation

## Knowledge Gaps
- **48 isolated node(s):** `Four-Tier Validation`, `Worktree Implementation Next Steps`, `Per-Member Git Worktree Isolation`, `Help Round-Trip Cost`, `Result After Follow Redundancy` (+43 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BridgeCase` connect `Bridge Test Helpers` to `Unparsed Event Handling`, `Report Timing Tests`, `Behavior Contract Tests`, `Help Fact Ownership`, `As Ready Pipeline`, `Output Contract Tests`, `Live Writing Safety`, `Batch Mode Constraints`, `Selector Conflict Tests`, `Review Removal Contract`, `Orphan Liveness Safety`, `Unreadable Group Safety`, `Worktree Honesty Tests`, `Wait Chain Safety`, `Unreadable Run Safety`?**
  _High betweenness centrality (0.269) - this node is a cross-community bridge._
- **Why does `BridgeTestCase` connect `JSON Contract Helpers` to `Lifecycle Mode Tests`, `Model Validation Tests`, `Batch Behavior Tests`, `Doctor Diagnostics Tests`, `Argument Default Tests`, `Status Payload Tests`, `Argument Composition Tests`, `Fault Injection Tests`, `Group Follow Filtering`, `Sandbox Resume Tests`, `Log Cursor End-to-End`, `Registry Resolution Tests`, `Worktree Cost Diagnostics`, `Batch Task Validation`, `Cursor Filtering Tests`, `Run State Reporting`, `CLI Flag Coverage`, `Batch Start Semantics`, `Group Selector Semantics`, `Git Worktree Faults`, `Retired Flag Tests`, `Group Result Tests`, `Registry Layout Tests`, `Follow Heartbeat Tests`, `Malformed Model Catalog`, `Partial Batch Startup`, `Projected Cost Tests`, `Model Lookup Failures`?**
  _High betweenness centrality (0.183) - this node is a cross-community bridge._
- **Why does `StatusFollowHelpNamesTheShapesItPrints` connect `Output Contract Tests` to `Bridge Test Helpers`?**
  _High betweenness centrality (0.102) - this node is a cross-community bridge._
- **Are the 26 inferred relationships involving `BridgeCase` (e.g. with `AsReadyBase` and `ForegroundIsNotABatchMode`) actually correct?**
  _`BridgeCase` has 26 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Four-Tier Validation`, `Worktree Implementation Next Steps`, `Per-Member Git Worktree Isolation` to the rest of the system?**
  _48 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Batch CLI Pipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.08348457350272233 - nodes in this community are weakly interconnected._
- **Should `Run Registry Utilities` be split into smaller, more focused modules?**
  _Cohesion score 0.08350168350168351 - nodes in this community are weakly interconnected._