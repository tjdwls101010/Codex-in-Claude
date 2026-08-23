---
name: codex
description: >-
  Run OpenAI Codex (the `codex` CLI, GPT models) as a managed subagent from Claude Code —
  start work in the background and get a run handle back immediately, watch its live event
  log at a controlled level of detail, interrupt and redirect a run, resume any earlier
  Codex thread including ones started in the Codex TUI, and collect results as text or
  schema-validated JSON. Use whenever work is being handed to Codex or GPT, when a second
  independent model should look at something, when an external agent should keep working
  while Claude does something else, or when an earlier Codex session needs continuing.
  Also covers Codex CLI setup, auth, sandbox and config diagnosis. Triggers include: codex,
  코덱스, 코덱스로, 코덱스한테, 코덱스에게, GPT, GPT한테, GPT에게 시켜, delegate to codex,
  run with codex, ask GPT, resume codex. Not for Claude's own subagents, the Task tool, or
  background Bash — those are Claude doing the work itself. Not for Codex Cloud or
  `codex mcp-server` / `app-server`.
allowed-tools:
  - Bash(python3 "${CLAUDE_PLUGIN_ROOT}/.claude/skills/codex/scripts/codex_bridge.py" *)

---

# Codex as a managed subagent

One CLI wraps the whole surface. Your context already carries a line reading **`Base directory for this skill: <dir>`** — the bridge is `<dir>/scripts/codex_bridge.py`. Use that absolute path, double-quoted, in every call:

```bash
python3 "<base directory>/scripts/codex_bridge.py" status
```

Below, `$CODEX` is shorthand for that literal `python3 "<base directory>/scripts/codex_bridge.py"` — write it out in full when you run it.

**Do not build the path from an environment variable.** `$CLAUDE_PLUGIN_ROOT` and `$CLAUDE_SKILL_DIR` are both empty in the Bash environment, even for a plugin install — `$CLAUDE_PLUGIN_ROOT` is expanded in permission rules, which is a different layer from the process environment. And because this skill's pre-approved permission pattern matches the command *text*, a call written as `python3 "$SOMEVAR/…"` is not covered by it and raises an approval prompt every time, which is exactly what makes background work unusable.

