"""The `codex exec` argv for a run, and the paragraphs put in front of its prompt.

Two invariants, both forced by `exec` having `-s` and `-C` while `exec resume` has neither: the sandbox always travels as `-c` entries — `sandbox_mode="<mode>"`, or for a read-only run that writes scratch a permissions profile in its place — and the working directory is always set on the child process. Applied uniformly, a resumed turn cannot drift.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from codex.codex_cli.catalog import PROFILE_FLOOR, codex_support, floor_text

SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")

# The modes under which a run can change files, and so collide with another run writing in the same directory.
WRITING_SANDBOXES = ("workspace-write", "danger-full-access")

# The profile a read-only run that writes scratch runs under. Defined in full on every turn rather than extended from a built-in, so its meaning does not depend on the Codex release; Codex merges a profile of the same name from config.toml, which is why only an isolated run gets it.
READ_ONLY_PROFILE = "codex_skill_read_only"

STRICT = "so this run gets the stricter read-only, which cannot write even a temporary file: tests and builds that need one fail"

# Situational facts only: the costly failure of a non-interactive turn is spending it asking a question nobody will answer, and a run told nothing about its situation was seen asserting false things about it.
PREAMBLE = (
    "[Run context: you are a single non-interactive `codex exec` turn. Nobody is "
    "watching a prompt, so a clarifying question ends this turn with the work not "
    "done — take the most reasonable reading, proceed, and state what you assumed. "
    "Your final message is what the caller receives; put the answer there, not only "
    "in files you touched.]"
)

# "may be" and "tasks", not "are" and "runs": members spawn in sequence and one may never have spawned, so asserting either would state something unobservable.
BATCH_PREAMBLE = (
    "[Batch context: you are one run in a batch of {n} tasks launched together "
    'as group "{group}". Other runs from this batch may be executing alongside '
    "you and editing other paths.]"
)

WORKTREE_PREAMBLE = (
    "[Working tree: yours is an isolated git worktree at {path}, created from "
    "commit {base}. It is not the tree the person who started you is looking at, "
    "and {uncommitted}]"
)


def toml_cfg(key: str, value: str):
    """`-c` values are parsed as TOML, so a string value is emitted quoted."""
    return ["-c", f'{key}="{value}"']


def toml_string(s: str) -> str:
    """A TOML basic string: a path can hold a quote, a backslash or a control character."""
    out = []
    for c in s:
        if c in '"\\':
            out.append("\\" + c)
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            out.append(f"\\u{ord(c):04X}")
        else:
            out.append(c)
    return '"' + "".join(out) + '"'


def read_only_profile(cwd) -> list:
    """Read everything, write only TMPDIR and ~/.cache, network off. The run's own directory is named read-only as well, because the more specific entry wins: inside TMPDIR it would otherwise be writable."""
    entries = ((":root", "read"), (":tmpdir", "write"), ("~/.cache", "write"), (str(cwd), "read"))
    table = "{" + ", ".join(f"{toml_string(k)}={toml_string(v)}" for k, v in entries) + "}"
    return ["-c", f"permissions.{READ_ONLY_PROFILE}.filesystem={table}",
            "-c", f"permissions.{READ_ONLY_PROFILE}.network.enabled=false",
            *toml_cfg("default_permissions", READ_ONLY_PROFILE)]


def read_only_blocker(cwd):
    """Why a read-only run in `cwd` cannot write scratch on this install, as the note its reply carries, or None."""
    s = codex_support()
    if not s["profile"]:
        which = (f"codex {s['version']} is older than {floor_text(PROFILE_FLOOR)}, the first release the read-only profile is known to work on"
                 if s["version"] else "`codex --version` could not be read, so the read-only profile is not known to work")
        return f"{which}, {STRICT}; upgrade Codex for read-only runs that can"
    real = os.path.realpath(cwd)
    for name, path in (("TMPDIR", tempfile.gettempdir()), ("~/.cache", Path.home() / ".cache")):
        if real == os.path.realpath(path):
            return f"{cwd} is itself {name}, which a read-only run may write, so it cannot also stay read-only, {STRICT}"
    return None


def build_argv(meta: dict, *, kind: str, prompt=None, thread_ref=None):
    """Compose the argv from a run's recorded settings, re-asserting every one on every turn: `codex exec resume` re-derives them from whatever config layer is in effect."""
    argv = ["codex", "exec"]
    if kind == "resume":
        argv.append("resume")
        if thread_ref:
            argv.append(thread_ref)
    argv.append("--json")
    if meta.get("isolated", True):
        argv.append("--ignore-user-config")
    if meta.get("skip_git_repo_check"):
        argv.append("--skip-git-repo-check")
    # `-c` is last-value-wins for a repeated key, so nothing added here may come after an entry this skill owns. A profile and `sandbox_mode` are never sent together: they do not combine, and which one wins depends on where each came from.
    if meta["sandbox"] == "read-only" and meta.get("read_only") == "scratch":
        argv += read_only_profile(meta["cwd"])
    else:
        argv += toml_cfg("sandbox_mode", meta["sandbox"])
    if meta.get("service_tier"):
        argv += toml_cfg("service_tier", meta["service_tier"])
    if meta.get("effort"):
        argv += toml_cfg("model_reasoning_effort", meta["effort"])
    if meta.get("model"):
        argv += ["-m", meta["model"]]
    if meta.get("schema_path"):
        argv += ["--output-schema", meta["schema_path"]]
    argv += ["-o", str(Path(meta["run_dir"]) / "last-message.txt")]
    if kind == "start":
        for d in meta.get("add_dirs") or []:
            argv += ["--add-dir", d]
    for img in meta.get("images") or []:
        argv += ["-i", img]
    if prompt is not None:
        # Required: `-i <FILE>...` takes several values and would swallow the prompt, and a prompt starting with `-` is rejected as a flag.
        argv += ["--", prompt]
    return argv


def uncommitted_clause(n) -> str:
    """The caller's uncommitted work is absent from a checkout either way; only the count can be unknown, and unknown is never stated as zero."""
    if n is None:
        return ("it does not contain the uncommitted file(s) that exist in "
                "theirs — git could not count them, so how many is unknown.")
    if n == 0:
        return "there is no uncommitted work in theirs for it to be missing."
    return f"it does not contain the {n} uncommitted file(s) that exist in theirs."


def apply_preamble(prompt: str, batch=None) -> str:
    """Prepend the run-context paragraphs. Not optional."""
    parts = [PREAMBLE]
    if batch:
        parts.append(BATCH_PREAMBLE.format(n=batch["n"], group=batch["group"]))
        if batch.get("worktree"):
            parts.append(WORKTREE_PREAMBLE.format(
                path=batch["worktree"], base=(batch.get("base") or "?")[:12],
                uncommitted=uncommitted_clause(batch.get("uncommitted"))))
    return "\n\n".join(parts + [prompt])
