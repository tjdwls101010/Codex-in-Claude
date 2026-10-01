# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Drive the OpenAI Codex CLI as a managed subagent. This file is the whole command surface — every flag, help text and epilog, each command's `Prints:` and `Exits:`, the checks made from the arguments alone, dispatch into the `codex` package, and rendering — and the entrypoint a detached supervisor re-executes. What a command does lives in `codex/`.

Exit codes:
    0  success
    1  the registry's state refused the command, or what it asked for failed; the reply carries `error`
    2  the command line itself must change; the reply carries `error` and the `help` to read
    3  `doctor` found a blocker
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from codex.batch import TASK_FIELDS, batch, clean
from codex.codex_cli import DEFAULT_LEVEL, FAIL_HEAD_BYTES, FULL_ITEM_BYTES, LEVELS, SANDBOX_MODES, pin_codex_home
from codex.doctor import doctor, models
from codex.errors import Refusal
from codex.observe import GROUP_MESSAGE_CAP, LISTING_ROWS, SHOW_MAX_BYTES, STALL_SECONDS, log, result, show, status
from codex.registry import valid_group_name
from codex.runs import DEFAULT_GRACE, THREAD_ID_WAIT, resume, start, stop, supervise
from codex.util import invocation

EXIT_REFUSED, EXIT_ARGUMENTS, EXIT_BLOCKED = 1, 2, 3

ROOT_EPILOG = """\
Every command prints one JSON line on stdout — its result, or a refusal carrying `error` — unless its --help says it prints text.
Exit codes: 0 success; 1 the registry's state refused the command, or what it asked for failed, and `error` says why; 2 the command line must change, and the reply's `help` names the --help to read; 3 `doctor` found a blocker. Each command's --help says what it prints and which of these it ends with when."""


START_DESC = """\
Start a fresh non-interactive Codex thread, detached, and answer as soon as it has a handle.
Prints: one JSON line — `run_id`, `thread_id` (null until Codex reports one), `state`, `next` (the `result --run <id> --wait` call to run in the background), the `sandbox` and `isolated` it runs under, `concurrent_writers` when other live runs can write in its directory, then its `cwd`, `project` and `events` paths.
Exits: 0 started; 1 refused — a model or effort taken from your config.toml that this install does not offer, no free run id — or an internal error; 2 the command line must change — an empty or unreadable prompt, a --cwd, --schema or --image that does not exist, a --model or --effort this install does not offer, or anything else the parser refuses."""


RESUME_DESC = """\
Run another turn on an existing thread, detached: a new run with its own event log, under the sandbox, model, effort, service tier and isolation the thread recorded except where a flag changes them.
Prints: one JSON line as `start` prints, with `sandbox_changed_from` when --sandbox changed the thread's sandbox and, with --last, `resolved_from_run_id` and `resolved_from` naming the run it continued.
Exits: 0 started; 1 refused — the thread has a live turn, or a run whose meta.json will not parse may be on it (both lifted by --force); --last finds no run with a thread, or two or more live ones; the run named has no thread id yet; a thread this registry never recorded, without --sandbox; a model or effort from your config.toml this install does not offer; no free run id — or an internal error; 2 the command line must change — no REF and no --last, more than REF and PROMPT, an empty or unreadable prompt, a --schema or --image that does not exist, a --model or --effort this install does not offer, a directory the thread recorded that no longer exists, or anything else the parser refuses."""


BATCH_DESC = """\
Start several runs as one group: each --task, then each --tasks-file line, is a member started as `start` (or `resume`) would start it, with the group's options as its defaults. The group is addressed afterwards as one name by `status`, `log`, `result` and `stop` with --group, by `clean`, and by `batch --resume-from`; it outlives the session that started it, and its name stays reserved until `clean` releases it.
Prints: one JSON line — `group`, `spawned`, `requested`, `next` (the `result --group <name> --wait` call to run in the background, left out when no member started), `resumed_from` with --resume-from, `worktrees` when checkouts were cut or members share a tree, `runs` (per slot its `run_id`, `state`, `cwd`, `sandbox` and `worktree`, or the `error` that kept it from starting) and the `manifest` path.
Exits: 0 every member's start was tried, even when some failed and carry `error`; 1 refused before anything started — the name is reserved; a model or effort from your config.toml this install does not offer; a --resume-from group that is not there, will not parse, has no started member, has a member without a thread id, has a different number of members than there are tasks, or is still running (lifted by --force) — or the name was released and claimed again while members started, or an internal error; 2 the command line must change — a --group that breaks the naming rule, no task, a tasks file that cannot be read or has a line that is not a valid task, --base without --worktree or naming no commit, a --model or --effort a task names that this install does not offer, under --resume-from a task that names its own `resume` target without kind `resume`, or anything else the parser refuses."""


