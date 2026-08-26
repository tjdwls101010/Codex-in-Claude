# Orchestration

Running several Codex runs as one thing: what the batch commands do, what worktrees buy you, how a batch continues into a next phase, and what it all costs.

This page is mechanics. It deliberately doesn't tell you *which* work to parallelize or how many ways to split it — that depends on the task, and whoever is driving knows more about the task than this page could. See [CLI Reference §10–11](CLI-Reference.md#10-batch-start) for the exact flags.

## 1. Why a group and not N `start` calls

Nothing stops you running `start` five times. What you get from `batch start` instead is one name that addresses all five:

```bash
$CODEX batch start --group audit --task "audit the parser" --task "audit the lexer"
$CODEX status --group audit          # one call, not two
$CODEX status --group audit --follow # notified when the GROUP ends, not each member
$CODEX result --group audit          # capped messages + which paths both members wrote
$CODEX stop   --group audit          # all of them
$CODEX batch clean --group audit     # remove their worktrees once you've collected
```

And you get worktrees, which is the part you can't get by calling `start` five times.

## 2. Group names are single-use

A second `batch start --group audit` fails rather than adding to the group, and it fails before starting anything.

The reason is that "the members of `audit`" has to mean one list in one order. `--resume-from` pairs a next phase against exactly that list, positionally — a name that accumulated members across two invocations would silently pair the wrong ones, and every member after the mismatch would continue work it wasn't written for.

Membership lives in `.codex-runs/.groups/<name>.json`, recorded in start order, and written after **every** member rather than once at the end: a member that has spawned is a live process, and it has to be reachable through its group from the instant it exists. A member that failed to spawn keeps its slot with an `error` and no `run_id`, so you see which task is missing rather than a shorter list than you asked for.

`batch clean` releases the name once nothing is left behind. That's also how you reclaim a name from a `batch start` that died partway through.

## 3. Tasks

`--task "<prompt>"` is repeatable and always starts a new thread. `--tasks-file <jsonl>` takes one JSON object per line for anything a bare prompt can't express. Both may be given; `--task` entries come first, because that's the order they were typed.

```jsonl
{"prompt": "audit the parser", "label": "parser"}
{"prompt": "audit the lexer",  "label": "lexer", "sandbox": "read-only"}
{"kind": "review", "review": {"uncommitted": true}}
```

Group-level flags are **defaults, not constraints** — a batch is usually the same thing N ways, and the per-item fields are how you say the exceptions. An unknown field name, or a field with the wrong type, fails the whole command before anything starts; a silently ignored field would mean a run that quietly used the group default instead, and nothing downstream could notice.

## 4. Worktrees

**Process groups isolate signals, not files.** Each run gets its own process group, so stopping one never touches another — but two runs in the same directory still edit the same files, and neither can tell another agent's change from its own.

By default the members share your tree, which is what a fan-out of Claude's own subagents does — the changes appear in front of you as they are made, and there is nothing to collect afterwards. `--worktree` trades that for isolation: each writing member gets its own git worktree at `.codex-runs/<run_id>/wt`, checked out detached at `HEAD` (or at `--base <ref>`). Your own tree is untouched either way: `.codex-runs/.gitignore` is `*`, and `git status` in the main tree stays clean even while eight worktrees hold modified files. That's measured, not assumed.

**The default was the other way round until 2026-08-26, and three measurements moved it.** A session handed isolation collected three checkouts by hand — a `git apply` per member, then `batch clean --force` — steps a native fan-out simply does not have. A second session, knowing that cost, declined to fan out at all and did three files in one run: the default was suppressing the parallelism the command exists for. And a worktree holds only what git tracks, so `.venv`, provider caches and fixture directories are absent from it — two field reports of runs that could not execute the verification they were asked for, or that rebuilt a cache against live data and then reported every comparison as a regression. Against all that, sessions judge overlap correctly on their own: asked to fan out across three named modules, three separate sessions each reasoned that the files do not overlap and said so. So the judgement is yours and `--worktree` is how you act on it.

When you do pass it, assignment is **per member**, and each exclusion has its own reason:

