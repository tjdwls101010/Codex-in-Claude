# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Drive the OpenAI Codex CLI as a managed subagent. This file is the whole command surface — every flag, help text and epilog, the checks made from the arguments alone, dispatch into the `codex` package, and the output contract — and the entrypoint a detached supervisor re-executes. What a command does lives in `codex/`.

Exit codes:
    0  success
    1  the registry's state refused the command, or the run failed; the reply carries `error`
    2  the command line itself must change; the reply carries `error` and the `help` to read
    3  `doctor` found a blocker
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from codex.batch import commands as batch_commands
from codex.batch.tasks import TASK_FIELDS
from codex.codex_cli.argv import SANDBOX_MODES
from codex.codex_cli.config import codex_home
from codex.codex_cli.events import DEFAULT_LEVEL, FAIL_HEAD_BYTES, FULL_ITEM_BYTES, LEVELS
from codex.doctor import doctor, models
from codex.errors import Refusal
from codex.observe import log, result, status
from codex.observe.collect import GROUP_MESSAGE_CAP
from codex.observe.rows import STALL_SECONDS
from codex.observe.show import SHOW_MAX_BYTES, show
from codex.observe.status import LISTING_ROWS
from codex.registry.groups import valid_name
from codex.runs import commands as run_commands
from codex.runs.supervisor import DEFAULT_GRACE, THREAD_ID_WAIT, supervise

EXIT_REFUSED, EXIT_ARGUMENTS, EXIT_BLOCKED = 1, 2, 3

OUTPUT_CONTRACT = """\
Output: every command prints one line of JSON on stdout, a result or a refusal carrying `error`, except the text views below.
Exit codes: 0 success; 1 refused by the registry's state — a run or group that is not there, a thread with a live turn, a name already taken — or the run failed; 2 the command line itself must change — it does not parse, combines flags that cannot go together, or names a file, commit or model that does not exist — and the reply's `help` is the `--help` to read; 3 `doctor` found a blocker.
These views print text instead:
  result --run              a JSON header line, then the message itself and one newline its `message_bytes` leaves out (a --schema run stays one JSON document)
  result --group            a JSON header line, then per member a `--- [<index>:<label>] run=<id> state=<state> bytes=<n>` line, its message and one newline; the header's `members[].shown_bytes` say where each message ends
  log --run                 event lines, then `# cursor=<n> run=<id>`
  log --group               a `group.members` header, member-prefixed event lines, then a closing `group.<state>` line
  status --group --follow   a line per member state change, then a closing `group.<state>` line"""


RUN_EPILOG = f"""\
Returns as soon as the run has a handle: once its thread id appears, or after {THREAD_ID_WAIT:.0f} s with `thread_id: null`, which `status` fills in later. A run without a thread id cannot be resumed yet. A detached supervisor runs the turn, so the run outlives this command.
Nothing announces the end: run the reply's `next.command` — `log --run <id> --follow`, written out whole — in the background, and it returns when the run does, with a line for every terminal state. `status --run <id>` answers once; `result --run <id>` collects what it concluded.
Codex receives the prompt behind a paragraph saying the turn is non-interactive — a clarifying question ends it with the work undone — and that its final message is what reaches the caller."""


RESUME_EPILOG = RUN_EPILOG + """
A resume is a new run on the same thread with its own event log. It re-asserts the sandbox, model, effort, service tier and isolation the thread recorded, except where a flag changes them."""


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


BATCH_START_EPILOG = f"""\
Returns once every member's spawn has been tried, each after up to {THREAD_ID_WAIT:.0f} s for its thread id. A member that fails to spawn keeps its slot with an `error` and no `run_id`, and the others start anyway. Group options are defaults each task's own fields override.
Nothing announces the end: run the reply's `next.command` — `status --group <name> --follow` — in the background; it is left out when no member started.
Worktrees: with --worktree, a member gets a detached checkout at <run_dir>/wt when it is a fresh start (not a resume), its sandbox can write, it has no cwd of its own, and the project is a git repository with a commit to cut from. A checkout holds only what git tracks at --base, none of your uncommitted or ignored files; the reply's `missing_ignored` names ignored entries the checkouts lack. Results stay in the checkouts: `result --group` reports which paths more than one member wrote, moving the changes into your tree is yours to do, and `batch clean` removes the checkouts.
Without --worktree, members work in your tree as they go and none can tell another member's edit from its own; the reply says so when two or more writers share a directory.
Each member is told the group's name and size; a member with a checkout is also told it is not your tree, which commit it came from, and how many uncommitted files yours has."""


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


