# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-08-04

A verification round, and what it found. No new capability: this version exists because the previous one was measured properly for the first time — every user-facing flag driven against the real Codex CLI, deliberate faults injected, and four adversarial review rounds. Nineteen defects came out of that, and their common shape is the reason to upgrade: almost all of them were **silent**. The command succeeded, the JSON parsed, and the answer was wrong.

**Read the Changed section before upgrading.** Five things that used to be accepted are now refused, and one JSON field was renamed.

### Security

- **`--config` could override the sandbox this skill exists to enforce.** `codex`'s `-c` is last-value-wins for a repeated key, and the caller's raw `--config` entries were emitted *after* the enforced `-c sandbox_mode=`. So `start --sandbox read-only --config 'sandbox_mode="danger-full-access"'` ran fully privileged while `status` went on reporting `read-only` — and because `extra_config` is inherited by every resume, it did so for the rest of the thread. Measured against the real binary: the same file write is refused one way and succeeds the other. Two guards now — the four keys this wrapper sets are refused outright with the flag that owns each one named, and the enforced settings are emitted last, so a key nobody thought to reserve still cannot outrank an invariant.

### Changed

- **Refused where previously accepted.** Each of these used to succeed and silently do something other than what was asked:
  - `--config` naming `sandbox_mode`, `service_tier`, `model_reasoning_effort` or `model` — use `--sandbox`, `--priority`/`--no-priority`, `--effort`, `--model`.
  - `status --follow` without `--group`. `--follow` only ever meant `--group --follow`; elsewhere it returned one snapshot and exited, which a caller reads as "I waited for this". To watch one run, use `log --run <id> --follow`.
  - `--run` together with `--group`, on `status`, `stop` **and** `result`. They are different questions, and passing both silently dropped one — `stop --group G --run L` left every member of G running and reported success.
  - `log --since <n>` where *n* is not an event boundary. Such a cursor is one fed back from a different run; accepting it destroyed the event straddling that offset and said nothing.
  - A `review` task in a `--tasks-file` whose `review` object combines selectors, sets `title` without `commit`, or holds an unknown key. The command-line `review` refused all three; the batch path enforced none, so a `title` was dropped without a word.
- **`projected_cost` fields renamed** from `input_floor_per_run` / `input_floor_total` to `input_median_per_run` / `input_median_total`. It was never a floor: checked against the registry it is computed from, 6 of 11 real runs came in *below* it, which is what a median does. Anything parsing those names must be updated.
- **`doctor` no longer blames every `codex login status` failure on authentication.** A malformed `config.toml` makes that command fail before it looks at auth at all — and `codex login`, the fix both `doctor` and the troubleshooting docs pointed at, fails identically, forever. It now separates "could not run" from "not logged in", and quotes what it saw.
- **`doctor` only counts worktrees this skill cut.** A checkout the user made themselves was reported as "from batch runs, checked out under `.codex-runs`" — false twice over, and `batch clean` cannot touch it either.
- **`doctor` and `concurrent_writers` now agree on what "the same directory" means.** `doctor` compared exact paths, so two live writers in `/p` and `/p/sub` landed in two groups of one and it warned about neither, while the check at run creation had already seen them.
- **`result --group` no longer reports a review member's zero usage as a real zero.** Review turns report all-zero usage after doing real work; the single-run surfaces have carried "unavailable, not free" since v0.1.0. The group total was silently undercounting any batch that mixed a reviewer with writers, which is the documented normal pattern. Such members are now named in `usage_unmeasured` and left out of `totals`.
- **`status` and `doctor` report `runs_unreadable`.** A run whose `meta.json` will not parse used to vanish from every listing while `doctor` went on counting its bytes.

### Fixed

