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

**The pre-approved permission pattern matches the command *text*, so two ways of writing a correct call are refused.** A path built from a variable — `$CLAUDE_PLUGIN_ROOT` and `$CLAUDE_SKILL_DIR` are both empty in the Bash environment anyway, even for a plugin install, because the former is expanded in permission rules rather than in the process — raises an approval prompt every time, which is what makes background work unusable. And a command broken across lines with a trailing `\` does not match either. That second one bites where it is least convenient: `batch start` with several `--task` flags is long, long commands invite continuations, and a refused `batch start` is the whole batch.

`$CODEX --help` lists the commands. `$CODEX <command> --help` is the option surface — every flag, its default, what it refuses and why. None of that is repeated below: a second copy is a second thing that can be wrong, and this one already was, by seven flags. What is below is the other kind — what these commands are *for*, how they compare with each other, and how they line up against instruments you already have. No single `--help` can reach any of that, so leaving it out is not deferring to the tool; it is dropping it.

## Which mode

Deciding *what* to hand to Codex is yours; nothing here knows the task. Deciding *which shape* to hand it in is mechanism — and it is the one thing `--help` cannot tell you, because each of these is a comparison *between* commands and no single command knows about the others.

**`review` or `start`.** `review` comes back with findings on a diff and cannot be redirected mid-turn into fixing what it found. So: `review` when you want a verdict *you* will act on, `start` when you want the change made. If you are planning to review and then apply, that is two phases, not one review.

**`resume` or a fresh `start`.** A resumed thread keeps what it already worked out and replays a transcript that grows every turn — measured on one thread, input tokens roughly doubled per turn for the first few. A fresh thread pays Codex's base-instruction floor once and knows nothing. Continue when the new work depends on the old understanding; start fresh when it does not, because the replay is not free and an unrelated task inherits a context it has to read past. Judge it per thread; there is no threshold worth memorising. A thread this skill never started — one left behind in the Codex TUI — is a third option and reachable, but only once you can name it: `status --include-external` is what lists those, and what `resume` then requires before it will touch one is in `resume --help`.

**Two axes decide the rest.** *How many runs, and how you address them.* One is `start`; several is `batch start`, which puts N runs under one name so watching, collecting and stopping are one call each instead of N — a read-only fan-out counts, because the reason is addressing rather than writing. Members share your tree the way a fan-out of your own subagents does; `--worktree` is for when they would edit the same files. What N runs cost is N base-instruction floors, where N turns on one thread pay one floor plus a transcript that replays and grows every turn.

*And whether anything has to be computed between rounds.* If every round's prompts can be written down before the round before it returns, `--resume-from` carries them — and a phase boundary you did not need costs each member a full turn of that replay. If round two's prompts come *from* round one's results — deduplicated against everything seen so far, filtered by a verdict, repeated until a round comes back empty — that is a program, and it runs in your own context between two batches, or in a workflow.

**Against the instruments you already have.** They are the control, not the norm: where the correspondence runs out, change the shape of the work rather than simulating the missing half.

| Yours | The close equivalent here | The extra premise | No equivalent |
|---|---|---|---|
| `Agent` | `start`, a background `log --run --follow`, then `result` | you choose a sandbox, and the wake-up is a follower you armed rather than the harness holding your turn | — |
| `Workflow` | `--task` repeated ≈ `parallel()`, `--as-ready --resume-from` ≈ `pipeline()`, `--schema` ≈ a stage's `schema`, `--worktree` ≈ `isolation: 'worktree'`, and a `--tasks-file` entry takes `model` and `effort` the way `agent()` does | every phase boundary replays each member's whole transcript | round two computed from all of round one — the second axis above, and it happens in your context |
| an agent team | `resume` keeps a thread's context across rounds; `--resume-from` runs the rounds | a message into a turn already running is `stop` then `resume`; there is no channel into one | members addressing each other, and a shared board — a run knows only that N-1 others exist, from its preamble |

**`status`, `log` or `result`** answer three different questions, and reaching for the wrong one is how a caller ends up polling something that was never going to change. Is it alive and how far along; what is it doing, incrementally, without re-reading what you have seen; what did it conclude. A finished run needs `result`, not more `log`.

There is no channel into a turn that is already running, so redirecting one is stop then resume:

```bash
$CODEX start --label refactor "…"              # hand the work over
$CODEX log --run <id> --follow --level compact # arm it, in a background Bash call
$CODEX log --run <id> --since <cursor>         # only to look in mid-run
$CODEX stop --run <id>                         # if it is going wrong
$CODEX resume <id> "Stop rewriting tests — …"  # correct it, same thread
$CODEX result --run <id>                       # what it concluded
```

## Arming a wait

**What is forbidden is not the wait. It is a wait that wakes nobody.** The run goes on without you and says nothing when it stops, so something has to be holding a line that ends when the run does.

**The idiom, the moment `start` comes back:** put `log --run <id> --follow --level compact` in a **background Bash** call. It exits on the run's last line, and a background Bash call that exits notifies you — which is the contract the Agent tool gives you for a subagent, and what "Codex as a managed subagent" was always supposed to mean. *Then* decide what to do with the turn. Genuinely parallel work, do it. No parallel work, hand the turn back armed and say so — do not invent work to fill the wait, which spends tokens nobody asked for and, in its most obvious form, walks into the concurrent-writer gotcha below. Arming costs nothing and is safe at any moment: aimed at a run that is already over it prints the last line and exits at once.

The follower's own text goes to a file the notification names — `Read` it when the notification lands. `--since` is for looking in mid-run, not for the wait: a poll you have to remember to repeat is an unarmed wait wearing a different hat.

**Exception — this is your only turn.** If you cannot name the thing that would wake you, this is a one-turn context, and arming is useless whichever instrument you reach for: a background follower and a Monitor both die with the turn. Do any parallel work first, then make the turn's *last* call a blocking foreground `--follow`, bounded by `--follow-timeout`, because a foreground Bash call stops at 600 seconds. Two measured sessions ended on a promise instead — one had armed a follower, the other a Monitor.

**One notification or one per event.** One at the end is the default, and it is a background `--follow`. Take one per event when there is something you could *do* mid-run — stop a run that is going wrong, move a batch's members onward as each lands — and the run is longer than the delay of making that judgement. That is the **Monitor** tool, with `persistent: true`, because its default lifetime is five minutes, a Codex run routinely outlasts that, and the expiry announces itself in a way that reads like an ending. `--heartbeat` belongs under a per-event watcher and nowhere else: only there does a follower with nothing to say look like a follower that died.

**A batch is the N-case, not a different rule.** `status --group <name> --follow` is the line that ends when the group does, `log --group <name> --follow` is the same line with the members' events interleaved rather than only their state changes, and `result --group <name>` is what collects it. One thing about a batch genuinely is different: it outlives the session that started it, and `status` is how a later session finds one it did not start — the group name being the one thing about a batch nobody can re-derive.

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

**Isolating writers is decided when a group is started, and cannot be decided later.** A resumed run takes its directory from its thread and there is no `--worktree` on `resume`, so `batch start --worktree --resume-from` cuts nothing either: continuing three writing threads puts three writers in one directory whichever command does it. Measured in an e2e session, which escaped only because the three edits happened to land in three different files. You do not have to spot it yourself — a writing run started into a directory another live writing run already occupies comes back with `concurrent_writers` naming them, and `doctor` reports the same across the registry — but that report arrives after the spawn, and the decision is before it.

**A worktree holds only what git tracks.** The reply names which of your gitignored entries the checkouts do not have; what it cannot tell you is the consequence. A run whose canonical interpreter or fixture directory is missing cannot execute the verification it was asked for, and one that rebuilds its own cache gets live data and reports every comparison against the recorded baseline as a regression.

## Troubleshooting

Run `$CODEX doctor` first; it reports the whole environment in one line and exits non-zero when something will actually stop a run. Two things it cannot help with:

- **`No such file or directory` on the bridge itself.** The path is wrong, and `doctor` cannot diagnose it because `doctor` is the same script. The `Base directory for this skill:` line in your context is the answer; `ls "<base directory>/scripts/"` confirms it.
- **Auth that works in your terminal but not from here.** `CODEX_HOME` differs between the two environments. Compare `doctor`'s resolved value against `echo $CODEX_HOME` in the shell where it works.

Two more worth knowing where to look:

- **A run behaving in a way its prompt does not explain** — read the project's `AGENTS.md`, per the gotcha above.
- **What a turn actually ran under.** The rollout file at `$CODEX_HOME/sessions/**/rollout-*-<thread_id>.jsonl` appends one `turn_context` line per turn recording the sandbox policy, model, effort and cwd that turn really used. That is the authoritative record, and far better than grepping the developer message; `codex exec resume` appends to the same file rather than starting a new one.

A run in a Korean or spaced path is not a category of problem: APFS returns NFD while argv carries NFC, and the bridge normalises at every boundary. If you see that surface anywhere, it is a bug worth reporting.
