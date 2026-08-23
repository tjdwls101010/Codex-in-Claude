# Skill rewrite inventory

Every prose block of the pre-rewrite `codex` skill, classified by who should own it. This is the rewrite's safety net: a rewrite can lose a hard-won fact silently, and the only defence is a list that has to be complete before the rewriting starts.

The block list is not hand-kept. `tests/260823/blocks.py` splits the five source files at blank lines (fenced code held whole, heading-only lines dropped as structure rather than claim) and hashes each block's whitespace-normalised text. It reads them out of commit `2357bd3`, because the rewrite deletes the files. `tests/260823/test_inventory_coverage.py` re-derives the same list and fails if this table's ids or hashes disagree with it — so "everything was classified" is a machine's verdict, not a claim.

## The four classes

| Class | Meaning | Where it goes |
|---|---|---|
| **a** | The tool can say it | `--help`, an epilog, a subcommand description, a refusal message, or an output field. Re-read from the signature on every use, and it cannot drift from the code that emits it. |
| **b** | Only the user can say it | `SKILL.md`. A gotcha the tool cannot reach — because it is about the host, or about a decision made before any call happens. |
| **c** | Developer narrative | Dropped. How something was measured, why an implementation went the way it did, what a section is about to do. |
| **d** | Already known, or already handled | Dropped. Either general model competence, or something the tool's behaviour makes moot. |

`a+b` is a block that splits: part of it is a fact the tool states, part is the judgement the caller needs before calling. The `owner_anchor` column then names both destinations, `|`-separated.

An `owner_anchor` is checked, not decorative. `SKILL.md#…` must be a heading in the new SKILL.md; `help:<command> <flag>` must be an argument that command's parser takes and explains; `epilog:<command>` must be a non-empty epilog on that parser; `desc:<command>` must be a non-empty description.

## The reference verdict: zero

A `references/` file earns its existence when a real branch in the caller's reading leaves 40+ lines of mechanism the tool cannot state. Reading the (b) column against that bar: the largest surviving cluster is the batch material, and it comes to roughly 25 lines once the worktree eligibility rules and the tasks-file convention move into `batch start`'s epilog — which they can, because they are facts about what that command accepts and does. Codex read the same two as branches worth a file; they are not, because a branch only pays when the reader would otherwise load both halves, and a caller who is not running a batch never reads the batch section either way.

So the four references dissolve. What each loses is recorded per block below.

## Codex review 3 — the table argued against

Run `20260823-151527-inv-rebut-89f6` (gpt-5.6-sol, xhigh, read-only) was given the classification scheme and the bridge source and asked to find misclassifications, ordered by damage. It returned 25. Fourteen changed a row; the rest were rejected, and why is worth recording, because the same argument will be made again.

**Accepted, and what it caught.** Two shapes recurred. One: a (d) whose *consequence* is not derivable from what the tool prints — `doctor` prints `codex_home` and a boolean, which does not tell you that sessions, auth and the thread database moved with the override. Two: a (b) whose fact is genuinely the tool's own behaviour and whose destination was simply unclaimed — that SIGINT leaves a thread resumable is what `stop` does, so `stop --grace` says it; that `status` already lists the project's groups is `status`'s own contract. Ten rows moved from (b) or (d) into (a) on that reading, and one (c) came back: that a non-zero exit code is a *proxy* for "this output matters" rather than a verdict is filter semantics a caller acts on, not measurement narrative.

It also caught a false sentence rather than a misfiled one. `SKILL-20` said the entire context risk is `command_execution.aggregated_output`; agent messages are emitted in full at every level too ([`_events.py:261`](../../.claude/skills/codex/scripts/_events.py)), so they are unbounded as well. What is true is narrower: `aggregated_output` is the risk *the filter can act on*. The block stays (b) and the claim is corrected.

