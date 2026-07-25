# The event stream

Open this to reason about raw events or to tune how much detail reaches context.

## Two different schemas

Codex writes the same run twice, in two formats. Confusing them wastes time, because they
share almost no field names.

### 1. `codex exec --json` on stdout — what `events.jsonl` stores

```jsonl
{"type":"thread.started","thread_id":"019f9958-629c-7983-9d6b-fdc4edd47b20"}
{"type":"turn.started"}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"/bin/zsh -lc 'git status'","aggregated_output":"","exit_code":null,"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"/bin/zsh -lc 'git status'","aggregated_output":"…FULL STDOUT…","exit_code":0,"status":"completed"}}
{"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"…"}}
{"type":"item.completed","item":{"id":"item_3","type":"file_change","changes":[{"path":"/abs/path/b.txt","kind":"add"}],"status":"completed"}}
{"type":"item.completed","item":{"id":"item_0","type":"error","message":"…"}}
{"type":"turn.completed","usage":{"input_tokens":46238,"cached_input_tokens":22272,"output_tokens":179,"reasoning_output_tokens":0}}
```

Facts that change how you read it:

- **`thread.started` is always the first line** and carries the thread id — including on
  `resume`, where it repeats the *same* id. That is why the first line alone identifies a
  run's thread.
- **`item.id` restarts at `item_0` on every invocation.** It is per-invocation, not
  per-thread. Key items by `(run_id, item_id)`; an item id alone is meaningless across runs.
- **`file_change` carries paths and a kind only — never contents.** Always cheap.
- **`command_execution.aggregated_output` carries full stdout.** This is the only field
  that can be arbitrarily large, and the only reason the filter exists.
- Commands are wrapped as `/bin/zsh -lc "…"`. The wrapper is identical on every line and
  is stripped for display.
- **`error` items are informational**, usually config warnings, and are not fatal. They are
  shown at every level anyway, because the one time an `error` is not routine you need it.
- **`review` runs report all-zero `usage`** even after doing real work. `status` and
  `result` report `null` for them — unavailable, not free.

### 2. The rollout file — `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ISO>-<thread_id>.jsonl`

A different shape: `{"timestamp", "type": "session_meta"|"event_msg"|"response_item"|
"turn_context"|"world_state", "payload": {…}}`. Written live, and `codex exec resume`
**appends to the same file** rather than starting a new one.

You rarely need it, with one exception: the `turn_context` line is the authoritative record
of what a turn actually ran under (`sandbox_policy`, `model`, `reasoning_effort`, `cwd`).
See `environment.md`.

## Filter levels

| Level | Includes | Excludes |
|---|---|---|
| `compact` (default) | thread/turn lifecycle, agent messages **in full**, each command line + exit code + output **size**, changed paths + kind, errors, token usage | all `aggregated_output` |
| `normal` | compact, plus head/tail of output for **non-zero-exit** commands only | successful commands' output |
| `full` | every item with output capped per item | nothing structural |
| `raw` | the events verbatim | — |

The split is on **exit code**, not size, because a failed command's output is exactly the
case where the output is what you need, and a successful one's is exactly the case where it
is not.

### Measured cost

Four real runs against a 148-line Python package. Token figures are `bytes ÷ 4` — an
approximation, stated as one; the ratios are exact. Full method, per-workload prompts, the
qualitative reading and the threats to validity are in
[`docs/measurements/filter-calibration.md`](../../../../docs/measurements/filter-calibration.md).

| Workload | raw | `compact` | `normal` | `full` |
|---|---:|---:|---:|---:|
| read-heavy ("explain this architecture") | 12,233 B | **4,951 B** (40.5%) | 4,951 B | 11,392 B |
| write-heavy ("add a module + tests") | 13,262 B | **2,511 B** (18.9%) | 2,511 B | 11,168 B |
| review (`--uncommitted`) | 16,841 B | **1,974 B** (11.7%) | 1,974 B | 11,964 B |
| debug-failure ("tests fail, fix them") | 14,629 B | **1,516 B** (10.4%) | 3,647 B | 8,312 B |

