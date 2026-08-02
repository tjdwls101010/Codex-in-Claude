# Context Discipline & Event Log Levels

How much of a run's output actually reaches Claude's context, why the default is set where it is, and the measurements behind that decision. For anyone tuning `--level`, or deciding whether the default is too conservative for their use case.

## 1. The Problem: One Field Carries All the Risk

Codex's `--json` event stream includes a `file_change` item for every edit, but it only ever carries a path and a kind (`add`/`modify`/`delete`) — never file contents. It's always cheap to show. The entire context risk is concentrated in one other field: `command_execution`'s `aggregated_output`, which holds a command's complete stdout. If Codex runs `cat` on a 2,000-line file, that file's entire contents land in this one field. That asymmetry — one universally-cheap item type, one item type that can be arbitrarily large — is why the filter levels below split exactly where they do, and why `normal` splits on **exit code** rather than on size.

## 2. The Four Levels

| Level | Includes | Excludes |
|---|---|---|
| `compact` (default) | Thread/turn lifecycle, agent messages **in full**, each command's line + exit code + output **size**, changed paths + kind, errors, token usage | All `aggregated_output` |
| `normal` | Everything in `compact`, plus head/tail of output for commands that exited **non-zero** | Successful commands' output |
| `full` | Every item, with output capped per item (2,000 bytes head + 2,000 bytes tail) | Nothing structural |
| `raw` | Every event, verbatim | — |

A few things hold at **every** level, by design: an `agent_message` is never truncated (it's the answer the run was for), and an `error` item is never hidden (the one time it isn't routine, you need to see it). `reasoning` steps are shown only at `full`.

Example `compact` line for a command:

```
cmd[item_2] exit=0 out=8797B rg -n "" tests . --glob '*.py'
```

## 3. The Byte-Size Annotation

That `out=8797B` is always computed and always shown, regardless of whether the level includes the actual output — it costs one integer, and it's what turns fetching a command's output into an informed decision rather than a guess. Pull that one command's full output on demand with:

```bash
$CODEX show --run <run_id> --item item_2
```

See [CLI Reference § show](CLI-Reference.md#7-show) for the full flag set, including the loud-truncation behavior above 20,000 bytes by default.

## 4. Measured Cost

Four real workloads run against a 148-line Python package, at every filter level (token figures are `bytes ÷ 4`, an approximation — the byte counts and ratios are exact):

| Workload | raw | `compact` | `normal` | `full` |
|---|---:|---:|---:|---:|
| read-heavy ("explain this architecture") | 12,233 B | **4,951 B** (40.5%) | 4,951 B | 11,392 B |
| write-heavy ("add a module + tests") | 13,262 B | **2,511 B** (18.9%) | 2,511 B | 11,168 B |
| review (`--uncommitted`) | 16,841 B | **1,974 B** (11.7%) | 1,974 B | 11,964 B |
| debug-failure ("tests fail, fix them") | 14,629 B | **1,516 B** (10.4%) | 3,647 B | 8,312 B |

`compact` and `normal` come out identical on the first three workloads because every command in them exited `0` — `normal` costs nothing extra until something actually fails. The debug-failure workload was added specifically because the first three gave no evidence for comparing `compact` against `normal` at all. Full methodology, per-workload prompts, and the threats to validity are recorded in [`docs/measurements/filter-calibration.md`](../measurements/filter-calibration.md).

## 5. Why `compact` Is the Default

Not because it's the smallest number in the table above — because of what's actually inside it:

| Workload | `compact` bytes | of which are the agent's own message |
|---|---:|---:|
| read-heavy | 4,951 | 4,218 (85%) |
| write-heavy | 2,511 | 966 (38%) |
| review | 1,974 | 779 (39%) |
| debug-failure | 1,516 | 685 (45%) |

Codex states what it found and what it did in its own final message, and that message is never filtered at any level — so raw command output is, in the common case, a **second copy** of a summary you already have. Read-heavy's apparently unimpressive 40.5%-of-raw figure is 85% the actual architecture explanation the run was asked to produce; strip that answer out and the structural overhead is roughly 730 bytes for a 12 KB stream.

When the output genuinely isn't redundant with the summary, it's usually one specific command, not all of them — and the byte-size marker is what tells you which one to pull with `show`.

**Raise to `normal`** when a command failed and the agent's own account of the failure isn't enough to act on — that's the one case where the withheld bytes are the diagnosis, not a copy of one. **Raise to `full`** to audit what a run actually did rather than to understand it; at 57–93% of raw, it's barely a filter, which is deliberate — it's the level for when you've stopped trusting the summary.

## 6. A Known Limitation

Exit code is a good proxy for "this output matters," not a perfect one. On the debug-failure workload, roughly half of what `normal` added over `compact` was ordinary `ripgrep` output from a command that exited `2` only because one of its file arguments didn't exist — not an actual failure worth surfacing. The alternatives (size thresholds, content-sniffing) are worse and less predictable, so the exit-code split stays as the default despite this — it's documented here rather than hidden.

## 7. Cursors, Polling, and Live Following

`log` always ends with `# cursor=<n>`, a byte offset into `events.jsonl`. Passing that back as `--since <n>` returns exactly what arrived since — never duplicated, never skipped, even if a line is half-written at the moment you poll, since only complete lines are ever consumed.

```bash
$CODEX log --run <run_id> --follow --level compact
```

`--follow` streams new events as they arrive and prints a terminal line for **every** terminal state (`run.completed`, `run.failed`, `run.interrupted`, `run.orphaned`), each with the exit code — so a crash is never indistinguishable from "still working." `--follow-timeout <sec>` bounds the wait with a `run.still-running` line instead of hanging forever on a stuck run.

For reading liveness without `--follow`, `status` reports `idle_seconds` together with `in_progress_item`: idle with an in-progress command means a long build or test run (normal); idle with nothing in progress means it's worth investigating.

---
**Next:** [Sandbox Stability](Sandbox-Stability.md) · [Testing](Testing.md)
[Back to index](README.md)
