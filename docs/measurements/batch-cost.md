# Batch cost

**Measured 2026-08-03** on macOS 25.5.0, Python 3.12.8, APFS.

What a batch and a long-lived registry actually cost. The registry section below needs no Codex at all — it is synthesis plus timing — so it is the cheapest of these numbers and the one most likely to be re-run.

Reproduce the registry section with `python3 tests/legacy/measure_registry_scale.py <N>`; the Codex sections cost real API usage and say so.

## Registry scale

`concurrent_writers` walks every run on each `start`. `projected_cost` calls `reversed(list(iter_runs(...)))`, which materialises every run's meta before taking ten samples. `doctor` sums the size of every file under `.codex-runs` with `rglob("*")` and walks the runs twice more. Nine call sites in all. None of that had ever been timed against a registry that had been used for a while, and "it walks everything" is the kind of fact that reads as a problem before it is measured.

### Method

A throwaway git project, one real run made through the bridge with the fake `codex` first on `PATH`, then N synthesised run directories cloned from that run's own `meta.json` — never a hand-written one, because guessing the shape of a fixture is exactly how `overlaps` ended up with a test that could not fail (R11). Each synthesised run carries a copy of `tests/legacy/fixtures/mixed-bigout-and-failure.jsonl` (24 KB) as its event stream, so `doctor`'s byte sum has something realistic to add up: at N=2000 the registry holds about 48 MB. Timed with `time.perf_counter()` around the subprocess, one cold invocation each.

### Results

| Command | N=100 | N=500 | N=2000 |
|---|---:|---:|---:|
| `status` | 0.066 s | 0.146 s | 0.503 s |
| `status --all` | 0.067 s | 0.144 s | 0.498 s |
| `doctor` | 0.148 s | 0.222 s | 0.627 s |
| `batch start` (1 member) | 0.208 s | 0.234 s | 0.435 s |
| `result --run` | 0.047 s | 0.048 s | 0.060 s |
| `status --group` | 0.058 s | 0.051 s | 0.061 s |
| `status --group --follow` (one tick) | 0.057 s | 0.052 s | 0.062 s |
| `result --group` | 0.071 s | 0.061 s | 0.076 s |

### What follows from it

**Nothing needs caching or a cap.** The whole-registry commands scale linearly and stay under a second at 2000 runs — twenty times the size the question was asked about. A cache would be a new invalidation problem bought with no measured gain, and a cap would hide runs from the one view whose job is to show them.

**The group views are flat.** `status --group`, its `--follow` tick and `result --group` do not move between N=100 and N=2000, because a group resolves its members through the manifest's run ids and never enumerates the registry. That is worth stating because it is the loop a caller runs repeatedly: polling a group costs the same on day one and day four hundred.

**`batch start` roughly doubles from N=100 to N=2000** and is still under half a second. It carries the two full scans — `concurrent_writers` and `projected_cost` — and pays them once per batch rather than once per member.

The honest limit on all of this: one machine, one filesystem, warm page cache after the synthesis loop wrote the files. A cold registry on a slow disk would be worse. What the numbers rule out is an order-of-magnitude problem, not a factor of two.

## Concurrency above N=8

V-11 and V-12 measured up to eight concurrent runs and said so: *"N=8 is the highest concurrency validated; larger fan-outs are unmeasured."* D34 removed `--max-concurrent` and made a `--stagger` fallback conditional on contention appearing — and it never had, at a ceiling nobody had pushed on.

Two things were being conflated in that question, and they are different failures with different remedies:

- **How long `batch start` takes to return.** Members are spawned in a plain loop, one after another, and each waits up to `THREAD_ID_WAIT` (15 s) for Codex to name its thread. If that dominated, a large batch would be slow to hand back a handle — a latency and UX problem, fixed by changing the loop.
- **Whether sqlite contention or rate limiting actually appears.** Only this is D34's condition. `--stagger` is a remedy for contention and for nothing else.

### Method

V-11's method, unchanged so the numbers compose with it: one trivial prompt (`Reply with exactly the word ACKNOWLEDGED and nothing else.`) held identical across sizes, one `CODEX_HOME`, real `codex exec` through the bridge, `--sandbox read-only --effort low`, a throwaway git project per run. Every member's `events.jsonl` and `stderr.log` was then scanned for `database is locked`, `SQLITE_BUSY`, `rate limit`, `429` and `too many requests`. Reproduce with `python3 tests/legacy/measure_concurrency.py 12 16 24`.

### Results

| N | `batch start` returns | group wall clock | distinct thread ids | contention hits | terminal states |
|---:|---:|---:|---:|---:|---|
| 12 | 3.97 s | 10.1 s | 12 / 12 | 0 | 12 completed |
| 16 | 4.23 s | 15.1 s | 16 / 16 | 0 | 16 completed |
| 24 | 7.07 s | 10.1 s | 24 / 24 | 0 | 24 completed |

