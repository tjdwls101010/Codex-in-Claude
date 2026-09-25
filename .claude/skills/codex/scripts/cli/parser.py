"""Every flag, choice, help string and epilog of the CLI, and the formatter that renders them."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cli.batch import cmd_batch_clean, cmd_batch_start
from cli.diagnose import cmd_doctor, cmd_models
from cli.observe import SHOW_MAX_BYTES, cmd_log, cmd_result, cmd_show, cmd_status
from cli.runs import cmd_resume, cmd_start, cmd_stop
from codex.argv import SANDBOX_MODES
from codex.events import DEFAULT_LEVEL, FAIL_HEAD_BYTES, FAIL_TAIL_BYTES, FULL_ITEM_BYTES, LEVELS
from core.groups import TASK_FIELDS
from core.observe import STALL_SECONDS
from core.supervisor import DEFAULT_GRACE, THREAD_ID_WAIT, supervise


OUTPUT_CONTRACT = """\
Output. Every public command that parses its arguments prints one line of JSON,
success or failure, except `log`, which streams events and ends with
`# cursor=<n>`, and `status --group --follow`, which streams a line per member
state change and then a terminal `group.<state>` line. Anything that does not
parse is argparse's own usage error on stderr instead.
"""

STATUS_EPILOG = """\
The states, and what each one is telling you.

  starting    forked; the supervisor has not reported yet
  waiting     left by releases before 0.8: a batch member queued behind the
              run it continues. Live until its supervisor exits; `stop` ends it
  running     Codex has the turn
  stalled     running, with no events for %(stall)ds. Derived for display,
              never
              stored, and nothing is ever killed for it — the threshold cannot
              tell a slow command from a wedged one and you can. It does not
              look at in_progress_item: read that field alongside it, because
              idle inside a command_execution is a long build and idle with no
              item is worth investigating.
  completed   terminal: Codex finished the turn
  failed      terminal: Codex ended non-zero
  interrupted terminal: you stopped it
  timed_out   terminal: --timeout's deadline passed
  orphaned    terminal, and the odd one: this run's supervisor died without
              writing an outcome, so nothing is left recording it — a machine
              sleep, a hard kill. Codex itself may still be running and still
              writing files. The thread survives either way, so `resume`
              continues it.

A group reports its own `group_state`, and it has three values. `running`;
`completed` when every member reached a terminal state successfully; `partial`
otherwise — which includes after a `stop --group`, so `partial` means "not all
members succeeded", never "Codex failed". `--group` never truncates its listing;
you named the members.

`idle_seconds` is now minus the mtime of the last event.
""" % {"stall": STALL_SECONDS}

RUN_RETURN_EPILOG = """\
When this returns. As soon as there is a handle to hand back; it does not wait
for the turn to finish. The run is spawned under a supervisor process of its
own, so it is not tied to this command's lifetime.

The report waits up to %(wait)ds for the thread id to appear before it is
written, so this can come back with `thread_id: null`. That is a normal return, not a failure — `status`
backfills the id from the first line of events.jsonl — and until a run has one
there is no conversation to continue, so `resume` refuses it.

Nothing announces the end. No callback, no signal: the supervisor writes the
outcome into this run's meta.json and exits, so a run that finished and a run
still working are the same thing to look at until something asks. `status --run
<id>` asks once. `log --run <id> --follow` is the call that ends when the run
does, and it has a line for every terminal state, so a run that dies is not
silence.

Collecting it is a separate call. `result --run <id>` is what hands back the
work, and a run that finished is not a run you have read.

What Codex is actually sent. Your prompt, with one paragraph in front of it
stating what this turn's situation is: that nobody is watching, so a clarifying
question ends the turn with the work not done, and that the final message is
what reaches the caller. It is not optional. Measured, a run without it asserted
something about its own situation that was simply false, so the paragraph
corrects a fabrication rather than merely adding facts, and it costs about 113
input tokens.
""" % {"wait": THREAD_ID_WAIT}


BATCH_START_EPILOG = """\
When this returns. Every spawn has been attempted; it does not wait for a
single turn to finish. Each member is given up to %(wait)ds for its thread id
to appear before the report is written, so a member can come back with
`thread_id: null`. That is a normal return, not a failure — `status` backfills
the id from the first line of events.jsonl — but do not resume a member until
it has one.

