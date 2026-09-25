# Contributing to Codex in Claude

Thanks for considering a contribution. This project is a Claude Code plugin — a single skill (`codex`) backed by a Python standard-library CLI (`scripts/cli_codex.py`) — so most contributions fall into a few clear categories: bug fixes in the CLI, new Codex CLI surface area, documentation, and test coverage.

## 1. Scope

Welcome:

- Bug fixes, especially anything touching sandbox handling, process-group signaling, or the run registry — this project exists specifically to get those right.
- New `codex` CLI flags or subcommands surfaced through the bridge.
- Documentation and reference material improvements.
- New or improved tests, at any of the tiers below.

Please open an issue or discussion before starting on:

- New runtime dependencies — the bridge is deliberately Python-standard-library-only (no `jq`, no third-party packages). A dependency addition needs a strong reason.
- Anything in the non-goals (`codex cloud`, `codex mcp-server`/`app-server` integration, true mid-turn steering) — these were left out deliberately, not overlooked.

## 2. Ways to Contribute

- **Bug reports** — open a GitHub issue with the command you ran, what you expected, and what happened. Include `doctor` output when the issue is environment-related.
- **Pull requests** — for anything beyond a trivial fix, open an issue first so the approach can be agreed before you invest time in it.
- **Documentation** — improvements to this repo's README, the skill's `SKILL.md`, or a command's `--help` are welcome even without a code change attached. `--help` is the one reference for flags, defaults and output shapes; `SKILL.md` carries only what no single `--help` can say.

## 3. Development Setup

Clone the repository and make sure the requirements in the [README](README.md#3-quick-start) are met (Python 3.10+, and the [Codex CLI](https://developers.openai.com/codex/cli) authenticated if you'll run the integration tier). There's no build or install step — `cli_codex.py` runs directly. Under it, `cli/` is the command surface, `core/` the registry, settings and run supervision, and `codex/` the formats the Codex CLI owns (argv, config, model catalog, events).

To develop against a local checkout instead of a plugin install, symlink the skill:

```bash
ln -s /path/to/Codex-in-Claude/.claude/skills/codex ~/.claude/skills/codex
```

## 4. Tests & Checks

**The suite — free, no network or API calls:**

```bash
python3 -m unittest discover -s tests
```

It drives the real `cli_codex.py` as a subprocess, with a fake `codex` executable (`tests/support/fake_codex/codex`) first on `PATH` that replays recorded event streams from `tests/support/fixtures/`. Process spawning, process-group signalling, argv composition and the on-disk registry are all tested for real; only the model is faked. A few tests call pure functions directly (settings precedence, argv, event formatting), race several real processes against one registry, or check the package layering and every `--help`. Always run it before opening a PR.

**S5 — the real Codex CLI, consumes tokens:**

```bash
CODEX_BRIDGE_REAL=1 python3 tests/smoke_real_codex.py
```

Starts, follows, collects and resumes a real thread in a throwaway repository and a `CODEX_HOME` of its own, then reads the rollout Codex wrote to check that the resumed turn ran under the sandbox the thread started with. Run it when your change touches how the CLI invokes `codex` (argv, sandbox/model/effort handling, process lifecycle).

**S6 — real headless Claude sessions with the skill, consumes tokens:**

```bash
python3 tests/e2e/run_e2e.py --scenario 1 --variant draft --out /tmp/e2e
```

Runs one scenario from `tests/e2e/scenarios.md` in a session that loads only this skill, either as written or as a control without its judgement text, and saves a digest of every tool call. Run it when you change `SKILL.md`, and compare the variants against the scenario's pass criteria.

**Plugin validation:**

```bash
claude plugin validate --strict .claude/skills
```

## 5. Making a Change

1. Open an issue first for anything non-trivial, so the approach is agreed before you invest time in it.
2. Branch from `main`.
3. Make the change, keeping it scoped to what the issue describes — this codebase favors small, direct modules over abstraction, so prefer matching that over introducing new layers.
4. Run the suite (and S5 if your change touches how `codex` is invoked, S6 if it changes `SKILL.md`) before opening a PR.
5. Open a pull request describing what changed and why, referencing the issue it addresses.

## 6. Code Style

There's no configured linter or formatter in this repository — match the style of the file you're editing (the existing modules are consistent stdlib Python with descriptive docstrings explaining *why*, not just *what*).

## 7. Reporting Bugs / Requesting Features

Use [GitHub Issues](https://github.com/tjdwls101010/Codex-in-Claude/issues). There are no issue templates yet, so just include: the command you ran, the flags, expected vs. actual behavior, and `doctor` output if it might be environment-specific. For security-sensitive bugs (sandbox escalation, permission issues), see [SECURITY.md](SECURITY.md) instead of filing a public issue.

## 8. Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you're expected to uphold it.
