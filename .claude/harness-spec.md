# Harness Spec — Codex-in-Claude

## Context

This repository *is* the harness component it ships: a Claude Code plugin (`codex`) containing a single skill (`codex`) that lets Claude drive the OpenAI Codex CLI as a managed subagent. There is no application code to support — the skill and its Python CLI are the entire product.

- Language / runtime: Python 3.10+, standard library only (no `jq`, no third-party packages).
- External dependency: `codex-cli` (verified against **0.144.1**), authenticated via `CODEX_HOME`.
- Host: Claude Code 2.1.220.
- Distribution: Claude Code plugin, self-marketplace in this repo; dev install via symlink into `~/.claude/skills/codex`.
- Documentation language: **English** for SKILL.md and `references/`; Korean README; Korean trigger keywords inside the skill `description`.
- User proficiency: high. Comfortable with hooks, plugins, skills, and CLI internals; already ships a plugin (`skills-for-repo-wiki`) using this exact packaging pattern. Interview was conducted in Korean at full technical vocabulary.

Full design reasoning, measurements, and implementation order: `docs/plan/codex-skill-implementation-plan.md`.

## Goals

In the user's own words: *"코덱스를 클로드코드의 자체 integrated된 서브에이전트처럼 활용할 수 있는 스킬을 만들고 싶은거지."*

Concretely, Claude should be able to:

1. Hand work to Codex and get a run handle back immediately.
2. Continue an earlier Codex thread rather than starting cold every time.
3. Watch a Codex run's log live and intervene when it goes wrong.
4. Leave Codex running while Claude does something else.

Two constraints the user stated explicitly, and which shape every component below:

- **No use-case rails.** *"그 사용목적을 일일이 스킬에 명시할 필요는 없을거 같아. 이건 일종의 레일이니까."* The skill teaches mechanism, gotchas, and judgment criteria — never a menu of approved tasks.
- **Context discipline is a first-class requirement.** *"코덱스가 접근한 파일의 내용을 전부 클로드에게 그대로 돌려주면 컨텍스트가 낭비될 거 같거든. 이건 일종의 트레이드오프겠지. 이 부분에 대해선 실측을 하며 최적의 전략을 세울 필요가 있을거 같아."* Filter defaults are to be chosen by measurement, not assumption.

## Behavior inventory

All 21 rows are **validated**. The evidence column names the specific check; full detail is in Validation below.

| id | behavior/knowledge/constraint | layer | component | status | evidence |
|----|-------------------------------|-------|-----------|--------|----------|
| B1 | Start a Codex thread with explicit, recorded sandbox/model/isolation settings; background by default | skill+script | `codex_bridge.py start` | validated | T1 `ArgvComposition` (9 tests); T2 I1; T4 E1 |
| B2 | Resume any Codex thread (own runs, `--last`, or a thread created in the Codex TUI) | skill+script | `codex_bridge.py resume` | validated | T1 `test_resume_by_thread_id_and_by_last`; T2 I2; T4 E4. External-thread path checked directly: with an **empty registry**, `--include-external` listed 11 sqlite-recorded threads and resuming a bare-`codex`-created one by id returned its remembered passphrase |
| B3 | A resumed or reviewed run must never silently escalate its filesystem sandbox | skill+script | `codex_bridge.py` (`-c sandbox_mode=` re-injection from the registry) | validated | T1 `SandboxDriftRegression` (7 tests); T2 **I4** against the real CLI (`turn_context` = `['read-only','read-only']`, write refused); T4 E4's recorded argv. Generalised by R1: drift goes both ways |
| B4 | Read a run's event log incrementally at a controlled detail level | skill+script | `codex_bridge.py log --since --level` | validated | T1 `CursorExactness` (5 tests) incl. a partial trailing line; T4 E1/E2/E5 all polled |
| B5 | File contents and successful commands' stdout never reach Claude's context by default | skill+script | filter levels; `show --item` as the only escape hatch | validated | T1 `test_compact_never_leaks_command_output` against a real 22 KB `cat`; T3 measured 10–19% of raw on command-heavy workloads |
| B6 | Inspect one specific event's full output on demand | skill+script | `codex_bridge.py show` | validated | T1 `LogAndShowEndToEnd` incl. loud truncation and per-run item scoping. Not exercised by T4 — no scenario needed it, which is the intended shape |
| B7 | List runs for this project with state, elapsed, idle, tokens; detect stalls without auto-killing | skill+script | `codex_bridge.py status`, `_run.run_row` | validated | T1 `StateReporting` (11 tests) incl. `stalled` with the process confirmed still alive, and `orphaned`. F3: the default view is gated on state, not on recency, so an old run that is still alive cannot fall off the list |
| B8 | Interrupt one or more runs, by explicit selector, without touching other concurrent runs | skill+script | `codex_bridge.py stop --run <id>… \| --group <name> \| --all` (process group, never name matching) | validated | T1 `StopIsolation` (7 tests); T2 I3 with distinct process groups verified |
| B9 | Collect a run's final message, usage, and schema-validated JSON when a schema was supplied | skill+script | `codex_bridge.py result`, `start --schema` | validated | T1 `Results` (7 tests) incl. loud failure on malformed JSON; T2 I5 |
| B10 | Drive `codex exec review`'s distinct flag surface (`--uncommitted`/`--base`/`--commit`/prompt) | skill+script | `codex_bridge.py review` | validated | T1 `ReviewArgumentValidation` (5 tests); T2 I6; T4 E2 chose the review path unprompted; V-10 covers the clean-tree case |
| B11 | Attach images to a Codex prompt | skill+script | `start --image` | validated | T2 I8 (model identified a generated crimson PNG) after R9; T1 adds three argv tests for the `-i`-eats-the-prompt trap |
| B12 | Diagnose the Codex environment in one command (PATH, version, `CODEX_HOME`, auth, config sandbox, resolved skill dir, runs dir) | skill+script | `codex_bridge.py doctor` | validated | T1 `test_doctor` (15 tests) across all four failure modes; T4 E2 used it unprompted as a preflight |
| B13 | Run isolated from the user's Codex config by default; opt back in per run | skill+script | `--ignore-user-config` default, `--inherit-config` opt-in | validated | T1 `test_start_defaults`, `test_inherit_config_drops_isolation_and_priority`; T2 I7 (0 config-error events isolated vs 8 inherited). Magnitude claim corrected by R8 |
| B14 | Preserve the user's priority service tier despite isolation | skill+script | `-c service_tier="priority"` | validated | V-02 — a bogus tier produces an explicit error event, `priority` produces none, so it is parsed and sent; T1 `test_priority_can_be_forced_off_and_on` |
| B15 | Persist run state (thread id, sandbox, pid, session id) durably across Claude context loss, with several writers at once | script | `<project>/.codex-runs/<run_id>/meta.json`, `_registry` (per-writer tmp names, `flock`, compare-and-set) | validated | T1 `test_run_directory_contents`, `test_registry_concurrency` (9 tests); T4 E4 resumed across a **separate session** using only what the registry held. F1 was reproduced first — 152 of 240 concurrent writes raised `FileNotFoundError` before the fix |
| B16 | The run registry must never pollute the user's git history or `.gitignore` | script | `.codex-runs/.gitignore` containing `*` | validated | T1 `test_runs_dir_is_self_ignoring` asserts the file is exactly `*` and that `git status --porcelain` never mentions it |
| B18 | Running the bridge must not raise an approval prompt on every poll | permissions | SKILL.md `allowed-tools` (plugin-portable); `settings.json` equivalent documented for symlink installs | validated | Headless session in **default** permission mode ran the bridge with no prompt; `${CLAUDE_PLUGIN_ROOT}` is expanded in permission matching even though it is absent from the process environment (R6) |
| B19 | Prepend minimal situational facts to every Codex prompt (non-interactive, single turn, nobody to ask) — facts only, no methodology | script | `start`/`resume` preamble, `--no-preamble` disables | validated | T1 `test_prompt_is_last_and_carries_the_preamble`, `test_no_preamble_disables_it` |
| B20 | Codex-CLI gotchas that cannot be derived from general competence | skill | SKILL.md gotcha section + `references/` | validated | Eight gotchas, each carrying the measurement that produced it; `validate_harness.py` 0 errors / 0 warnings; frontmatter re-verified to parse |
| B21 | Live-follow a run so each event becomes a notification, including terminal failure states | skill+script | `log --follow`, paired with the Monitor tool | validated | T1 `test_follow_emits_a_terminal_line` (asserts `run.failed exit=4`, so silence can never read as success); T4 E1/E2/E5 all used `--follow --level compact` |
| B22 | Start N runs as one named, addressable group and get every handle back at once | skill+script | `batch start --group <name> --task/--tasks-file` | validated | T1 `BatchStart`, `TasksFile` (17 tests) incl. start order recorded in the manifest and a broken tasks file costing nothing |
| B23 | Ask one question of a whole group's state, and be notified when the *group* ends; find a group a later session did not start | skill+script | `status --group <name> [--follow]`, per-run `group`, top-level `groups` | validated | T1 `GroupSelectors` (9 tests) incl. `group.completed` / `group.still-running` terminal lines so a group can never end in silence, `AMemberThatNeverStartedIsStillAMember` (4), `AGroupIsDiscoverableFromStatus` (3); T2 I13; T4 E9. A member that never spawned counts toward `partial` and is named under `unstarted` — resolving membership through run ids alone made a group asked for two and given one report `completed` |
| B24 | Concurrent writers must not edit each other's files mid-edit | script | per-member git worktree at `.codex-runs/<run_id>/wt`; `concurrent_writers` where isolation is unavailable | validated | V-13 (main tree stays clean; `git worktree remove` refuses a dirty tree); T1 `Assignment` (13 tests), `ConcurrentWritersAreNamedWhereTheMistakeHappens` (5). T4 measured the gap this closes: `resume` has no worktree option, so continuing several writers is unisolatable by construction and the only defence is saying so at the moment it happens. Per member, not per batch: V-15 measured that a fresh worktree has 0 lines of `git diff HEAD`, so `read-only` and `review` members must stay in the caller's tree |
| B25 | Collect a group's results under a cap, and surface what more than one member wrote | skill+script | `result --group`, `overlaps` | validated | T1 `GroupResults` (6 tests) incl. cutting and measuring in the same unit, and `OverlapsUnderIsolation` (3); T2 I10 against real Codex. `overlaps` is the intersection only (D30), keyed by run so a resumed member never overlaps its own past self, and compared **relative to each run's own root** — absolute per-worktree paths intersect to nothing, which made this field blind in the one situation it exists for until T2 caught it |
| B26 | Continue a whole group into a next phase, member for member | skill+script | `batch start --resume-from <group>` | validated | T1 `ResumeFrom` (12 tests). Pairs positionally against the manifest's recorded order — F15 makes same-second, same-label starts the normal case, so id or timestamp ordering would be a coin flip exactly here |
| B27 | Stop a whole group, and remove its worktrees without discarding uncollected work | skill+script | `stop --group`, `batch clean --group [--force]` | validated | T1 `Clean` (10 tests). Four refusals; the dirty-worktree one is git's own (V-13) rather than reimplemented, and occupancy is asked of the registry rather than of the group graph, which is one hop deep and evaporates when an intermediate group is cleaned |
| B28 | Tell a batch run the facts about its own situation that it cannot observe | script | batch preamble (group size, worktree path, base, uncommitted count) | validated | V-18: without it a run asserted *"we are looking at the same tree"* — wrong, and unhedged; with it, correct, and it propagated N−1. 113 input tokens. Hedged wording, since members spawn in sequence and the earliest may already have finished |
| B29 | Give a background run a deadline the caller chose, distinguishable from every other ending | script | `--timeout`, terminal state `timed_out` | validated | V-16: the thread stays resumable across the timeout SIGINT with the pre-timeout turn's context intact, so `timed_out` is recoverable rather than a failure. T1 `BackgroundTimeout` (3 tests) |