BATCH_EPILOG = f"""\
Returns once every member's spawn has been tried, each after up to {THREAD_ID_WAIT:.0f} s for its thread id; a member that fails to spawn keeps its slot with an `error` and no `run_id`, and the others start anyway.
Worktrees: with --worktree, a member gets a detached checkout at <run_dir>/wt when it is a fresh start (not a resume), its sandbox can write, it has no cwd of its own, and the project is a git repository with a commit to cut from. A checkout holds only what git tracks at --base, none of your uncommitted or ignored files; the reply's `missing_ignored` names ignored entries the checkouts lack. Results stay in the checkouts: `result --group` reports which paths more than one member wrote, moving the changes into your tree is yours to do, and `clean` removes the checkouts.
Without --worktree, members work in your tree as they go and none can tell another member's edit from its own; the reply says so when two or more writers share a directory.
Each member is told the group's name and size; a member with a checkout is also told it is not your tree, which commit it came from, and how many uncommitted files yours has."""


RUN_EPILOG = f"""\
Returns as soon as the run has a handle: once its thread id appears, or after {THREAD_ID_WAIT:.0f} s with `thread_id: null`, which `status` fills in later; a run without a thread id cannot be resumed yet. A detached supervisor runs the turn, so the run outlives this command, and nothing announces its end: the reply's `next.command`, run in the background, returns when the run does and prints its result.
Codex receives the prompt behind a paragraph saying the turn is non-interactive — a clarifying question ends it with the work undone — and that its final message is what reaches the caller."""


STATUS_DESC = f"""\
Run state from the registry: whether runs are live, how far along, and what they last said, with short excerpts of the last message and stderr.
Prints: one JSON line. With no selector, the listing — `running` (the live run ids), `counts` of live, completed and failed runs, the project's `groups`, and a summary row per run: every live run plus the {LISTING_ROWS} newest, `runs_truncated` counting the rest (--all lifts the cap). --run prints that run's full row itself. --group prints `group_state`, `running`, `done`, `failed`, `unstarted` when a member never became a readable run, and the members' full rows. --group --follow prints text instead: `run <id> <prev> -> <state>` for each member state change (with ` exit=N` when the state is not completed), then one closing line — `group.<state> group=<name> done=N failed=N`, or `group.empty group=<name>` when no member resolves, with ` unstarted=N` and ` unreadable=N` appended when non-zero; when --follow-timeout passes first, `group.still-running group=<name> running=N done=N failed=N`.
Exits: 0 answered; 1 refused — a --run that is not there or whose meta.json will not parse, a --group that is not there or whose manifest will not parse — or an internal error; 2 the command line must change — --follow without --group, --follow-timeout without --follow, or anything else the parser refuses, --run with --group included."""


STATUS_EPILOG = f"""\
States:
  starting     the supervisor has not reported yet
  running      Codex has the turn
  stalled      running with no event for {STALL_SECONDS} s; advisory, nothing is killed for it — read `in_progress_item` beside it
  waiting      left by releases before 0.8: a batch member queued behind the run it continues; live until its supervisor exits, and `stop` ends it
  completed    terminal: Codex exited 0
  failed       terminal: Codex exited non-zero
  interrupted  terminal: stopped
  timed_out    terminal: its --timeout passed
  orphaned     terminal: its supervisor died without recording an outcome; `codex_still_running` says Codex is still writing, and the thread is resumable if a thread id was recorded
A group's `group_state` is `running` while any member is live, `completed` when every member completed, and `partial` otherwise — a failure, a stop, a timeout or a member that never started.
`idle_seconds` is the time since the run's last event."""


