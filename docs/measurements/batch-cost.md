# Batch cost

**Measured 2026-08-03** on macOS 25.5.0, Python 3.12.8, APFS.

What a batch and a long-lived registry actually cost. The registry section below needs no Codex at all — it is synthesis plus timing — so it is the cheapest of these numbers and the one most likely to be re-run.

Reproduce the registry section with `python3 tests/measure_registry_scale.py <N>`; the Codex sections cost real API usage and say so.

## Registry scale

`concurrent_writers` walks every run on each `start`. `projected_cost` calls `reversed(list(iter_runs(...)))`, which materialises every run's meta before taking ten samples. `doctor` sums the size of every file under `.codex-runs` with `rglob("*")` and walks the runs twice more. Nine call sites in all. None of that had ever been timed against a registry that had been used for a while, and "it walks everything" is the kind of fact that reads as a problem before it is measured.

### Method

A throwaway git project, one real run made through the bridge with the fake `codex` first on `PATH`, then N synthesised run directories cloned from that run's own `meta.json` — never a hand-written one, because guessing the shape of a fixture is exactly how `overlaps` ended up with a test that could not fail (R11). Each synthesised run carries a copy of `tests/fixtures/mixed-bigout-and-failure.jsonl` (24 KB) as its event stream, so `doctor`'s byte sum has something realistic to add up: at N=2000 the registry holds about 48 MB. Timed with `time.perf_counter()` around the subprocess, one cold invocation each.

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