| Excluded | Why |
|---|---|
| `read-only` members | Nothing to isolate — they can't write |
| `kind: review` members | A freshly cut worktree has **zero** uncommitted changes (measured). A reviewer inside one reviews nothing: the uncommitted work it was started to look at exists only in your tree |
| `kind: resume` members | They continue a thread whose directory they inherit. A new worktree would be a directory the thread has never seen |
| Members with an explicit `cwd` | You already made that decision, and an inferred default shouldn't overrule a stated one |

`--base` is refused without `--worktree`, because it names the commit a checkout is cut from and there is no checkout otherwise. Two things to know when you do use it:

- A worktree cut from an older base can silently lack `AGENTS.md`, so those runs start without your project's instructions. `batch start` compares and tells you when that happens.
- The members' results are uncommitted changes **inside each worktree**, not in your tree. `result --group` reports `files_changed` per member; collecting the content is yours to do.

## 5. Cleaning up

There is no automatic cleanup and no hook. A worktree holds the only copy of what its run produced, and nothing should delete that on a schedule you didn't choose.

`batch clean --group <name>` refuses, without `--force`, when:

1. the group still has running members;
2. another run is still working inside one of the worktrees;
3. a group derived from this one exists (a next phase is living in these worktrees);
4. a worktree holds uncommitted changes — **git's own refusal**, reported back to you. `git worktree remove` already declines a dirty tree, and git's notion of dirty is the correct one.

`--force` lifts all four at once, not only the one you were after. The result's `forced_past` lists what it overrode; none of it is recoverable.

## 6. Phases: `--resume-from`

```bash
$CODEX batch start --group fix --resume-from audit \
       --task "now fix what you found" --task "now fix what you found"
```

Task *i* continues member *i* of `audit`, keeping that thread and the directory it already lives in. Note that continuing several writing threads with individual `resume` calls is **not** equivalent: `resume` has no `--worktree` and takes its directory from its thread, so three of them put three writers in one directory at once. Only `batch start` assigns worktrees, which makes `--resume-from` the only isolated way to continue a group. You don't have to spot this yourself: a writing run started into a directory another live writing run already occupies comes back with `concurrent_writers` naming them, and `doctor` reports the same across the whole registry. Phase 2 inherits phase 1's worktrees rather than getting new ones, and the new group records where it came from — which is what makes cleaning phase 1 refuse while phase 2 is still there.

Everything that could go wrong here is a refusal rather than a guess:

- **One task per started member.** A count mismatch fails before anything starts.
- **Every member must be resumable.** A phase-1 member whose Codex died before opening a thread has a run id and a terminal state but no conversation; it's named and refused rather than producing a `resume` with nothing to resume.
- **No live members.** Two turns on one thread race on the same rollout file. Checked for the whole group up front, so you never get a phase 2 half-started against a phase 1 half-finished. `--as-ready` below lifts this one without lifting the invariant under it.

### `--as-ready` — don't wait for the slowest member

```bash
$CODEX batch start --group fix --resume-from audit --as-ready \
       --task "now fix what you found" --task "now fix what you found"
```

The refusal above waits for every member of `audit`, which is a group-shaped answer to a thread-shaped question: one turn per thread is per *thread*, so member 3's fix is safe to start the moment member 3's audit is done, whatever member 1 is still doing. `--as-ready` starts each member exactly then. Without it, `--resume-from` behaves as it always has.

A member that is waiting shows `state: "waiting"` with `waits_for` naming the run it is behind, and `codex_started_at` records when its turn actually began — distinct from `started_at`, which is when the run was created and is therefore *before* its predecessor finished. Any terminal state releases a member, including a failure: `predecessor_state` says how it ended, and "work out what went wrong" is a legitimate next phase. A wait is unbounded — `--timeout` bounds the Codex turn, never the wait — and `stop --group` is what ends one.

Chains work: `p1 → p2 → p3` can all be registered up front, each waiting on its own predecessor. Not combinable with `--force`, which is the opposite instruction.
- **A task may name its own target** with `kind: resume` and a `resume` field, and keeps it. A `resume` field on a `kind: start` task is a contradiction and is refused; so is a `kind: review` task, which can't be a continuation.

## 7. Watching and collecting

`status --group <name>` returns every member — a group you started is bounded by definition, so unlike the default `status` view it never truncates. `status --group <name> --follow` prints a line per tick and always ends with a terminal line — `group.completed`, `group.partial`, or `group.still-running` if `--follow-timeout` expires first — so a group can never end in silence. Arm it in a **background Bash** call: the follower exits on that terminal line, and a background call that exits is what notifies you. The Bash tool's 600-second ceiling belongs to a foreground call and does not reach a backgrounded one — measured at 200 seconds straight through a 120-second default.