LOG_DESC = """\
What a run or a group is doing: its events filtered to a level, from a byte cursor, followed to the end on request.
Prints: text. For a run, its event lines, then `# cursor=<n> run=<id>`; with --follow, a closing `run.<state> run=<id> exit=<n>` comes before the cursor, or `run.still-running run=<id> state=<state>` when --follow-timeout passes first. For a group, a `group.members group=<name> 0=<run_id>[:<label>] …` header, each event line prefixed `[<index>:<label>]` or `[<index>]`, then the closing line `status --group --follow` prints (`group.running` for a live group without --follow), and no cursor.
Exits: 0 printed; 1 refused — no --run or --group and no runs in the registry, or two or more live runs to choose from; a --run that is not there or whose meta.json will not parse; a --group that is not there or whose manifest will not parse; a --since past the end of this run's events file or not on a line boundary of it — or an internal error; 2 the command line must change — --since with --group, --follow-timeout without --follow, or anything else the parser refuses, an unknown --level or --run with --group included."""


SHOW_DESC = """\
One item of a run in full: a command's output, capped by --max-bytes with the truncation reported, a file change's list of paths, or any other item as recorded.
Prints: one JSON line — `run_id`, `item_id`, `item_type`, then for a command its `command`, `exit_code`, `total_bytes`, `truncated` and `output` (with `shown_bytes` and `truncation_notice` when capped), for a file change its `changes`, and for anything else the `item`.
Exits: 0 found; 1 refused — a run that is not there or whose meta.json will not parse, an item the run does not have (`available` lists up to 60 it does) — or an internal error; 2 the command line must change — no --run or --item, a --max-bytes that is not a number, or anything else the parser refuses."""


RESULT_DESC = f"""\
What a run or a group concluded: at once, partial while it is live, or — with --wait — once it has ended.
Prints: for a run, a JSON header line — `run_id`, `state`, `exit_code`, `thread_id`, `note` when the result is partial, `turn_failed` when the turn failed, `files_changed`, `commands`, `usage`, `message_bytes` — then the final message and one newline `message_bytes` leaves out, neither when the message is empty. A --schema run prints one JSON document instead, indented, carrying `json`: the final message parsed (not re-validated against the schema), or null while the run is live. For a group, a JSON header line — `group_state`, `done`, `failed`, `running`, `unstarted` (members that never became a readable run), `overlaps` (paths more than one member wrote), `totals`, and `members` with each one's state and sizes — then per member a `--- [<index>:<label>] run=<id> state=<state> bytes=<n>` line (`[<index>]` without a label), its message capped at {GROUP_MESSAGE_CAP} B at a character boundary, and one newline; `members[].shown_bytes` says where each message ends.
Exits: 0 printed, whatever state the run or group is in, also when --wait-timeout passes first; 1 refused — a run that is not there or whose meta.json will not parse, a group that is not there or whose manifest will not parse, a finished --schema run whose final message is missing, not UTF-8 or not JSON (`message` carries it) — or an internal error; 2 the command line must change — neither or both of --run and --group, --wait-timeout without --wait or not a positive number, or anything else the parser refuses."""


STOP_DESC = """\
Interrupt runs through their recorded process groups, never by process name: SIGINT, then SIGTERM after --grace, then SIGKILL. A running turn cannot be redirected; stop it, then `resume` the thread.
Prints: one JSON line — `stopped`, an entry per run with its `run_id`, `pgid`, `signals_sent`, `signalled`, `state` and `thread_id` (`state` is `interrupted` for a run that was still active; one that had already recorded an outcome, or an orphaned one, keeps its state), with `reason` when it recorded no process group and `error` when the group could not be signalled — then `claude_session_id`.
Exits: 0 every target was tried; 1 refused — a --run that is not there or whose meta.json will not parse, a --group that is not there or whose manifest will not parse — or an internal error; 2 the command line must change — none, or more than one, of --run, --group and --all, or anything else the parser refuses."""


CLEAN_DESC = """\
Remove a group's worktrees and release its name once nothing is left. Live work is never removed, --force or not.
Prints: one JSON line — `group`, `name_released`, `forced_past` and `forced_note` when --force overrode something, `note` saying why the name stays reserved, `removed`, and `kept` with each kept worktree's `reason`, and `occupied_by` with the `stop` call that ends it when a live run works there.
Exits: 0 cleaned as far as it could, `name_released` saying whether all of it; 1 refused — no such group; a live member (`stop` holds the calls that end them); without --force, a manifest or a member's meta.json that will not parse, or another group continued from this one — or an internal error; 2 the command line must change — no --group, or anything else the parser refuses."""


