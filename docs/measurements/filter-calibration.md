# T3 — filter calibration

**Measured 2026-07-25** against `codex-cli 0.144.1`, model `gpt-5.6-sol`, isolated (`--ignore-user-config`), on macOS 25.5.0.

This is the measurement the shipped default filter level is chosen from. A number in a skill without its measurement is a rail wearing a digit, so the table comes first and the decision comes after it.

Reproduce with:

```bash
python3 tests/measure_filter_calibration.py --project <repo-with-a-registry>
```

## Method

Four workloads, each a real background Codex run through `codex_bridge.py start` against the same scratch repository (`taskq`, a 148-line Python package with a test suite). Each run's `events.jsonl` was then rendered at every filter level and the output measured.

**Token figures are `bytes ÷ 4` and are approximations.** There is no local tokenizer for the model that reads this output. The *ratios* between levels are exact — those are what the decision rests on; the absolute token counts are indicative only.

| Workload | Prompt | Why it is in the set |
|---|---|---|
| `read-heavy` | "Explain this repository's architecture… read the actual source files" | Maximises `aggregated_output` from file reads — the worst case for context bloat |
| `write-heavy` | "Add `taskq/metrics.py`, wire it in, add tests, run the suite" | Maximises `file_change` volume and build/test output |
| `review` | `review --uncommitted` over the previous workload's changes | The realistic mixed case |
| `debug-failure` | "The test suite is failing — diagnose, fix, re-run until it passes" | **Added during measurement.** See below. |

### Why a fourth workload was added

The plan specified the first three. Run against them, `compact` and `normal` came out **byte-identical in all three**, because every command in all three runs exited 0 — and the only thing `normal` adds is output for commands that *failed*. The table could not distinguish the two levels at all, so choosing between them from it would have been unjustified.

`debug-failure` is the case where `normal` earns its keep, and it is also one of the most common real shapes of work. Without it there is no evidence for the decision below.

## Results

| Workload | Level | Bytes | ≈ tokens | vs raw | vs compact |
|---|---|---:|---:|---:|---:|
| **read-heavy** | _raw stream_ | 12,233 | 3,058 | 100% | 2.5× |
| | `compact` | 4,951 | 1,237 | 40.5% | 1.0× |
| | `normal` | 4,951 | 1,237 | 40.5% | 1.0× |
| | `full` | 11,392 | 2,848 | 93.1% | 2.3× |
| **write-heavy** | _raw stream_ | 13,262 | 3,315 | 100% | 5.3× |
| | `compact` | 2,511 | 627 | 18.9% | 1.0× |
| | `normal` | 2,511 | 627 | 18.9% | 1.0× |
| | `full` | 11,168 | 2,792 | 84.2% | 4.4× |
| **review** | _raw stream_ | 16,841 | 4,210 | 100% | 8.5× |
| | `compact` | 1,974 | 493 | 11.7% | 1.0× |
| | `normal` | 1,974 | 493 | 11.7% | 1.0× |
| | `full` | 11,964 | 2,991 | 71.0% | 6.1× |
| **debug-failure** | _raw stream_ | 14,629 | 3,657 | 100% | 9.6× |
| | `compact` | 1,516 | 379 | 10.4% | 1.0× |
| | `normal` | 3,647 | 911 | 24.9% | 2.4× |
| | `full` | 8,312 | 2,078 | 56.8% | 5.5× |

| Workload | Events | Commands | Command stdout | Files changed | Non-zero exits |
|---|---:|---:|---:|---:|---:|
| read-heavy | 13 | 4 | 5,463 B | 0 | 0 |
| write-heavy | 19 | 5 | 7,163 B | 4 | 0 |
| review | 10 | 3 | 13,188 B | 0 | 0 |
| debug-failure | 16 | 4 | 10,837 B | 1 | 2 |

### What `compact` actually spends its bytes on

| Workload | `compact` bytes | of which agent messages | share |
|---|---:|---:|---:|
| read-heavy | 4,951 | 4,218 | 85% |
| write-heavy | 2,511 | 966 | 38% |
| review | 1,974 | 779 | 39% |
| debug-failure | 1,516 | 685 | 45% |

This is the most useful row in the whole measurement. **`compact` is the agent's own answer plus a few hundred bytes of scaffolding.** `read-heavy` looks like the worst ratio in the table at 40.5% of raw — but 85% of that is the architecture explanation the run was *asked* to produce. Strip the answer and the structural overhead is ~730 bytes for a 12 KB event stream.

