# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.0]: https://github.com/tjdwls101010/Codex-in-Claude/releases/tag/v0.2.0
[0.1.0]: https://github.com/tjdwls101010/Codex-in-Claude/releases/tag/v0.1.0
