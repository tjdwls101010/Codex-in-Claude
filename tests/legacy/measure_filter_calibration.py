#!/usr/bin/env python3
"""T3 — measure what each filter level costs, across real Codex runs.

Parameterised so it can be re-run against any project's registry when Codex
changes or the filter is tuned:

    python3 tests/measure_filter_calibration.py --project /path/to/repo \
        --out docs/measurements/filter-calibration.md

Token counts are `bytes / 4`. There is no local tokenizer for the model that
reads this output, so the figure is an approximation and is labelled as one
everywhere it appears; the ratios between levels are what the decision rests
on, and those are exact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent
                       / ".claude" / "skills" / "codex" / "scripts"))

from _events import LEVELS, format_events, read_events  # noqa: E402
from _registry import iter_runs, resolve_runs_dir  # noqa: E402


def measure(run_dir: Path, meta: dict):
    events_path = run_dir / "events.jsonl"
    raw_bytes = events_path.stat().st_size
    events, _ = read_events(events_path, 0)
    project = Path(meta.get("cwd") or ".")

    row = {"label": meta.get("label") or meta.get("run_id"),
           "kind": meta.get("kind"), "raw_bytes": raw_bytes,
           "events": len(events), "commands": 0, "output_bytes": 0,
           "files": 0, "levels": {}}
    for ev in events:
        it = ev.get("item") or {}
        if ev.get("type") == "item.completed":
            if it.get("type") == "command_execution":
                row["commands"] += 1
                row["output_bytes"] += len((it.get("aggregated_output") or "")
                                           .encode("utf-8", "replace"))
            elif it.get("type") == "file_change":
                row["files"] += len(it.get("changes") or [])

    for level in LEVELS:
        text = "\n".join(format_events(events, level, project))
        row["levels"][level] = len(text.encode("utf-8"))
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--runs-dir")
    ap.add_argument("--out")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    rows = [measure(rd, m) for rd, m in iter_runs(runs_dir)]
    if not rows:
        sys.exit(f"no runs in {runs_dir}")

    if args.json:
        print(json.dumps(rows, indent=2))
        return

    out = []
    w = out.append
    w("| Workload | Level | Bytes | ≈ tokens | vs raw | vs compact |")
    w("|---|---|---:|---:|---:|---:|")
    for r in rows:
        base = r["levels"]["compact"]
        w(f"| **{r['label']}** | _raw stream_ | {r['raw_bytes']:,} | "
          f"{r['raw_bytes'] // 4:,} | 100% | {r['raw_bytes'] / base:.1f}× |")
        for level in ("compact", "normal", "full"):
            b = r["levels"][level]
            w(f"| | `{level}` | {b:,} | {b // 4:,} | "
              f"{100 * b / r['raw_bytes']:.1f}% | {b / base:.1f}× |")
    w("")
    w("| Workload | Events | Commands | Command stdout | Files changed |")
    w("|---|---:|---:|---:|---:|")
    for r in rows:
        w(f"| {r['label']} | {r['events']} | {r['commands']} | "
          f"{r['output_bytes']:,} B | {r['files']} |")

    text = "\n".join(out)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    print(text)


if __name__ == "__main__":
    main()
