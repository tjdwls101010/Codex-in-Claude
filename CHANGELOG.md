# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] — 2026-09-26

The skill's code takes the layout every bundled skill shares and runs under `uv`, and its replies are shaped for how the model actually reads them: `result` is text, the default `status` no longer grows with the registry, a start says which follower to run, and the exit code says whether to fix the command line or wait.

**Read Changed before upgrading.** The entrypoint and how it is run, `result`'s output, the default `status` listing and the exit codes change.

### Changed

- **The entrypoint is `scripts/cli.py`, run with `uv run` — BREAKING.** It was `python3 scripts/cli_codex.py`. A PEP 723 header declares Python 3.11+ and no dependencies, so uv provides the interpreter whatever `python3` a terminal, hook or scheduled job finds first (the macOS system one is 3.9). The code moved into one package, `scripts/codex/`, with a subpackage per feature (`runs`, `batch`, `observe`), per system someone else owns (`codex_cli`, `git`) and for the run registry; imports run one way, and `tests/test_structure.py` fails a change that breaks the tree. **Migration:** install uv, and replace a permission rule naming `…/cli_codex.py` with `Bash(uv run "<skill dir>/scripts/cli.py" *)`.
- **`result` prints text — BREAKING.** `result --run` prints a one-line JSON header (state, exit code, thread, `message_bytes`, changed files, commands, usage, and `turn_failed` when the turn failed), then the final message as written and one newline its `message_bytes` leaves out. `result --group` prints a group header with `members[]`, then per member a `--- [<index>:<label>] run=<id> state=<state> bytes=<n>` line (`[<index>]` without a label) and its message, capped at 4000 bytes; the header's byte counts, not the separator lines, say where each message ends. A `--schema` run's answer is still one JSON document. With 0.8.0 the model piped 419 of 514 `result` replies through a JSON parser only to print the message. **Migration:** read the first line as JSON and the rest as the message; a script splits on the byte counts.
- **The default `status` listing counts finished runs instead of naming them — BREAKING.** Without `--run`, `--thread` or `--group`, and with `--all`, `status` gives `running` (the live run ids) and `counts` (live, completed, failed) in place of the `threads` map and the `done`/`failed` id lists, which grew with every run the registry kept. On a 304-run registry the reply goes from 40,806 bytes to 8,032. `--run`, `--thread` and `--group` are unchanged. **Migration:** ask `status --run`, `--thread` or `--group` for the ids.
- **Exit codes — BREAKING.** 1 now means only a refusal by the registry's state or a failed run. A command line that has to change exits 2 with `{"error", "help"}` on stdout, `help` naming the `--help` to read; argparse errors answer the same way instead of printing usage to stderr. `doctor` exits 3 on a blocker (it was 2). A model or effort named on the command line that the catalog lacks is 2; one adopted from `config.toml` stays 1. **Migration:** treat 2 as "fix the command", 3 as `doctor`'s blockers.
- JSON replies put the cheap signal first — state, counts, warnings, `next` — and paths, pids and long lists last. The keys are unchanged.
- **`SKILL.md` points at the new interface**: run the reply's `next.command` in the background, read replies as printed, and have Monitor run `log --follow` to catch a run going wrong (a group's `status --follow` reports only member states). Against v0.8.0's skill in real headless sessions over two scenarios, one session each, the new text followed in the background and collected with `result` both times, where v0.8.0's followed in the foreground both times.

### Added

- **`next` in `start`, `resume` and `batch start` replies**: `{"command", "run_in_background": true}`, the follower written out whole — `log --run <id> --follow`, or `status --group <name> --follow` for a batch that started a member — in the form a permission rule for the entrypoint matches, carrying `--project` and `--runs-dir` when given. With 0.8.0 the model held values in shell variables or substitutions in 468 of 3,282 calls, which such a rule does not match.

### Fixed

- **A missing `--schema` or `--image` left an empty run directory** that no listing showed. Both are checked before the directory is claimed.
- **`config.toml` was read by a regex over `key = value` lines**, so quoted keys, escapes and multi-line strings were misread, and a number or a list came back as a string. It is read with `tomllib`; only top-level strings count, and a file that does not parse reads as empty.
- **A prompt file, a prompt on stdin or a tasks file that is not UTF-8 was an internal error.** It is refused with exit 2. A `--schema` run whose final message is not UTF-8 is refused instead of crashing, and a text answer shows such bytes as U+FFFD.
- **A finished run whose Codex pid had been handed to another process counted as live**, so it stayed in `status`'s `running`, its thread's `resume` was refused as a live turn and `batch clean` refused its group; a dead supervisor whose pid was reused kept its run `running` instead of `orphaned`. A recorded pid now counts only while it is still in the run's process group.

## [0.8.0] — 2026-09-25

The surface nobody used is gone, the engine is split into three layers with one implementation per question, `--help` is the one reference for flags, and `SKILL.md` keeps only the judgement no single `--help` can carry. Eight defects an audit reproduced are fixed on the way.

**Read Removed and Changed before upgrading.** The entrypoint is renamed, three flags are refused, and several replies have a different shape.

### Removed

- **`--as-ready`, `start`/`resume --foreground` and `status --include-external` — BREAKING.** In 720 runs of real use `--as-ready` was used zero times, `--include-external` zero times, and `--foreground` 13 times, nearly all by this repository's own tests; together they were the most complex part of the engine (a waiting-run chain and two ways to place a process group). They are refused now (exit 2). **Migration:** start the next round with `batch start --resume-from <group>` once the group has finished; let a background `log --run <id> --follow` do what `--foreground` did; resume a thread started outside the registry by its id with `resume <id> --sandbox <mode>`.
- **The Codex thread database lookup — BREAKING.** `resume --last` no longer falls back to Codex's own thread list when the registry has no candidate, and `doctor` drops `thread_db`/`thread_db_readable`.
- **`batch start`'s `projected_cost`**, and the usage the supervisor copied into `meta.json` to compute it. It arrived after the spend it estimated.
- **`models --project`/`--runs-dir`**, which did nothing. Refused now (exit 2).
- **`docs/wiki/`.** It was a second copy of what `--help` and `SKILL.md` own, and it had drifted from both.

`waiting` is still read as a live state, so a registry written by an older release, holding a run that waits on another, is stopped, reaped and protected as before.

### Changed