def invocation(*words):
    """This CLI called again the way SKILL.md calls it: `uv run "<this file, as the caller named it>" <words>`. The path is not resolved, so a symlinked install keeps the path its pre-approval matches."""
    path = os.path.abspath(sys.argv[0])
    # Double quotes are what the pre-approval pattern has; a path they cannot hold safely gets shell quoting instead.
    quoted = shlex.quote(path) if any(c in path for c in '"$`\\') else f'"{path}"'
    return " ".join(["uv run", quoted, *(shlex.quote(str(w)) for w in words)])


class JsonArgumentParser(argparse.ArgumentParser):
    """A command line that does not parse is answered like any other that must change: one line of JSON on stdout, exit 2, naming the `--help` to read."""

    def parse_args(self, args=None, namespace=None):
        # Arguments no parser claimed are reported by the root, whose own help says nothing about them; the namespace already names the command they were given to.
        ns, extras = self.parse_known_args(args, namespace)
        if extras:
            self.refuse(f"unrecognized arguments: {' '.join(extras)}", command_words(ns) if getattr(ns, "cmd", None) else [])
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
    if not valid_name(text):
        raise argparse.ArgumentTypeError("group name must be 1–64 ASCII letters, digits, `.`, `_` or `-`, starting with a letter or digit (no path separators)")
    return text


def refuse_unusable_follow_options(args):
    """`--follow-timeout` and `--heartbeat` only mean something to a follower; accepted otherwise they would read as obeyed."""
    for flag in ("--follow-timeout", "--heartbeat"):
        if getattr(args, flag[2:].replace("-", "_"), None) is not None and not args.follow:
            raise Refusal(f"{flag} requires --follow", arguments=True)


def with_next(out, args, *words):
    """The reply with `next` after its handle: the follower to run in the background, written out whole so it matches the pre-approval, and carrying the registry the command line named."""
    where = []
    if args.project:
        where += ["--project", os.path.abspath(os.path.expanduser(args.project))]
    if args.runs_dir:
        where += ["--runs-dir", os.path.abspath(os.path.expanduser(args.runs_dir))]
    items = list(out.items())
    # Right after the handle: a run's state, or a batch's counts.
    at = next((i + 1 for i, (k, _v) in enumerate(items) if k in ("state", "requested")), 1)
    return dict(items[:at] + [("next", {"command": invocation(*words, *where), "run_in_background": True})] + items[at:])


def cmd_start(args):
    out = run_commands.start(args)
    return with_next(out, args, "log", "--run", out["run_id"], "--follow")


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
    out = run_commands.resume(args)
    return with_next(out, args, "log", "--run", out["run_id"], "--follow")


def cmd_status(args):
    if args.follow and not args.group:
        raise Refusal("--follow requires --group; to follow one run use `log --run <id> --follow`", arguments=True, run=args.run)
    refuse_unusable_follow_options(args)
    return status.status(args)


def cmd_log(args):
    refuse_unusable_follow_options(args)
    if args.group and args.since is not None:
        raise Refusal("--since takes one run's cursor and a group has one per member; use `log --run <id> --since <n>`",
                      arguments=True, group=args.group)
    return log.log(args)


def cmd_batch_start(args):
    if args.base and not args.worktree:
        # Refused before the claim, so a typo does not burn the name.
        raise Refusal("--base requires --worktree", arguments=True, base=args.base)
    out = batch_commands.start(args)
    return with_next(out, args, "status", "--group", out["group"], "--follow") if out["spawned"] else out


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
    p.add_argument("--heartbeat", type=positive_seconds, metavar="SEC",
                   help="print `still-running elapsed=<s> running=<n>` on the first poll at or after every SEC seconds of following (default: off). Requires --follow; SEC must be positive")


