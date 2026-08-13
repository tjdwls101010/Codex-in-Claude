# Running several Codex runs as one group

This file is mechanics and traps. It does not say which work to parallelise, how many ways to split it, or what shape the phases should take — you decide that per task, with more context about the task than this file could ever have. What it can tell you is what the commands actually do, what they cost, and which of their behaviours will surprise you.

## The group

A group is a set of runs started by one `batch start` and addressable afterwards as one thing:

```bash
$CODEX batch start --group review-p1 --task "audit the parser" --task "audit the lexer"
$CODEX status --group review-p1
$CODEX result --group review-p1
$CODEX stop   --group review-p1
$CODEX batch clean --group review-p1
```

**A group name is single-use within a project.** A second `batch start --group review-p1` fails rather than adding to the group, and it fails before starting anything. The reason is that "the members of review-p1" has to mean one list in one order — `--resume-from` pairs against exactly that list positionally, and a name that accumulated members across two invocations would silently pair the wrong ones. The name is released by `batch clean` once nothing is left behind, and that is also how you reclaim a name from a `batch start` that died partway through.

Membership is recorded in `.codex-runs/.groups/<name>.json` in start order, and each member's own `meta.json` records its group as a fallback.

**A later session can find a batch it did not start**, which is the case that matters — a group's whole value is being addressable after the context that created it is gone. `status` lists the project's `groups`, and every run row carries the `group` it belongs to (and its `worktree`, when it has one). That is what makes `status --group` and `--resume-from` reachable from a cold start; without it a recovering session sees N unrelated runs and no name to pass.

A member that failed to spawn keeps its slot in the manifest with an `error` and no `run_id`, so the caller sees which task is missing rather than a shorter list than they asked for. Those slots stay visible afterwards too: `status --group` and `result --group` list them under `unstarted`, and they make the group `partial` rather than `completed`.

**One failing member does not take the batch down.** Whatever the failure — a schema path that does not exist, a bad value in a tasks file, a full disk — it is recorded in that member's slot and the rest still start.

## Tasks

`--task "<prompt>"` is repeatable and always starts a new thread. `--tasks-file <jsonl>` takes one JSON object per line for anything a bare prompt cannot express; both may be given, and `--task` entries come first because that is the order they were typed.

Per-item fields: `prompt`, `kind` (`start`, `resume`, `review`), `label`, `model`, `effort`, `sandbox`, `schema`, `image`, `cwd`, `resume`, `review`. Group-level options are **defaults, not constraints** — a batch is usually the same thing N ways, and the per-item fields are how the exceptions get said:

```jsonl
{"prompt": "audit the parser", "label": "parser"}
{"prompt": "audit the lexer",  "label": "lexer", "sandbox": "read-only"}
{"kind": "review", "review": {"uncommitted": true}}
```

An unknown field name, or a field with the wrong type, fails the whole command **before anything starts** rather than being ignored. A silently ignored field means a run that quietly used the group default instead, and nothing downstream could notice.

## Phases: `--resume-from`

```bash
$CODEX batch start --group p2 --resume-from p1 --task "now write the fix" --task "now write the fix"
```

Task *i* continues member *i* of `p1`, in the manifest's start order, keeping that thread and the directory it already lives in. The rules, all of which are refusals rather than guesses:

- **One task per started member.** A count mismatch fails before anything starts, because pairing a short list lands a phase-2 task on the wrong phase-1 thread and every member after the mismatch continues work it was not written for.
- **Every member must be resumable.** A phase-1 member whose Codex died before opening a thread has a run id and a terminal state but no conversation; it is refused by name rather than producing a `codex exec resume` with nothing to resume.
- **No live members.** Two turns on one thread race on the same rollout file. Checked for the whole group up front, so you never get a phase 2 half-started against a phase 1 half-finished. `--as-ready` below is the way to lift this one without lifting the invariant under it.
- **A task may name its own target** with `kind: resume` and a `resume` field, and keeps it. A `resume` field on a `kind: start` task is a contradiction and is refused; so is a `kind: review` task, which cannot be a continuation.

Phase 2 inherits phase 1's worktrees — it does not get new ones — and the new group records `derived_from`, which is what makes `batch clean --group p1` refuse while phase 2 is still living there.

### `--as-ready`: start each member as its own predecessor finishes

```bash
$CODEX batch start --group p2 --resume-from p1 --as-ready --tasks-file p2.jsonl
```

