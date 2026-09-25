---
name: codex
description: >-
  Hand non-interactive work to the local Codex CLI (GPT models) and manage it like a subagent: start runs in the background, continue their threads, watch, stop and redirect them, run several as one group, and collect text or schema-shaped JSON results. Use when work is being delegated to Codex or GPT, when a second, independent model should review or verify something, when an agent should keep working while Claude does something else, when an earlier Codex thread should be continued, or to diagnose the local Codex CLI. Triggers include: codex, 코덱스, 코덱스로, 코덱스한테, 코덱스에게, GPT한테, GPT에게 시켜, delegate to codex, ask codex, resume codex. Not for general questions about GPT, OpenAI or their API; not Claude's own subagents, the Task tool or background Bash; not Codex Cloud, `codex mcp-server` or `app-server`.
allowed-tools:
  - Bash(python3 "${CLAUDE_SKILL_DIR}/scripts/cli_codex.py" *)
---

# Codex as a managed subagent

Call it as `python3 "${CLAUDE_SKILL_DIR}/scripts/cli_codex.py" <command> …`, written out in full on one line: the pre-approval matches the command text, so a path kept in a shell variable or a command continued with `\` asks for permission every time. `--help` lists the commands, and `<command> --help` owns every flag, default, refusal and output shape.

## Handing work over

**Pick the sandbox by what you hand over:** `read-only` to review, investigate or answer; `workspace-write` when the run should change files. Loading your own Codex config is a separate decision (see Gotchas).

**`resume` or a fresh `start`.** A resumed thread brings what it already worked out and replays a transcript that grows every turn; a fresh start knows nothing. Continue when the new work builds on the old understanding; start fresh when it doesn't, because an unrelated task then pays to read past context it has no use for.

**A verification loop stops on a predicate the work can satisfy.** "Until nothing new comes back" never ends: each new look finds something, so that count comes from the examiner, not from the work. Stop on something the work runs out of — no finding reachable in ordinary use, a named property that holds, a `--schema` answer over a set you can bound. Continue the reviewer's thread when its earlier findings and the ones you rejected matter to the next round, since a fresh reviewer reopens what you closed; start fresh when they don't.

**Against your own instruments:**

| Yours | Here | Not available |
|---|---|---|
| `Agent` | `start`, a background `log --run <id> --follow`, then `result` | — |
| `Workflow` `parallel()` | `batch start` with several `--task` | runs calling or messaging each other |
| a next stage | `batch start --resume-from <group>` once every member has finished | a stage that starts itself: each round is computed and started from your context |

## Several runs at once

A batch is for when N runs should be one name you watch, collect and stop — a read-only fan-out included.

**Decide isolation when you start.** Members share your tree by default, as your own subagents do; when two can edit the same files, start them with `--worktree`. Only a fresh start gets a checkout: a resumed member continues in its thread's directory, so members that shared your tree go on sharing it.

**A worktree is a committed snapshot.** It has none of your uncommitted changes and none of what git ignores — interpreters, fixtures, caches. Check that a task has what its verification needs; the reply's `missing_ignored` names what is absent.

**Rounds:** `--resume-from` continues each member's thread with the next round's prompts, written in advance or computed from the last results; choose it over a new batch by the same test as `resume` over `start`.

**A group outlives the session.** Its name is the one thing nobody can re-derive, and `status` lists the project's groups. Collect with `result --group`; moving changes out of worktrees into your tree is yours to do; finish with `batch clean`.

## Waiting and collecting

**A detached run announces nothing.** Right after `start` or `batch start`, put a follower in a background Bash call: `log --run <id> --follow`, or `status --group <name> --follow` for a group. It exits when the work ends, and that exit notifies you. Then use the turn for other work or hand it back; don't invent work to fill the wait.

**Ended is not collected.** Take `result`, then check the claims and changes that matter before relying on them.

**If this is your only turn** — nothing will wake you later — make a foreground follow the turn's last call, with the Bash call's own timeout set above `--follow-timeout`, then take `result`. If the budget runs out first, hand back the run id and say the work is unfinished.

**Per-event notifications**, worth it only when you would act mid-run (stop a run going wrong, move members on as each lands), come from Monitor running the follower. Monitor ends at its own deadline and that end reads like the run's; set it longer than the run and re-arm it when it expires.

`status` answers whether a run is live and how far along, `log` what it is doing (incrementally with `--since`), `result` what it concluded.

## Context discipline

`log`'s default level replaces each command's output with its size and item id, because the agent's own messages, never filtered, usually say what the output showed. Raise `--level` when a command failed and the agent's account is not enough to act on; use `show --run <id> --item <item>` to check a summary against the output it summarises.

## Gotchas

- A project's `AGENTS.md` reaches every run, isolated or not: a standing briefing, and also input you did not write into the prompt.
- `--inherit-config` loads your config's MCP servers, plugins and agent roles. Use it when the run needs one of them, not as a precaution.

## When something goes wrong

- `doctor` checks the environment a run would start in and spawns nothing. A run that fails right after starting says why in `status --run <id>` (`error`, `stderr_tail`).
- Auth that works in your terminal but not here: first compare `doctor`'s `codex_home` with the terminal's, since two environments resolving different `CODEX_HOME`s is the likeliest cause.
- What a turn actually ran under is in its rollout, `$CODEX_HOME/sessions/**/rollout-*-<thread_id>.jsonl`: one `turn_context` line per turn with its sandbox, model, effort and cwd.
- If the command itself is not found, the skill's path did not resolve: `ls "${CLAUDE_SKILL_DIR}/scripts"`.
