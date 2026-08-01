# Codex in Claude — Documentation

This is the full documentation for **Codex in Claude**, a Claude Code plugin that runs the OpenAI Codex CLI as a managed, resumable background subagent. The [project README](../../README.md) gets you installed and running; this wiki is where the depth lives — how it works, why it's built this way, and what to do when something looks wrong.

**New here?** Start with [Getting Started](Getting-Started.md) for installation through your first real run.

## Table of Contents

| Page | What it covers |
|---|---|
| [Overview](Overview.md) | The problem this solves, the value it delivers, where it sits relative to alternatives, and what it deliberately doesn't do |
| [Getting Started](Getting-Started.md) | Prerequisites, installation (plugin, local, or symlink), and a full first-run walkthrough |
| [Architecture](Architecture.md) | The components, the request-flow diagram, the module map, and the key design decisions |
| [Concepts](Concepts.md) | The vocabulary — threads, runs, sandbox modes, isolation, the run registry, filter levels, cursors |
| [CLI Reference](CLI-Reference.md) | Every subcommand and flag: `start`, `resume`, `review`, `status`, `log`, `show`, `stop`, `result`, `doctor` |
| [Sandbox Stability](Sandbox-Stability.md) | The measured sandbox-drift defect this plugin exists to fix, and exactly how the fix works |
| [Context Discipline & Event Log Levels](Context-Discipline.md) | The four-level output filter, the measurements behind the default, and its one known limitation |
| [Session Cleanup Hook](Session-Cleanup-Hook.md) | What happens to background runs when a Claude session ends, and the `--detach` exemption |
| [Testing](Testing.md) | The four test tiers (unit, integration, filter calibration, headless e2e) and how to run each one |
| [Troubleshooting](Troubleshooting.md) | Symptom → cause → fix, what's not actually broken, and what's deliberately out of scope |

---
[Back to the project README](../../README.md)
