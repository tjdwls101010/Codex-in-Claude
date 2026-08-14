# Contributing to Codex in Claude

Thanks for considering a contribution. This project is a Claude Code plugin — a single skill (`codex`) backed by a Python standard-library CLI (`codex_bridge.py`) — so most contributions fall into a few clear categories: bug fixes in the bridge script, new Codex CLI surface area, documentation, and test coverage.

## 1. Scope

Welcome:

- Bug fixes, especially anything touching sandbox handling, process-group signaling, or the run registry — this project exists specifically to get those right.
- New `codex` CLI flags or subcommands surfaced through the bridge.
- Documentation and reference material improvements.
- New or improved tests, at any of the tiers below.

Please open an issue or discussion before starting on:

- New runtime dependencies — the bridge is deliberately Python-standard-library-only (no `jq`, no third-party packages). A dependency addition needs a strong reason.
- Anything in the [v1 non-goals](docs/wiki/Overview.md#5-non-goals) (`codex cloud`, `codex mcp-server`/`app-server` integration, true mid-turn steering) — these were left out deliberately, not overlooked.

## 2. Ways to Contribute

- **Bug reports** — open a GitHub issue with the command you ran, what you expected, and what happened. Include `doctor` output when the issue is environment-related.
- **Pull requests** — for anything beyond a trivial fix, open an issue first so the approach can be agreed before you invest time in it.
- **Documentation** — improvements to this repo's README, `docs/wiki/`, or the skill's own `SKILL.md`/`references/` are welcome even without a code change attached.

## 3. Development Setup

Clone the repository and make sure the requirements in the [README](README.md#3-quick-start) are met (Python 3.10+, and the [Codex CLI](https://developers.openai.com/codex/cli) authenticated if you'll run the integration tier). There's no build or install step — `codex_bridge.py` and its helper modules (`_codex.py`, `_events.py`, `_registry.py`, `_util.py`) run directly.

To develop against a local checkout instead of a plugin install, symlink the skill:

```bash
ln -s /path/to/Codex-in-Claude/.claude/skills/codex ~/.claude/skills/codex
```

## 4. Tests & Checks

There are three tiers, run in this order as you make a change:

**T1 — unit tests against a fake `codex`, free, no network or API calls:**

```bash
python3 -m unittest discover -s tests/legacy -p 'test_*.py'
python3 -m unittest discover -s tests/260813 -p 'test_*.py'
python3 -m unittest discover -s tests/260814 -p 'test_*.py'
```

These drive the real `codex_bridge.py` as a subprocess, but with a fake `codex` executable (`tests/legacy/fake_codex/codex`) placed first on `PATH`. The fake replays recorded event streams from `tests/legacy/fixtures/`, so process spawning, process-group signaling, and argv composition are all tested for real — only the Codex model itself is faked. This tier includes the sandbox-drift regression test: it asserts that a resumed run's recorded argv actually re-injects `-c sandbox_mode="..."`, which is the specific defect this project exists to close. Always run this tier before opening a PR — it's fast and requires nothing beyond a Python 3.10+ interpreter.

Both directories are separate `unittest` start dirs rather than one, because neither is a package: `discover -s tests` walks only as far as the first directory without an `__init__.py` and reports the empty result as `NO TESTS RAN` with exit status 0. A suite that can answer "everything passed" by finding nothing is worse than one that fails, so `tests/260813/test_suite_integrity.py` asserts that every discovery command written in this file collects a nonzero number of tests, and that every directory under `tests/` holding `test_*.py` is reachable from one of them.

**T2 — integration tests against the real Codex CLI, consumes tokens:**

```bash
CODEX_SKILL_TEST_INTEGRATION=1 python3 tests/legacy/integration/run_integration.py
```

This spins up a throwaway git repo and runs real `codex` calls through the bridge — background start/resume/stop, parallel runs, `--output-schema`, `review`, and image attachment. It costs real API usage, so it isn't run by default and isn't required for most PRs; run it if your change touches how the bridge invokes `codex` itself (argv composition, sandbox/model/effort handling, process lifecycle). Use `--only <case-id>` to run a single case while iterating.

**Harness validation:**

```bash
python3 ~/.claude/skills/harness-creator/scripts/validate_harness.py --path .
```

Checks the plugin/skill manifests and structure against the conventions a Claude Code harness is expected to follow. Requires the `harness-creator` skill to be installed globally.

## 5. Making a Change

1. Open an issue first for anything non-trivial, so the approach is agreed before you invest time in it.
2. Branch from `main`.
3. Make the change, keeping it scoped to what the issue describes — this codebase favors small, direct modules over abstraction, so prefer matching that over introducing new layers.
4. Run the T1 suite (and T2 if your change touches CLI invocation) before opening a PR.
5. Open a pull request describing what changed and why, referencing the issue it addresses.

## 6. Code Style

There's no configured linter or formatter in this repository — match the style of the file you're editing (the existing modules are consistent stdlib Python with descriptive docstrings explaining *why*, not just *what*).

## 7. Reporting Bugs / Requesting Features

Use [GitHub Issues](https://github.com/tjdwls101010/Codex-in-Claude/issues). There are no issue templates yet, so just include: the command you ran, the flags, expected vs. actual behavior, and `doctor` output if it might be environment-specific. For security-sensitive bugs (sandbox escalation, permission issues), see [SECURITY.md](SECURITY.md) instead of filing a public issue.

## 8. Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you're expected to uphold it.