- **A batch killed while spawning reported `group_state: completed`.** The manifest recorded members as the loop reached them and nothing recorded how many had been asked for, so "asked for three, given two" was byte-identical to a group that only ever wanted two. `claim_group` now records `requested` before the first spawn — the last moment that fact still exists.
- **A batch killed while spawning could leave a checkout no group could clean.** `create_run` now publishes the run before cutting its worktree and again immediately after; `batch clean` resolves membership through the registry as well as the manifest; and where a path is still unrecorded it falls back to `<run_dir>/wt`, which is where `create_run` always puts it.
- **`batch clean --force` did not force.** `git worktree add` holds a lock reading `initializing`, a batch killed inside it leaves the worktree locked forever, and `git worktree remove --force` refuses a locked tree — it wants `-f -f`. `batch clean` had been printing that it "lifted every protection at once" while a checkout survived it.
- **`batch clean` could delete the worktree of a run whose `meta.json` was unreadable**, without `--force`, even when that run was last recorded `running`. Unknown is not terminal.
- **Two simultaneous `resume` calls on one thread both started a turn**, leaving two Codex processes appending to one rollout file. The guard now runs under a per-thread lock spanning the check and the new run's publication — including for a thread this registry has never seen, which is the case the feature leads with and which the first attempt at this fix missed.
- **A group name released mid-spawn could be re-claimed under the first batch's feet**, after which that batch's `write_members` merged its members into a stranger's manifest. Each claim now carries an epoch, and a writer that no longer owns the file says so and names what it had already started.
- **A foreground run without `--timeout` recorded the caller's process group**, so `stop --run` on it would have signalled the caller.
- **`overlaps` was never tested against the shapes it exists for.** Seven cases added: a submodule (whose `--git-common-dir` is `<parent>/.git/modules/<name>`), two worktrees of a bare repository, a phase-2 member inheriting its predecessor's tree, a newline in a path, and Unicode — APFS *preserves* normalisation rather than folding it, so NFC and NFD are two true names for one file at the same time, and a run reporting the other form was silently missing the overlap.

### Documentation

- **The `settings.json` rule this project documented for symlink installs never worked.** `$HOME` is not expanded in a permission rule — `${CLAUDE_PLUGIN_ROOT}` is, which is why a plugin install needs no settings at all — and `Skill(codex)` needs its own entry or the skill cannot load and the bridge rule is never reached. Both corrected in the README, verified against a positive control in the default permission mode.
- **A bridge command must be written on one line.** The permission pattern matches command *text*, so a command broken with a trailing backslash does not match. This bites exactly where it is least convenient: `batch start` with several `--task` flags is long, and long commands invite continuations. Now a gotcha in `SKILL.md`.
- **`docs/measurements/batch-cost.md`** — new. Registry cost at 2000 runs (worst command 0.63 s, linear, group views flat — so no cache and no cap), concurrency at N=12/16/24 (no contention, `--stagger` stays out), what `result --group` costs (about 1.75× fetching each member separately — it buys `overlaps` and one round trip, not cheapness), and what `projected_cost` actually predicts.

## [0.2.0] — 2026-08-02

Batch orchestration. Several Codex runs can now be started, watched, collected and cleaned up as one named thing, with a git worktree per writer so concurrent runs cannot edit each other's files mid-edit.

### Added