- **The entrypoint is `scripts/cli_codex.py` — BREAKING.** It was `scripts/codex_bridge.py`. A permission rule naming the old path no longer matches; see the README for the rule to use instead. `SKILL.md`'s `allowed-tools` now uses `${CLAUDE_SKILL_DIR}`, so a symlinked or project install is pre-approved the same way as the plugin — but Claude Code applies a skill's `allowed-tools` only when the user invokes the skill, so a skill Claude picks on its own still needs that rule.
- **Output shapes — BREAKING.** `status` without `--run`/`--thread`/`--group` lists a summary row per run (`run_id`, `label`, `state`, `group`, `idle_seconds`, a `last_agent_message` excerpt, and a still-writing flag) instead of full rows. `result --run` on a `--schema` run returns only `json`; the raw `message` and the parse error come back only when the message is not JSON (`message_preview` is gone).
- **`--priority` together with `--no-priority` is an argparse usage error (exit 2)** instead of a JSON error (exit 1), and a prompt that happens to contain `--no-priority` after `--` is no longer refused.
- **`batch clean --force` cannot remove the checkout of a live run** — a live member, or another group's or a single run's work inside that checkout. The refusal names the runs in the way and the `stop` command that ends them; `forced_past.removed_under_live_runs` is gone and `kept[]` carries that `stop`.
- **The engine is split into `cli/`, `core/` and `codex/`.** Settings precedence, liveness, the SIGINT → SIGTERM → SIGKILL ladder, atomic JSON writes, locking and follower timing each have one implementation, where several hand-written copies had disagreed with each other.
- **Every `--help` is rewritten** as the reference the model reads: what a flag does, its default, what it refuses, and the clause that lets the rule be re-derived. The rendered help totals 27,330 bytes, from 50,354 in 0.7.0, and nine claims that were false are corrected. Error messages say the condition, the target and the way out, and no longer assert causes nobody established.
- **`SKILL.md` is rewritten** to hold only judgement between commands — sandbox choice, `resume` against `start`, when a verification loop ends, isolation and rounds in a batch, how to wait and when a run is collected — and `--help` holds the rest (118 lines to 67). Its draft was compared against a control without that judgement in real headless sessions over four scenarios; the draft followed a detached run in the background and checked a claim before relaying it where the control blocked in the foreground and relayed it unchecked, and it cleaned a batch's worktrees where the control left them.

### Fixed

- **`batch start` accepted a group-level `--prompt-file` or `--image` and did nothing with it.** Refused now; the task fields `prompt` and `image` are unchanged.
- **`result --group` counted a member whose supervisor had died while Codex was still writing as failed**, and reported the group `partial`. It now uses the same still-writing judgement as `status --group`.
- **An `OSError` inside a locked block was swallowed as a lock failure**, surfacing as `generator didn't stop after throw()`.
- **`--timeout` started counting only after the thread id arrived, and its last step killed only the child.** The deadline now runs from launch, and the whole process group gets SIGINT, then SIGTERM, then SIGKILL, with `timed_out` recorded first. Descendants still alive after Codex exits are swept, for `stop` as well.
- **A relative `CODEX_HOME` meant the supervisor and Codex looked in different places.** It is made absolute at the entrypoint.
- **`log --follow-timeout` without `--follow` was silently accepted**, and `--follow-timeout 0` silently meant "no limit". Both are refused.
- **The shared-tree warning resolved a member's sandbox in a different order from the run itself.** Task field, then group flag, then the thread's record, as the run does.
- **A `batch clean --force` on a member whose `meta.json` could not be read removed its worktree and released its name**; the checkout is now kept and reported. A checkout left half-built by a kill inside `git worktree add` is recovered, and reported removed only once the source repository confirms its registration is gone.
- **A long `last_agent_message` was clipped twice in a summary row**, so the reported number of omitted characters was wrong.

## [0.7.0] — 2026-08-28

One command is gone, and the paragraph that pointed at it is replaced by what this repository has actually measured about verification loops that do not end.

**Read Removed before upgrading.** `review` no longer exists.

### Removed

- **`review` — BREAKING.** The bridge added nothing to it: the argv it built differed from `start`'s only by the subword and a selector flag, with sandbox, model, effort, `--output-schema`, `-o` and prompt termination all going through the same code. Four things stood against keeping it. Of 46 runs in this project's registry, its 13 contain **zero** ad-hoc uses — four from a flag-surface walk and nine from one commit-by-commit sweep. It reported all-zero token usage after doing real work, so the cost of a verification round vanished from the accounting and three files carried code to wrap that. It could not take a lens and a scope at once — `review --uncommitted "races only"` was refused before spawning — so verification through it was always a general sweep, and a general sweep has no predicate to satisfy and nothing to hand back but findings. And a subcommand overlapping `start` with no measured difference is the case this project already refused once, when it turned down `--fast` on "one config key, one tier — a second name, not a second switch".

  **Migration:** `review --commit <sha>` becomes `start --sandbox read-only "Review this commit: git show <sha>"`; `--uncommitted` and `--base <ref>` the same way, with `git diff` in the prompt. Say what to look for in the prompt — that is the thing `review` could not let you do. No preset or selector shim is provided, deliberately: writing the prompt yourself is half of why the command was redundant.

  What goes with it: the `kind: review` task kind and its nested `review` object (a tasks file still carrying either is refused by name, with this migration in the message, rather than silently); `--uncommitted`, `--base`, `--commit`, `--title` as bridge flags; and the `usage_note` a `review` run's `status`/`result` carried. `usage` on those surfaces is now simply what the run reported.

- **`result --group`'s `usage_unmeasured`.** It named members whose zero usage meant "unavailable, not free", and `review` runs were the only thing that could ever populate it. `totals` no longer excludes anybody.

### Changed

- **SKILL.md's `## Which mode` says why a verification loop fails to end, instead of routing you into one.** The paragraph it replaces promised that `review` came back with "a verdict you will act on" — the tool returned findings, which is a different object. What is there now is three things a model cannot re-derive from general competence, each measured in this repository. A stopping predicate whose subject is the examiner has no floor: four adversarial rounds ran here and none came back at zero, because a sufficiently new lens finds something in any codebase. What actually ended it was counting a *different* quantity — of nineteen findings, three were reachable in ordinary single-session use, and reachability is a property of the artifact, so it runs out. And a fresh round does not know what you rejected, so it reopens the questions the last one closed and "still wrong" and "asked again" arrive as one list of the same shape. `--schema` is pointed at rather than re-explained; its own `--help` already states what `result` hands back and how it fails.

- **The wiki drops `review` throughout, and `CLI Reference`'s sections renumber** — §5–§12 become §4–§11. Cross-page anchors are updated.