The barrier above waits for the *slowest* member of `p1`, which is a group-shaped answer to a thread-shaped question. One turn per thread is the actual invariant, and member 3's phase 2 is safe to begin the moment member 3's phase 1 is done, whatever member 1 is still doing. `--as-ready` starts each member exactly then. Without it, `--resume-from` behaves as it always has.

- **Any terminal state releases a member**, including a failure — the barrier does not look at phase 1's success either, and "work out what went wrong here" is a legitimate phase-2 task. How the predecessor ended is recorded as `predecessor_state`, so the task can tell.
- **A waiting member is `state: "waiting"`**, with `waits_for` naming the run it is behind. `waiting` is not terminal, which is what keeps a third turn off that thread while the member sits there.
- **`--timeout` bounds the Codex turn, never the wait.** `stop --group` is what ends a wait, and it reaches a waiting member like any other.
- **A wait is unbounded on purpose.** If a predecessor never finishes, its successor never starts; nothing times it out. Stopping the predecessor group releases the waiters rather than cancelling them, since `interrupted` is terminal — stop both groups if that is not what you want.

Not compatible with `--force`, which is the opposite instruction (start now, accept two live turns on one thread), or with a `--resume-from`-less batch, where there is no predecessor for anything to wait on. Both combinations are refused before the group name is claimed.

There is no queue and no group supervisor here: each member spawns its own supervisor immediately, exactly as it would have, and that supervisor waits before it starts Codex. A queued run with nothing supervising it is reaped as `orphaned` within thirty seconds, which is why the earlier `--max-concurrent` idea was abandoned.

**Continuing several writing threads with individual `resume` calls is not the same thing, and it is not safe.** `resume` has no `--worktree`, and a resumed run takes its directory from its thread — so three `resume` calls put three writers in one directory, editing at once, which is the collision worktrees exist to prevent. `--resume-from` is the only path that can isolate them, because only `batch start` assigns worktrees. Measured: an e2e session continued three threads this way and escaped damage only because the three edits happened to land in three different files.

You do not have to notice this yourself. A writing run started into a directory another live writing run already occupies comes back with `concurrent_writers` naming them and `concurrent_writers_note` pointing here, and `doctor` reports the same across the registry. It is a report and never a refusal (D17) — sharing a directory is sometimes exactly what you meant — but it is a fact the caller otherwise has no way to see.

## Worktrees

**Two or more members that can write get a git worktree each**, at `.codex-runs/<run_id>/wt`, detached at HEAD (or `--base <ref>`). `--worktree` forces it for a lone writer, `--no-worktree` turns it off.

Process groups isolate *signals*, not files. Two runs in one directory edit the same files and neither can tell another agent's change from its own; a worktree is what turns that from corruption into a merge you do later. The traps:

- **A fresh worktree has zero uncommitted changes.** This is measured, and it is why `read-only` members and `kind: review` members never get one: the uncommitted work a reviewer was started to look at lives only in your tree, so a reviewer inside a worktree reviews nothing.
- **Members' results are not in your tree.** They are uncommitted changes inside each worktree. `result --group` reports `files_changed` per member and `overlaps` across them; collecting the actual content is yours to do.
- **`--base` older than HEAD can drop your project instructions.** `AGENTS.md` reaches a worktree run, but only from a base where the file exists. `batch start` compares and says so when they differ.
- **An explicit `cwd` wins.** A per-item `cwd` is a decision you already made, and an inferred default does not overrule it. `kind: resume` members inherit their thread's directory.
- **Your own tree is untouched.** `.codex-runs/.gitignore` is `*`, so `git status` in the main tree stays clean even while eight worktrees hold modified files.

`batch clean --group <name>` removes them, and refuses without `--force` if the group has live members, if another run is still working inside one of the worktrees, if a group derived from this one exists, or if a worktree holds uncommitted changes — that last one is git's own refusal, reported back to you. **`--force` lifts all of them at once**, not only the one you were after; the result says what it overrode, and none of it is recoverable.

## Watching a group

`status --group <name> --follow` prints one line per tick and a terminal line — `group.completed`, `group.partial`, or `group.still-running` if `--follow-timeout` expires first. Pair it with the **Monitor** tool rather than a foreground Bash call: Bash caps out at 600 seconds and a batch can outlive that, and Monitor turns each line into a notification instead of a poll.

`--follow` is a pure view. It holds no state, and everything it prints is re-derived from the registry — a follower that dies loses nothing, and `status --group` answers the same question at any time.