`--follow` holds no state; everything it prints is re-derived from the registry, so a follower that dies loses nothing.

Which way to wait depends on whether the session gets another turn, and the rule is the same for one run as for a group. With another turn coming, arm the follow in the background and carry on — `log --run <id> --follow` for a single run, `log --group <name> --follow` for a group's events or `status --group <name> --follow` for its state changes — and collect when the notification lands. When this is the only turn the follower dies with it, so run the same follow in the **foreground** and let the call block, bounded by `--follow-timeout`. Claude Code's **Monitor** tool is for the third case only: a notification per event rather than one at the end, such as watching for an early failure or moving members onward as each lands. Give it `persistent: true` there — its default lifetime is five minutes and a Codex run routinely outlasts that; `--heartbeat` is worth adding under Monitor and nowhere else, because a follower with nothing to say and a follower that died look the same only when something is watching per event. And note that `batch start` returning is not the batch being done, and the group finishing is not the results being collected: `result --group` is a separate call.

A member that never spawned — a bad schema path, a malformed task — keeps its slot and appears under `unstarted` in both `status --group` and `result --group`, with the reason it was refused. It counts toward the group's state, so a group asked for three and given two reports `partial`, never `completed`.

`group_state` is `completed` when every member succeeded, `partial` when some didn't, `running` otherwise. Note that `partial` is also what you get after `stop --group` — it means "not all members succeeded", not "Codex failed".

`result --group` returns each member's final message capped at 4,000 bytes with the true size stated, plus **`overlaps`**: the paths more than one member wrote, keyed by run. It's the intersection only — a full path list per run would invert the context discipline this plugin exists for, and `log` already prints `file_change` paths for anyone who wants them. Under worktree isolation an overlap is **a merge conflict ahead, not damage already done**. Without worktrees, it's damage already done.

## 8. What it costs

Each run pays Codex's isolation floor separately. **N parallel runs pay N floors**, where N turns on one thread pay one floor plus a replay that grows every turn. Neither is always cheaper: parallel wins when the work is genuinely independent, one thread wins when each step needs what the last one learned.

`batch start` reports a `projected_cost` computed from *this project's* recent completed isolated runs — the median of their input tokens, times the number of members. It's `null` below three samples, because a median of one or two runs is just one run's number wearing the word; three is the smallest sample where an outlier doesn't become the answer. It's **a scale, not a bound**, and it's reported rather than enforced. It was called a floor until that was checked against the registry it comes from: 6 of 11 real runs landed below it, which is what a median does. About half will be under and half over, and a resume grows from there — so re-measure rather than budgeting from it. The fields are `input_median_per_run` and `input_median_total`. A constant measured at design time in this project moved by a factor of 2.7 within two weeks, which is exactly why there's no constant here.

Concurrency was measured at N=1–8 and again at 12, 16 and 24: no sqlite contention, no thread-id collisions, every member completing, and `batch start` returning in about 0.29 s per member — so the sequential spawn isn't the bottleneck the 15-second thread-id wait makes it look like. Above 24 is unmeasured, and so is a batch of that width doing genuinely heavy work: a trivial prompt's turn is dominated by round-trip latency rather than by anything that queues.

## 9. What the batch runs are told

Batch members get an extra paragraph in their prompt stating facts they can't observe from inside a single non-interactive turn: that they're one run in a batch of N launched together under a group name, that other runs may be executing alongside them, and — when isolated — their worktree's path, its base commit, and how many uncommitted files exist in your tree that they don't have.

This isn't politeness. Measured: asked what tree it was in, a run without that paragraph answered *"it is the shared workspace with the person who started me, so we are looking at the same tree"* — wrong, and asserted rather than hedged. With it, the same run answered correctly and reasoned about the others. It costs 113 input tokens. The failure it prevents is fabrication, not omission.

Facts only — nothing tells Codex *how* to cooperate. Being told the others exist is enough to stop it assuming they don't. There is no way to switch it off: V-18 measured it correcting a confident falsehood rather than merely adding facts, at a cost of 113 input tokens, and a caller who wants to state those things itself can write them into the prompt.

---
[Back to the wiki index](README.md)
