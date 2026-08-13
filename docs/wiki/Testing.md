# Testing

The four-tier test strategy behind this project, and how to run the tiers that live in this repository. For anyone verifying a change, or deciding how much testing a contribution needs — see also [CONTRIBUTING.md](../../CONTRIBUTING.md) for the day-to-day commands.

## 1. T1 — Unit Tests Against a Fake Codex

```bash
python3 -m unittest discover -s tests/legacy -p 'test_*.py'
python3 -m unittest discover -s tests/260813 -p 'test_*.py'
```

**301 tests in `tests/legacy`, passing in about two and a half minutes**, requiring no network access and no real Codex CLI. These tests drive the real `codex_bridge.py` as a subprocess — not an in-process mock — with a fake `codex` executable (`tests/legacy/fake_codex/codex`) placed first on `PATH`. That fake replays event streams recorded from real runs (`tests/legacy/fixtures/*.jsonl`), so everything except the model itself is exercised for real: argument parsing, argv composition, process spawning, process groups, and signal delivery.

`tests/260813` is the second start directory, and it holds the checks that the suite is there at all. They exist because moving `tests/` to `tests/legacy/` shifted every `__file__`-rooted path constant by one directory and the documented command answered `NO TESTS RAN` with exit status 0 — a suite reporting success by finding nothing. `test_suite_integrity.py` asserts that every discovery command in CONTRIBUTING.md and this file collects tests and imports cleanly, that every directory holding `test_*.py` is reachable from one of those commands, and that every path either suite computes by walking up from its own `__file__` still resolves to something on disk.

This tier includes the single most load-bearing test in the suite: a regression assertion that a resumed run's *recorded argv* actually contains `-c sandbox_mode="read-only"` when its thread was created read-only — the specific defect described in [Sandbox Stability](Sandbox-Stability.md), caught at the argument-composition level before it ever reaches a real Codex process. It also covers Unicode/NFC path handling (Korean paths, spaces), the run registry's self-`.gitignore`ing behavior, cursor-exactness on partial trailing lines, all four filter levels, and all four `doctor` failure modes.

Since v0.2.0 it additionally drives real `git` — worktrees are cut, written into and removed for real rather than faked — and reproduces the registry race that motivated the concurrency work by running several writers as actual separate processes. Several of these tests exist because something got past this tier and was caught by a real run below it; where that is so, the test says which failure it is holding.

Run this tier before opening any pull request — it's fast, free, and covers most of the codebase's actual logic.

## 2. T2 — Real Codex Integration

```bash
CODEX_SKILL_TEST_INTEGRATION=1 python3 tests/legacy/integration/run_integration.py
```

Gated behind an explicit environment variable so it never runs by accident, since it consumes real API usage. Spins up a throwaway git repository and drives the real bridge against the real, authenticated `codex` binary. **15 of 15 cases passing**, in about four minutes, verified against `codex-cli 0.146.0`:

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
| I9 | Three members of one batch get three distinct threads and three distinct process groups |
| I10 | **Worktree isolation, for real** — three writers told to create the same filename produce three files in three checkouts, the main tree stays clean, and `overlaps` catches the collision |
| I11 | `--resume-from` continues each member on *its own* thread, checked against the rollout rather than the wrapper's bookkeeping |
| I12 | A member refused before it can spawn does not take the batch with it; the group ends `partial` |
| I13 | `status --group --follow` ends on a terminal line rather than going quiet |
| I14 | A background `--timeout` records `timed_out`, and the same thread resumes to completion afterwards |
| I15 | `batch clean` refuses to discard uncollected work, `--force` removes it, and git stops listing the worktrees |

I10 is the case worth knowing about: it is what caught `overlaps` reporting `{}` for three members all editing the same repository path in their own worktrees — a defect the unit tier missed because its fixture planted repo-relative paths, which is not the shape real events have.

Use `--only <case-id>` to run a single case while iterating. This tier isn't required for most contributions — run it when a change touches how the bridge invokes `codex` itself.

## 3. T3 — Filter Calibration

```bash
python3 tests/legacy/measure_filter_calibration.py --project <repo-with-a-registry>
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

| E6 | Three modules audited by three Codex runs as one group, then collected — findings delivered, not promised |
| E7 | Continuing that group's three threads, each on the bug it personally found |
| E8 | **A second near-miss** — "review these three files at once", no mention of Codex — correctly does not trigger |
| E9 | Noticing and reporting that a group started fewer members than it was asked for |

E3 and E8 matter as much as the scenarios that trigger the skill: a description that over-triggers is as much a defect as one that under-triggers, and for both the evidence of a pass is an absence — no skill invocation anywhere in the transcript.

The v0.2.0 round of this tier is the one that found the most, and the reason is worth stating. Every failure was a session that ran the *right commands* and still did not do the job: two that started a batch correctly and then ended the turn promising to report back, and one that declared three grouped runs to be unrelated because `status` did not say they were a group — reasoning correctly from a false premise the tool had handed it. Grading on tool calls alone would have passed all three. The rule that catches them is that surface compliance is a failure: a verdict must cite the final message, not the commands that preceded it.

One scenario also failed for the opposite reason, which is recorded rather than papered over. E7's third run found the group, reasoned aloud about the shared-directory hazard, serialised the writers so they could not collide, waited, verified with `git diff`, and reported real per-file diffs — and was marked failed only because it did not use `--resume-from`. That criterion was over-specified: serialised writers cannot collide. The finding was in the rubric, not the harness.

## 5. Harness Validation

```bash
python3 ~/.claude/skills/harness-creator/scripts/validate_harness.py --path .
```

Checks the plugin and skill manifests against the structural conventions a Claude Code harness is expected to follow (frontmatter validity, manifest consistency, and similar static checks). Requires the `harness-creator` skill installed globally.

---
**Next:** [Troubleshooting](Troubleshooting.md) · [Architecture](Architecture.md)
[Back to index](README.md)
