# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- 120 unit tests against a fake `codex` shim replaying event streams captured from real runs, including a dedicated regression test asserting that a resumed run's recorded argv carries the sandbox it was created with.

### Known limitations

- **No mid-turn steering.** `codex exec` is a single non-interactive turn with no input channel once running; intervention is stop-then-resume. `codex app-server` is the one plausible route to real steering and is recorded as unexplored, not impossible.
- **`review` runs report zero token usage.** Measured on every review run. `status` and `result` report `null` rather than presenting zero as a measurement.
- **Exit code is an imperfect proxy** for "this command's output matters" at the `normal` filter level. Search and lint tools routinely exit non-zero without failing. The alternatives are worse; the limitation is documented rather than hidden.
- **`codex cloud` and `codex mcp-server`/`app-server` are out of scope**, both documented upstream as subject to change without notice.
- Measurements were taken against `codex-cli 0.144.1` on a single machine. The thread database filename is version-stamped, so a Codex upgrade may degrade `--include-external` and a registry-less `resume --last`; `doctor` reports that case rather than failing.

[0.1.0]: https://github.com/tjdwls101010/Codex-in-Claude/releases/tag/v0.1.0