def add_run_options(p, *, kind):
    """Options shared by `start` (kind "start"), `resume` and `batch start` (kind "batch")."""
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
    p.add_argument("--schema", help="JSON Schema file Codex shapes its final message to. `result --run` then returns the message parsed as `json` — parsed, not re-validated against the schema — and fails when it is not JSON; `result --group` does not parse" + (". A resume keeps the thread's schema unless this replaces it" if kind == "resume" else ""))
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
        prog="cli.py", formatter_class=OneLinePerParagraph, epilog=OUTPUT_CONTRACT,
        description="Drive the OpenAI Codex CLI as a managed subagent: detached runs with a handle, resumable threads, filtered event logs, and batches addressed as one group. Each command's --help has its flags, defaults and refusals.")
    ap.subparser_map = {}
    # An explicit metavar: argparse's default one lists the suppressed internal command.
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="{start,resume,status,log,show,stop,result,batch,models,doctor}")

    def command(name, help, **kw):
        return sub.add_parser(name, help=help, formatter_class=OneLinePerParagraph, **kw)

    p = command("start", "start a fresh non-interactive thread, detached", epilog=RUN_EPILOG)
    add_common(p)
    add_run_options(p, kind="start")
    p.add_argument("prompt", nargs="?", help="the prompt; `-` or omitted reads stdin when it is not a terminal")
    p.set_defaults(func=cmd_start)

    p = command("resume", "run another turn on an existing thread", epilog=RESUME_EPILOG)
    add_common(p)
    add_run_options(p, kind="resume")
    p.add_argument("--last", action="store_true", help="continue the thread nobody named: the one live run with a thread in this registry, else the newest such run; the reply says which. Refused, listing them, when two or more are live. Never looks outside the registry")
    p.add_argument("--force", action="store_true", help="start a turn even though the thread has a live turn, or a run whose meta.json will not parse may be on it")
    p.add_argument("rest", nargs="*", metavar="[REF] PROMPT", help="a run id, thread id, run-id prefix or thread name, then the prompt (with --last, just the prompt). A ref this registry never recorded is passed to Codex and needs --sandbox; a run whose thread id is still null cannot be resumed yet")
    # `cmd` is set here too because `resume` is parsed by its own subparser, which the root's `dest` never reaches.
    p.set_defaults(func=cmd_resume, cmd="resume", cwd=None, add_dir=None, ref=None, prompt=None)
    ap.subparser_map["resume"] = p

    p = command("status", "run state: whether it is live, how far along, what it last said", epilog=STATUS_EPILOG,
                description=f"Run state from the registry, with short excerpts of the last message and stderr. The default listing, --all included, names the live runs in `running`, counts live, completed and failed runs in `counts` rather than naming finished ones, lists the project's `groups`, and gives a summary row per run — every live run plus the {LISTING_ROWS} newest, with `runs_truncated` counting the rest. --run, --thread and --group give full rows, with the `done` and `failed` run ids among them.")
    add_common(p)
    selector = p.add_mutually_exclusive_group()
    selector.add_argument("--run", metavar="REF", help="one run's full row: a run id, thread id or run-id prefix (newest match wins)")
    selector.add_argument("--thread", metavar="THREAD_ID", help="full rows of the runs on one thread, capped like the default listing unless --all")
    selector.add_argument("--group", help="full rows of one batch group's members, with `group_state`; never truncated")
    p.add_argument("--all", action="store_true", help=f"no display cap: every run, not only the live ones and the {LISTING_ROWS} newest")
    p.add_argument("--follow", action="store_true", help="requires --group. Text instead of JSON: `run <id> <prev> -> <state>` for each member state change (with ` exit=N` when the state is not completed), then one closing line — `group.<state> group=<name> done=N failed=N`, or `group.empty group=<name>` when no member resolves — which appends ` unstarted=N` and ` unreadable=N` when either is non-zero")
    add_follow_options(p, closing="`group.still-running group=<name> running=N done=N failed=N`")
    p.set_defaults(func=cmd_status)

    p = command("log", "a run's or a group's events, filtered, from a byte cursor")
    add_common(p)
    target = p.add_mutually_exclusive_group()
    target.add_argument("--run", metavar="REF", help="a run id, thread id or run-id prefix (newest match wins). Omitted: the project's one live run, else its newest run; refused when two or more are live")
    target.add_argument("--group", metavar="NAME", help="every member of a batch group, interleaved: a `group.members group=<name> 0=<run_id>[:<label>] …` header, each event line prefixed `[<index>:<label>]` or `[<index>]`, then the group's closing line as `status --group --follow` prints it (for a live group without --follow, `group.running`); no cursor trailer")
    p.add_argument("--since", type=int, default=None, metavar="CURSOR", help="print only events after this byte offset from a previous `# cursor=<n>` trailer (default: the whole log). Refused unless it is a line boundary of this run's file, and with --group")
    p.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL, help=f"how much of each event to print (default: {DEFAULT_LEVEL}). Every level prints the lifecycle, the agent's messages in full, each command line with its exit code and output size, changed paths, errors, searches, MCP calls and usage. compact: nothing more. normal: a {FAIL_HEAD_BYTES} B head and tail of the output of commands that exited non-zero, and todo lists. full: a {FULL_ITEM_BYTES} B excerpt of every command's output, and reasoning. raw: every event parsed and re-serialised, one JSON object per line")
    p.add_argument("--follow", action="store_true", help="keep printing events as they arrive until the end: for a run, one closing `run.<state> run=<id> exit=<n>` line for every terminal state and the cursor trailer; for a group, its closing line. A run whose Codex is still writing has not ended")
    add_follow_options(p, closing="`run.still-running run=<id> state=<state>` and the cursor trailer for a run, or `group.still-running group=<name> running=N done=N failed=N` for a group")
    p.set_defaults(func=cmd_log)

    p = command("show", "one item of a run in full: a command's output or a file change's paths",
                description="One run-scoped item in full: a command's output, capped by --max-bytes with the truncation reported, a file change's list of paths, or any other item as recorded.")
    add_common(p)
    p.add_argument("--run", required=True, metavar="REF", help="the run: item ids restart at item_0 in every run, so an item id means nothing without it")
    p.add_argument("--item", required=True, metavar="ITEM_ID", help="the item id as `log` prints it (item_0, item_1, …); an unknown id is refused with up to 60 of the run's items listed")
    p.add_argument("--max-bytes", type=int, default=SHOW_MAX_BYTES, help=f"cap on the command output returned (default: {SHOW_MAX_BYTES}); the reply states the full size")
    p.set_defaults(func=show)

    p = command("stop", "interrupt a run, a group, or every live run",
                description="Interrupt runs through their recorded process groups, never by process name. A run still in an active state is recorded `interrupted`; one that already recorded an outcome, or an orphaned one, keeps its state, and `state` in the reply says which. One of --run, --group or --all is required. A running turn cannot be redirected; stop it, then `resume` the thread.")
    add_common(p)
    selector = p.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run", action="append", metavar="REF", help="a run to interrupt; repeatable")
    selector.add_argument("--group", help="every live member of a batch group")
    selector.add_argument("--all", action="store_true", help="every live run in this registry, including an orphaned run whose Codex is still writing")
    p.add_argument("--grace", type=float, default=DEFAULT_GRACE, metavar="SEC", help=f"seconds after SIGINT before SIGTERM (default: {DEFAULT_GRACE}); SIGKILL follows 3 s later, and whatever of the run is left is swept with SIGKILL. SIGINT first lets Codex flush its rollout, so the thread can be resumed")
    p.set_defaults(func=run_commands.stop)

    p = command("result", "what a run or a group concluded",
                description="An answer is read rather than parsed, so it comes as text after a one-line JSON header, and the header's byte counts, not the text, say where each answer ends. A --schema run's answer is parsed, so it stays one JSON document. One of --run or --group is required.")
    add_common(p)
    selector = p.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run", metavar="REF", help="one run: a header with its state, exit code, thread, `message_bytes`, changed files, commands and usage, and `turn_failed` when the turn failed, then its whole final message; while the run is live, what it has said so far, with `note` saying it is partial. A --schema run is one JSON document carrying `json`, the parsed message, and fails while its final message is missing or not JSON")
    selector.add_argument("--group", help=f"every member: a header with `group_state`, usage totals, `overlaps` (the paths more than one member wrote), `unstarted` (members that never started) and each member's state and sizes, then each member's message after its separator line, capped at {GROUP_MESSAGE_CAP} B and cut at a character boundary, the full size stated")
    p.set_defaults(func=result.result)

    p = command("batch", "several runs under one group name",
                description="A group is the set of runs one `batch start` created, addressed afterwards as one name by `status`, `log`, `result` and `stop` with --group, by `batch clean`, and by `batch start --resume-from`. It outlives the session that started it, and its name stays reserved until `batch clean` releases it.")
    bsub = p.add_subparsers(dest="batch_cmd", required=True)
    b = bsub.add_parser("start", help="start N runs as one group", formatter_class=OneLinePerParagraph, epilog=BATCH_START_EPILOG)
    add_common(b)
    add_run_options(b, kind="batch")
    b.add_argument("--group", required=True, type=group_name, help="name for the group: 1–64 characters, ASCII letters, digits, `.`, `_` and `-`, starting with a letter or digit; refused while the name is reserved")
    b.add_argument("--task", action="append", help="a prompt; repeatable, ordered before --tasks-file entries")
    b.add_argument("--tasks-file", help="JSONL, one task object per line, for per-task settings: " + ", ".join(TASK_FIELDS) + ". An unknown field or a wrongly typed value refuses the batch before anything starts")
    b.add_argument("--force", action="store_true", help="with --resume-from, continue members whose turn is still live")
    b.add_argument("--worktree", action="store_true", help="give each eligible member its own git checkout (default: members share your tree); eligibility is below")
    b.add_argument("--base", help="commit the worktrees are cut from (default: HEAD). Requires --worktree")
    b.add_argument("--resume-from", metavar="GROUP", help="continue an earlier group: task i resumes member i in start order, in the directory that member's thread already uses, its worktree included, unless --cwd or the task's `cwd` names another. A task naming its own `resume` target keeps it. Refused, before anything is claimed, unless every started member has recorded a thread and finished (see --force) and the task count matches")
    b.set_defaults(func=cmd_batch_start)

    b = bsub.add_parser("clean", help="remove a group's worktrees and release its name", formatter_class=OneLinePerParagraph,
                        description="Remove a group's worktrees and release its name once nothing is left.")
    add_common(b)
    b.add_argument("--group", required=True, help="the group to clean. Refused while a member is live, and a worktree another live run works in is kept; both name the `stop` that ends them. A worktree whose run's meta.json will not parse is kept too. Refused, unless --force, when the manifest or a member's meta.json will not parse or another group was resumed from this one; a worktree with uncommitted changes is kept unless --force")
    b.add_argument("--force", action="store_true", help="lift the refusals --group says --force lifts, all at once, and discard uncommitted changes in the worktrees — that work has no other copy. `forced_past` in the reply says what was overridden")
    b.set_defaults(func=batch_commands.clean)

    p = command("models", "the models and efforts this Codex install offers",
                description="This install's model catalog from `codex debug models`: each model's slug, efforts and default effort. `start`, `resume` and `batch start` check a --model or --effort against it before spawning. When it cannot be read the check is skipped and this command exits 1.")
    p.set_defaults(func=models)

    p = command("doctor", "check the environment a run would start in",
                description="The environment a run would start in, as one JSON line: Python, codex on PATH and its version, CODEX_HOME (resolved; `codex_home_from_env` says whether it was set), login, config.toml's sandbox and the defaults a run naming nothing would get, the model catalog, the registry, overlapping live writers and leftover worktrees. Exits 3 when a blocker would stop a run — no codex, not logged in, a missing CODEX_HOME, an unwritable registry, Python below 3.11 — else 0. It spawns nothing, so a failure that only appears once Codex launches shows in the run's `stderr_tail` instead.")
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


def command_words(args):
    """The words that name the command a namespace came from: `status`, or `batch start`."""
    return [args.cmd, args.batch_cmd] if args.cmd == "batch" else [args.cmd]


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    if os.environ.get("CODEX_HOME"):
        # The supervisor and codex run in other directories, so a relative value is pinned to what it meant here.
        os.environ["CODEX_HOME"] = str(codex_home())
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
                out["help"] = invocation(*command_words(args), "--help")
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
