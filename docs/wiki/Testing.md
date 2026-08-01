# Testing

The four-tier test strategy behind this project, and how to run the tiers that live in this repository. For anyone verifying a change, or deciding how much testing a contribution needs — see also [CONTRIBUTING.md](../../CONTRIBUTING.md) for the day-to-day commands.

## 1. T1 — Unit Tests Against a Fake Codex

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

**124 tests, passing in about 40 seconds**, requiring no network access and no real Codex CLI. These tests drive the real `codex_bridge.py` as a subprocess — not an in-process mock — with a fake `codex` executable (`tests/fake_codex/codex`) placed first on `PATH`. That fake replays event streams recorded from real runs (`tests/fixtures/*.jsonl`), so everything except the model itself is exercised for real: argument parsing, argv composition, process spawning, process groups, and signal delivery.

This tier includes the single most load-bearing test in the suite: a regression assertion that a resumed run's *recorded argv* actually contains `-c sandbox_mode="read-only"` when its thread was created read-only — the specific defect described in [Sandbox Stability](Sandbox-Stability.md), caught at the argument-composition level before it ever reaches a real Codex process. It also covers Unicode/NFC path handling (Korean paths, spaces), the run registry's self-`.gitignore`ing behavior, cursor-exactness on partial trailing lines, all four filter levels, all four `doctor` failure modes, and 16 tests driving the `SessionEnd` hook against real process groups.

Run this tier before opening any pull request — it's fast, free, and covers most of the codebase's actual logic.

## 2. T2 — Real Codex Integration

```bash
CODEX_SKILL_TEST_INTEGRATION=1 python3 tests/integration/run_integration.py
```

Gated behind an explicit environment variable so it never runs by accident, since it consumes real API usage. Spins up a throwaway git repository and drives the real bridge against the real, authenticated `codex` binary. **8 of 8 cases passing**, in about 88 seconds, verified against `codex-cli 0.144.1`:

| Case | What it verifies |
|---|---|
| I1 | Background start returns a `thread_id`, and `result` returns the expected final message |
| I2 | Stop mid-run, then resume with a correction — same `thread_id`, rollout grows to include it |
| I3 | Two parallel runs get distinct process groups; stopping one doesn't touch the other |
| I4 | **The sandbox regression, against the real CLI** — a `read-only` thread stays `read-only` across a resume, verified via the rollout's `turn_context` |
| I5 | `--output-schema` round-trips valid, schema-shaped JSON |
| I6 | `review --uncommitted` produces real findings; usage is correctly reported as `null`, not zero |
| I7 | Isolation has a measurable effect (config-error event count), without asserting an unstable token ratio |
| I8 | Image attachment via `--image` — the model correctly identifies a synthesized test image |

Use `--only <case-id>` to run a single case while iterating. This tier isn't required for most contributions — run it when a change touches how the bridge invokes `codex` itself.

## 3. T3 — Filter Calibration

```bash
python3 tests/measure_filter_calibration.py --project <repo-with-a-registry>
```

Measures the byte cost of each filter level (`compact`/`normal`/`full`/`raw`) across four real workloads, producing the tables in [Context Discipline & Event Log Levels](Context-Discipline.md) and the raw data in [`docs/measurements/filter-calibration.md`](../measurements/filter-calibration.md). This is what the shipped default (`compact`) is chosen from — not an assumption.

## 4. T4 — Headless End-to-End

Unlike the tiers above, T4 isn't a file committed in this repository. It's run using `run_e2e.py`, tooling belonging to a separate, globally-installed skill (`harness-creator`), which spawns real headless `claude -p` sessions against natural-language prompts and grades the resulting transcripts against cited evidence. Scenarios are composed fresh each time rather than fixed in a workflow file, since freezing them would just be a flexibility tax with no real payoff.

The results of the most recent run are recorded in `.claude/harness-spec.md` rather than in a test file: **5 of 5 scenarios passed**, run against the plugin-installed (not symlinked) skill, in Korean natural-language prompts:

| Scenario | What it checked |
|---|---|
| E1 | A plain natural-language request correctly triggers the skill and completes a real background run |
| E2 | A code-review request correctly routes to the `review` path, and finds a real planted bug |
| E3 | **A deliberate near-miss** — a review request with no mention of Codex/GPT — correctly does **not** trigger the skill (zero skill invocations), and Claude reviews it directly instead |
| E4 | Resuming an earlier session's thread from a fresh session, using only the run registry — no in-context memory of the original run |
| E5 | Delegating a long-running task to Codex in the background while Claude does unrelated work in parallel, then reconciling both |

E3 matters as much as the four that trigger the skill: a skill whose description over-triggers is as much a defect as one that under-triggers.

## 5. Harness Validation

```bash
python3 ~/.claude/skills/harness-creator/scripts/validate_harness.py --path .
```

Checks the plugin and skill manifests against the structural conventions a Claude Code harness is expected to follow (frontmatter validity, manifest consistency, and similar static checks). Requires the `harness-creator` skill installed globally. There's also a standalone `test_hook.py` that must pass against the `SessionEnd` hook specifically before it's considered complete.

---
**Next:** [Troubleshooting](Troubleshooting.md) · [Architecture](Architecture.md)
[Back to index](README.md)
