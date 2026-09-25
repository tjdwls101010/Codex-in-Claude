"""The `codex exec` argv for a run, and the paragraphs put in front of its prompt.

Two invariants, both forced by `exec` having `-s` and `-C` while `exec resume` has neither: the sandbox always travels as `-c sandbox_mode="<mode>"`, and the working directory is always set on the child process. Applied uniformly, a resumed turn cannot drift.
"""

from __future__ import annotations

from pathlib import Path

SANDBOX_MODES = ("read-only", "workspace-write", "danger-full-access")

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
    # `-c` is last-value-wins for a repeated key, so nothing added here may come after an entry this skill owns.
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