### Refinements forced by v0.2.0's measurements

Same form as R1–R9: each one is a place the plan said something that turned out to be wrong, found by running the thing rather than by reading it.

- **R10 — `batch clean`'s protection cannot be derived from the group graph.** Plan §3.6 plus §1.4 listed the refusals as live members, dirty worktrees, and a derived group. `derived_from` is one hop deep and evaporates the moment an intermediate group is cleaned: with p1 → p2 → p3, a `batch clean --group p2 --force` leaves p1 looking unreferenced while p3 is still running inside p1's worktree — reproduced, and it deleted from disk the exact directory a live run had as its cwd. The right question is not lineage but occupancy: **is any non-terminal run's recorded cwd inside this worktree.** A run's own cwd cannot go stale the way a graph edge can. The `derived_from` check stays, because it gives the better message while the chain is intact.

- **R11 — "keyed by run, not by worktree" (§3.4, D30) was necessary and not sufficient.** The plan correctly saw that a worktree-keyed set would make every `--resume-from` member overlap its own predecessor. What it never noticed is that **Codex reports absolute paths**, so under worktree isolation three members editing the same `src/parser.py` produce three distinct strings and intersect to nothing — `overlaps` reported a clean run in precisely the situation it exists to warn about, and the cleaner the isolation the more reliably it lied. Caught by T2 I10, not by T1, because the unit fixture planted repo-relative paths, a shape real events never have. The obvious fix — relative to each run's own cwd — then introduced a false positive (two repositories each with an `output.txt`) and a false negative (two members rooted at different depths of one repository). The key is a pair: `--git-common-dir`, which every worktree of one repository shares and no two repositories do, plus the path relative to that run's own top level.

- **R12 — "recorded in place" (§3.2) was true of one line of JSON and nothing else.** A member that fails to spawn keeps its manifest slot, as planned. But every later view of a group resolves membership through run ids, and that member has none — so it existed only in `batch start`'s reply and vanished the moment that scrolled past. Measured: a group asked for two members and given one reported `group_state: completed`. Those slots are now first-class in every group view, they count toward `partial`, and `--follow`'s terminal line carries `unstarted=N`.

- **R13 — the plan never made a group discoverable.** §3.3 defines `status --group <name>`, and every group command takes a name the caller is assumed to have. A session that did not start the batch has no way to learn one: `status` listed runs and said nothing about groups. Measured in a headless e2e session, which found three runs, declared out loud that they "were individual starts, not a batch group", correctly deduced that plain `resume` cannot isolate writers, and continued three of them into one shared directory — **reasoning perfectly well from a false premise the tool had handed it**. `create_run` had been recording each run's group in meta.json since M4a with a comment saying it was there so `status` could answer this; `status` now does, and also lists the project's groups.

- **R14 — D35 recorded that resume members inherit their directory, and never drew the consequence.** `resume` has no worktree option at all, so continuing several writers at once is **unisolatable by construction**; only `batch start --resume-from` can assign one per member. Documentation was measured to be insufficient here twice over: a session that had the guidance available still used three individual `resume` calls into one directory, and escaped damage only because the three edits happened to land in three different files. The conclusion is a general one — where the tool knows a fact the caller cannot see, the tool should say it at the moment it matters rather than leaving it to prose. `concurrent_writers` on `start`/`resume`, and the same check registry-wide in `doctor`.

- **R15 — "pair `--follow` with Monitor" (§3.3) is right only when another turn is coming.** The plan's reasoning was the Bash tool's 600-second ceiling, which is correct as far as it goes. In a single-turn context the follower dies with the turn and nothing arrives. Measured: two headless sessions each started their batch correctly, launched a background wait, and ended the turn promising to report back — delivering the user a promise instead of the findings they asked for. With one turn, `status --group --follow --follow-timeout <sec>` in the **foreground** is the right shape. And separately: `batch start` returning is not the batch being done, and the group finishing is not the results being collected.

- **R17 — a flag nothing asserts on is a flag that can stop working silently.** `--include-external` had zero test coverage, and a change to a neighbouring line disabled it without anything going red. Asked afterwards how much more of the surface was in that state, the answer was measurable rather than a guess: diffing the parser's registered flags against every string in the suite found four more. None of the four turned out to be broken — but they were in the same position, and that position is the defect. All 43 user-facing flags are now named by at least one test, and that diff is worth re-running before any release.

- **R24 — the invariant had a documented flag pointing straight through it.** `--config` hands a raw `-c key=value` to Codex, and `codex`'s `-c` is last-value-wins for a repeated key. The wrapper emitted its own enforced `-c sandbox_mode=` *before* the caller's raw entries, so `--config 'sandbox_mode="danger-full-access"'` simply won. Measured against the real binary, same prompt both ways: with the raw entry last the write to `/tmp` returned exit 0 and the file appeared; with the enforced entry last it returned `Operation not permitted`. Throughout, `meta["sandbox"]` and therefore `status` reported `read-only` — and since `extra_config` is inherited by every resume that does not pass `--config` itself, the drift rode along for the rest of the thread. This is B3, the one behaviour the skill exists for, defeated by a flag in its own `--help`. Two guards now, deliberately redundant: the four keys the wrapper sets are refused outright with the flag that owns each one named, and the argv order is inverted so a key nobody thought to reserve still cannot outrank an invariant. The general lesson is narrower than "validate input": **a pass-through option is a second, unaudited way to set everything the tool sets itself**, and it needs listing against the settings the tool considers its own.

