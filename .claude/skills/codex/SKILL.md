---
name: codex
description: >-
  Hand non-interactive work to the local Codex CLI (GPT models) and manage it like a subagent: start runs in the background, continue their threads, watch, stop and redirect them, run several as one group, and wait for and collect text or schema-shaped JSON results. Use when work is being delegated to Codex or GPT, when a second, independent model should review or verify something, when an agent should keep working while Claude does something else, when an earlier Codex thread should be continued, or to diagnose the local Codex CLI. Triggers include: codex, 코덱스, 코덱스로, 코덱스한테, 코덱스에게, GPT한테, GPT에게 시켜, delegate to codex, ask codex, resume codex. Not for general questions about GPT, OpenAI or their API; not Claude's own subagents, the Task tool or background Bash; not Codex Cloud, `codex mcp-server` or `app-server`.
allowed-tools:
  - Bash(uv run "${CLAUDE_SKILL_DIR}/scripts/cli.py" *)
---

# Codex as a managed subagent

Call it as `uv run "${CLAUDE_SKILL_DIR}/scripts/cli.py" <command> …`, written out in full on one line: the pre-approval matches the command text, so a path kept in a shell variable, a `$(…)` or a pipe added to the call, or a command continued with `\` asks for permission every time. Replies are made to be read as printed — an answer, a `--schema` answer and a run's status included — so no reply needs a pipe or a parser. `--help` lists the commands, and `<command> --help` owns every flag, default, refusal, output shape and exit code.

## Handing work over

**The sandbox decides what a run can do, and so what it can show you.** `read-only` reads anything and runs tests and builds — only temporary files and caches are writable — so a review or an investigation can bring back what it ran, not only what it read; `workspace-write` when the run must change files or leave output in the tree; `danger-full-access` only when it needs the network or to write outside its directory.

**A project's `AGENTS.md` reaches every run**, in a worktree as committed at its base: a standing briefing, and also input you did not write into the prompt.

**`resume` or a fresh `start`.** A resumed thread brings what it already worked out and replays a transcript that grows every turn; a fresh start knows nothing. Continue when the new work builds on the old understanding; start fresh when it doesn't, because an unrelated task then pays to read past context it has no use for.

**A verification loop stops on a predicate the work can satisfy.** "Until nothing new comes back" never ends: each new look finds something, so that count comes from the examiner, not from the work. Stop on something the work runs out of — no finding reachable in ordinary use, a named property that holds, a `--schema` answer over a set you can bound. Continue the reviewer's thread when its earlier findings and the ones you rejected matter to the next round, since a fresh reviewer reopens what you closed; start fresh when they don't.

**Against your own instruments:**

| Yours | Here | Not available |
|---|---|---|
| `Agent` | `start`, then its reply's `next.command` in the background, which prints the result when the run ends | — |
| `Workflow` `parallel()` | `batch` with several `--task` | runs calling or messaging each other |
| a next stage | `batch` with a `--tasks-file` of one `kind: resume` line per member, once every member has finished | a stage that starts itself: each round is computed and started from your context |

## Several runs at once

A batch is for when N runs should be one name you watch, collect and stop — a read-only fan-out included.

**Decide isolation when you start.** Members share your tree by default, as your own subagents do; when two can edit the same files, start them with `--worktree`. Only a fresh start gets a checkout: a resumed member continues in its thread's directory, so members that shared your tree go on sharing it.

**A worktree is a committed snapshot.** It has none of your uncommitted changes and none of what git ignores — interpreters, fixtures, caches. Check that a task has what its verification needs; the reply's `missing_ignored` names what is absent.

**Rounds:** a next round resumes each member's thread — a `--tasks-file` line per member with kind `resume` and its run id — with prompts written in advance or computed from the last results; choose it over a batch of fresh starts by the same test as `resume` over `start`.

**A group outlives the session.** Its name is the one thing nobody can re-derive, and `status` lists the project's groups. Collect with `result --group`; moving changes out of worktrees into your tree is yours to do; finish with `clean`.

## Waiting and collecting

**A detached run announces nothing.** Run the reply's `next.command` in a background Bash call, as given: it waits for that run, or for the group after `batch`, and prints its result, written the way the pre-approval matches. Its exit notifies you, and the output file the notice points to is the result. Then use the turn for other work or hand it back; don't invent work to fill the wait. **A result read is not a result checked:** check the claims and changes that matter before relying on them.

**If this is your only turn** — nothing will wake you later — run `next.command` in the foreground instead, with `--wait-timeout` added and the Bash call's own timeout set above it. If the budget runs out first, hand back the run id and say the work is unfinished.

## When something goes wrong

- `doctor` checks the environment a run would start in and spawns nothing. A run that fails right after starting says why in `status --run <id>` (`error`, `stderr_tail`).
- Auth that works in your terminal but not here: first compare `doctor`'s `codex_home` with the terminal's, since two environments resolving different `CODEX_HOME`s is the likeliest cause.
- What a turn actually ran under is in its rollout, `$CODEX_HOME/sessions/**/rollout-*-<thread_id>.jsonl`: one `turn_context` line per turn with its model, effort, cwd and permissions — a read-only turn's in `permission_profile`, since its `sandbox_policy` names the nearest legacy mode.
- If the command itself is not found: without `uv` nothing here runs, and installing it is the fix (it also provides the Python the skill needs); with `uv`, the skill's path did not resolve: `ls "${CLAUDE_SKILL_DIR}/scripts"`.