## [0.6.0] — 2026-08-27

Twenty-one headless sessions were run before a line of this was written, each one delegating the same task twice — once to Claude's own `Agent`/`Workflow`/agent team, once to Codex — and graded on four invariants rather than on whether the two looked alike. Six of the seven axes came back identical. What this release changes is the one that did not, plus two waiting defects the benchmark surfaced and two things two field reports did. Every commit was then handed to a Codex review before the next was written, and the new `--help` strings to a second one; between them they found fourteen more defects, ten of which this release had just created.

**Read Changed before upgrading.** The batch worktree default is inverted, five flags are gone, and an isolated run now takes the model, reasoning effort and service tier your `config.toml` sets instead of the server's defaults.

### Changed

- **`batch start` shares your tree by default; `--worktree` is how you ask for isolation.** It used to isolate any batch with two or more writing members. Three measurements moved it. A session handed isolation collected three checkouts by hand — a `git apply` per member, then `batch clean --force` — steps a fan-out of Claude's own subagents does not have, because a native subagent's work lands in your tree. A second session, knowing that cost, declined to fan out at all and did three files in one run: the default was suppressing the parallelism the command exists for. And a worktree holds only what git tracks, so `.venv`, provider caches and fixture directories are absent — two field reports of runs that could not execute the verification they were asked for, or that rebuilt a cache against live data and reported every comparison as a regression. Against that, sessions judge file overlap correctly unaided: three separate sessions, asked to fan out across three named modules, each reasoned that the files do not overlap. **To keep the old behaviour, add `--worktree`.** Everything else about isolation is unchanged — it is still per member, and a resume, a review, a read-only member and one with its own `cwd` are never isolated.

- **Your `config.toml` defaults survive isolation.** Isolation passes `--ignore-user-config`, which drops the file whole, and only `service_tier="priority"` was ever put back — so an unnamed run took Codex's *server* default model rather than the one you configured. Not one of the 21 benchmark argvs carried a model or an effort, which answers this spec's own oldest open item by measurement. Three keys now come back: `model`, `model_reasoning_effort`, `service_tier`. Precedence is an explicit flag, then whatever a resumed thread recorded, then `config.toml`, then the server. `sandbox_mode` is deliberately not among them — a config the caller can edit deciding the sandbox is R24 arriving by another road, which is the same reason `--config` is gone.

  **This can change which model your runs use.** If `config.toml` names a model this Codex install does not offer, `start` now refuses before spawning and names the file, instead of the run coming back `turn.failed`. And an isolated run no longer gets `service_tier="priority"` unless your config asks for it — the tier is read, not assumed. Codex labels it "Fast mode" and its config spells it `"fast"`; both names were measured to run clean against codex-cli 0.149.1, so whatever the file says is passed through verbatim rather than translated. `doctor` gained `effective_defaults`, which is where you read all three without starting a run. `meta.json`'s boolean `priority` is replaced by the string `service_tier`, so an empty record can now mean "deliberately no tier" and a resume re-asserts it.

- **`--base` is refused without `--worktree`.** It names the commit a checkout is cut from, and no checkout is cut otherwise. Accepted silently it would hand back a success the caller reads as "cut from that commit".

- **A batch that continues threads now says who shares your tree.** The warning was keyed off worktree *eligibility*, and a resumed member is never eligible — its thread keeps the directory it already lives in. So a `--resume-from` phase, which after the default change is N writers continuing into the one tree phase 1 shared, was the only batch that could not produce the warning it most needed. Members are now grouped by the directory they will actually write in, resolved per member the way the run itself resolves it.

- **Two remedies that did not work are gone.** `--worktree` on a resume phase answered *"no member writes to the tree, so there is nothing to isolate"* — false of a phase of `workspace-write` members, and it is the sentence a caller acts on; it now says that a resumed thread keeps its directory and that isolation is decided when the group is first started. The `concurrent_writers_note` prescribed `batch start --worktree --resume-from`, which cuts no worktrees for the same reason: it now names what actually separates writers, and says plainly that runs already under way cannot be separated.

- **A batch validates the config's own model and effort before it claims its name.** With the three keys above now feeding every isolated member, a `config.toml` effort the second task's model does not accept was found inside that member's own setup — after the group name was claimed and the first member had spawned. Measured at `spawned: 1` of 2. The check `load_tasks` already did for `--model`/`--effort` now covers the values the file supplies, and skips a `--resume-from` phase for the same reason a resume is never re-checked: those members take their model from the threads they continue.

- **A run recorded before this version keeps its tier when resumed.** `meta.json`'s boolean `priority` became the string `service_tier` in the same release that started reading the tier from `config.toml`; a thread recorded under the old key would have lost Fast mode for the rest of its life. The old key is read when the new one is absent — presence, not truth, so a new record that deliberately holds no tier is not overwritten.

### Added

- **`log --group <name>` follows a whole batch's events.** `log --run --follow` gives one run its commands, exit codes and agent messages as they arrive; a group had no equivalent, so wanting the same from three members meant arming three followers. A field report wrote its own polling loop instead, got its format wrong, and came within one step of reporting a false completion — its reviewer's bootstrap trouble, two suite failures and a render phase were all found by hand-polling `status --group`, which prints only state *changes* and stays silent through the twenty minutes a member spends `running`. A first line maps index to run id, every event line is prefixed `[<index>:<label>]`, and the stream ends on the same terminal line `status --group --follow` ends on. `--since` is refused here: a cursor is a byte offset into one file and every member has its own.

- **`--heartbeat SEC` on both followers.** A periodic `still-running elapsed=<s> running=<n>` line. Off by default, and worth turning on only under a watcher woken per event: a run that has genuinely gone quiet already announces itself, since `stalled` is derived after 300 idle seconds. What had no signal at all was the other half — a follower that is alive with nothing to say, and one that died, look identical from outside.

- **`batch start --worktree` names what the checkouts do not have.** A worktree is `git worktree add` output — tracked files at the base commit and nothing else — so `.venv`, provider caches and fixture directories are all absent. Reproduced directly: `.venv/bin/python` planted in a fixture, two worktree members asked to `ls .venv/bin`, both `No such file or directory`. The reply now carries `missing_ignored` listing what this tree actually has, at the moment the checkouts are cut, since that is the last point where the caller could still act on it. The tool's own run registry is left out — it gitignores itself, and a checkout not having it is neither news nor actionable.