**Rejected, and on what grounds.** Five findings moved the *Which mode* blocks into (a), on the argument that `<cmd> --help` is also read before the command runs, so "the caller needs it before deciding" is not a reason for prose. That argument answers a question this rewrite already settled differently, and it has a hole: to read `resume --help` you must already have `resume` on your shortlist. What SKILL.md holds there is not a copy of each command's one-liner — it is the comparison *between* them, which no single command's help can carry because no single command knows about the others.

Four more argued that facts in the plan's fixed gotcha set are tool-owned: that `--resume-from` preserves phase 1's worktrees rather than making new ones, that a worktree is a committed base with none of the caller's uncommitted work, that the project's `AGENTS.md` reaches an isolated run, and that `thread_id: null` from `start` is normal. Each is reported by the tool *after* the spawn it would have changed. `batch start`'s output tells you how many uncommitted files you left behind at the moment the worktrees already exist.

One finding is neither accepted nor rejected but redirected. `orchestration-23` observed that `concurrent_writers_note` points at `orchestration.md` — a file that is about to stop existing, and which the note described as containing guidance it does not. The classification stands; the note's text is fixed instead.

## The blocks

| id | hash | class | owner_anchor | note |
|---|---|---|---|---|
| `SKILL-01` | `5fcb3c91f95d` | b | SKILL.md#codex-as-a-managed-subagent | the absolute-path rule; nothing the tool can say before it can be called |
| `SKILL-02` | `d6eb8abf927f` | b | SKILL.md#codex-as-a-managed-subagent | the worked path example |
| `SKILL-03` | `9e83864a04f5` | b | SKILL.md#codex-as-a-managed-subagent | env vars are empty in Bash; the permission matcher is textual |
| `SKILL-04` | `cccca25b56f2` | b | SKILL.md#codex-as-a-managed-subagent | one line per call, same matcher |
| `SKILL-05` | `d55818006d9f` | b | SKILL.md#troubleshooting | doctor cannot diagnose its own path |
| `SKILL-06` | `20a5f55cb49c` | a | epilog:(top level) | output contract; Codex corrected the wording to 'every public command that parses' |
| `SKILL-07` | `efd86bfba9cd` | a | help:(top level) | the 12-row command table is a copy of the subcommand listing; needs __supervise hidden (change 1) |
| `SKILL-08` | `34ee92bd9e65` | b | SKILL.md#codex-as-a-managed-subagent | keep the `--help` pointer; drop the seven-flags drift story as (c) |
| `SKILL-09` | `96d07cb416e2` | b | SKILL.md#which-mode | what to hand over is the caller's; which shape is mechanism |
| `SKILL-10` | `8f9e953556e3` | b | SKILL.md#which-mode | review vs start |
| `SKILL-11` | `3d8aae3a4609` | b | SKILL.md#which-mode | resume vs fresh start |
| `SKILL-12` | `224b2fbbfba3` | b | SKILL.md#which-mode | one run vs a batch |
| `SKILL-13` | `42574f766a87` | b | SKILL.md#which-mode | one batch vs two phases |
| `SKILL-14` | `10fcfb91df25` | b | SKILL.md#which-mode | status vs log vs result |
| `SKILL-15` | `efc18246aef7` | b | SKILL.md#which-mode | show --item as the escape hatch |
| `SKILL-16` | `ba35cb5d5971` | a | help:start --timeout | timed_out is its own state; resumable only when a thread id was recorded |
| `SKILL-17` | `414e1be837da` | a | epilog:status | truncation, --group never truncating, group_state vocabulary |
| `SKILL-18` | `d3c768233e62` | b | SKILL.md#which-mode | the start → log → stop → resume → result loop |
| `SKILL-19` | `b06fa19b0fac` | a | help:stop --grace | Codex review 3: that SIGINT leaves the thread resumable is what stop does, so stop says it |
| `SKILL-20` | `2a23f477ed73` | b | SKILL.md#context-discipline | Codex review 3 corrected the claim: agent messages are also unbounded, so aggregated_output is the risk the filter can act on, not the only one |
| `SKILL-21` | `1f025fa4bb59` | b | SKILL.md#context-discipline | the default level reports size instead of output |
| `SKILL-22` | `39cab9b2bc24` | b | SKILL.md#context-discipline | the cmd line with its out=NNNNB marker |
| `SKILL-23` | `c21a681c8d53` | a | desc:show | Codex review 3: that show returns exactly one item's output is show's own contract |
| `SKILL-24` | `1a1a3dd151eb` | b | SKILL.md#context-discipline | agent messages are never filtered, so output is usually a second copy |
| `SKILL-25` | `58f1c70d0e1b` | b | SKILL.md#context-discipline | when to leave the default; the measured-cost pointer goes with the reference |
| `SKILL-26` | `37d9970a904f` | b | SKILL.md#gotchas | the section's own framing |
| `SKILL-27` | `c0e1233e7435` | a | help:status --include-external|help:resume [REF] PROMPT | Codex review 3: --include-external already states it, and change 4 makes the resume itself say so; the measured drift tables are (c) |
| `SKILL-28` | `835e03f3dd8c` | a | help:show --run | item ids restart per invocation — already stated there |
| `SKILL-29` | `317e53d49f1d` | b | SKILL.md#which-mode | resume replays and gets dearer; the token ladder is (c) |
| `SKILL-30` | `c77252753299` | b | SKILL.md#gotchas | the project's AGENTS.md reaches an isolated run |
| `SKILL-31` | `bc1af9503334` | d | — | status already filters the stdin notice, so the caller never sees it |
| `SKILL-32` | `996515efb4d5` | a | help:stop --grace | signals go to the recorded process group, never to a matched name |
| `SKILL-33` | `4adf43c627ca` | b | SKILL.md#gotchas | only batch start assigns worktrees; plain resume cannot isolate writers |
| `SKILL-34` | `5f5cdbb6a64b` | a+b | help:batch start --as-ready|SKILL.md#gotchas | the barrier and its lift are the flag's; stopping a predecessor group starting its successors is not |
| `SKILL-35` | `fd3ad34bc125` | a | desc:status | Codex review 3: status already lists the project's groups and carries group and worktree on every row |
| `SKILL-36` | `e5a0ed2f28e3` | a+b | epilog:batch start|SKILL.md#collecting-a-batch | Codex review 3: that start returns after the spawns is the epilog's; only the host-turn half is prose |
| `SKILL-37` | `f94e0c517c37` | a | help:stop --grace | Codex review 3: what a process group does and does not buy is stop's to state |
| `SKILL-38` | `587bf83ac7e4` | a | help:start --no-preamble | already stated there |
| `SKILL-39` | `49317ae3477d` | a | desc:doctor | Codex review 3: the consequence of an override is not derivable from the two fields doctor already prints |
| `SKILL-40` | `0bb7736b9426` | a | help:start --effort | efforts are per-model and omitting is not medium |
| `SKILL-41` | `4b51cfc04d35` | a | help:start --foreground | background is the default |
| `SKILL-42` | `9f5ede140ae5` | b | SKILL.md#collecting-a-batch | Monitor pairing is a host fact the CLI cannot know |
| `SKILL-43` | `58c5495de99f` | a | help:log --follow | the follow invocation |
| `SKILL-44` | `4732a30b40b4` | a | help:log --follow | the terminal line, with timed_out added |
| `SKILL-45` | `f70316dfd5cf` | a | epilog:status | idle_seconds with and without an in-progress item |
| `SKILL-46` | `99a6f6ba791a` | b | SKILL.md#which-mode | what a group buys |
| `SKILL-47` | `85111060369c` | b | SKILL.md#which-mode | what a group costs |
| `SKILL-48` | `91c17f0ee9ee` | c | — | pointer into a reference that is being dissolved |
| `SKILL-49` | `e7d6e5366539` | a | help:start --schema | already stated there |
| `SKILL-50` | `b5de6a75c0ce` | a | help:start --inherit-config | already stated there |
| `SKILL-51` | `32e0b9c677fc` | b | SKILL.md#gotchas | the clean stream is what isolation reliably buys |
| `SKILL-52` | `c610a914b58e` | b | SKILL.md#gotchas | the saving is not a number; the two measurements are (c) |
| `SKILL-53` | `65a2d57ad611` | d | — | the frontmatter description already draws this boundary |
| `SKILL-54` | `cd46defa7efe` | c | — | the references index goes with the references |
| `environment-01` | `162ed559f4b8` | c | — | version provenance for the numbers below |
| `environment-02` | `873f8b0e00a7` | a | desc:doctor | Codex review 3: a path and a boolean do not say that sessions, auth and the thread database move with the override |
| `environment-03` | `579927bbf4b0` | c | — | the story of the machine it was found on |
| `environment-04` | `24f43e9f6744` | d | — | doctor prints both fields |
| `environment-05` | `6af24acb581f` | c | — | lead-in to the table |
| `environment-06` | `12eba2021468` | c | — | the layout of CODEX_HOME is Codex's, not this tool's |
| `environment-07` | `55a73e3949a3` | a | help:start --inherit-config | what isolation drops, and that auth survives it |
| `environment-08` | `f1cd4d94ec4f` | c | — | measurement method |
| `environment-09` | `6be5c721b947` | c | — | the token table |
| `environment-10` | `d910f8836bfe` | c | — | reading instructions for the table |
| `environment-11` | `31a90a5649e6` | b | SKILL.md#gotchas | the clean stream is the stable half; the floor number is (c) |
| `environment-12` | `ff970d54463e` | b | SKILL.md#gotchas | the saving is not stable |
| `environment-13` | `127d1ed29648` | b | SKILL.md#gotchas | measure your own rather than quoting one |
| `environment-14` | `7404ce13ae9f` | b | SKILL.md#gotchas | the criterion for inheriting anyway |
| `environment-15` | `6ff84d5fa142` | a | help:start --priority | already stated there |
| `environment-16` | `41924669c951` | c | — | evidence that the key is parsed |
| `environment-17` | `705ef0545609` | c | — | the bogus-tier event |
| `environment-18` | `2cf8184cdafb` | c | — | why injecting unconditionally is safe |
| `environment-19` | `d51439909d69` | a | help:start --sandbox | the three modes are the flag's choices |
| `environment-20` | `bb46c9d906d0` | c | — | why the wrapper never uses -s |
| `environment-21` | `e79562005ead` | c | — | Codex's per-subcommand flag matrix |
| `environment-22` | `3404345aa849` | c | — | the wrapper's implementation choice |
| `environment-23` | `f9d932443121` | a | help:start --add-dir | already stated there |
| `environment-24` | `6279f00dd366` | a+b | help:resume [REF] PROMPT|SKILL.md#gotchas | resume re-derives the sandbox; that is what the registry re-assertion covers and an outside thread does not have |
| `environment-25` | `8b4dd73bc830` | c | — | measurement setup |
| `environment-26` | `d7cc673a653e` | c | — | the drift table |
| `environment-27` | `2caa058af4f2` | c | — | the other direction's setup |
| `environment-28` | `aff0562ef0f2` | c | — | the escalation table |
| `environment-29` | `03dc32e856b5` | c | — | why isolation masking it is not something to rely on |
| `environment-30` | `6d4923298262` | c | — | what property the wrapper buys |
| `environment-31` | `af2a883609e9` | c | — | confirmation that -c constrains |
| `environment-32` | `81c4cd287ea9` | c | — | lead-in to the rollout sample |
| `environment-33` | `59c9aef8c5fd` | c | — | the turn_context sample |
| `environment-34` | `745f091c92a7` | b | SKILL.md#troubleshooting | turn_context is the authoritative record of what a turn ran under |
| `environment-35` | `bfb996b0b582` | c | — | the ZEBRAFISH measurement |
| `environment-36` | `3d25bc1c573d` | c | — | the injected instructions block |
| `environment-37` | `392dc682a29b` | c | — | lead-in to the two consequences |
| `environment-38` | `53b225da61fd` | b | SKILL.md#gotchas | briefing channel and uncontrolled input, both surviving isolation |
| `environment-39` | `22e3a3fa3c7c` | c | — | the cost of a two-line AGENTS.md |
| `environment-40` | `d6ab86275b94` | a | desc:doctor | what doctor runs for auth |
| `environment-41` | `f171eceb1d3f` | a | desc:doctor | a failing login is a blocker and exits 2 |
| `environment-42` | `9f9980aea7d1` | a | help:start --model | nothing is pinned by default |
| `environment-43` | `846a0dae6ce0` | a | help:start --model | re-asserted on later turns |
| `environment-44` | `88be7a3564bd` | a | desc:models | efforts and default_effort per model; Codex corrected the source to `codex debug models` |
| `environment-45` | `5452076e08bb` | a | help:start --effort | the catalog check runs before the spawn and is skipped, never fail-closed, when unreadable |
| `environment-46` | `d40daf207521` | a | desc:doctor | exit 0 healthy, 2 on a blocker |
| `environment-47` | `971bb6700c6b` | a | desc:doctor | the blocker and warning lists |
| `environment-48` | `4cfe4ee3e76c` | a | desc:doctor | thread_db_readable:false means no thread row could be read, not that the schema changed |
| `eventstream-01` | `ea3059bf5f50` | c | — | the file's own framing |
| `eventstream-02` | `5b98138f50ca` | d | — | the model reads the exec stream directly at --level raw; the one consequence — that a rollout is a different file in a different shape — travels with eventstream-07 |
| `eventstream-03` | `8abe0131983b` | d | — | the sample is the stream itself |
| `eventstream-04` | `74cfc411390d` | c | — | lead-in |
| `eventstream-05` | `7ca3e171b7c1` | a+b | help:show --run|SKILL.md#context-discipline | item ids and the aggregated_output risk; the rest is readable from the stream |
| `eventstream-06` | `33eaabe59258` | c | — | the rollout file's shape |
| `eventstream-07` | `8822895f3f72` | b | SKILL.md#troubleshooting | turn_context as the one reason to open a rollout |
| `eventstream-08` | `92c291c52b46` | a | help:log --level | what the four levels include |
| `eventstream-09` | `7d4a9e95eb42` | a | help:log --level | the split is on exit code |
| `eventstream-10` | `d29005306c27` | c | — | measurement method and its pointer into docs/measurements |
| `eventstream-11` | `96028e82a428` | c | — | the calibration table |
| `eventstream-12` | `a7a5855a358b` | a | help:log --level | compact and normal coincide while everything exits 0 |
| `eventstream-13` | `736e8c18482c` | c | — | lead-in |
| `eventstream-14` | `b58f108f5b46` | c | — | the agent-message share table |
| `eventstream-15` | `c8940d40195a` | b | SKILL.md#context-discipline | compact is the agent's own answer |
| `eventstream-16` | `7f047184ff37` | b | SKILL.md#context-discipline | when output is not redundant it is one command |
| `eventstream-17` | `806ce7777385` | b | SKILL.md#context-discipline | when to raise the level |
| `eventstream-18` | `0606cec7712a` | a | help:log --level | Codex review 3: that a non-zero exit is a proxy rather than a verdict is filter semantics a caller acts on |
| `eventstream-19` | `017addfd6363` | a | help:log --since | the cursor is a byte offset |
| `eventstream-20` | `fd5599691e10` | a | help:log --since | nothing duplicated or skipped |
| `eventstream-21` | `895df36c90be` | a | help:log --since | --since 0 replays everything |
| `eventstream-22` | `58c5495de99f` | d | — | duplicate of SKILL-43's invocation |
| `eventstream-23` | `593db15761b9` | a | help:log --follow | events then a terminal line |
| `eventstream-24` | `a48231bb34df` | a | help:log --follow | the terminal line's shape |
| `eventstream-25` | `fcf737fa3a64` | a+b | help:log --follow|SKILL.md#collecting-a-batch | Codex review 3: the terminal line is the flag's; pairing it with Monitor is a host fact |
| `eventstream-26` | `a1c9ade22f81` | a | help:log --follow-timeout | already stated there |
| `eventstream-27` | `ab63ae6a73a2` | a | epilog:status | idle_seconds and in_progress_item |
| `eventstream-28` | `b9cfe6de5bdc` | a | epilog:status | how to read the two together |
| `eventstream-29` | `010ba6ff1ce5` | a | epilog:status | stalled is advisory; Codex corrected it to a display state, not a stored one |
| `eventstream-30` | `d2d966c0b327` | a | help:show --item | the show invocation |
| `eventstream-31` | `543c52743a2b` | a | desc:show | what show returns |
| `eventstream-32` | `583518eb836c` | a | help:show --max-bytes | truncation is loud |
| `orchestration-01` | `52eed5583459` | c | — | the file's own framing |
| `orchestration-02` | `3ea5070c9a2e` | c | — | a correction to the framing above it |
| `orchestration-03` | `167b87e62e53` | a | desc:batch | what a group is |
| `orchestration-04` | `ed956a019742` | b | SKILL.md#collecting-a-batch | the five calls a group answers to |
| `orchestration-05` | `b14986acc565` | a | help:batch start --group | already stated there |
| `orchestration-06` | `4060ece3c6cf` | c | — | where membership is stored |
| `orchestration-07` | `e1a831eab3b3` | b | SKILL.md#collecting-a-batch | a later session can find a group it did not start |
| `orchestration-08` | `59554ebb0bad` | a | epilog:batch start | an unstarted member keeps its slot |
| `orchestration-09` | `310a8fdd471c` | a | epilog:batch start | one failure does not take the batch down |
| `orchestration-10` | `29c6b0c44b56` | a | help:batch start --tasks-file | the per-item field list is generated from the validator's own tuple |
| `orchestration-11` | `0e841a8042b0` | a | help:batch start --tasks-file | group options are defaults, not constraints |
| `orchestration-12` | `01fb500bf14e` | a | epilog:batch start | the JSONL sample |
| `orchestration-13` | `aea4ac007b3b` | a | help:batch start --tasks-file | an unknown field fails before anything starts |
| `orchestration-14` | `ef6d368228db` | a | help:batch start --resume-from | the resume-from invocation |
| `orchestration-15` | `74b06b330dde` | a | help:batch start --resume-from | positional pairing in start order |
| `orchestration-16` | `4b561eaa4434` | a | help:batch start --resume-from | the four pairing rules are refusals that name the case |
| `orchestration-17` | `31c21b78ef96` | b | SKILL.md#gotchas | phase 2 keeps phase 1's worktrees rather than getting new ones |
| `orchestration-18` | `9e325ae9cbf9` | a | help:batch start --as-ready | the as-ready invocation |
| `orchestration-19` | `df0f0eb6e311` | a | help:batch start --as-ready | one turn per thread is the invariant the barrier over-serves |
| `orchestration-20` | `577106f51f10` | a+b | help:batch start --as-ready|SKILL.md#gotchas | terminal states release and waits are unbounded; that stopping phase 1 starts phase 2 is the trap |
| `orchestration-21` | `0f9ef84fc327` | c | — | why there is no queue |
| `orchestration-22` | `7cb54dd0a41a` | b | SKILL.md#gotchas | three resume calls put three writers in one directory |
| `orchestration-23` | `10d7e57218bd` | b | SKILL.md#gotchas | concurrent_writers is reported after the spawn, so the decision needs prose; its note currently points at this file, which is the lie to fix |
| `orchestration-24` | `a2f4f49bb98c` | a | epilog:batch start | which members qualify for a worktree |
| `orchestration-25` | `c315e3121df0` | a | help:stop --grace | same fact as SKILL-37, same owner |
| `orchestration-26` | `c05e2fa5d4e1` | a+b | epilog:batch start|SKILL.md#gotchas | the worktree rules are the epilog's; that a worktree is a committed base without the caller's uncommitted work has to be known before the spawn |
| `orchestration-27` | `965251689705` | a | help:batch clean --force | what clean refuses and what --force lifts |
| `orchestration-28` | `4732892c6683` | a+b | help:status --follow|SKILL.md#collecting-a-batch | the line shapes are the flag's; the Bash ceiling is a host fact |
| `orchestration-29` | `6905e7a9f4b7` | a | help:status --follow | --follow is a pure view |
| `orchestration-30` | `5c96459a63ee` | b | SKILL.md#collecting-a-batch | how to wait depends on whether another turn is coming |
| `orchestration-31` | `732c7997d1c8` | a+b | epilog:batch start|SKILL.md#collecting-a-batch | Codex review 3: three bridge states; only "ending the turn on a promise produces nothing" is host-owned |
| `orchestration-32` | `ac459d5751bd` | a | epilog:status | the group_state vocabulary, including partial after a stop |
| `orchestration-33` | `35b4f1534e08` | a | help:result --group | what result --group returns |
| `orchestration-34` | `0c15185db4c2` | a | help:result --group | overlaps is the intersection only |
| `orchestration-35` | `2e36e4fe087e` | a | help:result --run | one member's full message |
| `orchestration-36` | `f5a5afac0472` | a | help:batch start --no-preamble | what a batch member is additionally told |
| `orchestration-37` | `08855ffab4c9` | c | — | the fabrication measurement |
| `orchestration-38` | `af09dd28c646` | c | — | why the preamble prevents fabrication rather than omission |
| `orchestration-39` | `9f444091d17f` | b | SKILL.md#which-mode | N floors against one floor plus a growing replay |
| `orchestration-40` | `fea4bd590133` | a | epilog:batch start | projected_cost is a median scale, not a bound; the 6-of-11 sample story leaves the output (change 6) |
| `orchestration-41` | `8bea88c38a9b` | c | — | the concurrency soak |
| `orchestration-42` | `f673f5393387` | c | — | subagent and workflow usage is out of scope for this rewrite |
| `orchestration-43` | `fb961a7941ed` | c | — | workflow cost arithmetic, same scope decision |
| `troubleshooting-01` | `7cfd23e5bb77` | a | desc:doctor | doctor first, and what its exit codes mean |
| `troubleshooting-02` | `ca7c805bf25d` | c | — | the file's editorial rule for its own table |
| `troubleshooting-03` | `9ef82ec36adc` | a+b | desc:doctor|SKILL.md#troubleshooting | the rows the tool now owns (auth, exit 127, orphaned, stalled, no pgid, resume --last, schema) leave; the ones outside the bridge stay |
| `troubleshooting-04` | `5c162336cf06` | b | SKILL.md#gotchas | thread_id:null from start is normal and status backfills it |
| `troubleshooting-05` | `907a128b04a7` | c | — | lead-in to the scope notes |
| `troubleshooting-06` | `bbf7dc8b03dd` | d | — | the frontmatter description already excludes Codex Cloud |
| `troubleshooting-07` | `4690670f6dec` | d | — | the frontmatter description already excludes the server modes |
| `troubleshooting-08` | `8920937e06b3` | b | SKILL.md#which-mode | there is no mid-turn channel, so the model is stop then resume |
| `troubleshooting-09` | `93f0aae83bb0` | c | — | app-server recorded as unexplored |
| `troubleshooting-10` | `151084e55398` | c | — | how to report a bug in this tool |
