# Security Policy

## Reporting a Vulnerability

If you believe you've found a security vulnerability in Codex in Claude, please report it privately — **do not open a public GitHub issue**. A public issue for a sandbox-escalation or permission bug gives potential attackers a head start before a fix ships.

Use GitHub's private vulnerability reporting instead:

1. Go to the [Security tab](https://github.com/tjdwls101010/Codex-in-Claude/security) of this repository.
2. Click **"Report a vulnerability"**.
3. Fill in the advisory form. This opens a private discussion visible only to you and the maintainer.

This project is particularly interested in reports involving:

- **Sandbox or permission escalation** — a run started with `--sandbox read-only` (or under `--ignore-user-config` isolation) gaining broader filesystem or network access than it was granted, across a `resume` or otherwise.
- **Process-group / `stop` handling** — `stop` signaling or affecting a process it doesn't own.
- **Run registry (`.codex-runs/`) tampering** — anything that lets a run's recorded settings be read or altered by another process or session in a way that changes what gets re-asserted on the next turn.
- **Command injection** in how `codex_bridge.py` constructs or passes arguments to the underlying `codex` CLI.

## What to Include

To help triage quickly, include:

- The command(s) you ran, including flags (redact anything sensitive).
- What you expected to happen versus what actually happened.
- The `codex_bridge.py doctor` output, if relevant (CLI version, sandbox config, resolved paths).
- Whether the issue is reproducible, and the minimal steps to reproduce it.

## Response Expectations

This is a solo-maintained, early-stage (pre-1.0) project. There's no guaranteed SLA, but reports are triaged as they come in and acknowledged as soon as possible. Once a fix is available, a coordinated disclosure timeline will be agreed with the reporter before any public advisory or release notes go out.