`compact` and `normal` are identical on the first three because every command in them
exited 0 — `normal` costs nothing until something fails.

### Why `compact` is the shipped default

Not because it is smallest. Because of this:

| Workload | `compact` bytes | of which are agent messages |
|---|---:|---:|
| read-heavy | 4,951 | 4,218 (85%) |
| write-heavy | 2,511 | 966 (38%) |
| review | 1,974 | 779 (39%) |
| debug-failure | 1,516 | 685 (45%) |

**`compact` is the agent's own answer plus a few hundred bytes of scaffolding.** Codex
states what it found and what it did, and that summary is never filtered at any level — so
raw command output is a *second copy* of something you already have, in the common case.
read-heavy's apparently poor 40.5% is 85% the architecture explanation the run was asked to
produce; strip the answer and the structural overhead is ~730 bytes for a 12 KB stream.

When the output is *not* redundant, it is one command, not all of them — and the size
marker tells you which one.

**Raise to `normal`** when a command failed and the agent's account of the failure is not
enough to act on. **Raise to `full`** to audit what a run did rather than to understand it;
at 57–93% of raw it is barely a filter, which is deliberate — it is the level you pick when
you have stopped trusting the summary.

One honest limitation, found during the measurement: exit code is a good proxy for "this
output matters", not a perfect one. On the debug run, half of what `normal` added was
ordinary ripgrep output from a command that exited 2 only because one file argument did not
exist. The alternatives (size thresholds, content-sniffing) are worse and less predictable,
so the exit-code split stays.

## Cursors and polling

`log` ends with `# cursor=<n>`, a **byte offset** into `events.jsonl`. Pass it back as
`--since <n>` and you get only what arrived since.

It is exact in both directions. Only complete lines are consumed and the cursor lands after
the last one, so a line half-written at the moment you poll is left for the next call —
never duplicated, never skipped, however often you poll.

`--since` on a finished run replays from any offset, so `--since 0` always reproduces the
whole log.

## Live following and Monitor

```bash
$CODEX log --run <id> --follow --level compact
```

`--follow` prints events as they arrive and then a terminal line before exiting:

```
run.completed run=20260725-224124-read-heavy-d418 exit=0
```

It emits that line for **every** terminal state — `run.completed`, `run.failed`,
`run.interrupted`, `run.orphaned` — with the exit code. This matters more than it looks: a
filter that only prints progress is silent through a crash, and silence is
indistinguishable from "still working". Pair it with the **Monitor** tool and each line
becomes a notification, including the one that says it died.

`--follow-timeout <sec>` bounds the wait and prints `run.still-running` instead, so a
monitor cannot hang forever on a stuck run.

### Reading liveness

`status` reports `idle_seconds` (now − mtime of the last event) *and* `in_progress_item`.
Use both:

- idle, **with** an in-progress `command_execution` → a long build or test run. Normal.
- idle, **no** in-progress item → nothing is happening. Worth investigating.

A run idle past a threshold is labelled `stalled`, which is advisory only — nothing is ever
auto-killed, because the threshold cannot know whether a command is slow or wedged and you
can.

## `show` — the escape hatch

```bash
$CODEX show --run <id> --item item_2 [--max-bytes 20000]
```

Returns one item's full `aggregated_output` (or a `file_change`'s full change list). This is
the only path by which complete command output reaches context, and it is always an
explicit per-item request.

Output above `--max-bytes` (default 20,000) is truncated **loudly**: the response carries
`truncated: true`, `total_bytes`, `shown_bytes` and a notice saying how much was withheld
and how to raise the cap. A silently truncated blob is worse than a loud one — you would
reason about a fragment believing it was the whole thing.

Pass `--run` always: item ids are per-invocation, so `item_2` exists in most runs and means
something different in each.