### What follows from it

**`--stagger` stays out, and now at three times the ceiling that justified leaving it out.** Zero contention events at N=24, every thread id distinct, every member terminal and completed. D34's condition has still never fired.

**The sequential spawn is not the bottleneck it looked like.** About 0.29 s per member, nowhere near the 15 s `THREAD_ID_WAIT` that made it look expensive on paper: the wait is a ceiling for a member whose thread id is slow to arrive, not a cost every member pays. A 24-member batch hands back its handle in about seven seconds.

**Wall clock does not grow with N here** — 10 s at twelve, 15 s at sixteen, 10 s at twenty-four — because a trivial prompt's turn is dominated by round-trip latency rather than by anything that queues. That is the same shape V-12 saw from N=1 to N=8, extended. It says nothing about N heavy members, which is what the section below measures instead.

## Collecting a group

`docs/measurements/filter-calibration.md` chose the default filter level from single-run workloads. A batch changes the shape of the question: N streams arrive in one payload, `result --group` adds an `overlaps` map and `totals`, and each member's message is capped at `GROUP_MESSAGE_CAP = 4000` — a number whose only justification was that it looked reasonable.

### Method

T3's `write-heavy` shape, held identical across N: each member adds one function to `lib/util.py`, wires it into `__all__`, adds a test, and runs the suite. Writers are isolated per member, so they do genuinely independent work instead of fighting over one tree. Bytes are measured on the actual stdout a caller receives — `result --group` once, against the sum of `result --run` for every member. Token figures are `bytes ÷ 4` and are approximations; the ratios are exact. Reproduce with `python3 tests/legacy/measure_group_cost.py 3 5 8`.

### Results

| N | `result --group` | Σ `result --run` | ratio | member messages | truncated at the cap | overlapping paths |
|---:|---:|---:|---:|---|---:|---:|
| 3 | 4,034 B (≈1,008 tok) | 2,284 B | **1.77×** | 258–658 B | 0 | 3 |
| 5 | 6,232 B (≈1,558 tok) | 3,636 B | **1.71×** | 273–661 B | 0 | 3 |
| 8 | 9,075 B (≈2,269 tok) | 5,210 B | **1.74×** | 267–327 B | 0 | 3 |

### What follows from it

**`result --group` is not a context saving, and calling it one would be wrong.** It costs about 1.75× what fetching each member separately costs, flat across N. The extra is per-member `label`, `message_bytes`, `message_truncated` and the worktree's absolute path, plus the group-level `overlaps` and `totals`. What it buys is one call instead of N, and `overlaps` — which is not derivable from the individual results at any price, because each member's result knows only its own paths. Reach for it because you want the intersection and the single round trip, not because it is cheaper. It is not.

**Growth is linear and modest**: about 1,130 bytes per member on top of a ~600-byte envelope, so a group of eight lands around 2.3k tokens. That is the cost of collecting eight parallel writers in one call, and it is small next to what those eight runs consumed to produce it (603k input tokens at N=8).

**`GROUP_MESSAGE_CAP` never engaged.** Every member's final message came in between 258 and 661 bytes, against a 4,000-byte cap — an order of magnitude of headroom. So the cap costs nothing on this workload, and this workload does not justify the number either: it is insurance that has not yet been claimed on. Choosing 4,000 on evidence would need a workload whose members write long final messages, which a "add a function and run the tests" task does not. That remains open, and it is a smaller question than it looked: the cap only ever binds on the messages, which are the smallest part of the payload measured here.

## What `projected_cost` predicts

`batch start` reports a per-run number computed from the project's own recent completed isolated runs (D37, because a constant measured at design time moved 2.7× in two weeks). It called itself a **floor**. That had never been checked against the registry it is computed from.

Checked, on this repository's own registry: predicted 149,031 input tokens per run, against eleven real isolated completed runs whose actual input tokens ran 35,342 / 92,898 median / 486,648. **Six of the eleven came in below the predicted "floor."**

Which is exactly what a median does — it is exceeded by half its samples by construction, and `projected_cost` takes `samples[len(samples) // 2]`. The statistic was never wrong; the word was. A caller reading "floor" plans for at-least-this-much and is wrong more often than not, and a misleading field name is a false premise the caller then reasons correctly from — R19 arriving somewhere else.

The fields are now `input_median_per_run` and `input_median_total`, and the note says what the number is: a scale, not a bound, with about half of real runs under it and a resume growing from there. The spread is the real lesson — a 14× range between the smallest and largest run in one project — and it is why the standing advice remains to re-measure rather than to budget from any single figure.

**`overlaps` earned its keep at N=8.** All eight members, each in its own worktree, edited the same three files — `lib/util.py`, `lib/__init__.py`, `tests/test_util.py` — and all three were reported, with every member named. This is the situation R11 records the field being blind in, run at eight-way width against the real CLI.