- **SKILL.md now sets Codex beside Claude's own delegation instruments.** Twenty-one sessions were graded against `Agent`, `Workflow` and agent teams as a control rather than as a norm, and what a caller could not get from any `--help` was the comparison itself. A three-row table says, per instrument, what the close equivalent here is, what extra premise it carries, and what has no equivalent at all — `Agent`'s harness holding your turn, a workflow computing round two from all of round one, a team's members addressing each other. The batch/workflow analogy it replaces led with the correspondence and put the limits after it; this leads with the limit.

- **Choosing a shape is now two axes rather than four comparisons.** How many runs and how you address them, and whether anything has to be computed between rounds. A read-only fan-out is a batch for the first reason, and a round whose prompts come from the previous round's results leaves the tool entirely for the second.

- **The one-turn waiting rule covers every way of arming, and names the thing that was actually killing the wait.** It named the follower, so a session that armed a Monitor instead read the exception and still ended the turn on a promise. The rule is now the property rather than the instrument: if you cannot name what would wake you, do the parallel work first and make the turn's last call a blocking foreground `--follow`. Re-measured, that was still not enough — three of four sessions given the corrected rule left the **Bash call's own `timeout` at its 120-second default**, so the foreground follow was killed after two minutes and each reported it was still watching; the document had named the 600-second ceiling in a sentence that reads as the default. And the section's main idiom licensed "no parallel work, hand the turn back armed" with no condition on there being another turn, which is exactly what the exception forbids. With both fixed: 9 of 10 waiting sessions, against 3 of 8 at the start of the round. Choosing between one notification and one per event is stated as a criterion in the same section instead of as an exception.

### Fixed

Four defects found by adversarial review of this release's own commits, each reproduced before it was fixed.

- **`missing_ignored` handed back an encoded token instead of a path** for any name git C-quotes — anything non-ASCII, or with a tab, quote or backslash. This repository keeps Korean paths in its own fixtures. The scan now asks for NUL-delimited output.

- **`missing_ignored` could name a path the checkouts do have.** A `--base` older than the commit that stopped tracking something puts that something back in every worktree. Entries are now filtered against the base the checkouts were cut from.

- **A phase resuming read-only members was warned that they share your tree.** A resume inherits its sandbox from its thread, and the count defaulted every member to the group's `workspace-write` instead — a warning about a collision that cannot happen, which is how a field stops being read. The same resolution now supplies each member's directory and its sandbox.

- **The sharing note explained every exclusion as a resume.** `--worktree` also passes over a review, which has to see the uncommitted work in your tree, and a member given its own `cwd`. Two fresh tasks pointed at one directory were told they were resumed threads whose isolation had been decided in an earlier phase. The note now names the reason that actually applies.

### Removed

**Five flags.** Each is now argparse's usage error, exit status **2**, refused before anything is claimed. The shared reason is that none was used in 51 real delegations, which on its own would only argue for leaving them alone — what decided each one is the second reason.

- **`--config k=v`** (`start`, `resume`, `review`, `batch start`). A raw `-c` passthrough, and `codex`'s `-c` is last-value-wins for a repeated key, so `--config 'sandbox_mode="danger-full-access"'` beat the wrapper's own enforced entry — the run executed fully privileged while `status` went on reporting `read-only`, and because `extra_config` was inherited by every resume that did not pass `--config` itself, the drift rode along for the rest of the thread (R24). Two guards were added at the time; neither is needed once the flag cannot be typed. A pass-through that can reach an invariant is a thing to remove rather than to guard twice. `extra_config` is gone from `meta.json` with it, so a run recorded before this version loses whatever raw entries it held when resumed.

- **`--no-preamble`** (`start`, `resume`, `review`, `batch start`). V-18 measured the preamble *correcting a confident falsehood* — without it a batch member asserted it shared the caller's tree — for 113 input tokens. There is no good reason to switch that off, and a caller who wants to state those facts itself can write them into the prompt, which is the same channel. The flag was also the only place `--help` said anything was prepended at all; `start`'s and `batch start`'s epilogs say it now, unconditionally.

- **`--isolate`** (`start`, `resume`, `review`, `batch start`). Isolation is the default, so on a fresh run the flag only ever agreed with what was already happening. On a resume it re-asserted a recorded choice with no way to take it back.

- **`--interval`** (`log`, `status`). One second, in one place, and no measurement has ever wanted another value. A poll period is not a decision the caller has to make. Worth recording against the "0 uses" count that justified this: the flag *was* used in-repo, by three test files and two measurement scripts, which counted delegations do not see — those now poll at the default.

- **`batch start --no-worktree`.** It negated a default that no longer exists (see Changed). Left in the parser it would parse and decide nothing, which is worse than absent: a caller typing it would read the success as isolation having been turned off.

Counted across the whole release rather than this section alone — three flags are added below — the surface goes from **45 distinct flag names to 41**, and 142 command/argument pairs to 130, with `start --help` at 8,111 → 7,518 bytes. That is the small half of the point; the real change is five fewer decisions in front of a caller who has to make none of them.

## [0.5.0] — 2026-08-23

The skill was written by adding a gotcha at a time across five rounds, so its structure was the order they were discovered in. This version rewrites it against one rule: **whatever the tool can say, the tool says.** A sentence in `--help` is regenerated from the code on every call and cannot drift from it; the same sentence in a paragraph is a copy, and the copy is what goes wrong.

**Read Changed before upgrading.** Four things that used to be accepted are now refused, one flag is gone from `batch start`, and the four `references/` files no longer exist.

### Changed

- **`references/` is empty.** `environment.md`, `event-stream.md`, `orchestration.md` and `troubleshooting.md` — 454 lines — are gone, and `SKILL.md` went from 177 lines to 106. Nothing was lost silently: all 187 prose blocks were classified by owner first, in `.claude/plans/260823/skill-rewrite-inventory.md`, and a test fails if that table and the files disagree about which blocks existed. What survived in prose is what the tool cannot say for itself — facts about the *host* (the permission matcher matches command text; a follower dies with the turn that started it) and comparisons *between* commands, which no single command's `--help` can carry because no command knows about the others.

- **Every `help=` string was audited against the code.** A second Codex read all 143 of them and named 73 as false, overstated, or ambiguous — `--worktree` did not isolate "every writing member", `status --all` did not cap at 20 rows, `--as-ready` did not release on "any terminal state", `--config` replaced a resumed thread's extra config rather than adding to it. All 73 are corrected. What was read is recorded in `.claude/plans/260823/help-audit-manifest.md`, one row per argument, and a test holds that table and the parser to the same shape — so an argument nobody read is now a red suite rather than an omission.