- **`batch start --group <name>`** — N runs as one addressable group, from repeated `--task` flags or a `--tasks-file` JSONL where each line may override any group-level option. Group names are single-use per project: reusing one would make "the members of this group" ambiguous, and `--resume-from` pairs against exactly that list. One member failing to spawn never takes the batch with it.
- **A git worktree per writing member.** Assigned when two or more members can write, at `.codex-runs/<run_id>/wt`, detached at `HEAD` or `--base <ref>`. Per member rather than per batch: `read-only` and `kind: review` members stay in the caller's tree, because a freshly cut worktree has zero uncommitted changes and a reviewer inside one would be reviewing nothing (measured). The main tree's `git status` stays clean throughout.
- **`--group` selectors on `status`, `result` and `stop`.** `status --group --follow` streams member state changes and always ends on a terminal line, so a group can never end in silence. `result --group` returns each member's message under a byte cap plus `overlaps` — the paths more than one member wrote, keyed by repository so two checkouts of different projects never collide.
- **`batch start --resume-from <group>`** — task *i* continues member *i* of an earlier group, in its recorded start order, keeping that thread and the directory it lives in. Every ambiguity is a refusal rather than a guess: a count mismatch, a member with no thread to continue, a live member, a task whose `kind` contradicts its target.
- **`batch clean --group <name>`** — the only cleanup path; there is no automatic removal and no hook. Refuses without `--force` when the group has live members, when another run is still working inside one of the worktrees, when a group derived from this one exists, or when git itself declines to discard uncommitted changes. `--force` lifts all four at once and says in its reply what it overrode.
- **`--timeout <sec>` now works in the background**, with a terminal state of its own. `timed_out` is distinguished from `interrupted` (you stopped it) and `failed` (Codex did) because only the third is answered by raising the timeout; the thread stays resumable across it with the pre-timeout turn's context intact (measured).
- **A batch preamble** telling each member facts it cannot observe from inside a single non-interactive turn: the group it belongs to, that other runs may be executing alongside it, and — when isolated — its worktree's path, base commit, and how many uncommitted files exist in the caller's tree that it does not have. Measured: without it a run asserted *"we are looking at the same tree"*, wrong and unhedged. 113 input tokens.
- **`concurrent_writers`** on `start` and `resume`, naming other live runs that can write to the same directory, and the same check registry-wide in `doctor`. Reported, never refused. `resume` has no worktree option, so continuing several writers at once is unisolatable by construction and this is the only thing that can say so.
- **Group discoverability.** `status` lists the project's `groups`, and every run row carries its `group` and `worktree` — which is what lets a later session address a batch it did not start.
- **`references/orchestration.md`** and **[Orchestration](docs/wiki/Orchestration.md)** — the mechanics and the traps, deliberately without a catalogue of phase patterns.

### Changed

- **`codex_bridge.py` split into modules.** The entrypoint holds the CLI surface and one handler per subcommand; `_run.py` builds and describes a run, `_batch.py` owns the group subsystem, `_worktree.py` the worktrees. Behaviour unchanged, verified by the suite passing across the move.
- **The run registry is safe under concurrent writers.** Per-writer temp filenames, `flock` around read-modify-write, and compare-and-set for `reap`. The defect was reproduced first: 152 of 240 concurrent writes raised `FileNotFoundError`, and a reaper could overwrite a finished run's recorded outcome.
- **`status`'s default view** keeps every non-terminal run plus a tail of recent ones rather than a plain tail, so a long-running old run can no longer fall off the list. `--group` never truncates.
- **A foreground `--timeout`** now records `timed_out` rather than `interrupted`, so one cause no longer has two names.

### Removed

**Both removals are breaking.** They follow from one principle the user set: the skill holds capability, and cost policy stays theirs.

- **The `SessionEnd` cleanup hook**, and with it `--detach`. Background runs are no longer stopped when a Claude session ends. If you relied on this, `status --all` finds runs from earlier sessions and `stop --run <id>` or `stop --all` ends them; `doctor` now reports the registry's size, the project's groups and any residual worktrees so the accumulation is visible rather than silent.
- **`stop --all-mine`**, replaced by `stop --run <id>… | --group <name> | --all`. Scope is now whatever is visible in the registry rather than an invisible session boundary a subagent's runs may not even share.

### Fixed

- `resume --last` picked the newest run with no filter, so a read-only caller could inherit another run's label and its `danger-full-access` sandbox. It now requires an unambiguous target and echoes which run it resolved to.
- Two turns could run concurrently on one thread, racing on the same rollout file, with exit 0 and no warning. Refused unless `--force`.
- `--since` past the end of the events file printed nothing, exited 0, and echoed the bad cursor back, so a poll loop stuck there forever looked identical to "no new events".
- `turn.failed` was parsed and never surfaced: a failed run showed a null message and the reason needed a second call.
- Thread lookup missed Korean paths stored NFD, and scanned a bounded prefix of the thread database rather than querying it.
- `result --group` cut messages by character and reported by byte, so a 3,000-character Korean message that had not been truncated reported itself truncated.

### Known limitations