MODELS_DESC = """\
This install's model catalog from `codex debug models`. `start`, `resume` and `batch` check a --model or --effort against it before spawning; when it cannot be read, the check is skipped.
Prints: one JSON line — `models`, each with its `slug`, `display_name`, `default_effort`, `efforts`, `context_window`, `visibility` and `supported_in_api`, and `codex_version`.
Exits: 0 read; 1 the catalog cannot be read (`doctor` says why), or an internal error; 2 an argument the parser refuses."""


DOCTOR_DESC = """\
The environment a run would start in. It spawns nothing, so a failure that only appears once Codex launches shows in the run's `stderr_tail` instead.
Prints: one JSON line — `ok`, `blockers`, `warnings`, then what they rest on: Python; codex on PATH and its version; CODEX_HOME, resolved, with `codex_home_from_env` saying whether it was set; login; config.toml's sandbox and the `effective_defaults` a run naming nothing would get; the model catalog; the skill's `entry`; the registry, overlapping live writers and leftover worktrees.
Exits: 0 no blocker; 3 a blocker would stop a run — no codex, not logged in, a missing CODEX_HOME, an unwritable registry, Python below 3.11; 1 an internal error; 2 an argument the parser refuses."""


TIER_DEFAULT = "a resumed thread's recorded tier while its isolation is unchanged, otherwise `service_tier` from your config.toml, as for --model"


class OneLinePerParagraph(argparse.HelpFormatter):
    """Renders each help paragraph and list item as one physical line, never re-wrapped to a width, and leaves suppressed subcommands out of the listing."""

    def _split_lines(self, text, width):
        return text.splitlines() or [""]

    def _fill_text(self, text, width, indent):
        return "\n".join(indent + line for line in text.splitlines())

    def _iter_indented_subactions(self, action):
        for sub in super()._iter_indented_subactions(action):
            if sub.help is not argparse.SUPPRESS:
                yield sub


class JsonArgumentParser(argparse.ArgumentParser):
    """A command line that does not parse is answered like any other that must change: one line of JSON on stdout, exit 2, naming the `--help` to read."""

    def parse_args(self, args=None, namespace=None):
        # Arguments no parser claimed are reported by the root, whose own help says nothing about them; the namespace already names the command they were given to.
        ns, extras = self.parse_known_args(args, namespace)
        if extras:
            self.refuse(f"unrecognized arguments: {' '.join(extras)}", [ns.cmd] if getattr(ns, "cmd", None) else [])
        return ns

    def error(self, message):
        self.refuse(message, self.prog.split()[1:])

    def refuse(self, message, words):
        reply({"error": message, "help": invocation(*words, "--help")}, code=EXIT_ARGUMENTS)


# -- checks made from the arguments alone --------------------------------------