- **The output contract and the state vocabulary are stated once each**, in the top-level and `status` epilogs. There were four copies of the contract and no gloss at all for `stalled` or `orphaned`, the two states callers misread — `stalled` is derived for display and kills nothing, `orphaned` means the supervisor is gone and not that Codex is.

- **`projected_cost.note` no longer carries its sample story.** "measured 6 under of 11" was a fact about eleven runs in one project on one afternoon, printed to every caller forever. What it is — a median, so a scale rather than a bound — survives.

- **`batch start` no longer accepts `--foreground`.** It was accepted by the parser and refused by the command, which forced its help string to read "Refused on `batch start`" — an option surface documenting a hole in itself. Why it cannot work is unchanged. The refusal is now argparse's, so it arrives as a usage error with exit status **2** rather than a JSON error with exit status 1.

- **`__supervise` is hidden from the command listing.** It is a re-exec target this process spawns for itself, and it used to print as `__supervise ==SUPPRESS==`. It still runs when named; it is no longer advertised. This is what lets `SKILL.md` drop its hand-kept command table and point at `--help` instead.

### Removed

- `docs/measurements/` — the two write-ups were method narratives whose conclusions already live in `.claude/harness-spec.md` and next to the constants they justify.

### Fixed

- **`resume` of a thread this skill has never started is refused without an explicit `--sandbox`.** `codex exec resume` has no `-s`, so this wrapper re-asserts the sandbox it recorded on every turn. A thread it never started has no record — and the fallback invented `workspace-write` for a conversation whose own policy nobody knows. Inventing a write policy is the direction that cannot be undone. Pass `--sandbox` once and it is recorded from then on; `status --include-external` lists the threads this applies to.

- **`status` refuses selectors that contradict each other** — `--run` with `--thread`, `--thread` with `--group`, `--include-external` with `--group` — instead of answering whichever branch came first. It also refuses `--interval` or `--follow-timeout` without `--follow`, which previously shaped nothing and read as an instruction that had been taken.

- **`--priority` and `--no-priority` together are refused.** They share one setting, so argparse took whichever came last, and whether a run paid for the priority tier is not visible afterwards.

## [0.4.0] — 2026-08-14

Two new capabilities, and twenty-one defects found by running the thing rather than reading it. The theme is the same one the previous version had, arriving one layer up: almost every defect here is a **confident wrong answer** — the command succeeded, the JSON parsed, and what it said was not true.

**Read Changed before upgrading.** Two things that used to work are now refused, and one JSON field can now be `null` where it was always a number.

### Added

- **`batch start --resume-from <group> --as-ready`** — start each member of a next phase as soon as the member *it* continues finishes, instead of waiting for the slowest member of the previous group. A five-member phase whose first task finishes in a minute and whose last takes twenty no longer holds four members idle for nineteen of them.

  The barrier it replaces was never a concurrency requirement — it existed to stop a phase 2 from half-starting against a phase 1 that was half-finished. The invariant underneath is one turn per thread, and that is per *thread*, so member 3's next phase is safe to begin the moment member 3's current one ends. There is no queue and no group supervisor: each member spawns its own supervisor immediately, exactly as before, and that supervisor waits before it starts Codex. A queued run with nothing supervising it is reaped as `orphaned` within thirty seconds, which is why the earlier `--max-concurrent` idea was abandoned and why this one is shaped differently.

  A waiting member reports `state: "waiting"` with `waits_for` naming the run it is behind. Any terminal state releases it, including a failure — `predecessor_state` says how its predecessor ended, and "work out what went wrong" is a legitimate next phase. Chains work: `p1 → p2 → p3` can all be registered up front. `--timeout` bounds the Codex turn, never the wait; `stop --group` is what ends a wait.

- **`codex_bridge.py models`**, and pre-flight validation of `--model` and `--effort` against it. Valid reasoning efforts differ per model — `gpt-5.6-sol` accepts `ultra`, `gpt-5.6-luna` stops at `max`, `gpt-5.5` at `xhigh` — so a typo used to cost a spawned run that failed at the API. It is now refused before anything is claimed on disk, with the valid efforts for that model named. The catalog is read from Codex rather than hardcoded, because any static list is already wrong for some model the day it is written.

- **`codex_elapsed_seconds`** on every run row: how long the *turn* has taken, as distinct from how long the run has existed. They differ only for a member that waited, which is exactly the member the question gets asked about.

- **`unparsed_events`**, reported when non-zero, counting lines of the event stream that could not be read. `status` and `result` previously summarised a damaged stream identically to a clean one.

### Changed

- **`batch start --foreground` is now refused.** It ran the batch one member at a time: `task_args` copied the flag onto every member and nothing downstream ever looked at it, so the spawn loop waited out each member's entire Codex turn before starting the next. Measured: three members hanging two seconds each took 7.15 seconds, with their run ids two seconds apart, and the reply had the same shape it would have had concurrently. To block until a batch is done, start it and then `status --group <name> --follow`.

- **`stop --run X --all` is now refused.** `--all` was silently dropped and only the named run was stopped, with a success reply. `status --run X --all` is unaffected and still means what it meant — there `--all` lifts a row-count cap rather than selecting anything.

- **`uncommitted_files_in_caller_tree` can now be `null`.** It was `0` when `git status --porcelain` failed, so "there are none" and "I could not tell" left by the same door — and that number is stated to Codex as fact in the worktree preamble, which exists precisely to correct a confident falsehood. A corrupt `.git/index` makes `status` exit 128 while `rev-parse` and `worktree add` both still succeed, so the batch got far enough to write the sentence. The preamble now says the count is unknown when it is.

- **A run whose `meta.json` will not parse is no longer reported as a run that never existed.** `status`, `log`, `show`, `stop` and `result` answered `no such run` for a directory sitting on disk with its event stream intact. They now say what is actually wrong and where to look.

- **A corrupt group manifest is no longer a permanent dead end.** `batch clean --group X --force` could not clear it, because the check ran before `--force` was ever consulted — so the members' worktrees, which hold the only copy of what those runs produced, were stranded with no way out. Membership does not depend on the manifest (each run records its own group), so only `--resume-from`, which needs the recorded order, still refuses.

### Fixed