- Concurrency was measured up to **8 simultaneous runs** with no thread-database contention, no thread-id collisions and flat wall-clock from N=2 to N=8. Above 8 is unmeasured — that is a range that was not tested, not a ceiling that was found.
- **`overlaps` is the intersection only** (paths more than one member wrote), not a per-run file list. Under worktree isolation an overlap is a merge conflict ahead rather than damage already done; without worktrees it is damage already done.
- **Collecting a batch's results is a separate step.** `batch start` returns when the members are spawned and the group finishing is not the results being collected — `result --group` is its own call. Ending a turn on "I'll report when it finishes" delivers nothing.
- Measured against `codex-cli 0.146.0`. The earlier tiers were measured on `0.144.1`; the thread database's filename is version-stamped, so a Codex upgrade may still degrade `--include-external` and a registry-less `resume --last`, which `doctor` reports rather than failing on.

## [0.1.0] — 2026-07-25

First release. A Claude Code plugin containing one skill (`codex`) that drives the OpenAI Codex CLI as a managed subagent.

### Added

- **`codex_bridge.py`** — a Python 3.10+ stdlib-only CLI with nine subcommands: `start`, `resume`, `review`, `status`, `log`, `show`, `stop`, `result`, `doctor`. Every command prints one line of JSON except `log`, which prints compact text plus an incremental cursor.
- **Sandbox stability across turns.** Every per-invocation setting — sandbox, model, reasoning effort, isolation, working directory — is recorded at run creation and re-asserted on every subsequent invocation as `-c sandbox_mode=` and friends. This closes a measured defect in the Codex CLI: `codex exec resume` has no `-s` flag, so an unre-asserted resume re-derives the sandbox from whatever config layer is in effect — escalating a `read-only` thread to `danger-full-access` under the user's config, or silently downgrading a `workspace-write` thread to `read-only` under isolation.
- **Run registry** at `<project>/.codex-runs/`, self-ignoring via a `.gitignore` containing `*` so it never touches the user's own git configuration.
- **Background-first execution.** Runs are supervised by a process spawned into its own session, so supervisor and Codex share one process group. `stop` signals exactly one run's group and never matches processes by name, which is what makes concurrent runs safe.
- **Filtered event log** with four levels. The default, `compact`, was chosen from a measurement across four real workloads recorded in `docs/measurements/filter-calibration.md`, not by assumption.
- **`show --item`** as the single, explicit escape hatch to a command's full output, with loud truncation above a byte cap.
- **`SessionEnd` hook** that stops this session's non-detached background runs. Standalone by design so it fits the event's 1.5 s timeout; the no-runs-dir path measures 20–30 ms.
- **`doctor`**, which separates blockers (exit 2) from warnings and reports the resolved `CODEX_HOME`, auth state, the config-file sandbox, the resolved script path, and whether the project has an `AGENTS.md`.
- Structured output via `--output-schema`, image attachment via `-i`, and a `review` path over `codex exec review`'s distinct flag surface.
- 124 unit tests against a fake `codex` shim replaying event streams captured from real runs, including a dedicated regression test asserting that a resumed run's recorded argv carries the sandbox it was created with.

### Known limitations

- **No mid-turn steering.** `codex exec` is a single non-interactive turn with no input channel once running; intervention is stop-then-resume. `codex app-server` is the one plausible route to real steering and is recorded as unexplored, not impossible.
- **`review` runs report zero token usage.** Measured on every review run. `status` and `result` report `null` rather than presenting zero as a measurement.
- **Exit code is an imperfect proxy** for "this command's output matters" at the `normal` filter level. Search and lint tools routinely exit non-zero without failing. The alternatives are worse; the limitation is documented rather than hidden.
- **`codex cloud` and `codex mcp-server`/`app-server` are out of scope**, both documented upstream as subject to change without notice.
- Measurements were taken against `codex-cli 0.144.1` on a single machine. The thread database filename is version-stamped, so a Codex upgrade may degrade `--include-external` and a registry-less `resume --last`; `doctor` reports that case rather than failing.

[0.3.0]: https://github.com/tjdwls101010/Codex-in-Claude/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/tjdwls101010/Codex-in-Claude/releases/tag/v0.2.0
[0.1.0]: https://github.com/tjdwls101010/Codex-in-Claude/releases/tag/v0.1.0