Waiting for it, and collecting it. `status --group <name>` is the snapshot and
`status --group <name> --follow` blocks until the group reaches a terminal
state; `--follow-timeout` bounds that wait. Neither returns the work: `result
--group <name>` is a separate call, and a group that finished is not a group
you have read.

A member that failed to spawn keeps its slot with an `error` and no run_id, so
the list is never shorter than the tasks you handed over. Those slots appear as
`unstarted` and make the group `partial`. One member failing never takes the
others down, whatever the cause.

Worktrees. Off unless --worktree is passed, in which case a member is eligible
for its own git checkout at <run_dir>/wt when all of this holds: it is a
kind=start task, its sandbox can write, it names no cwd of its own, the project
is a git repository, and --base resolves. Eligible, not guaranteed — if git
cannot cut the checkout, that member's spawn fails and the others carry on. A
resume, a read-only member and one with an explicit cwd are never isolated, by
any flag. The checkout is cut from --base (default HEAD), so it holds none of
your uncommitted work — which is also why a read-only member never gets one,
since an uncommitted diff it was started to look at lives only in your tree —
and none of what git does not track either, so a canonical interpreter,
a provider cache or a fixture directory kept out of git is absent from it.
`missing_ignored` in the reply names up to 20 of the ones this tree actually
has, with `missing_ignored_truncated` counting any beyond that. Members' results
stay inside those checkouts: `result --group` reports what each member did and
which paths more than one wrote, and moving the changes into your tree is yours
to do. `batch clean --group` removes the checkouts once they are clean, or
discards their contents under --force.

Without it, every member works in your tree, which is what a fan-out of Claude's
own subagents does: the changes are in front of you as they are made and there
is nothing to collect. What you give up is that no member can tell another
member's edit from its own, so `result --group`'s `overlaps` is a report of what
already happened rather than of a merge still ahead.

What a member is told on top of that. The group's size and name, so a run knows
other runs may be editing other paths alongside it — and, where it was given a
worktree, that its tree is not the caller's, which commit it was cut from, and
how many uncommitted files the caller's tree has that its own does not.