- **Two turns could run on one thread**, racing the same rollout file — the corruption the whole guard system exists to prevent — through three separate routes. A run whose `meta.json` was unreadable was invisible to the concurrent-turn guard, because the thread id and the state both live in the file that will not parse. A supervisor killed on its own leaves its `codex exec` running, and `reap` correctly records `orphaned`, which anything reading terminal as "safe to start" then treated as free. And a member chained behind another could start when its direct predecessor went terminal while its *grandparent* was still mid-turn.

  `orphaned` keeps its meaning — nothing is left to *record* this run's outcome, which is not the same as nothing running. What changed is that every place asking whether a **thread** is free now asks whether anything is still writing, rather than reading a state that answers a different question.

- **`stop --group` and `stop --all` reported success having signalled nothing**, for a run whose supervisor had died while its Codex kept writing. An empty `stopped` list with exit status 0 — and `stop` is the escape hatch every other refusal points at.

- **`batch clean` could delete a live member's worktree with no `--force`**, in the loop whose own comment names that case as the first thing that must stop a clean. git independently refuses to remove a *dirty* worktree, so work already written was safe; a run that had just committed, or was still reading before writing, was not. Relatedly, `--force` released a group name while a live member still claimed it, after which reclaiming the name broke the new owner's own `batch clean`.

- **`status --group --follow` and `log --follow` could print their terminal line and exit while events were still arriving**, which is precisely the contract they are paired with the Monitor tool on. `result` could return two different "final" messages ten seconds apart with neither marked partial.

- **`doctor` and `concurrent_writers` invented a collision** between a waiting member and the predecessor it is queued behind — they share a directory by design and are the one pair that cannot write at once — and went silent about a real one, a still-writing run in the same directory, which they are the only surfaces able to report.

- **A `waiting` member was invisible to seven places** that asked "is this active" against a hand-written list of states instead of the shared one: `stop` skipped it, a group of waiters reported `completed` on its first poll, and plain `status` counted it in no summary bucket while `status --group` counted it as running.

- **The test suite had been dead and said it was fine.** Moving `tests/` to `tests/legacy/` shifted every path constant by one directory and killed all 301 tests, and the documented command answered `NO TESTS RAN` with exit status 0. Fixed, and the suite now asserts that every command written in the contributing guide and the wiki actually collects tests — a suite cannot notice its own absence unless something makes it.

### Known limitations

Everything listed under 0.3.0 still applies, with two updates.

- Measurements are now against `codex-cli 0.147.0`. The integration tier passes 14 of 15 in one run and 15 of 15 across two: case I15 asks two Codex runs each to create a file and then checks that `batch clean` refuses both dirty worktrees, so it depends on the model performing a task and is **flaky by construction**. Worth knowing before anyone debugs it as a regression.
- The concurrency question the previous version listed as unmeasured — several processes driving one project — is now measured two ways: a ten-oracle soak in the suite, and independent agents driving one repository at once. Neither runs for hours, neither exceeds a handful of concurrent writers, and both use the fake Codex shim, so what is proven is the bridge's own concurrency rather than Codex's behaviour under it.
- **The defect-discovery rate has not converged.** Four review rounds ran for this version and none came back clean; three of them found defects in the *previous* round's fixes. The project's own bar — two consecutive rounds finding nothing reachable in ordinary single-session use — is not met and is not claimed.

## [0.3.0] — 2026-08-04

A verification round, and what it found. No new capability: this version exists because the previous one was measured properly for the first time — every user-facing flag driven against the real Codex CLI, deliberate faults injected, and four adversarial review rounds. Nineteen defects came out of that, and their common shape is the reason to upgrade: almost all of them were **silent**. The command succeeded, the JSON parsed, and the answer was wrong.

**Read the Changed section before upgrading.** Five things that used to be accepted are now refused, and one JSON field was renamed.

### Security

- **`--config` could override the sandbox this skill exists to enforce.** `codex`'s `-c` is last-value-wins for a repeated key, and the caller's raw `--config` entries were emitted *after* the enforced `-c sandbox_mode=`. So `start --sandbox read-only --config 'sandbox_mode="danger-full-access"'` ran fully privileged while `status` went on reporting `read-only` — and because `extra_config` is inherited by every resume, it did so for the rest of the thread. Measured against the real binary: the same file write is refused one way and succeeds the other. Two guards now — the four keys this wrapper sets are refused outright with the flag that owns each one named, and the enforced settings are emitted last, so a key nobody thought to reserve still cannot outrank an invariant.

### Changed

- **Refused where previously accepted.** Each of these used to succeed and silently do something other than what was asked:
  - `--config` naming `sandbox_mode`, `service_tier`, `model_reasoning_effort` or `model` — use `--sandbox`, `--priority`/`--no-priority`, `--effort`, `--model`.
  - `status --follow` without `--group`. `--follow` only ever meant `--group --follow`; elsewhere it returned one snapshot and exited, which a caller reads as "I waited for this". To watch one run, use `log --run <id> --follow`.
  - `--run` together with `--group`, on `status`, `stop` **and** `result`. They are different questions, and passing both silently dropped one — `stop --group G --run L` left every member of G running and reported success.
  - `log --since <n>` where *n* is not an event boundary. Such a cursor is one fed back from a different run; accepting it destroyed the event straddling that offset and said nothing.
  - A `review` task in a `--tasks-file` whose `review` object combines selectors, sets `title` without `commit`, or holds an unknown key. The command-line `review` refused all three; the batch path enforced none, so a `title` was dropped without a word.
- **`projected_cost` fields renamed** from `input_floor_per_run` / `input_floor_total` to `input_median_per_run` / `input_median_total`. It was never a floor: checked against the registry it is computed from, 6 of 11 real runs came in *below* it, which is what a median does. Anything parsing those names must be updated.
- **`doctor` no longer blames every `codex login status` failure on authentication.** A malformed `config.toml` makes that command fail before it looks at auth at all — and `codex login`, the fix both `doctor` and the troubleshooting docs pointed at, fails identically, forever. It now separates "could not run" from "not logged in", and quotes what it saw.
- **`doctor` only counts worktrees this skill cut.** A checkout the user made themselves was reported as "from batch runs, checked out under `.codex-runs`" — false twice over, and `batch clean` cannot touch it either.
- **`doctor` and `concurrent_writers` now agree on what "the same directory" means.** `doctor` compared exact paths, so two live writers in `/p` and `/p/sub` landed in two groups of one and it warned about neither, while the check at run creation had already seen them.
- **`result --group` no longer reports a review member's zero usage as a real zero.** Review turns report all-zero usage after doing real work; the single-run surfaces have carried "unavailable, not free" since v0.1.0. The group total was silently undercounting any batch that mixed a reviewer with writers, which is the documented normal pattern. Such members are now named in `usage_unmeasured` and left out of `totals`.
- **`status` and `doctor` report `runs_unreadable`.** A run whose `meta.json` will not parse used to vanish from every listing while `doctor` went on counting its bytes.