- **R22 — two fixes that were each right and together were a regression.** Publishing a run's `meta.json` before cutting its worktree (R18) made it visible to `reap`, whose grace period for a supervisor-less `starting` run is thirty seconds of file mtime. `git worktree add` is allowed sixty. So a large checkout on a slow disk leaves a *live* run looking half a minute dead, `orphaned` is terminal, and the run therefore drops out of `batch clean`'s live-member guard and out of the occupancy check protecting its worktree — at which point `-f -f`, added by the same commit precisely to defeat git's `initializing` lock on a worktree whose owner died, removes a checkout whose owner is alive and still writing into it. The two changes cancelled each other. A run now records `creator_pid` before it does anything slow, so `reap` asks a process rather than a clock. The transferable part: a heuristic's safety is a property of *when* the thing it reads is written, and moving that write is a change to the heuristic even when the heuristic is not touched.

- **R23 — unknown is not terminal.** `batch clean`'s live-member loop skipped a member whose `meta.json` would not parse, while the removal loop below it still found that member's worktree by the `<run_dir>/wt` convention. A run last recorded `running` therefore lost the only copy of its work with no `--force` ever passed. The skip read as "nothing to check here"; what it actually meant was "I cannot tell whether this is running", which is the case for refusing, not for proceeding. Also from the same shape: `vanished_members` said "its run directory is no longer in the registry" about a directory that was still there with a corrupt meta — sending the caller away from work still on disk, while the same payload's `unreadable` field said the opposite.

- **R18 — the fix a commit claimed, and the test that let it claim it.** A batch killed while spawning left a checkout belonging to no member of any group. Writing the manifest slot *before* the spawn looked like the fix, its regression test went green, and the commit said so. The test passed six times in ten; the four failures were the defect, still there. The slot cannot carry a run id — the id is minted inside `create_run` — so the guard was in the wrong place entirely. Closing it took four changes plus a fifth underneath them all: **`--force` did not force.** `git worktree add` holds a lock reading `initializing`, a batch killed inside the add leaves it locked forever, and `git worktree remove --force` refuses a locked tree; it wants `-f -f`. `batch clean` had been printing that it "lifted every protection at once" while a checkout survived it. Two process notes: a test that passes intermittently is a finding, not noise, and "did the fix do what the commit says" needs asking by something other than the author.

- **R19 — a silently ignored flag is a false premise the caller then reasons correctly from.** `status --run <id> --follow` returned one snapshot and exited: `--follow` is registered on `status` as a whole but only the `--group` branch reads it. Guarding that symptom left the precedence underneath it untouched, so `--run X --group g --follow` walked past the new guard and the `--run` branch won again — found by a Codex `review` member pointed at the commit that added the guard. Both are R13's shape: the tool hands back an answer the caller reads as "I waited for this."

- **R20 — one rule enforced at the top level and not one level down.** `load_tasks` refuses unknown *top-level* task fields, with a comment saying exactly why: "the failure mode of a silently ignored field is a run that quietly used the group default instead". `review` is the only nested object a task has, and inside it the rule did not apply — `title` was dropped without a word, and combinations the Codex CLI rejects were passed straight through to fail asynchronously. Both callers now build the flags in one place. Worth generalising: a validation principle stated in a comment tends to hold exactly at the depth someone was looking at when they wrote it.

- **R21 — `${CLAUDE_PLUGIN_ROOT}` is expanded in a permission rule and `$HOME` is not.** R6 measured the first and it was reasonable to assume the second followed. It does not, so the `settings.json` rule this project has been documenting for symlink installs never matched anything, and every bridge call under it was refused. `Skill(codex)` also needs its own rule or the skill cannot load at all, and the `Bash(...)` rule is never reached. And the plan's guess that a long `batch start` would break the text match was right about the symptom and wrong about the cause: length is irrelevant against a prefix and a trailing `*`; the **line continuation** a model reaches for because the command is long is what breaks it.

- **R16 — a specified, assigned item was never implemented, and nothing at the milestone level noticed.** §1.7's `doctor` warning for non-terminal runs sharing a cwd was written into the plan, assigned to M4b, and simply not built; the pre-release sweep found it. Milestone checks verified what was written against what was planned for *that* milestone, and this fell between two. Worth carrying forward as a process note: a plan item's completion should be checked against the plan, not against the diff.


### What is still unmeasured after the 2026-08-03 round

The eleven open items from `docs/plan/260802/README.md` were worked through on 2026-08-03; what that found is in the results section below. What is left:

- **N above 24.** Measured at 12, 16 and 24 with zero contention, every thread id distinct, and `batch start` returning in about 0.29 s per member — so `--stagger` stays out and D34's condition has still never fired, now at three times the ceiling that justified leaving it out (`docs/measurements/batch-cost.md`). What that does *not* say anything about is many simultaneous **heavy** members: a trivial prompt's turn is dominated by round-trip latency, not by anything that queues.
- **Batch collection at bigger messages.** `GROUP_MESSAGE_CAP = 4000` never engaged across N=3/5/8 — every member's final message came in between 258 and 661 bytes — so the number still has no evidence behind it, only headroom. It would take a workload whose members write long final messages to choose 4,000 rather than inherit it.
- **The plugin install's permission path.** Everything below was measured on the **symlink** install with a `settings.json` rule. `${CLAUDE_PLUGIN_ROOT}` expansion in the frontmatter pattern was last measured at v0.1.0 (R6) and is the path most users are on.
- **A group name is burned by a batch whose members all fail to spawn.** `claim_group` runs before the loop and a per-member failure does not unwind it, so a tasks file that fails *validation* costs nothing while one whose members fail *to spawn* costs the name. `batch clean --group` releases it and the name is reusable — the friction is one command deep, and the refusal now says so.
- **`status --include-external` at the fifty-thread limit.** Titles are capped now; the rest is about 830 bytes per thread, mostly `sandbox_policy` and `rollout_path`, which would be roughly 40 KB at the limit.

**Linux is out of scope**, by the user's decision on 2026-08-03: this skill targets macOS. The previous wording here ("everything was measured on one macOS machine") invited someone to go and measure Linux; it is not a gap, it is the supported surface.

**Two consecutive adversarial rounds at zero high/medium was the standing bar, and this round did not clear it.** Round one found that a fix had not worked and its regression test passed six times in ten. Round two, over the fixes round one prompted, found two more high-severity defects — both reproduced end to end, both *created by* those fixes (R22, R23) — plus four documentation claims that had gone stale inside the same session that wrote them. Everything found is fixed and covered by tests that fail when the fix is reverted, but a third round has not been run, so the bar is still not met and should not be reported as met.

The signal worth carrying, now with more evidence behind it: **defect discovery has never converged to zero.** Seven deliberate `overlaps` property tests found no new defect, and then nine deliberate fault injections found three. Fixing those three drew an adversarial review round that found the fix had not worked and its own regression test passed only six times in ten. Walking the option surface flag by flag against the real CLI then found four more. Every one of these was reachable only by running the thing.

### T5 — the option surface against the real CLI (2026-08-03)

A new tier, and the reason it exists is R17's limit. R17 established that all 43 user-facing flags are **named by at least one test**. That is a real property and it is not the one that matters: `overlaps` was named by a test throughout the whole period it was blind, because the fixture planted a shape real events never have. So the flags were walked one at a time against `codex-cli 0.146.0`, with the evidence for each being its recorded `argv`, an event stream, or an observed state transition — never the absence of an error.