## Qualitative check: does `compact` still show every decision point?

The numbers say `compact` is cheapest; they cannot say whether it is *sufficient*. Here is the entire `compact` rendering of `debug-failure` — 379 approximate tokens covering a four-command debugging session:

```
thread 019f9985-5423-7aa0-b3ac-18421a110076
turn.started
msg I'll reproduce the failures first, then trace the affected code and make the smallest targeted fix.
cmd.start[item_1] python3 -m unittest discover -s tests -t .
cmd[item_1] exit=1 out=682B python3 -m unittest discover -s tests -t .
cmd.start[item_2] rg -n "" tests . --glob '*.py' …
cmd[item_2] exit=0 out=8797B rg -n "" tests . --glob '*.py' …
msg The retry loop's exhaustion check is unreachable: the loop only runs while
    `attempts < max_retries`, but the exception branch checks `attempts > max_retries`.
cmd.start[item_4] rg -n "max_retries|retry|attempt" README* pyproject.toml …
cmd[item_4] exit=2 out=1257B rg -n "max_retries|retry|attempt" README* …
file update taskq/task.py
cmd.start[item_6] python3 -m unittest discover -s tests -t .
cmd[item_6] exit=0 out=101B python3 -m unittest discover -s tests -t .
msg Fixed the unreachable retry-exhaustion condition in taskq/task.py:39.
    Test result: **3 tests passed**.
turn.completed in=114429 cached=76544 out=946 reasoning=185
# cursor=14629
```

Every question a caller would actually ask is answered: the suite failed (`exit=1`), what the root cause was (the agent says so), which file changed, that the re-run passed (`exit=0`), and what it cost. The 8,797 bytes that `rg` printed are not here, and nothing is worse for it.

### What `normal` adds, and the limitation it exposes

`normal` expands the two non-zero-exit commands. One is genuinely valuable — the unittest traceback naming `test_exhausts_retries` and `AssertionError: RuntimeError not raised`. The other is 18 lines of ordinary ripgrep matches: `item_4` exited 2 only because one of its file arguments did not exist, and its output was a perfectly successful search.

So roughly **half of what `normal` added on this run was noise**, and the finding generalises: *exit code is a good proxy for "this output matters", not a perfect one.* Search and lint tools routinely exit non-zero for reasons that are not failures. The alternative proxies are worse — size does not correlate with relevance at all, and content-sniffing is unpredictable — so the exit-code split stays, with its limitation recorded here rather than discovered later.

## Decision

**The shipped default is `compact`** (`_events.py: DEFAULT_LEVEL`).

The reasoning, which matters more than the number:

1. **The agent message is a summary channel and it survives intact at every level.** Codex states what it found and what it did. The raw command output is therefore *redundant with the summary* in the common case — as the `debug-failure` excerpt shows, the diagnosis is in the agent's own words before any output is expanded.
2. **When it is not redundant, it is one item, not all of them.** Every withheld command carries its byte count (`out=8797B`), so `show --run … --item item_2` is a decision rather than a guess. Paying for all output up front to cover the case where one command's output is needed is the wrong trade.
3. **The saving is largest exactly where the risk is largest.** `compact` costs 10–19% of raw on the three workloads dominated by command output, and its worst ratio (read-heavy, 40.5%) is worst only because that run's output *is* the answer.

**When to raise it, stated as a rule with its reason:** move to `normal` when a run has failing commands and the agent's own account of the failure is not enough to act on — that is the one case where the withheld bytes are the diagnosis rather than a copy of it. Move to `full` only to audit what a run actually did, not to understand it; at 57–93% of raw it is barely a filter, and that is by design — it is the level you choose when you have stopped trusting the summary.

## Threats to validity

- **One repository, one model, one machine.** Ratios will move with repository size and with how chatty a model is. The mechanism (agent-message share vs command-output share) is what transfers, not the exact percentages.
- **`bytes ÷ 4`** is a stand-in for tokenisation, and Korean or heavily punctuated output tokenises worse than the English prose measured here.
- **Four workloads is a small sample**, and three of them produced no failing commands at all. That is itself informative — non-zero exits are not the common case, which is part of why `normal`'s extra cost is usually zero — but it means the `compact`↔`normal` comparison rests on a single run.
- The `review` row's raw size is inflated by `git`'s `confstr()`/`xcrun_db` warnings on this machine, which are environmental noise rather than anything Codex did. `compact` discards them either way.