def positive_seconds(text):
    """A number of seconds above zero; zero or less would read as obeyed while meaning something else."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of seconds") from None
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive number of seconds")
    return value


def group_name(text):
    """A name a group can be claimed under: it becomes a filename."""
    if not valid_group_name(text):
        raise argparse.ArgumentTypeError("group name must be 1–64 ASCII letters, digits, `.`, `_` or `-`, starting with a letter or digit (no path separators)")
    return text


def refuse_unusable_follow_options(args):
    """`--follow-timeout` only means something to a follower; accepted otherwise it would read as obeyed."""
    if args.follow_timeout is not None and not args.follow:
        raise Refusal("--follow-timeout requires --follow", arguments=True)


def cmd_resume(args):
    # `[REF] PROMPT` is two optional positionals argparse cannot tell apart; with --last everything positional is the prompt.
    rest = list(args.rest)
    args.ref = None if args.last else (rest.pop(0) if rest else None)
    if len(rest) > 1:
        raise Refusal("too many positional arguments: resume takes [REF] PROMPT", arguments=True,
                      expected="resume <ref> <prompt>  |  resume --last <prompt>", got=list(args.rest))
    args.prompt = rest[0] if rest else None
    if not args.last and not args.ref:
        raise Refusal("resume needs a run id, thread id, thread name, or --last", arguments=True)
    return resume(args)


def cmd_status(args):
    if args.follow and not args.group:
        raise Refusal("--follow requires --group; to follow one run use `log --run <id> --follow`", arguments=True, run=args.run)
    refuse_unusable_follow_options(args)
    return status(args)


def cmd_log(args):
    refuse_unusable_follow_options(args)
    if args.group and args.since is not None:
        raise Refusal("--since takes one run's cursor and a group has one per member; use `log --run <id> --since <n>`",
                      arguments=True, group=args.group)
    return log(args)


def cmd_batch(args):
    if args.base and not args.worktree:
        # Refused before the claim, so a typo does not burn the name.
        raise Refusal("--base requires --worktree", arguments=True, base=args.base)
    return batch(args)


def cmd_result(args):
    if args.wait_timeout is not None and not args.wait:
        raise Refusal("--wait-timeout requires --wait", arguments=True)
    return result(args)


def doctor_reply(args):
    """The report, with the exit code that says whether a blocker would stop a run."""
    report = doctor(args)
    return report, 0 if report["ok"] else EXIT_BLOCKED


# -- the parser -------------------------------------------------------------------

def add_common(p):
    p.add_argument("--runs-dir", help="registry directory (default: <project>/.codex-runs)")
    p.add_argument("--project", help="project whose registry to use (default: the git top level of the current directory, or the directory itself)")


def add_follow_options(p, *, closing):
    p.add_argument("--follow-timeout", type=positive_seconds, metavar="SEC",
                   help=f"stop following after SEC seconds with {closing} (default: follow until the end). Requires --follow; SEC must be positive")


def add_run_options(p, *, kind):
    """Options shared by `start` (kind "start"), `resume` and `batch` (kind "batch")."""
    p.add_argument("--label", help="short name shown in the run id and in `status`" + ("; a resume keeps the thread's label unless this replaces it" if kind == "resume" else ""))
    if kind == "resume":
        p.add_argument("--sandbox", choices=SANDBOX_MODES, help="change the thread's sandbox for this and later turns (default: the sandbox the thread recorded). Required for a thread this registry never recorded. A change is reported as `sandbox_changed_from`")
    else:
        p.add_argument("--sandbox", choices=SANDBOX_MODES, help="what the run may do to the filesystem (default: workspace-write" + ("; a resumed member keeps its thread's" if kind == "batch" else "") + "), recorded and re-asserted on every later turn of the thread")
    p.add_argument("--model", help="model slug (default: what a resumed thread recorded, as long as --inherit-config does not change its isolation; otherwise `model` from your config.toml — passed in for an isolated run, read by Codex itself under --inherit-config — and with none, the server's choice). Checked against `models` before spawning when the catalog can be read")
    p.add_argument("--effort", help="reasoning effort; which values a model accepts differs per model, and `models` lists them (default: as for --model, from `model_reasoning_effort`)")
    p.add_argument("--inherit-config", action="store_true", help="load your config.toml — MCP servers, plugins, agent roles, hooks — instead of running isolated (default: isolated for a new thread; a resume keeps the thread's choice). Auth comes from auth.json either way")
    tier = p.add_mutually_exclusive_group()
    tier.add_argument("--priority", dest="priority", action="store_true", default=None, help=f'request service_tier "priority", Fast mode (default: {TIER_DEFAULT})')
    tier.add_argument("--no-priority", dest="priority", action="store_false", help="send no service_tier and record that choice for later turns; under --inherit-config your config.toml can still set one")
    p.add_argument("--schema", help="JSON Schema file Codex shapes its final message to. `result --run` then returns the message parsed as `json` — parsed, not re-validated against the schema — and fails once the run has ended without a final message that is JSON; `result --group` does not parse" + (". A resume keeps the thread's schema unless this replaces it" if kind == "resume" else ""))
    p.add_argument("--timeout", type=float, metavar="SEC", help="seconds from launch before the run's process group gets SIGINT, then SIGTERM and SIGKILL, and the run is recorded `timed_out` (default: none). The thread stays resumable if it recorded a thread id")
    if kind != "batch":
        p.add_argument("--image", action="append", help="attach an image file to the prompt; repeatable")
        p.add_argument("--prompt-file", help="read the prompt from this file")
    if kind == "start":
        p.add_argument("--cwd", help="directory the run works in (default: the project root)")
    if kind == "batch":
        p.add_argument("--cwd", help="directory every member without a `cwd` of its own works in, a resumed member included (default: the project root, and a resumed member keeps its thread's directory). A member given a cwd never gets a worktree")
    if kind != "resume":
        p.add_argument("--add-dir", action="append", help="extra writable directory beyond the run's cwd; repeatable. `codex exec` only, so a resume cannot add one")


def build_parser():
    ap = JsonArgumentParser(
        prog="cli.py", usage="%(prog)s <command> [options]", formatter_class=OneLinePerParagraph, epilog=ROOT_EPILOG,
        description="Drive the OpenAI Codex CLI as a managed subagent: detached runs with a handle, resumable threads, filtered event logs, and batches addressed as one group.")
    ap.subparser_map = {}
    # An explicit metavar: argparse's default one lists the suppressed internal command.
    # `prog` given: derived from the root's usage, every command's usage would repeat `<command> [options]`.
    sub = ap.add_subparsers(dest="cmd", required=True, title="commands", prog="cli.py",
                            metavar="{start,resume,batch,status,log,show,result,stop,clean,models,doctor}")

    def command(name, help, usage, description, **kw):
        return sub.add_parser(name, help=help, usage=f"%(prog)s {usage}", description=description,
                              formatter_class=OneLinePerParagraph, **kw)

    p = command("start", "start a fresh thread, detached; the reply's `next` waits for it and prints its result",
                "[PROMPT] [options]", START_DESC, epilog=RUN_EPILOG)
    add_common(p)
    add_run_options(p, kind="start")
    p.add_argument("prompt", nargs="?", metavar="PROMPT", help="the prompt; `-` or omitted reads stdin when it is not a terminal")
    p.set_defaults(func=start)

    p = command("resume", "run another turn on an existing thread, detached", "(REF | --last) PROMPT [options]",
                RESUME_DESC, epilog=RUN_EPILOG)
    add_common(p)
    add_run_options(p, kind="resume")
    p.add_argument("--last", action="store_true", help="continue the thread nobody named: the one live run with a thread in this registry, else the newest such run; the reply says which. Refused, listing them, when two or more are live. Never looks outside the registry")
    p.add_argument("--force", action="store_true", help="start a turn even though the thread has a live turn, or a run whose meta.json will not parse may be on it")
    p.add_argument("rest", nargs="*", metavar="[REF] PROMPT", help="a run id, thread id, run-id prefix or thread name, then the prompt (with --last, just the prompt). A ref this registry never recorded is passed to Codex and needs --sandbox; a run whose thread id is still null cannot be resumed yet")
    # `cmd` is set here too because `resume` is parsed by its own subparser, which the root's `dest` never reaches.
    p.set_defaults(func=cmd_resume, cmd="resume", cwd=None, add_dir=None, ref=None, prompt=None)
    ap.subparser_map["resume"] = p

    b = command("batch", "start several runs as one group", "--group NAME (--task PROMPT ... | --tasks-file FILE) [options]",
                BATCH_DESC, epilog=BATCH_EPILOG)
    add_common(b)
    add_run_options(b, kind="batch")
    b.add_argument("--group", required=True, type=group_name, help="name for the group: 1–64 characters, ASCII letters, digits, `.`, `_` and `-`, starting with a letter or digit; refused while the name is reserved")
    b.add_argument("--task", action="append", help="a prompt; repeatable, ordered before --tasks-file entries")
    b.add_argument("--tasks-file", help="JSONL, one task object per line, for per-task settings: " + ", ".join(TASK_FIELDS) + ". An unknown field or a wrongly typed value refuses the batch before anything starts")
    b.add_argument("--force", action="store_true", help="with --resume-from, continue members whose turn is still live")
    b.add_argument("--worktree", action="store_true", help="give each eligible member its own git checkout (default: members share your tree); eligibility is below")
    b.add_argument("--base", help="commit the worktrees are cut from (default: HEAD). Requires --worktree")
    b.add_argument("--resume-from", metavar="GROUP", help="continue an earlier group: task i resumes member i in start order, in the directory that member's thread already uses, its worktree included, unless --cwd or the task's `cwd` names another. A task naming its own `resume` target keeps it. Refused, before anything is claimed, unless every started member has recorded a thread and finished (see --force) and the task count matches")
    b.set_defaults(func=cmd_batch)

    p = command("status", "whether runs are live, how far along, and what they last said", "[--run REF | --group NAME] [options]",
                STATUS_DESC, epilog=STATUS_EPILOG)
    add_common(p)
    selector = p.add_mutually_exclusive_group()
    selector.add_argument("--run", metavar="REF", help="one run's full row: a run id, thread id or run-id prefix (newest match wins)")
    selector.add_argument("--group", metavar="NAME", help="one batch group: its members' full rows and `group_state`; never truncated")
    p.add_argument("--all", action="store_true", help=f"no display cap: every run, not only the live ones and the {LISTING_ROWS} newest")
    p.add_argument("--follow", action="store_true", help="requires --group: print a text line per member state change until no member is live, then the closing line")
    add_follow_options(p, closing="`group.still-running group=<name> running=N done=N failed=N`")
    p.set_defaults(func=cmd_status)

    p = command("log", "what a run or a group is doing: its events, filtered, from a byte cursor",
                "[--run REF | --group NAME] [options]", LOG_DESC)
    add_common(p)
    target = p.add_mutually_exclusive_group()
    target.add_argument("--run", metavar="REF", help="a run id, thread id or run-id prefix (newest match wins). Omitted: the project's one live run, else its newest run; refused when two or more are live")
    target.add_argument("--group", metavar="NAME", help="every member of a batch group, interleaved")
    p.add_argument("--since", type=int, default=None, metavar="CURSOR", help="print only events after this byte offset from a previous `# cursor=<n>` trailer (default: the whole log). Refused unless it is a line boundary of this run's file, and with --group")
    p.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL, help=f"how much of each event to print (default: {DEFAULT_LEVEL}). Every level prints the lifecycle, the agent's messages in full, each command line with its exit code and output size, changed paths, errors, searches, MCP calls and usage. compact: nothing more. normal: a {FAIL_HEAD_BYTES} B head and tail of the output of commands that exited non-zero, and todo lists. full: a {FULL_ITEM_BYTES} B excerpt of every command's output, and reasoning. raw: every event parsed and re-serialised, one JSON object per line")
    p.add_argument("--follow", action="store_true", help="keep printing events as they arrive until the end, then the closing line. A run whose Codex is still writing has not ended")
    add_follow_options(p, closing="`run.still-running run=<id> state=<state>` and the cursor trailer for a run, or `group.still-running group=<name> running=N done=N failed=N` for a group")
    p.set_defaults(func=cmd_log)

    p = command("show", "one item of a run in full: a command's output or a file change's paths",
                "--run REF --item ITEM_ID [options]", SHOW_DESC)
    add_common(p)
    p.add_argument("--run", required=True, metavar="REF", help="the run: item ids restart at item_0 in every run, so an item id means nothing without it")
    p.add_argument("--item", required=True, metavar="ITEM_ID", help="the item id as `log` prints it (item_0, item_1, …)")
    p.add_argument("--max-bytes", type=int, default=SHOW_MAX_BYTES, help=f"cap on the command output returned (default: {SHOW_MAX_BYTES}); the reply states the full size")
    p.set_defaults(func=show)

    p = command("result", "what a run or a group concluded — now, or once it has ended with --wait",
                "(--run REF | --group NAME) [options]", RESULT_DESC)
    add_common(p)
    selector = p.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run", metavar="REF", help="one run: a run id, thread id or run-id prefix (newest match wins)")
    selector.add_argument("--group", metavar="NAME", help="every member of a batch group, in start order")
    p.add_argument("--wait", action="store_true", help="wait until the run or group has ended, printing nothing meanwhile, then print what `result` without it would. A run has ended once it is terminal and its Codex no longer writes; a group once no readable member is live — a slot that never started and a member whose meta.json will not parse are not waited for")
    p.add_argument("--wait-timeout", type=positive_seconds, metavar="SEC", help="stop waiting after SEC seconds and print the result as it stands then, partial and saying so (default: wait until the end). Requires --wait; SEC must be positive")
    p.set_defaults(func=cmd_result)

    p = command("stop", "interrupt a run, a group, or every live run", "(--run REF ... | --group NAME | --all) [options]",
                STOP_DESC)
    add_common(p)
    selector = p.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run", action="append", metavar="REF", help="a run to interrupt; repeatable")
    selector.add_argument("--group", metavar="NAME", help="every live member of a batch group")
    selector.add_argument("--all", action="store_true", help="every live run in this registry, including an orphaned run whose Codex is still writing")
    p.add_argument("--grace", type=float, default=DEFAULT_GRACE, metavar="SEC", help=f"seconds after SIGINT before SIGTERM (default: {DEFAULT_GRACE}); SIGKILL follows 3 s later, and whatever of the run is left is swept with SIGKILL. SIGINT first lets Codex flush its rollout, so the thread can be resumed")
    p.set_defaults(func=stop)

    b = command("clean", "remove a group's worktrees and release its name", "--group NAME [options]", CLEAN_DESC)
    add_common(b)
    b.add_argument("--group", required=True, metavar="NAME", help="the group to clean. Refused while a member is live, and a worktree another live run works in is kept; both name the `stop` that ends them. A worktree whose run's meta.json will not parse is kept too. Refused, unless --force, when the manifest or a member's meta.json will not parse or another group was resumed from this one; a worktree with uncommitted changes is kept unless --force")
    b.add_argument("--force", action="store_true", help="lift the refusals --group says --force lifts, all at once, and discard uncommitted changes in the worktrees — that work has no other copy. `forced_past` in the reply says what was overridden")
    b.set_defaults(func=clean)

    p = command("models", "the models and efforts this Codex install offers", "[options]", MODELS_DESC)
    p.set_defaults(func=models)

    p = command("doctor", "check the environment a run would start in", "[options]", DOCTOR_DESC)
    add_common(p)
    p.set_defaults(func=doctor_reply)

    p = sub.add_parser("__supervise", help=argparse.SUPPRESS)
    p.add_argument("--run-dir", required=True, help="internal: the run directory this detached supervisor runs")
    p.set_defaults(func=lambda a: sys.exit(supervise(Path(a.run_dir))))
    return ap


# -- output -------------------------------------------------------------------------

def reply(obj, code: int = 0):
    """Print one line of JSON and exit."""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    sys.exit(code)


def render(out):
    """A command's answer: a dict is one line of JSON, a `(dict, exit code)` pair the same with that code, and anything else is text to stream, piece by piece, each carrying its own newlines."""
    if isinstance(out, tuple):
        reply(*out)
    if isinstance(out, dict):
        reply(out)
    for piece in out:
        sys.stdout.write(piece)
        sys.stdout.flush()


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    pin_codex_home()
    if raw[:1] == ["batch"] and raw[1:2] in (["start"], ["clean"]):
        # A caller holding an older SKILL.md is told the new name once, rather than meeting a parse error.
        new = "batch" if raw[1] == "start" else "clean"
        reply({"error": f"`batch {raw[1]}` is now `{new}`, with the same options", "help": invocation(new, "--help")},
              code=EXIT_ARGUMENTS)
    ap = build_parser()
    # `resume [REF] PROMPT` has two optional positionals; plain parsing would drop the prompt when an option sits between them, and parse_intermixed_args cannot run on a parser that owns subparsers.
    if raw[:1] == ["resume"]:
        args = ap.subparser_map["resume"].parse_intermixed_args(raw[1:])
    else:
        args = ap.parse_args(raw)
    # The reply to a refusal is written inside the guard too: a reader that has gone away is not worth a traceback either way.
    try:
        try:
            out = args.func(args)
            if out is not None:
                render(out)
        except BrokenPipeError:
            raise
        except Refusal as e:
            out = {"error": e.error, **e.fields}
            if e.arguments:
                out["help"] = invocation(args.cmd, "--help")
            reply(out, code=EXIT_ARGUMENTS if e.arguments else EXIT_REFUSED)
        except KeyboardInterrupt:
            reply({"error": "interrupted"}, code=EXIT_REFUSED)
        except Exception as e:
            reply({"error": f"internal error: {e}"}, code=EXIT_REFUSED)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