Coverage before this round was about ten flags with real-CLI evidence (T2's I1–I15). Everything else had unit-test evidence only.

**Mode A — one thread, start to finish.** `--label`, `--sandbox`, `--model`, `--effort`, `--priority`, `--config`, `--add-dir`, `--prompt-file`, `--no-preamble`, `--foreground`, `resume --last`, `log --since/--level/--follow/--interval/--follow-timeout`, `show --item/--max-bytes`, `status --run/--thread/--all/--include-external`. The filter levels reproduced T3's shape on a real batch workload: `compact` and `normal` byte-identical at 641 B because every command exited 0, `full` 9,633 B, `raw` 44,026 B. Resuming re-asserted sandbox, model, effort, `service_tier` and `--ignore-user-config` from the registry — I4 had only ever covered the sandbox.

**Mode B — a group.** A four-member `--tasks-file` batch with a different `kind`, `label`, `sandbox`, `effort` and `model` per member. D35's per-member worktree assignment held against real git: the two `workspace-write` writers each got a checkout, the `read-only` member and the `review` member stayed in the caller's tree. Spawning four members took 1.45 s. `overlaps` correctly reported one collision when two writers in separate worktrees both edited `tests/test_worktree.py` — R11's fix, measured for the first time through the `--tasks-file` path.

**Mode C — two phases.** `--resume-from` paired positionally, each member continued its own thread in its predecessor's worktree and cut no second checkout. Refusals measured: resuming a group with live members, a task-count mismatch (before the name is claimed, so it costs nothing), and cleaning a group another group resumed into.

**Mode D — `review`.** `--base`, `--commit`, `--cwd`. `--title` was silently dropped and is the subject of R20.

**Mode E — a thread this skill never started.** A thread created by running `codex exec` directly was found through `status --include-external`, picked up by id with an explicit `--sandbox`, and continued — it quoted its own previous reply. The next turn, given no flags at all, re-asserted that sandbox and effort from the registry. This is the first measurement of SKILL.md's claim that an outside thread is protected from the pickup onward.

**Mode F — near-misses, headless.** Two, both passing with the absence shown rather than asserted: "review these three files at once" (no `Skill` event, no `SKILL.md` read, no bridge call, and all three seeded bugs found by Claude itself), and a harder one not previously tried — "does this project document which GPT models it works with, and is that accurate" — where `GPT` appears as the subject of a documentation question rather than as an instruction to delegate. It did not trigger, and it answered the question by checking each documented claim against the code.

**Coverage, counted rather than asserted.** The bridge exposes **41 user-facing flags** across eleven subcommands (`--runs-dir`, `--project` and `-h` excluded — they exist for tests and scripting). Every one of the 41 now has evidence from a real `codex-cli` invocation: 22 from T2's I1–I15 in earlier rounds, and the rest from this tier. The four that had no evidence anywhere until the ledger was actually built — `--grace`, `--isolate`, `--no-priority`, `--no-worktree` — plus `stop --group` and `stop --all` (T2 covered only `stop --run`) were run explicitly to close it:

| flag | evidence |
|---|---|
| `--no-worktree` | two `workspace-write` members, which normally force isolation, both landed in the caller's tree with `worktree: null` |
| `--no-priority` | `priority: false` and **no `service_tier` in argv**, against `--priority`'s `-c service_tier="priority"` |
| `--isolate` | `isolated: true`, `--ignore-user-config` in argv — passing it explicitly agrees with the default rather than changing it |
| `stop --group --grace 3` | both members signalled, `SIGINT` alone, both `interrupted`, group `partial`, returned in 1.6 s |
| `stop --all` | signalled the one live run and left the two already-terminal members alone |

One honest limit on that table: `--grace` bounds an escalation ladder (SIGINT → SIGTERM → SIGKILL) that real Codex never forces, because it exits on the first signal. The ladder itself is T1's, via a shim that ignores SIGINT. So `--grace` is measured as accepted and honoured as a bound; it is not measured as *elapsing*, and cannot be against a well-behaved Codex.

**What this tier found:** four defects, all in the class R17 predicted. `status --run --follow` accepted the flag and ignored it; `--run` together with `--group` silently discarded the group; `status --include-external` returned every thread's full stored prompt as its title; and the `review` surface had two rulebooks, with the batch one enforcing none of the single-run path's three rules.

### v0.2.0 validation results (2026-08-02)

**T1 — 239 tests, passing.** Grew from 124 at v0.1.0. The additions worth naming are the ones that exist because something got past the tier below them: multiprocess registry concurrency (F1 reproduced at 152 of 240 writes first), per-member worktree assignment against real git, the `--resume-from` pairing refusals, and `OverlapsUnderIsolation` — which exists because the pre-existing `overlaps` test planted repo-relative paths, a shape real events never have.

**T2 — 15/15 against `codex-cli 0.146.0`**, up from the 0.144.1 every earlier tier was measured on. I1–I8 unchanged; I9–I15 cover batch orchestration. Notable: I7 measured the isolated-vs-inherited input-token ratio at **1.06×**, against 2.92× at design time and 1.09× two weeks later — a third data point for R8, and the standing reason `projected_cost` is computed from the registry rather than baked in.

**T4 — headless e2e, 4 scenarios, run three times.** E8 (near-miss: "review these three files at once", no mention of Codex) passed on the first attempt with the correct evidence, which is an absence — no `Skill` event, no `SKILL.md` read, no `codex_bridge` call anywhere in the transcript — while the review itself correctly found all three seeded bugs. E9 passed: given a group that requested two members and started one, the session reported *"1건은 실행조차 못 됨"* with the reason, which is the specific failure that scenario exists to catch.

E6 failed the first run and passed the two after it. E7 failed all three, and the three failures were three different things, which is the useful part:

| Run | What failed | What it was |
|---|---|---|
| 1 | Both sessions started the batch correctly, launched a background wait, then ended the turn promising to report back | A real gap. A headless turn has nothing to resume it, so the promise was never kept. Fixed by documenting that Monitor is for when more turns are coming and a foreground `--follow` is for when this is the only one. E6 passed after this. |
| 2 | The session declared the earlier runs "individual starts, not a batch group" and fell back to unsafe individual `resume` calls | A real defect, and the tool's fault: `status` never said which group a run belonged to. The session reasoned correctly from a false premise the tool handed it. Fixed — every run row carries its `group`, and `status` lists the project's groups. |
| 3 | The session found the group, explicitly reasoned about the shared-directory hazard, serialised the three writers to avoid it, waited synchronously, verified with `git diff` and `py_compile`, and reported real per-file diffs — but still used plain `resume` rather than `--resume-from` | **The rubric was wrong, not the harness.** Serialised writers cannot collide, and for a fix phase, landing in the caller's own tree is arguably what was asked for. The criterion "must use `--resume-from`" was over-specified. |

What the third run did leave behind is a real question — a session that *doesn't* reason about the hazard would fire three parallel `resume` calls — so that case is now covered by the tool rather than by advice: a writing run started into a directory another live writing run occupies returns `concurrent_writers` naming them, `doctor` reports the same registry-wide, and both were verified on the resume path specifically, since that is where the measured failure was. This is plan §1.7, which had been specified and assigned to M4b and never implemented.

Three defects in this milestone were found by running the thing rather than reading it, and none of them were reachable by review: `group_state: completed` for a group that started one of two members; `overlaps` returning `{}` for three members all editing the same repo path in their own worktrees; and a group being invisible to the session that had to find it.


## Component specs

### `.claude/skills/codex/scripts/codex_bridge.py`

Single Python 3.10+ stdlib CLI. Subcommands: `start`, `resume`, `review`, `batch start`, `batch clean`, `status`, `log`, `show`, `stop`, `result`, `doctor`. All emit one line of JSON except `log`, and `status --group --follow`, which are line streams.

The entrypoint holds the CLI surface and one handler per subcommand; the machinery is in siblings — `_util`, `_registry`, `_events`, `_codex`, `_worktree`, `_run` (building a run and describing one), `_batch` (the group manifest, the batch subcommands, and the group views `status` and `result` grow for one). `_run` sits below `_batch` in the import order, which is what lets the batch subsystem live in one file without importing the entrypoint back.

Two invariants that unify the implementation, both forced by §3.8 of the plan (flag availability differs per subcommand):

- Sandbox is **always** expressed as `-c sandbox_mode="<mode>"`, never `-s`. `-s` does not exist on `resume` or `review`.
- Working directory is **always** set on the child process, never via `-C`. `-C` does not exist on `resume` or `review`.

Defaults: background, `workspace-write`, isolated (`--ignore-user-config`), `service_tier=priority` re-injected, no model pinned, no reasoning effort pinned, no hard timeout.

### `.claude/skills/codex/SKILL.md`

`name: codex`. `description` is the sole trigger signal — written to lean toward firing, naming intent rather than keywords alone, carrying Korean triggers (`코덱스`, `GPT에게 시켜`, …) and explicit near-misses (not Claude's own subagents/Task tool; not Codex Cloud or Codex-as-MCP-server). `allowed-tools` pre-approves the bridge script.

Body holds only what every invocation needs: path resolution, the CLI surface, the core loop (start → poll → judge → stop+resume → result), the context-discipline principle with its reason, the gotchas, background/parallel patterns, structured output, and cost/judgment inputs. No use-case list, no delegation methodology.

### `.claude/skills/codex/references/`

Split by the branch the model takes, not by volume:

- `environment.md` — `CODEX_HOME` resolution, isolation vs inherit with measured numbers, auth, sandbox semantics and the escalation story, `service_tier`, reading `doctor` output.
- `event-stream.md` — both event schemas (stdout API and rollout file), filter levels with the measured calibration table, cursor/polling, Monitor pairing, `show`.
- `orchestration.md` — running several runs as one group: the batch commands, worktree assignment and its traps, `--resume-from` pairing, how cost multiplies. Mechanism and gotchas only (D31): no catalogue of phase patterns, because the shape of a delegation varies every time and freezing it is a flexibility tax (D02, D12).
- `troubleshooting.md` — symptom → cause → fix, plus the out-of-scope list.

Launch/watch/interrupt/resume/collect deliberately stay in SKILL.md: a single invocation needs them together, so splitting them would add a routing decision with no payoff.

## Design rationale

**Why a run registry exists at all.** `codex exec resume` has no `-s/--sandbox` flag, so it falls back to `config.toml`'s `sandbox_mode`. Measured on this machine: a thread created `read-only` was resumed at `danger-full-access` and wrote a file its original policy forbade. The only way to hold a sandbox across turns is to remember the mode and re-assert it, which requires durable per-run state. Everything else the registry does (parallel-safe stop, stall detection, session-scoped cleanup) is a bonus on top of that one non-negotiable.

**Why isolation is the default.** Measured: an inherited-config run spent 46,238 input tokens on a one-line task and leaked 24 config-error events plus an unrelated plugin advertisement into the agent's own message; the isolated equivalent spent 15,863 with a clean four-line stream. Rejected alternative: always inherit (fidelity to the user's MCP/plugin setup, but ~3× the input cost on every call). Rejected alternative: a dedicated `CODEX_HOME` profile (cleanest isolation, but it severs continuity with threads created in the Codex TUI, which B2 requires). `--inherit-config` keeps the rejected option available per run.

**Why stop+resume rather than mid-turn steering.** `codex exec` is a single non-interactive turn with no input channel once running. The TUI's Enter-injection needs a TTY that Claude cannot drive. `codex app-server` could in principle support real steering but is documented as subject to change without notice. Stop+resume was chosen with that tradeoff stated; the app-server path is recorded as unexplored, not as impossible.

**Why no instruction-injection presets.** The legacy skill wrapped methodology files in `<SystemPrompt>` tags. Dropped on the user's reasoning: Claude is the caller and can write whatever Codex needs directly into the prompt, so a preset library is a rail that accumulates unused files. Only a minimal situational-facts preamble survives (B19), because Codex asking a clarifying question in a non-interactive turn wastes the entire turn.

**Why the filter default is deferred to measurement.** `file_change` events carry paths only; the whole context risk is `command_execution.aggregated_output`, which contains full stdout including file bodies Codex has `cat`ed. Picking a default without measuring would be exactly the unjustified-number rail this project avoids, so T3 measures three workloads across four levels and the default cites its own table.

**Why no agent and no workflow.** An agent was considered and rejected: the main thread is what needs to watch the log and decide when to intervene, subagents cannot ask the user anything, and Claude's own background Bash plus Monitor already provide the parallelism. A pre-defined workflow was rejected under the same D12 logic that governs e2e — the shape of "delegate something to Codex" varies every time, so freezing it would be a flexibility tax.

## Validation

Four tiers, all approved (*"목적을 달성하는데 필요한 모든 테스트를 해야해"*). Full case lists in the plan, §7.

- **T1** — unit tests against a fake `codex` shim on `PATH` replaying recorded fixtures. Free and repeatable; this is the primary safety net. Carries the sandbox-escalation regression, the parallel-stop isolation test, the filter-leak assertions, and the Korean-path/NFD case.
- **T2** — real Codex integration against a scratch repo, env-gated. Re-verifies the sandbox regression against the actual CLI.
- **T3** — filter calibration measurement across read-heavy / write-heavy / review workloads; output to `docs/measurements/filter-calibration.md`, summary into `references/event-stream.md`, and the shipped default cites it.
- **T4** — headless Claude e2e including a deliberate near-miss prompt that must **not** trigger the skill. Composed on the spot per `e2e-testing.md`; evidence-cited grading, surface compliance is a FAIL.

Plus `validate_harness.py` clean.

**Open verification items (V-01…V-10)** are listed in the plan §6 with a check recipe and a fallback each. V-03 (does `-c sandbox_mode=` genuinely constrain a resumed run?) is a blocker; the rest have documented degradations. Record every outcome here as it is resolved.

### V-01…V-10 results

Measured 2026-07-25 against `codex-cli 0.144.1`, Claude Code 2.1.220, macOS 25.5.0 (APFS), `CODEX_HOME=…/orca/codex-runtime-home/home`. Scratch repo under the session scratchpad. Raw event streams and rollout paths were kept for the run; the durable evidence is quoted inline below.

| ID | Verdict | Evidence |
|---|---|---|
| V-01 | **answered at M8 — NO** | `CLAUDE_PLUGIN_ROOT` is **empty in the Bash tool's environment even for a plugin-installed skill**. Measured in a headless session with the plugin installed and the skill active: `PLUGIN_ROOT=[] SKILL_DIR=[] PROJECT_DIR=[]`. The plan's §4 fallback (`$HOME/.claude/skills/codex`) does **not** rescue this — for a plugin install that path does not exist. See refinement R6 for what replaced it. **Two things that do work**, and the distinction is the useful part: `${CLAUDE_PLUGIN_ROOT}` *is* expanded in `allowed-tools` permission matching (a different layer from the process environment), and Claude Code injects `Base directory for this skill: <dir>` into the skill's own context. |
| V-02 | **PASS** | `-c service_tier="priority"` under `--ignore-user-config`: exit 0, no `error` item. Proof the key is genuinely parsed rather than ignored: `-c service_tier="bogus_tier_xyz"` emits `{"type":"error","message":"Configured service tier \`bogus_tier_xyz\` is not advertised as supported for model \`gpt-5.6-sol\` and will be omitted from requests."}`. `priority` produces no such warning ⇒ it is advertised and sent. **D18 stands.** Bonus: an unsupported tier degrades to a non-fatal warning, so always injecting `priority` is safe. |
| V-03 | **PASS (blocker cleared)** | `-c sandbox_mode=` genuinely constrains `resume`. Thread `019f9958`: turn 1 `exec -c sandbox_mode="read-only"`, turn 2 `exec resume -c sandbox_mode="read-only"` + an explicit write instruction. Rollout `turn_context` records `"sandbox_policy": {"type": "read-only"}` for **both** turns; agent replied *"Cannot: the workspace is read-only, and permission escalation is disabled."*; `escalated.txt` was never created. Re-confirmed positively on thread `019f995b` turn 3 (`read-only` → `workspace-write` via `-c`). |
| V-04 | **PASS** | `-c model_reasoning_effort=` is accepted and takes effect on `resume`. Thread `019f995b`: turn 1 `-c model_reasoning_effort="low"` → `turn_context…reasoning_effort=low`; turn 3 `resume -c model_reasoning_effort="high"` → `reasoning_effort=high`. |
| V-05 | **PASS — component since removed** | `SessionEnd` hook input keys: `cwd, hook_event_name, permission_mode, reason, session_id, transcript_path`. `cwd` is present as the plan assumed — **and so is `session_id`**, which is a better source than the env var (see refinement R4). Separately confirmed `CLAUDE_CODE_SESSION_ID` **is** set in the Bash tool env (`fbe1349d-…`), so `start` can record it. |
| V-06 | **PASS — and it answers "no"** | `--ignore-user-config` does **not** suppress a project `AGENTS.md`. Probe: scratch repo `AGENTS.md` containing *"The secret codeword for this repository is ZEBRAFISH."*; prompt *"Without running any commands and without reading any files, reply with exactly the secret codeword"* → agent replied `ZEBRAFISH`. Rollout confirms the mechanism: a `response_item`/`message` carries `<INSTRUCTIONS>\n# Project agent notes\nThe secret codeword for this repository is ZEBRAFISH.\n</INSTRUCTIONS>`. Cost: 16,410 input tokens vs a 15,871 baseline ⇒ ~540 tokens of injection. This is the plan's flagged branch: AGENTS.md is a live briefing channel and B19's preamble must account for it. |
| V-07 | **answered at M8** | The skill is invoked as **`codex:codex`** — the transcript shows `Skill` called with `{"skill": "codex:codex"}` and the result line `Launching skill: codex:codex`. Cosmetic, recorded in the README. |
| V-08 | **PASS** | SIGINT to the process group leaves the thread cleanly resumable. Thread `019f995f` spawned with `start_new_session=True`, interrupted mid-turn after 4 of 6 commands; exited **0.3 s** after SIGINT with code 1 (no SIGTERM escalation needed). Resume returned the same `thread_id`, the rollout grew 33 → 42 lines, and the agent answered *"Your favorite fruit is **MANGOSTEEN**. I completed ticks **1, 2, 3, and 4** before interruption."* — the partial turn's completed work survived, not merely the pre-turn state. |
| V-09 | **PASS** | Headless `claude -p "Reply with exactly: PONG" --output-format json` spawned from the Bash tool: exit 0, `"is_error": false`, real API usage recorded. `e2e-testing.md`'s documented open risk (Bash-spawned `claude` failing to authenticate) does **not** apply in this environment. T4 can be a real headless run. |
| V-10 | **PASS** | `codex exec review --uncommitted --ignore-user-config` on a genuinely clean tree exits 0 and emits a plain agent message — *"There are no staged, unstaged, or untracked changes to review."* No error to special-case. It does burn ~4 exploratory `command_execution` items first (the model re-verifies the empty diff), which is cost, not failure. |

### V-11…V-18 results (v0.2.0 batch orchestration)

Measured 2026-08-01 against `codex-cli 0.144.1`, macOS 25.5.0, this repository at `8a4288b`, `CODEX_HOME=~/.codex`. Each item's check recipe and its fallback are in `docs/plan/260801/implementation-plan.md` §9. **V-11 and V-13 were the blockers; both passed, so the batch design in that plan stands unchanged.**

| ID | Verdict | Evidence |
|---|---|---|
| V-11 | **PASS (blocker cleared)** | No sqlite contention at N=8. 15 concurrent `codex exec` runs (batches of 1/2/4/8 sharing one `CODEX_HOME`) each got a **distinct** `thread_id` (15 unique of 15) and all reached `completed`. `grep -iE 'database is locked\|sqlite\|rate.?limit\|429'` over all 15 `events.jsonl` returned **zero** hits. **Consequence: no `--stagger` is added** — D34 makes it conditional on this measurement, and the condition did not fire. |
| V-12 | **PASS** | No throttling or degradation through N=8. Wall clock for the whole batch: N=1 **4.45 s**, N=2 **5.53 s**, N=4 **5.41 s**, N=8 **7.55 s** — flat-to-mild, i.e. genuinely concurrent rather than serialised, with no bend. Zero rate-limit events at any N. N=8 is the highest concurrency validated; larger fan-outs are unmeasured, which is what `orchestration.md` must say rather than implying a ceiling was found. |
| V-13 | **PASS (blocker cleared)** | `git worktree add --detach <project>/.codex-runs/<id>/wt <sha>` works and the main tree's `git status --porcelain` stays **empty** — including while the worktree holds a modified tracked file and an untracked one, which is the actual batch scenario. The worktree appears in `git worktree list` as expected. Bonus, unplanned: `git worktree remove` **refuses** a dirty worktree (`fatal: … contains modified or untracked files, use --force`), so D06's "do not discard uncollected results" protection is free rather than something `batch clean` has to implement. |
| V-14 | **PASS** | `AGENTS.md` reaches a run whose cwd is a worktree. The repo's `AGENTS.md → CLAUDE.md` symlink resolves correctly inside a detached worktree, and Codex quoted it verbatim — *"# CLAUDE.md … Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed."* No fallback needed: the batch preamble does **not** have to carry project instructions. Caveat worth one line in the docs — this holds only for a worktree cut from a ref where the file exists; a worktree cut from an older `--base` would lose it silently. |
| V-15 | **PASS — and it answers "no"** | A freshly cut detached worktree has **0 lines** of `git diff HEAD`, so `review --uncommitted` inside one reviews nothing. This is the measured basis for **D35**: worktrees are assigned per member, and `read-only` / `kind: review` members never get one, because the uncommitted changes they exist to look at live only in the caller's tree. |
| V-16 | **PASS** | A timeout SIGINT leaves the thread resumable. `--foreground --timeout 12` recorded `state=interrupted, error="timed out after 12.0s", exit_code=1` at 13.6 s; resuming that `thread_id` returned `completed`, exit 0, the expected message, **the same thread_id**, and `cached_input_tokens=16128/17987` — the pre-timeout turn's context survived rather than a fresh thread being created. **D26's `timed_out` is therefore a recoverable state, documented as resumable, not a failure state.** |
| V-17 | **PASS, resolved after M4a** | `status --group --follow` streams member state changes and always exits on a terminal line — `group.completed` / `group.partial` / `group.still-running` — verified against the real CLI by T2 I13 and used by the T4 sessions. Monitor pairing works as `log --follow`'s does. **But the answer is conditional, and R15 is the part that matters**: pairing with Monitor is correct only when the caller gets another turn. |
| V-18 | **PASS — and it is stronger than expected** | The batch preamble does not merely add facts, it **corrects a confident falsehood**. Same question, same worktree, two runs. Without the preamble: *"it is the shared workspace with the person who started me, so we are looking at the same tree"* — wrong, and asserted rather than hedged. With it: *"it is an isolated Git worktree, **not** the same tree the person who started me is looking at, and three other Codex runs are running in parallel"* — correct, and it propagated N−1 from the stated group size. Cost **113 input tokens** against a ~16 k context. Keep the preamble, and keep it non-optional for batch runs: the failure mode it prevents is fabrication, not omission. |

One incidental measurement, recorded because `orchestration.md` will cite it: the isolated per-invocation input floor on this project is **~16,016 tokens** and it is **stable under parallelism** (median identical at N=1, 2, 4 and 8). That stability is the useful claim. The absolute number is not — R8 below is the standing reminder that this figure moved 2.92× → 1.09× in two weeks, which is why `projected_cost` computes from the registry at runtime (D37) instead of baking a constant.

### Refinements forced by the sweep

Recorded here and applied to `docs/plan/codex-skill-implementation-plan.md`. None of them change a component's design — each strengthens or corrects the *rationale* the design already rests on.

- **R1 — §3.1 is per-turn setting amnesia, not merely escalation.** `resume` inherits *no* per-invocation setting from the thread; it re-derives every one from whatever config is in effect for that invocation. Measured on thread `019f995b`, one thread, three turns:

  | Turn | Invocation | `turn_context.sandbox_policy` | `reasoning_effort` |
  |---|---|---|---|
  | 1 | `exec --ignore-user-config -c sandbox_mode="workspace-write" -c model_reasoning_effort="low"` | `workspace-write` | `low` |
  | 2 | `exec resume --ignore-user-config` (no flags) | **`read-only`** — silent *downgrade* | **`None`** — dropped |
  | 3 | `exec resume --ignore-user-config -c sandbox_mode="workspace-write" -c model_reasoning_effort="high"` | `workspace-write` | `high` |

The escalation direction reproduces too, exactly as the plan recorded it: thread `019f9959` created `read-only`, resumed **with inherited config** and no sandbox flag, got `"sandbox_policy": {"type": "danger-full-access"}` with `permission_profile.file_system: {"type": "disabled"}`, and wrote `escalated_inherit.txt` containing `ESCALATED`.

Which direction you get is decided by the config layer in effect, not by the thread: inherited config on this machine escalates to `danger-full-access`; isolation downgrades to `read-only`. Isolation therefore *masks* the escalation here purely by coincidence — Codex's own built-in `exec` default happens to be `read-only`. Relying on that would be a bug: it depends on a Codex default staying put, it collapses the moment `--inherit-config` is used, and it silently breaks legitimate `workspace-write` work in the other direction. Re-injection from the registry is what makes the sandbox *stable*, and stability is the property worth stating — anti-escalation is one consequence of it.

- **R2 — `turn_context` is the verification channel, not the `<permissions instructions>` text.** Each turn appends a `{"type":"turn_context","payload":{…}}` line to the rollout carrying `sandbox_policy`, `permission_profile`, `model`, `cwd`, `workspace_roots`, and `collaboration_mode.settings.reasoning_effort`. It is structured, one line per turn, and unambiguous — strictly better than grepping a developer message. T2/I4 uses it.

- **R3 — `review` reports zero token usage.** Both V-10 runs ended `{"usage":{"input_tokens":0,"cached_input_tokens":0,"output_tokens":0,"reasoning_output_tokens":0}}` despite doing real work. `result` and `status` must not present that as a real measurement for review runs; report usage as unavailable rather than as zero.

- **R4 — the `SessionEnd` hook should match on the input's `session_id` first.** *(Superseded: the hook was removed in v0.2.0 — D23. Kept because the finding about hook input keys is still true and would matter to anyone building one.)* Plan §5.4 assumed `$CLAUDE_CODE_SESSION_ID` in the hook's environment. The hook *input* carries `session_id` directly (V-05), which is authoritative. The hook matches a recorded run if its `claude_session_id` equals **either** the input's `session_id` or the hook process's `CLAUDE_CODE_SESSION_ID` — either source alone is a single point of failure, and disagreement between them would otherwise mean killing nothing (benign) or everything (not).

- **R5 — measured resume cost curve** (isolated, same machine, `gpt-5.6-sol`), which is the concrete form of plan §3.4:

  | Invocation | Input tokens | Cached |
  |---|---|---|
  | fresh `exec`, trivial prompt | 15,871 | 13,056 |
  | fresh `exec`, trivial prompt, repo has a 2-line `AGENTS.md` | 16,410 | 0 |
  | `resume`, 1 prior turn | 31,780 | 28,160 |
  | `resume`, 2 prior turns | 47,774 | 43,264 |
  | `resume`, after an interrupted 6-command turn | 86,142 | 75,520 |

- **R6 — script path resolution comes from the skill's context header, not from any environment variable.** V-01 answered "no", which invalidates the plan §4 snippet: `${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/skills/codex}` resolves to a path that does not exist under a plugin install. Three mechanisms were tested against a real install:

  | Mechanism | Works? | Evidence |
  |---|---|---|
  | `$CLAUDE_PLUGIN_ROOT` / `$CLAUDE_SKILL_DIR` in Bash | **no** | Both empty with the plugin installed and the skill active |
  | `` !`shell` `` preprocessing in a plugin SKILL.md body | **no** | The backtick expression reaches the model literally, unexpanded |
  | `Base directory for this skill: <dir>` in the skill's context | **yes** | Quoted back verbatim by a headless session from a neutral cwd |

SKILL.md now instructs the model to take the path from that context line and use it literally, double-quoted. Verified end to end: a headless session in **default** permission mode (no `--dangerously-skip-permissions`) ran `python3 "/…/.claude/skills/codex/scripts/codex_bridge.py" doctor` with **no approval prompt**, so B18 holds and the base-directory path and the `allowed-tools` pattern's expansion of `${CLAUDE_PLUGIN_ROOT}` agree.

The load-bearing consequence, written into SKILL.md with its reason: the permission pattern matches the command *text*, so a command built from a shell variable is not covered by it and would prompt on every poll — which is precisely what would make background work unusable.

- **R7 — `plugin.json` must not declare `"hooks"`.** `hooks/hooks.json` is auto-loaded for plugins; declaring it produced `Hook load failed: Duplicate hooks file detected` and the **entire plugin failed to load**, skill included. `validate_harness.py` passed clean throughout — only a real install surfaced it.

- **R8 — the isolation saving is not a stable number; the clean stream is.** The plan's §3.3 headline ("~66% of input tokens") did not reproduce. Same machine, same prompt (`Reply with exactly: OK`), no deliberate config change:

  | When | `--inherit-config` | `--ignore-user-config` | ratio | inherited `error` events |
  |---|---:|---:|---:|---:|
  | design session | 46,238 | 15,863 | 2.92× | 24 |
  | at M9, two weeks later | 17,327 | 15,837 | 1.09× | 8 |

Measured three consecutive times at M9 with identical results, so this is not noise. The isolated floor is stable to 26 tokens; what moved is how much of the user's config actually *loads* — an MCP server that fails to start contributes nothing to the prompt.

Consequences applied: SKILL.md and `environment.md` no longer quote a ratio as though it were a property, and say to measure it if it matters to a decision. **I7 was rewritten** to assert what the wrapper is actually responsible for — that `--ignore-user-config` reaches the argv and has an observable effect (0 config-error events isolated vs 8 inherited, and isolation never costing more) — instead of a token threshold, which tested the user's Codex configuration rather than this code and would fail for reasons no code change could fix.

- **R9 — the prompt must be preceded by `--`.** Found by I8 failing. `codex exec`'s `-i/--image <FILE>...` takes **multiple** values, so clap greedily consumed the following positional: the prompt became a second image path, Codex found no prompt, fell back to stdin (`/dev/null`) and exited having done nothing, with `state: failed` and no events. `exec resume`'s `-i` is single-valued, so only `exec` had it. `--` also fixes a second latent failure — a prompt beginning with `-` is rejected outright as an unknown flag (Codex's own error text suggests `--`). Now emitted unconditionally before the prompt on all three subcommands, verified against the real CLI on `exec` and `resume`.

The T1 fake `codex` had not caught this because it did not parse argv the way clap does. It now models greedy `-i` consumption and the `--` terminator and **exits non-zero when option parsing ate the prompt** — reverting the fix makes three T1 tests fail, confirming the gap is closed rather than merely patched.

### T2 — real Codex integration

Run at M9 against `codex-cli 0.144.1`, throwaway git repo, **8/8 passing** in 88 s.

| ID | Verdict | Evidence |
|---|---|---|
| I1 | PASS | Background start captured `thread_id` immediately; `events.jsonl` grew; `result` returned the exact sentinel; usage 15,911 input tokens |
| I2 | PASS | Interrupted mid-run, resumed with a correction: **same `thread_id`**, new `run_id`, rollout grew 15 → 27 lines, corrected answer returned |
| I3 | PASS | Two parallel runs got distinct threads **and distinct process groups**; stopping one left the other to complete |
| I4 | PASS | **The regression, against the real CLI.** `read-only` thread resumed: rollout `turn_context` reads `['read-only', 'read-only']`, the write was refused, and the resume argv contains `sandbox_mode="read-only"` |
| I5 | PASS | `--output-schema` returned `{'language': 'Python', 'confident': True}`, parsed and shape-checked |
| I6 | PASS | `review --uncommitted` over a deliberately unsafe diff produced 642 chars of findings; usage correctly reported `null` with the "unavailable, not free" note |
| I7 | PASS (rewritten — see R8) | isolated 15,908 / 0 error events vs inherited 17,398 / 8; `--ignore-user-config` present in one argv and absent from the other |
| I8 | PASS (after R9) | Image attached via `-i`; model replied `Crimson` to a generated crimson PNG |

### T4 — headless e2e

Five scenarios, run at M9 as real headless `claude -p` sessions via `run_e2e.py` against the **plugin-installed** skill (not a symlink), in a shared scratch repo so E4 could resume the thread E1 created. Composed on the spot per `e2e-testing.md` and graded here with cited transcript evidence; no fixed e2e workflow file was created. **5/5 PASS.**

`e2e-testing.md`'s standing caveat about headless auth does not apply here — V-09 confirmed it works in this environment, and all five scenarios completed against a real, authenticated `claude`.

| ID | Prompt (Korean) | Verdict | Cited evidence |
|---|---|---|---|
| E1 | *"이건 코덱스한테 시켜줘: … total() 함수가 …"* | **PASS** | `line 15: Skill(skill='codex:codex')`. `line 47` runs `codex_bridge.py start --sandbox read-only --label pricing-order --cwd …`. `line 71` polls with `log --follow --level compact`. Final response reports `run 20260725-232834-pricing-order-6170`. Registry confirms thread `019f99ad-878a-…`, `state=completed`. |
| E2 | *"GPT한테 이 diff 검토받아줘."* | **PASS** | `line 35: Skill(skill='codex:codex')`. `line 88` uses the **review path**: `review --sandbox read-only --label pricing-diff --uncommitted`, followed by `log --follow`, `status`, `result`. Not surface compliance — a bug deliberately planted in the diff (tax applied to the pre-discount subtotal) was found and explained with a worked example, `(100-20)*1.1 = 88` vs `100*1.1-20 = 90`. |
| E3 | **near-miss** — *"lib/discount.py 의 tier_discount 함수 좀 리뷰해줘."* (no Codex/GPT mention) | **PASS** | The correct evidence is an absence: **`Skill invocations: 0`**. Claude reviewed it itself with three `Read` calls and one `Bash`, and found a real off-by-one (`> 1000` excludes exactly 1000). The description's boundary language held — "리뷰해줘" alone did not steal the trigger from plain judgment. |
| E4 | *"아까 그 코덱스 세션 이어서 …"* | **PASS** | `line 19: Skill(skill='codex:codex')`. `line 56` searches with `status --all --include-external`. `line 128` runs `resume 20260725-232834-pricing-order-6170 --foreground --timeout 240`. Registry: the new run carries `parent_run_id=…-6170` and **the same `thread_id` 019f99ad-878a-…**, and its recorded argv is `codex exec resume 019f99ad-878a-… --ignore-user-config -c sandbox_mode="read-only" …` — the sandbox re-injection observed firing in an unscripted session rather than in a test. |
| E5 | *"코덱스에 긴 작업 맡기고, 그동안 README 정리해줘."* | **PASS** | `line 25: Skill(...)`. `line 113` starts in the background with `--sandbox workspace-write` — note it chose `read-only` for E1's explain task and `workspace-write` here, so the judgment differentiates. Unrelated work is genuinely interleaved (`Read`×3 then `Write` on README) before `status` (line 212), `log --follow` (236) and `result` (303). At line 331 it re-ran `pytest` itself instead of trusting Codex's report. **Artifacts verified on disk, not from the transcript:** README rewritten to 82 real lines, `tests/` contains 143 lines across two files, `pytest` reports `30 passed`, and `git status` shows `lib/` untouched. |

This also satisfies the "fresh session, plugin-installed, Korean natural-language prompt triggers the skill and a real Codex run appears" check: E1, E2, E4 and E5 are each exactly that.

Two observations worth carrying forward rather than burying:

- The model reached for `doctor` unprompted in E2 (`line 66`) before running the review. The skill points at `doctor` for "something is wrong"; it is apparently also read as a sensible preflight, which is harmless and arguably right.
- No scenario ever used `show --item`, because no scenario needed a specific command's full output. That is the intended shape — the escape hatch stayed shut — but it means `show` is exercised only by T1 and by hand, not by e2e.

### T1 — unit tests

**263 tests, passing**, ~132 s (239 at v0.2.0). The suite drives real subprocesses with real timeouts, so it is load-sensitive: run under competition from live Codex runs it took 580 s and produced five spurious errors, twice. That is the practice note about not running tiers concurrently, arriving as a measurement. Includes the sandbox-drift regression on the recorded resume argv, the `compact`-never-leaks-output assertions against a real 22 KB `cat`, cursor exactness, parallel-stop isolation, the Korean/NFD path case, the four `doctor` failure modes, nine deliberate fault injections, seven adversarial `overlaps` property cases, multiprocess registry-concurrency reproduction, per-member worktree assignment against real git, and the `--resume-from` pairing refusals. The 16 hook tests are gone with the hook (v0.2.0).

**Results:** M0 verification sweep complete; V-01 and V-07 answered at M8 against a real local install. The V-03 blocker is cleared and re-confirmed against the real CLI at I4. Four plan corrections came out of building and testing (R6, R7, R8, R9). No component's design changed; §4's path-resolution snippet and §3.3's headline number were both wrong and are replaced.

## Change history

| Date | Mode | Summary |
|---|---|---|
| 2026-08-03 | improve | Worked through the eleven open items in `docs/plan/260802/README.md`, and added **T5**, a new tier that walks the option surface against the real CLI rather than checking that a test names each flag (R17's limit). Two of the plan's own premises were wrong and are corrected: APFS is normalisation-*preserving*, not NFD-folding like HFS+, so NFC and NFD are two true names for one file at once — which makes `overlaps` miss rather than merely mismatch; and Linux is out of scope by the user's decision, not an unmeasured gap. **Seven defects**, every one reachable only by running something: a batch killed mid-spawn reporting `completed`; the same batch leaking a checkout no group could clean, whose first fix did not work and whose regression test passed six times in ten; `batch clean --force` unable to lift a git lock; a corrupt `meta.json` disappearing from every listing while its bytes were still counted; `status --run --follow` silently ignored, and `--run` with `--group` silently dropping the group; the `review` surface enforcing its rules on one caller and not the other; and the documented `settings.json` rule for symlink installs never matching, because `$HOME` is not expanded in a permission rule and `Skill(codex)` needs its own entry. Recorded as **R18–R21**. Registry cost measured at 2000 runs holding 48 MB — worst command 0.63 s, linear, group views flat — so no cache and no cap (`docs/measurements/batch-cost.md`). B18 re-verified for the v0.2.0 surface, against a positive control, after a first pass in `auto` mode proved nothing. Both near-misses pass, including a harder one where "GPT" appears as subject matter. Codex was driven throughout as the thing under test: it found the checkout leak, found the `--run`/`--group` hole in a commit written an hour earlier, and wrote two of the tests that shipped. T1 239 → 267 tests. A second adversarial round over this round's own fixes then found two more high-severity defects, both created by those fixes (R22, R23), and four documentation claims that had gone stale within the same session — so the two-consecutive-clean-rounds bar is still not met. |
| 2026-08-02 | extend | Shipped v0.2.0: batch orchestration. Eight new behaviours (B22–B29) — `batch start` with per-member git worktrees, `status/result/stop --group`, `batch clean`, `--resume-from`, the batch preamble, and a background `--timeout` with its own terminal state. Four decisions were added to the plan's D01–D33 before implementation began, each closing a gap that would otherwise have been guessed at: **D34** drops `--max-concurrent` (a queued run has no supervisor, so `reap()` would brand it `orphaned` within 30 s — and V-11 then measured no contention at N=8, so the `--stagger` fallback D34 made conditional never fired); **D35** assigns worktrees per member rather than per batch, on V-15's measurement that a fresh worktree has zero uncommitted changes; **D36** makes group names single-use and records membership in a manifest, because `--resume-from` pairs positionally and F15 makes same-second same-label starts the normal case; **D37** computes `projected_cost` from the registry at runtime rather than from a constant, because R8 is the record of a design-time constant being 2.7× wrong two weeks later. Every milestone was reviewed by three adversarial agents on distinct lenses before the next one started; that found 13 defects across M4a–M4c, including a `batch clean` that could delete a running run's working directory, a worktree leak that `batch clean` structurally could not reach while reporting the group fully cleaned, and a preamble paragraph that asserted something unobservable — the exact failure the paragraph exists to prevent. The batch subsystem then moved out of the entrypoint into `_batch.py` over a new `_run.py` (`codex_bridge.py` 1801 → 798 lines, no behaviour change, same tests). Seven places the plan was wrong are recorded as **R10–R16**, all found by running the thing rather than reading it. T1 124 → 233 tests; T2 15/15 against `codex-cli 0.146.0`; T4 four headless scenarios. Tagged v0.2.0. |
| 2026-08-01 | extend + improve (plan only) | Audited the shipped skill across five dimensions with an adversarial verification pass per finding: **45 raised, 21 confirmed, 24 refuted** (no blockers; highest confirmed severity is major). Record: `docs/plan/260801/audit-findings.md`. Then interviewed across seven AskUserQuestion rounds and planned v0.2.0 — batch/group primitives so several Codex runs launch, are watched, and are collected as one phase, with git-worktree isolation for concurrent writers and `--resume-from` for phase-to-phase thread continuation. Claude's main thread composes the phases; the bridge only ever sees one batch. 33 decisions recorded as D01–D33 in `docs/plan/260801/implementation-plan.md`. **Two removals are breaking:** the `SessionEnd` cleanup hook (B17) and `--detach` are dropped entirely on the user's principle that the skill holds capability while cost policy stays the user's — *"이 훅은 내 비용 관리를 위한건데, 이거까지 스킬에 위임하고 싶진 않아. 스킬은 역량에 충실하면 좋겠어."* `stop --all-mine` is replaced by `--run`/`--group`/`--all`. Nothing generated yet; B17 stays listed until M2 deletes it, and eight new rows (B22–B29) are specified in the plan §8.4 rather than added here, so an audit on re-entry should still match the shipped v0.1.0 tree. |
| 2026-07-25 | generate | Implemented and released v0.1.0. All 21 behaviours validated. V-01…V-10 swept (V-03 blocker cleared; V-01 answered "no" and forced R6). T1 124 tests, T2 8/8, T3 four workloads, T4 5/5 including the near-miss. Nine plan corrections recorded as R1–R9; no component's design changed, but plan §3.1, §3.3 and §4 were each wrong and are replaced. |
| 2026-07-25 | new (plan only) | Interviewed across five AskUserQuestion rounds; verified the Codex environment empirically (including a reproduced sandbox-escalation defect); recorded 20 decisions; wrote `docs/plan/codex-skill-implementation-plan.md` and this spec. All inventory rows are at `approved` — no files generated yet, so an audit on re-entry should report every row as awaiting generation. |