### Fixed

- **A batch killed while spawning reported `group_state: completed`.** The manifest recorded members as the loop reached them and nothing recorded how many had been asked for, so "asked for three, given two" was byte-identical to a group that only ever wanted two. `claim_group` now records `requested` before the first spawn — the last moment that fact still exists.
- **A batch killed while spawning could leave a checkout no group could clean.** `create_run` now publishes the run before cutting its worktree and again immediately after; `batch clean` resolves membership through the registry as well as the manifest; and where a path is still unrecorded it falls back to `<run_dir>/wt`, which is where `create_run` always puts it.
- **`batch clean --force` did not force.** `git worktree add` holds a lock reading `initializing`, a batch killed inside it leaves the worktree locked forever, and `git worktree remove --force` refuses a locked tree — it wants `-f -f`. `batch clean` had been printing that it "lifted every protection at once" while a checkout survived it.
- **`batch clean` could delete the worktree of a run whose `meta.json` was unreadable**, without `--force`, even when that run was last recorded `running`. Unknown is not terminal.
- **Two simultaneous `resume` calls on one thread both started a turn**, leaving two Codex processes appending to one rollout file. The guard now runs under a per-thread lock spanning the check and the new run's publication — including for a thread this registry has never seen, which is the case the feature leads with and which the first attempt at this fix missed.
- **A group name released mid-spawn could be re-claimed under the first batch's feet**, after which that batch's `write_members` merged its members into a stranger's manifest. Each claim now carries an epoch, and a writer that no longer owns the file says so and names what it had already started.
- **A foreground run without `--timeout` recorded the caller's process group**, so `stop --run` on it would have signalled the caller.
- **`overlaps` was never tested against the shapes it exists for.** Seven cases added: a submodule (whose `--git-common-dir` is `<parent>/.git/modules/<name>`), two worktrees of a bare repository, a phase-2 member inheriting its predecessor's tree, a newline in a path, and Unicode — APFS *preserves* normalisation rather than folding it, so NFC and NFD are two true names for one file at the same time, and a run reporting the other form was silently missing the overlap.

### Documentation

- **The `settings.json` rule this project documented for symlink installs never worked.** `$HOME` is not expanded in a permission rule — `${CLAUDE_PLUGIN_ROOT}` is, which is why a plugin install needs no settings at all — and `Skill(codex)` needs its own entry or the skill cannot load and the bridge rule is never reached. Both corrected in the README, verified against a positive control in the default permission mode.
- **A bridge command must be written on one line.** The permission pattern matches command *text*, so a command broken with a trailing backslash does not match. This bites exactly where it is least convenient: `batch start` with several `--task` flags is long, and long commands invite continuations. Now a gotcha in `SKILL.md`.
- **`docs/measurements/batch-cost.md`** — new. Registry cost at 2000 runs (worst command 0.63 s, linear, group views flat — so no cache and no cap), concurrency at N=12/16/24 (no contention, `--stagger` stays out), what `result --group` costs (about 1.75× fetching each member separately — it buys `overlaps` and one round trip, not cheapness), and what `projected_cost` actually predicts.

## [0.2.0] — 2026-08-02

Batch orchestration. Several Codex runs can now be started, watched, collected and cleaned up as one named thing, with a git worktree per writer so concurrent runs cannot edit each other's files mid-edit.

### Added

- **`batch start --group <name>`** — N runs as one addressable group, from repeated `--task` flags or a `--tasks-file` JSONL where each line may override any group-level option. Group names are single-use per project: reusing one would make "the members of this group" ambiguous, and `--resume-from` pairs against exactly that list. One member failing to spawn never takes the batch with it.
- **A git worktree per writing member.** Assigned when two or more members can write, at `.codex-runs/<run_id>/wt`, detached at `HEAD` or `--base <ref>`. Per member rather than per batch: `read-only` and `kind: review` members stay in the caller's tree, because a freshly cut worktree has zero uncommitted changes and a reviewer inside one would be reviewing nothing (measured). The main tree's `git status` stays clean throughout.
- **`--group` selectors on `status`, `result` and `stop`.** `status --group --follow` streams member state changes and always ends on a terminal line, so a group can never end in silence. `result --group` returns each member's message under a byte cap plus `overlaps` — the paths more than one member wrote, keyed by repository so two checkouts of different projects never collide.
- **`batch start --resume-from <group>`** — task *i* continues member *i* of an earlier group, in its recorded start order, keeping that thread and the directory it lives in. Every ambiguity is a refusal rather than a guess: a count mismatch, a member with no thread to continue, a live member, a task whose `kind` contradicts its target.
- **`batch clean --group <name>`** — the only cleanup path; there is no automatic removal and no hook. Refuses without `--force` when the group has live members, when another run is still working inside one of the worktrees, when a group derived from this one exists, or when git itself declines to discard uncommitted changes. `--force` lifts all four at once and says in its reply what it overrode.
- **`--timeout <sec>` now works in the background**, with a terminal state of its own. `timed_out` is distinguished from `interrupted` (you stopped it) and `failed` (Codex did) because only the third is answered by raising the timeout; the thread stays resumable across it with the pre-timeout turn's context intact (measured).
- **A batch preamble** telling each member facts it cannot observe from inside a single non-interactive turn: the group it belongs to, that other runs may be executing alongside it, and — when isolated — its worktree's path, base commit, and how many uncommitted files exist in the caller's tree that it does not have. Measured: without it a run asserted *"we are looking at the same tree"*, wrong and unhedged. 113 input tokens.
- **`concurrent_writers`** on `start` and `resume`, naming other live runs that can write to the same directory, and the same check registry-wide in `doctor`. Reported, never refused. `resume` has no worktree option, so continuing several writers at once is unisolatable by construction and this is the only thing that can say so.
- **Group discoverability.** `status` lists the project's `groups`, and every run row carries its `group` and `worktree` — which is what lets a later session address a batch it did not start.
- **`references/orchestration.md`** and **[Orchestration](docs/wiki/Orchestration.md)** — the mechanics and the traps, deliberately without a catalogue of phase patterns.

### Changed