**Which way you wait depends on whether you get another turn.** Pairing with Monitor is right when more turns are coming: the follower runs beside you and each line becomes a notification. It is wrong when this is your only turn, because the follower dies with the turn and nothing arrives. Two measured e2e sessions failed exactly there — both started their batch correctly, launched a background wait, then ended the turn saying they would report back, and nothing resumed them to do it. With one turn, run `status --group --follow --follow-timeout <sec>` in the **foreground** so the call blocks until the group ends; the Bash tool's 600-second ceiling is the real limit on that, and `group.still-running` is what you get if the deadline arrives first.

Either way, **`batch start` returning is not the batch being done, and the group finishing is not the results being collected.** `result --group` is a separate call. Ending a turn on "I'll report when it finishes" produces nothing at all.

`group_state` is `completed` when every member reached a terminal state successfully, `partial` when some did not, `running` otherwise. Note that `partial` is also what you get after `stop --group`: it means "not all members succeeded", not "Codex failed".

## Collecting

`result --group <name>` returns each member's final message capped at 4,000 bytes with the true size stated, plus `usage`, `files_changed`, and **`overlaps`** — the paths that more than one member wrote, keyed by run.

`overlaps` is the intersection only, deliberately. A full path list per run inverts the context discipline this skill exists for, and `log` already prints `file_change` paths for anyone who wants them; what nobody can derive cheaply is which paths two runs both touched. Under worktree isolation an overlap is **a merge conflict ahead, not damage already done** — the runs wrote to separate checkouts. Without worktrees, it is damage already done.

For one member's full message, `result --run <id>`.

## What a batch member is told, and why `--no-preamble` is not free here

A batch member's prompt carries an extra paragraph: that it is one run in a batch of N launched together under a group name, that other runs may be executing alongside it, and — when isolated — its worktree's path, that worktree's base commit, and how many uncommitted files exist in the caller's tree that it does not have.

Measured, and the measurement is the reason this matters more than it sounds. Asked what tree it was in, a run **without** that paragraph answered *"it is the shared workspace with the person who started me, so we are looking at the same tree"* — wrong, and asserted rather than hedged. **With** it, the same run answered correctly and reasoned about the others from N−1. Cost: 113 input tokens against a ~16k context.

So the failure it prevents is **fabrication, not omission**. A run that merely lacked the fact could say it did not know; what actually happens is that it fills the gap confidently, and every conclusion downstream of that is built on a false premise about which tree it is looking at. `--no-preamble` removes this along with the base preamble — reach for it only when you are supplying these facts yourself.

## What it costs

Each run pays Codex's isolation floor separately. **N parallel runs pay N floors**, where N turns on one thread pay one floor plus a replay that grows every turn. Neither is always cheaper: parallel wins when the work is genuinely independent, one thread wins when each step needs what the last one learned.

`batch start` reports a `projected_cost` computed from this project's own recent completed isolated runs — the median of their input tokens, times the number of members. It is `null` below three samples, because a median of one or two runs is not a median, it is one run's number wearing the word; three is the smallest sample where an outlier does not become the answer. It looks at the last ten, so it tracks the project as it is now rather than as it was. It is **a scale, not a bound, and it is reported rather than enforced**. It was called a floor until that was checked against the registry it comes from: 6 of 11 real runs were below it, which is what a median does. About half will be under and half over, and a resume grows from there. Re-measure rather than budgeting from it. A constant measured at design time in this project moved by a factor of 2.7 within two weeks, which is why there is no constant here.

Concurrency was measured at N=1–8 and again at 12, 16 and 24: no sqlite contention, no thread-id collisions, every member completing, and `batch start` returning in about 0.29 s per member — the 15-second thread-id wait is a ceiling for a slow member, not a toll every member pays. Above 24 is unmeasured, and so is a batch that wide doing heavy work, since a trivial prompt's turn is dominated by round-trip latency rather than by anything that queues.

## From a dynamic workflow

A workflow's `agent()` can drive these commands directly with Bash; a subagent does **not** need to load this skill first, and that is measured. Give the agent the absolute bridge path in its prompt, since a subagent has no `Base directory for this skill:` line of its own.

Workflow scripts cannot run shell commands themselves — only agents can. So one Codex run per workflow agent means paying for a Claude agent and a Codex run per worker. `batch start` from a single agent starts N Codex runs for one Claude agent, which is usually what you want; reach for one-agent-per-run when each run needs a Claude in the loop reading its output as it goes.