**Write each call on one line.** The same text matching means a command broken across lines with a trailing `\` does not match the pattern either, and gets refused. This bites where it is least convenient: `batch start` with several `--task` flags is long, long commands invite line continuations, and a refused `batch start` is the whole batch.

`$CODEX --help` lists the commands. `$CODEX <command> --help` is the option surface — every flag, its default, what it refuses and why. None of that is repeated below: a second copy is a second thing that can be wrong, and this one already was, by seven flags.

## Which mode

Deciding *what* to hand to Codex is yours; nothing here knows the task. Deciding *which shape* to hand it in is mechanism — and it is the one thing `--help` cannot tell you, because each of these is a comparison *between* commands and no single command knows about the others.

**`review` or `start`.** `review` comes back with findings on a diff and cannot be redirected mid-turn into fixing what it found. So: `review` when you want a verdict *you* will act on, `start` when you want the change made. If you are planning to review and then apply, that is two phases, not one review.

**`resume` or a fresh `start`.** A resumed thread keeps what it already worked out and replays a transcript that grows every turn — measured on one thread, input tokens roughly doubled per turn for the first few. A fresh thread pays Codex's base-instruction floor once and knows nothing. Continue when the new work depends on the old understanding; start fresh when it does not, because the replay is not free and an unrelated task inherits a context it has to read past. Judge it per thread; there is no threshold worth memorising.

**One run or a batch.** `batch start` buys one thing: N runs become one name, so watching, collecting and stopping are each one call instead of N. Reach for it the moment you would otherwise be tracking several run ids by hand. What it costs is N base-instruction floors, where N turns on one thread pay one floor plus that growing replay — so parallel wins when the work is genuinely independent, and one thread wins when each step needs what the last one learned.

**One batch or two phases.** `--resume-from` is for work whose second half depends on the first half's *result* — audit, then fix what the audit found. If you can write both prompts now, it is one prompt: a phase boundary you did not need costs a full turn of replay per member.

**`status`, `log` or `result`** answer three different questions, and reaching for the wrong one is how a caller ends up polling something that was never going to change. Is it alive and how far along; what is it doing, incrementally, without re-reading what you have seen; what did it conclude. A finished run needs `result`, not more `log`.

There is no channel into a turn that is already running, so redirecting one is stop then resume:

```bash
$CODEX start --label refactor "…"             # → run_id, thread_id, immediately
$CODEX log --run <id> --since 0               # → events + "# cursor=4213"
$CODEX log --run <id> --since 4213            # → only what is new
$CODEX stop --run <id>                        # if it is going wrong
$CODEX resume <id> "Stop rewriting tests — …" # correct it, same thread
$CODEX result --run <id>                      # what it concluded
```

## Context discipline

**One field ambushes you: `command_execution.aggregated_output`.** It carries a command's whole stdout, so a run that `cat`s a 2,000-line file puts that file in your context. The agent's own messages are unbounded too, but those are the answer you asked for; this is a byproduct of getting it. `file_change` events carry paths and a kind, never contents, and are always cheap.

So the default filter level withholds command output and reports its size instead:

```
cmd[item_2] exit=0 out=8797B rg -n "" tests . --glob '*.py'
```

That byte count is there so fetching output is a decision rather than a guess: `show --run <id> --item item_2` returns exactly that one command's output and nothing else's.

This works because the agent's own account of what it found and did is never filtered, at any level — so the withheld bytes are usually a second copy of a summary you already have. `log --help` says what each level includes; what it cannot say is when to leave the default. Raise it when a command failed and the agent's account of the failure is not enough to act on, which is the one case where the withheld bytes are the diagnosis rather than a copy of it. And reach for `show` when you need to *check* a summary rather than read it — a claim looks wrong, or a run stopped without explaining itself.

## Gotchas

**A project's `AGENTS.md` reaches an isolated run.** Isolation drops the user's config, plugins and MCP servers; the repository's own `AGENTS.md` is still injected verbatim as a developer instruction. That cuts both ways. It is a briefing channel that survives isolation — the one way to give an isolated run standing project instructions without pasting them into every prompt. It is also uncontrolled input: whatever is in it is in every run you start there, intended or not. If a run behaves in a way its prompt does not explain, read it.

**Isolation buys a clean stream. What it saves in tokens is not a number, and do not quote one.** The clean stream is the reliable half: an inherited-config run on a machine with a malformed user config emits config-error events before it does any work, and has been observed leaking an unrelated plugin advertisement into the agent's own message. The saving is the unreliable half — the same prompt on the same machine measured a 2.9× difference during design and 1.09× two weeks later, because the delta is whatever the user's config happens to load at that moment and an MCP server that fails to start contributes nothing. So reach for `--inherit-config` when a run genuinely needs a tool that only exists in the user's config, a specific MCP server or a custom agent role. "To be safe" is not a reason, and if the cost matters to a decision, measure this machine rather than budgeting from someone else's ratio.

**Only `batch start` can isolate writers — `resume` cannot.** A resumed run takes its directory from its thread, and there is no `--worktree` on `resume`. So continuing three writing threads with three `resume` calls puts three writers in one directory, editing at once, which is the collision worktrees exist to prevent. Measured in an e2e session: it did precisely this and escaped only because the three edits happened to land in three different files. To continue several writers at once, use `batch start --resume-from <group>`. You do not have to spot this yourself either — a writing run started into a directory another live writing run already occupies comes back with `concurrent_writers` naming them, and `doctor` reports the same across the registry — but that report arrives after the spawn, and the decision is before it.

## Collecting a batch

**A batch is not delivered until you have collected it, and how you wait depends on whether you get another turn.** `batch start` returns as soon as the members are spawned; the work is in `result --group`, which is a separate call you have to make.

If more turns are coming, run `status --group <name> --follow` beside you and pair it with the **Monitor** tool, so each line becomes a notification and you collect when it fires. If this is your only turn, that pairing is exactly wrong — the follower dies with the turn and nothing arrives. Two measured e2e sessions failed there: both started their batch correctly, launched a background wait, then ended the turn saying they would report back, and nothing ever resumed them. With one turn, run the same follow in the **foreground** so the call blocks until the group ends, bounded by `--follow-timeout` because the Bash tool stops at 600 seconds.

Either way, never end a turn on a promise. Say what you have, or wait for it.

A batch also outlives the session that started it, and `status` is how a later session finds one it did not start — the group name is the one thing about a batch nobody can re-derive.

## Troubleshooting

Run `$CODEX doctor` first; it reports the whole environment in one line and exits non-zero when something will actually stop a run. Two things it cannot help with:

- **`No such file or directory` on the bridge itself.** The path is wrong, and `doctor` cannot diagnose it because `doctor` is the same script. The `Base directory for this skill:` line in your context is the answer; `ls "<base directory>/scripts/"` confirms it.
- **Auth that works in your terminal but not from here.** `CODEX_HOME` differs between the two environments. Compare `doctor`'s resolved value against `echo $CODEX_HOME` in the shell where it works.

Two more worth knowing where to look:

- **A run behaving in a way its prompt does not explain** — read the project's `AGENTS.md`, per the gotcha above.
- **What a turn actually ran under.** The rollout file at `$CODEX_HOME/sessions/**/rollout-*-<thread_id>.jsonl` appends one `turn_context` line per turn recording the sandbox policy, model, effort and cwd that turn really used. That is the authoritative record, and far better than grepping the developer message; `codex exec resume` appends to the same file rather than starting a new one.

A run in a Korean or spaced path is not a category of problem: APFS returns NFD while argv carries NFC, and the bridge normalises at every boundary. If you see that surface anywhere, it is a bug worth reporting.
