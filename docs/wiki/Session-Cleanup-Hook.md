# Session Cleanup Hook

What happens to a session's background Codex runs when that session ends. For anyone wondering why a run they started seems to have disappeared, or deciding whether to use `--detach`.

## 1. What Fires and When

`hooks/hooks.json` wires a single script, `hooks/codex_session_cleanup.py`, to Claude Code's **`SessionEnd`** event — which fires not only on real termination, but also on `/clear` and `/resume`. That's deliberate: after a `/clear`, nobody is watching the run either, so the same cleanup applies.

`SessionEnd` hooks run under a **1.5-second default timeout**, by far the shortest of any hook event. Because of that, this script is deliberately standalone: it imports nothing from `codex_bridge.py` or its helper modules, avoiding the overhead of argparse, subprocess, and sqlite3 setup it doesn't need. When a project has never used Codex — the common case — the script detects that a `.codex-runs` directory doesn't exist within 24 levels of walking up from the current directory and returns immediately, in roughly 20–30 milliseconds.

## 2. Why It Exists

An unwatched background run left alive after its session ends is a worse failure mode than killing it: it keeps writing to the project and burning tokens with nobody able to see or correct it. Killing it is safe specifically because a SIGINT-stopped Codex thread stays cleanly resumable from its rollout file — the work isn't lost, just paused, and a later session can pick it back up with `resume`.

## 3. How It Decides What to Stop

The hook matches a recorded run to the ending session using **either** of two signals: the `session_id` field in the hook's own stdin payload, or the `CLAUDE_CODE_SESSION_ID` environment variable. Relying on only one would be a single point of failure whose failure mode is silent — if the two ever disagreed, trusting only one could mean killing nothing (when it should) or killing everything (when it shouldn't). A run is selected for cleanup only if all of these hold: `state` is `running` or `starting`, it is **not** `detached`, and its recorded `claude_session_id` matches the ending session by either signal.

## 4. The Signal Sequence

For each matched run, the hook sends **SIGINT** to its recorded process group immediately. Codex is measured to exit roughly **0.3 seconds** after SIGINT, having flushed its rollout file — which is exactly what keeps the thread resumable afterward. The hook then polls liveness every 50ms for up to `SIGINT_GRACE` (0.5s), and escalates any process group still alive to **SIGTERM** if that stays within the hook's overall signal budget of 0.9 seconds (out of the 1.5-second hook timeout, leaving headroom for interpreter startup). Sending SIGTERM immediately alongside SIGINT — instead of giving Codex that grace window first — would defeat the flush that makes the thread resumable, so the ordering here is load-bearing, not incidental.

## 5. The `--detach` Exemption

A run started with `--detach` (`$CODEX start --detach ...`) is recorded with `detached: true` in its `meta.json`, and the cleanup hook's selection logic skips any run with that flag set, regardless of which session it belongs to. Use `--detach` for a run that's meant to genuinely outlive the session that started it — check on it later with `status --all` (it will still show up), and stop it explicitly with `stop --run <id>` when you're done, or it'll keep running indefinitely. `doctor` separately reports any such runs still going under `detached_running`, as a warning rather than a blocker.

## 6. What Gets Recorded

For each run the hook stops, it atomically updates that run's `meta.json` with `state: "interrupted"`, an `ended_at` timestamp, `stopped_by: "SessionEnd(<reason>)"`, and `stop_signals` (`"SIGINT"`, `"SIGINT+SIGTERM"`, or `"already-gone"`). Since `SessionEnd` has no channel to block or report back to the user interactively, the hook writes a short human-readable summary to stdout as its only form of feedback.

---
**Next:** [Testing](Testing.md) · [Troubleshooting](Troubleshooting.md)
[Back to index](README.md)