- **`codex_bridge.py` split into modules.** The entrypoint holds the CLI surface and one handler per subcommand; `_run.py` builds and describes a run, `_batch.py` owns the group subsystem, `_worktree.py` the worktrees. Behaviour unchanged, verified by the suite passing across the move.
- **The run registry is safe under concurrent writers.** Per-writer temp filenames, `flock` around read-modify-write, and compare-and-set for `reap`. The defect was reproduced first: 152 of 240 concurrent writes raised `FileNotFoundError`, and a reaper could overwrite a finished run's recorded outcome.
- **`status`'s default view** keeps every non-terminal run plus a tail of recent ones rather than a plain tail, so a long-running old run can no longer fall off the list. `--group` never truncates.
- **A foreground `--timeout`** now records `timed_out` rather than `interrupted`, so one cause no longer has two names.

### Removed

**Both removals are breaking.** They follow from one principle the user set: the skill holds capability, and cost policy stays theirs.

- **The `SessionEnd` cleanup hook**, and with it `--detach`. Background runs are no longer stopped when a Claude session ends. If you relied on this, `status --all` finds runs from earlier sessions and `stop --run <id>` or `stop --all` ends them; `doctor` now reports the registry's size, the project's groups and any residual worktrees so the accumulation is visible rather than silent.
- **`stop --all-mine`**, replaced by `stop --run <id>… | --group <name> | --all`. Scope is now whatever is visible in the registry rather than an invisible session boundary a subagent's runs may not even share.

### Fixed

- `resume --last` picked the newest run with no filter, so a read-only caller could inherit another run's label and its `danger-full-access` sandbox. It now requires an unambiguous target and echoes which run it resolved to.
- Two turns could run concurrently on one thread, racing on the same rollout file, with exit 0 and no warning. Refused unless `--force`.
- `--since` past the end of the events file printed nothing, exited 0, and echoed the bad cursor back, so a poll loop stuck there forever looked identical to "no new events".
- `turn.failed` was parsed and never surfaced: a failed run showed a null message and the reason needed a second call.
- Thread lookup missed Korean paths stored NFD, and scanned a bounded prefix of the thread database rather than querying it.
- `result --group` cut messages by character and reported by byte, so a 3,000-character Korean message that had not been truncated reported itself truncated.

### Known limitations

- Concurrency was measured up to **8 simultaneous runs** with no thread-database contention, no thread-id collisions and flat wall-clock from N=2 to N=8. Above 8 is unmeasured — that is a range that was not tested, not a ceiling that was found.
- **`overlaps` is the intersection only** (paths more than one member wrote), not a per-run file list. Under worktree isolation an overlap is a merge conflict ahead rather than damage already done; without worktrees it is damage already done.
- **Collecting a batch's results is a separate step.** `batch start` returns when the members are spawned and the group finishing is not the results being collected — `result --group` is its own call. Ending a turn on "I'll report when it finishes" delivers nothing.
- Measured against `codex-cli 0.146.0`. The earlier tiers were measured on `0.144.1`; the thread database's filename is version-stamped, so a Codex upgrade may still degrade `--include-external` and a registry-less `resume --last`, which `doctor` reports rather than failing on.

## [0.1.0] — 2026-07-25

First release. A Claude Code plugin containing one skill (`codex`) that drives the OpenAI Codex CLI as a managed subagent.

### Added

- **`codex_bridge.py`** — a Python 3.10+ stdlib-only CLI with nine subcommands: `start`, `resume`, `review`, `status`, `log`, `show`, `stop`, `result`, `doctor`. Every command prints one line of JSON except `log`, which prints compact text plus an incremental cursor.
- **Sandbox stability across turns.** Every per-invocation setting — sandbox, model, reasoning effort, isolation, working directory — is recorded at run creation and re-asserted on every subsequent invocation as `-c sandbox_mode=` and friends. This closes a measured defect in the Codex CLI: `codex exec resume` has no `-s` flag, so an unre-asserted resume re-derives the sandbox from whatever config layer is in effect — escalating a `read-only` thread to `danger-full-access` under the user's config, or silently downgrading a `workspace-write` thread to `read-only` under isolation.
- **Run registry** at `<project>/.codex-runs/`, self-ignoring via a `.gitignore` containing `*` so it never touches the user's own git configuration.
- **Background-first execution.** Runs are supervised by a process spawned into its own session, so supervisor and Codex share one process group. `stop` signals exactly one run's group and never matches processes by name, which is what makes concurrent runs safe.
- **Filtered event log** with four levels. The default, `compact`, was chosen from a measurement across four real workloads recorded in `docs/measurements/filter-calibration.md`, not by assumption.
- **`show --item`** as the single, explicit escape hatch to a command's full output, with loud truncation above a byte cap.
- **`SessionEnd` hook** that stops this session's non-detached background runs. Standalone by design so it fits the event's 1.5 s timeout; the no-runs-dir path measures 20–30 ms.
- **`doctor`**, which separates blockers (exit 2) from warnings and reports the resolved `CODEX_HOME`, auth state, the config-file sandbox, the resolved script path, and whether the project has an `AGENTS.md`.
- Structured output via `--output-schema`, image attachment via `-i`, and a `review` path over `codex exec review`'s distinct flag surface.
- 124 unit tests against a fake `codex` shim replaying event streams captured from real runs, including a dedicated regression test asserting that a resumed run's recorded argv carries the sandbox it was created with.

### Known limitations

- **No mid-turn steering.** `codex exec` is a single non-interactive turn with no input channel once running; intervention is stop-then-resume. `codex app-server` is the one plausible route to real steering and is recorded as unexplored, not impossible.
- **`review` runs report zero token usage.** Measured on every review run. `status` and `result` report `null` rather than presenting zero as a measurement.
- **Exit code is an imperfect proxy** for "this command's output matters" at the `normal` filter level. Search and lint tools routinely exit non-zero without failing. The alternatives are worse; the limitation is documented rather than hidden.
- **`codex cloud` and `codex mcp-server`/`app-server` are out of scope**, both documented upstream as subject to change without notice.
- Measurements were taken against `codex-cli 0.144.1` on a single machine. The thread database filename is version-stamped, so a Codex upgrade may degrade `--include-external` and a registry-less `resume --last`; `doctor` reports that case rather than failing.

[0.5.0]: https://github.com/tjdwls101010/Codex-in-Claude/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/tjdwls101010/Codex-in-Claude/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/tjdwls101010/Codex-in-Claude/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/tjdwls101010/Codex-in-Claude/releases/tag/v0.2.0
[0.1.0]: https://github.com/tjdwls101010/Codex-in-Claude/releases/tag/v0.1.0