Tasks. --task is a bare prompt, kind=start unless --resume-from turns it into
the resume of the member it pairs with. --tasks-file takes one JSON object per
line for everything else; its fields are listed above and generated from the
same tuple the validator checks against. Group-level options are defaults a
per-item field overrides. An unknown field name, or one with the wrong type,
fails the whole command before anything starts, because a silently ignored field
is a member that quietly used the group default instead.
""" % {"wait": THREAD_ID_WAIT}


class HidesSuppressedCommands(argparse.RawDescriptionHelpFormatter):
    """argparse lists every named subparser and prints `==SUPPRESS==` for one
    whose help is suppressed, rather than leaving it out.

    That is the difference between a command list a caller can trust and one
    they have to filter. `__supervise` is a re-exec target this process spawns
    for itself; a listing that names it is a listing SKILL.md cannot defer to,
    which is the whole reason SKILL.md carried a hand-kept copy of it.

    Raw description handling comes along because the epilogs below are laid out
    — argparse's own wrapping would reflow them into one paragraph.
    """

    def _iter_indented_subactions(self, action):
        for sub in super()._iter_indented_subactions(action):
            if sub.help is not argparse.SUPPRESS:
                yield sub


def add_heartbeat(p):
    p.add_argument("--heartbeat", type=float, metavar="SEC",
                   help="print `still-running elapsed=<s> running=<n>` on the "
                        "first poll at or after each SEC of following — a poll "
                        "period, not a timer. Off by default, and refused "
                        "without --follow or at zero or less. What it adds is "
                        "the half nothing else covers: a run that has gone "
                        "quiet shows up as `stalled` in `status --group "
                        "--follow` after 300 idle seconds, while a follower "
                        "that is alive with nothing to say and one that died "
                        "look the same in either follower.")


def add_common(p):
    p.add_argument("--runs-dir",
                   help="where run state lives (default: <project>/.codex-runs)")
    p.add_argument("--project",
                   help="project root whose registry to use (default: the git "
                        "toplevel of the working directory, or that directory "
                        "itself when it is not a repository)")


def add_run_options(p, *, kind):
    p.add_argument("--label",
                   help="short name for the run; appears in its run id and in "
                        "`status`. A resumed run inherits the label of the run "
                        "it was resolved from unless this replaces it.")
    p.add_argument("--sandbox", choices=SANDBOX_MODES,
                   help="what the run may do to the filesystem (default: "
                        "workspace-write). Recorded against the run, and "
                        "re-asserted on every later turn this registry can "
                        "resolve a base for — which is every resume of a run "
                        "this skill started, and none of a thread it did not.")
    p.add_argument("--model",
                   help="model slug. Checked against this install's catalog "
                        "before the run spawns when that catalog can be read, "
                        "and not at all when it cannot — never fail-closed; "
                        "`models` prints it. Four steps decide it when this is "
                        "unset: what a resumed thread recorded, then your "
                        "config.toml's `model`, then nothing at all and the "
                        "server picks. `doctor` prints which of those applies "
                        "here as effective_defaults.")
    p.add_argument("--effort",
                   help="reasoning effort. Valid values differ per model — "
                        "`models` prints each model's, with its default, and "
                        "omitting this is not the same as passing `medium`. "
                        "Unset it follows the same four steps as --model, "
                        "reading `model_reasoning_effort` from your "
                        "config.toml; with nothing to read, nothing is sent "
                        "and the server applies that model's own default.")
    p.add_argument("--inherit-config", action="store_true",
                   help="load the user's config.toml: their MCP servers, "
                        "plugins, agent roles and hooks. Off by default — a "
                        "fresh run is isolated, and a resumed one keeps "
                        "whatever its thread recorded. Auth is unaffected "
                        "either way, coming from auth.json.")
    tier = p.add_mutually_exclusive_group()
    tier.add_argument("--priority", dest="priority", action="store_true", default=None,
                   help="force service_tier=\"priority\" — the tier Codex "
                        "labels \"Fast mode\" and its config.toml spells "
                        "\"fast\"; both names are advertised and both were "
                        "measured to run clean. Only needed to override: "
                        "unset, an isolated run already takes whatever "
                        "service_tier your config.toml sets, and a resumed one "
                        "carries forward what its thread recorded.")
    tier.add_argument("--no-priority", dest="priority", action="store_false",
                   help="send no service_tier at all, and record that choice "
                        "so later turns on the thread do not re-add Fast "
                        "mode. That "
                        "is not the same as forcing the standard tier — "
                        "omitting the key leaves the server's own default, and "
                        "a run under --inherit-config can still pick the tier "
                        "up from your config.toml. Refused alongside "
                        "--priority.")
    p.add_argument("--schema",
                   help="path to a JSON Schema file handed to Codex. "
                        "`result --run` then returns the parsed object as "
                        "`json` and fails loudly if the final message is not "
                        "valid JSON; `result --group` does not parse, so "
                        "collect a schema batch member by member.")
    p.add_argument("--timeout", type=float,
                   help="give the run this many seconds, then SIGINT its process "
                        "group and record state=timed_out — a state of its own, "
                        "so a deadline is never mistaken for a failure you "
                        "should not retry. "
                        "No default: no flag, no deadline. The thread is "
                        "resumable across it only if a thread id was recorded "
                        "before the deadline; without one there is no "
                        "conversation to continue. If Codex does not exit on "
                        "the SIGINT the signal ladder escalates.")
    if kind in ("start", "resume"):
        p.add_argument("--image", action="append",
                       help="attach an image file to the prompt. Repeatable.")
        p.add_argument("--prompt-file",
                       help="read the prompt from this file instead of the "
                            "positional argument")
    if kind in ("start", "batch"):
        p.add_argument("--cwd",
                       help="directory the run works in (default: the project "
                            "root)")
        p.add_argument("--add-dir", action="append",
                       help="extra writable root beyond --cwd. Repeatable. "
                            "Codex offers it on `exec` only, so it cannot be "
                            "added to a resumed run later.")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="cli_codex.py",
        formatter_class=HidesSuppressedCommands,
        description="Drive the OpenAI Codex CLI as a managed subagent.",
        epilog=OUTPUT_CONTRACT)
    ap.subparser_map = {}
    # An explicit metavar, because argparse builds the default one from every
    # registered name including the suppressed one.
    sub = ap.add_subparsers(
        dest="cmd", required=True,
        metavar="{start,resume,status,log,show,stop,result,batch,"
                "models,doctor}",
        help="the whole command surface. Each takes its own --help, which is "
             "where every flag, its default and what it refuses are stated.")

    p = sub.add_parser("start", formatter_class=HidesSuppressedCommands,
                       help="a fresh thread, backgrounded — when you want the work done rather than judged",
                       epilog=RUN_RETURN_EPILOG)
    add_common(p); add_run_options(p, kind="start")
    p.add_argument("prompt", nargs="?",
                   help="the prompt. May instead come from --prompt-file, or "
                        "from stdin when this is `-` or omitted and stdin is "
                        "not a terminal.")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser(
        "resume", formatter_class=HidesSuppressedCommands,
        help="another turn on a thread, keeping what it already worked out",
        epilog=RUN_RETURN_EPILOG)
    add_common(p); add_run_options(p, kind="resume")
    p.add_argument("--last", action="store_true",
                   help="pick the thread to continue instead of naming one. "
                        "Candidates are registry runs that recorded a thread "
                        "id: exactly one live run wins, none falls back to the "
                        "newest and says so, two or more is ambiguous and is "
                        "refused with the candidates listed. Threads started "
                        "outside this skill are never picked; name one to "
                        "resume it.")
    p.add_argument("--force", action="store_true",
                   help="start a turn on a thread the concurrency check "
                        "objected to — one that already has a live turn, or one "
                        "whose metadata could not be read, which is the same "
                        "refusal for the opposite reason.")
    p.add_argument("rest", nargs="*", metavar="[REF] PROMPT",
                   help="run id / thread id / thread name, then the prompt; "
                        "with --last, just the prompt. A ref this registry has "
                        "never seen — a thread id or name from the Codex TUI — "
                        "is passed through to Codex, but its original sandbox "
                        "was never recorded and there is nothing to re-assert, "
                        "so it is refused without an explicit --sandbox. A run "
                        "whose thread_id is still null has no conversation yet "
                        "and is refused too — wait for `status` to backfill it.")
    p.set_defaults(func=cmd_resume, cwd=None, add_dir=None, ref=None, prompt=None)
    ap.subparser_map["resume"] = p

    p = sub.add_parser(
        "status", formatter_class=HidesSuppressedCommands,
        help="is it alive, how far along, what it last said — registry state, not the event stream",
        description="State, never output. The default listing also carries this "
                    "project's `groups` and gives every row its `group` (the "
                    "full row, with `worktree`, is behind --run, --thread and "
                    "--group), which is how a session that did not start a "
                    "batch finds it: the group name is the one thing about a "
                    "batch nobody can re-derive.",
        epilog=STATUS_EPILOG)
    add_common(p)
    p.add_argument("--run", metavar="REF",
                   help="one run: a run id, a thread id, or a run-id prefix "
                        "(newest wins)")
    p.add_argument("--thread", metavar="THREAD_ID",
                   help="every run on one thread")
    p.add_argument("--group", help="report on one batch group's members only")
    p.add_argument("--all", action="store_true",
                   help="every run in the registry. Without this, and without "
                        "--run, --thread or --group, the listing keeps every "
                        "non-terminal run plus the 20 newest — so it can exceed "
                        "20 rows when older runs are still live — and reports "
                        "how many it withheld as runs_truncated.")
    p.add_argument("--follow", action="store_true",
                   help="requires --group: plain text rather than the one "
                        "JSON object `status --group` returns — a "
                        "`run <id> <prev> -> <state>` line per member state "
                        "change, with ` exit=N` appended when the state is not "
                        "`completed` and an exit code was recorded, then one "
                        "terminal `group.<state> group=<name> done=N failed=N` "
                        "line, then exit. A group with no resolvable member is "
                        "one `group.empty group=<name>` line instead, carrying "
                        "neither tally. Both closing lines append ` unstarted=N` "
                        "and ` unreadable=N` when either is non-zero. A pure "
                        "view — it holds no state, so a follower that dies loses "
                        "nothing and `status --group` answers the same question "
                        "at any time.")
    p.add_argument("--follow-timeout", type=float,
                   help="stop following after this many seconds and print "
                        "group.still-running instead of a terminal group line. "
                        "No default: the follow ends only when the group does. "
                        "Refused without --follow.")
    add_heartbeat(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser(
        "log", formatter_class=HidesSuppressedCommands,
        help="filtered events from a byte cursor — the whole log, or only what is new")
    add_common(p)
    target = p.add_mutually_exclusive_group()
    target.add_argument("--run", metavar="REF",
                        help="a run id, a thread id, or a run-id prefix (newest "
                             "wins). Omitted, the project's single live run is "
                             "used; with none live the newest terminal one, and "
                             "with two or more live it is refused rather than "
                             "guessed.")
    target.add_argument("--group", metavar="NAME",
                        help="every member of one batch group, interleaved as "
                             "each writes. A first line maps index to run id "
                             "(`group.members group=<name> 0=<run_id>[:label] "
                             "…`), and every event line is prefixed "
                             "`[<index>:<label>]`, or `[<index>]` for a member "
                             "with no label. Under --follow the stream ends on "
                             "the group's own terminal line, the same one "
                             "`status --group --follow` ends on; without it, one "
                             "pass over every member's whole log ending on the "
                             "group's line as it stands, which for a live group "
                             "is `group.running`. --since is refused here: a "
                             "cursor is a byte offset into one file and every "
                             "member has its own.")
    p.add_argument("--since", type=int, default=None,
                   help="resume from the byte offset a previous call printed as "
                        "`# cursor=<n>`. Omitted, the whole log. Only "
                        "complete lines are consumed, so nothing is duplicated "
                        "or skipped however often you poll.")
    p.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL,
                   help="how much of each event to print (default: compact). "
                        "All four carry the lifecycle, the agent's own messages "
                        "in full, every command line with its exit code and "
                        "output size, changed paths, errors, searches, MCP "
                        "calls and usage; they differ only in what rides "
                        "along. compact: nothing further. normal: a "
                        f"{FAIL_HEAD_BYTES}B head and {FAIL_TAIL_BYTES}B tail "
                        "of output for commands that exited non-zero, plus "
                        "todo lists. full: the same head/tail excerpt for every "
                        f"command whatever its exit code ({FULL_ITEM_BYTES}B "
                        "of excerpt, before the marker naming what was left "
                        "out), and reasoning items, which no lower level "
                        "shows. raw: the events verbatim. The split is on exit "
                        "code rather than size, which is a proxy and not a "
                        "verdict — a command that exits non-zero because one "
                        "file argument was missing brings its output along too.")
    p.add_argument("--follow", action="store_true",
                   help="print events as they arrive, then one terminal line "
                        "(run.completed / run.failed / run.interrupted / "
                        "run.timed_out / run.orphaned, with the exit code) "
                        "before exiting. There is a line for every terminal "
                        "state on purpose: a follower that only printed "
                        "progress would go silent through a crash, and silence "
                        "is indistinguishable from still working.")
    p.add_argument("--follow-timeout", type=float,
                   help="stop following after this many seconds and print "
                        "run.still-running instead of a terminal line, so a "
                        "watcher cannot hang on a wedged run. Shapes nothing "
                        "without --follow.")
    add_heartbeat(p)
    p.set_defaults(func=cmd_log)

    p = sub.add_parser(
        "show", formatter_class=HidesSuppressedCommands,
        help="one item's output, when the summary looks wrong",
        description="Returns exactly one item's full aggregated_output (or a "
                    "file_change's whole change list) and nothing else's. This "
                    "is the only path by which complete command output reaches "
                    "a caller's context, and it is always one explicit request "
                    "at a time.")
    add_common(p)
    p.add_argument("--run", required=True, metavar="REF",
                   help="required: item ids restart at item_0 in every run's "
                        "event stream, so two runs on one thread each have an "
                        "item_0 meaning different things and an item id alone "
                        "identifies nothing")
    p.add_argument("--item", required=True, metavar="ITEM_ID",
                   help="the item to fetch, as printed by `log` (item_0, "
                        "item_1, …). An unknown id is refused with up to 60 of "
                        "the run's completed items listed.")
    p.add_argument("--max-bytes", type=int, default=SHOW_MAX_BYTES,
                   help=f"cap on command output returned (default: "
                        f"{SHOW_MAX_BYTES}); a file_change's list is not capped. "
                        "Truncation is reported with the true size and how to "
                        "raise the cap, never silent.")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser(
        "stop", formatter_class=HidesSuppressedCommands,
        help="interrupt a run, a group, or everything, by process group")
    add_common(p)
    p.add_argument("--run", action="append", metavar="REF",
                   help="a run to interrupt. Repeatable. No default target: one "
                        "of --run, --group or --all is required.")
    p.add_argument("--group",
                   help="interrupt every live member of a batch group")
    p.add_argument("--all", action="store_true",
                   help="interrupt every run in this project's registry that "
                        "is still doing something — every non-terminal one, "
                        "plus an orphaned run whose Codex is still writing")
    p.add_argument("--grace", type=float, default=DEFAULT_GRACE,
                   help="seconds to wait after SIGINT before SIGTERM, then 3s "
                        "before SIGKILL (default: 5.0). Signals go to the run's "
                        "recorded process group, never to a matched process "
                        "name, so one run's stop cannot reach another's — "
                        "matching `codex exec` by name would reach every Codex "
                        "on the machine, including another person's. The ladder "
                        "starts at SIGINT because that lets Codex flush its "
                        "rollout: a stopped run stays resumable and the resumed "
                        "turn still knows what the interrupted one finished. "
                        "That is the whole of mid-turn steering — there is no "
                        "channel into a running turn, so redirecting one is "
                        "stop then resume. A process group isolates signals and "
                        "nothing else: two runs in one directory still edit the "
                        "same files.")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser(
        "result", formatter_class=HidesSuppressedCommands,
        help="the run's message and usage — final once it ends, partial while it runs")
    add_common(p)
    p.add_argument("--run", metavar="REF",
                   help="one run's whole message — final once the run ends, "
                        "and whatever it has said so far while it is live. No "
                        "default target: one of --run or --group is required.")
    p.add_argument("--group",
                   help="collect a batch group: every member that started, "
                        "capped per run, with usage, files_changed and "
                        "`overlaps` — the paths more than one member was "
                        "observed writing. Members that never started are "
                        "listed separately under `unstarted` rather than "
                        "silently shortening the list.")
    p.set_defaults(func=cmd_result)

    p = sub.add_parser(
        "batch", formatter_class=HidesSuppressedCommands,
        help="several runs as one name you can watch, collect and stop together",
        description="A group is the set of runs one `batch start` created, "
                    "addressable afterwards as one thing — by `status --group`, "
                    "`result --group`, `stop --group`, `batch clean --group` "
                    "and `batch start --resume-from`. It outlives the session "
                    "that started it. The name is single-use per project.")
    bsub = p.add_subparsers(dest="batch_cmd", required=True)
    b = bsub.add_parser("start", help="start N runs as one addressable group",
                        formatter_class=HidesSuppressedCommands,
                        epilog=BATCH_START_EPILOG)
    add_common(b); add_run_options(b, kind="batch")
    b.add_argument("--group", required=True,
                   help="name for this group. Single-use per project until "
                        "`batch clean` releases it: reusing a live name would "
                        "make membership and start order ambiguous, and "
                        "--resume-from pairs positionally against exactly that "
                        "list.")
    b.add_argument("--task", action="append",
                   help="a prompt. Repeatable, and ordered before any "
                        "--tasks-file entries. kind=start on its own; under "
                        "--resume-from each becomes the resume of the member it "
                        "pairs with.")
    b.add_argument("--tasks-file",
                   help="JSONL, one task object per line, for long or "
                        "heterogeneous tasks; see the epilog for how these "
                        "interact with the group-level options. Fields: "
                        + ", ".join(TASK_FIELDS))
    b.add_argument("--force", action="store_true",
                   help="allow a resume task to start a second turn on a thread "
                        "that already has a live one")
    b.add_argument("--worktree", action="store_true",
                   help="give each writing member its own git checkout instead "
                        "of the caller's tree. Off by default: members share "
                        "the tree, so their work is in it as they do it. Reach "
                        "for this when two or more members can touch the same "
                        "files — the cost is that results stay in the "
                        "checkouts until you collect them, and that a checkout "
                        "holds only what git tracks. Per member, not per "
                        "batch: a resume, a read-only member and one with "
                        "its own cwd stay in the caller's tree whatever this "
                        "says.")
    b.add_argument("--base",
                   help="commit or ref the worktrees are cut from (default "
                        "HEAD). Refused without --worktree, which is the only "
                        "thing it shapes. A base older than HEAD can be "
                        "missing the project's AGENTS.md, which reaches a "
                        "worktree run only from a base where the file exists.")
    b.add_argument("--resume-from", metavar="GROUP",
                   help="continue an earlier group: task i resumes member i of "
                        "that group, in its start order, keeping its thread and "
                        "the directory it already lives in — including that "
                        "group's worktrees, which are preserved rather than "
                        "reissued, so a phase 1 that was never isolated stays "
                        "un-isolated. One task per started member, unless a "
                        "task names its own target with kind/resume, which "
                        "wins over its positional counterpart.")
    b.set_defaults(func=cmd_batch_start)

    b = bsub.add_parser("clean", formatter_class=HidesSuppressedCommands,
                        help="remove a group's worktrees, and release its name when nothing is left")
    add_common(b)
    b.add_argument("--group", required=True,
                   help="the group to clean up. The name is released only when "
                        "nothing is left behind. Refused while a member is live, "
                        "and a worktree another live run is working inside is "
                        "kept; both say which `stop` ends them. Also refused "
                        "while a member's meta.json will not parse or a group "
                        "derived from this one still needs the worktrees, and a "
                        "worktree git will not discard uncommitted changes from "
                        "is kept.")
    b.add_argument("--force", action="store_true",
                   help="lift every refusal at once, not only the one you "
                        "hit, including a manifest that will not parse — except "
                        "that a worktree whose run is live, or whose meta.json "
                        "will not parse, is always kept. The result says what "
                        "it overrode. "
                        "Where a worktree held uncommitted changes, that work "
                        "had no other copy.")
    b.set_defaults(func=cmd_batch_clean)

    p = sub.add_parser(
        "models", formatter_class=HidesSuppressedCommands,
        help="which models and efforts exist here, before you name one",
        description="This install's model catalog, read live from `codex debug "
                    "models` and cached once per process. Each model carries "
                    "its own `efforts` and its own `default_effort` — they are "
                    "not a shared ladder every model climbs the same way, which "
                    "is why no list of them is written down anywhere here. "
                    "`start`, `resume` and `batch start` check a passed --model "
                    "or --effort against this before spawning. When it cannot "
                    "be read the check is skipped rather than failing closed, "
                    "and `doctor` reports models_catalog as null with a "
                    "warning saying why.")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser(
        "doctor", formatter_class=HidesSuppressedCommands,
        help="why is Codex not behaving — env, auth, sandbox, paths",
        description="Exits 0 when healthy and 2 when there is a blocker, so it "
                    "is usable in a conditional. Blockers stop a run working at "
                    "all: no codex on PATH, no authentication, a missing "
                    "CODEX_HOME, an unwritable runs dir, Python below 3.10. "
                    "The warnings are things that work but are worth "
                    "knowing: a "
                    "config.toml set to danger-full-access, a project "
                    "AGENTS.md. Check auth "
                    "before anything else — an unauthenticated run fails in "
                    "ways that look like other problems. `codex_home` is "
                    "printed resolved, with `codex_home_from_env` saying "
                    "whether it was overridden; an override moves sessions, "
                    "config.toml and auth.json with it, so ~/.codex is then "
                    "someone else's state or nothing.")
    add_common(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("__supervise", help=argparse.SUPPRESS)
    p.add_argument("--run-dir", required=True,
                   help="the run directory to supervise. Not a command a caller "
                        "runs: this process re-execs itself with it to become "
                        "the detached supervisor for a run it just claimed.")
    p.set_defaults(func=lambda a: sys.exit(supervise(Path(a.run_dir))))

    return ap
