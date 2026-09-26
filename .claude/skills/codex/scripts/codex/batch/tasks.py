"""What a batch is asked to do: the ordered tasks, each validated before anything is claimed, and the options each member runs with."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex.codex_cli.catalog import check_model_effort, model_catalog
from codex.codex_cli.config import user_defaults
from codex.errors import Refusal
from codex.registry.runs import find_run
from codex.runs import settings
from codex.util import clip


TASK_FIELDS = ("prompt", "kind", "label", "model", "effort", "sandbox", "schema", "image", "cwd", "resume")


# Types are checked too: a wrong-typed value would otherwise surface as a Python error inside `create_run`, after earlier members spawned.
TASK_FIELD_TYPES = {"prompt": str, "kind": str, "label": str, "model": str, "effort": str, "sandbox": str,
                    "schema": str, "cwd": str, "resume": str, "image": list}


def load_tasks(args):
    """The ordered task list: `--task` prompts first (as typed), then `--tasks-file` entries, each validated so a broken file costs nothing."""
    tasks = [{"prompt": p, "kind": "start"} for p in (args.task or [])]
    if args.tasks_file:
        try:
            raw = Path(args.tasks_file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise Refusal(f"cannot read tasks file: {e}", arguments=True)
        for n, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if line and not line.startswith("#"):
                tasks.append(_task_from_line(n, line, args))
    if not tasks:
        raise Refusal("batch start needs at least one --task or a --tasks-file", arguments=True)
    return tasks


def _task_from_line(n, line, args):
    try:
        item = json.loads(line)
    except json.JSONDecodeError as e:
        raise Refusal(f"tasks file line {n} is not valid JSON: {e}", line=clip(line, 200), arguments=True)
    if not isinstance(item, dict):
        raise Refusal(f"tasks file line {n} is not a JSON object", line=clip(line, 200), arguments=True)
    unknown = set(item) - set(TASK_FIELDS)
    if unknown:
        # A silently ignored field is a member that quietly used the group default.
        raise Refusal(f"tasks file line {n} has unknown field(s): {sorted(unknown)}", known_fields=list(TASK_FIELDS), arguments=True)
    for field, want in TASK_FIELD_TYPES.items():
        if field in item and not isinstance(item[field], want):
            raise Refusal(f"tasks file line {n}: {field!r} must be {want.__name__}, got {type(item[field]).__name__}",
                          line=clip(line, 200), arguments=True)
    if any(not isinstance(i, str) for i in item.get("image") or []):
        raise Refusal(f"tasks file line {n}: 'image' must be a list of paths", line=clip(line, 200), arguments=True)
    item.setdefault("kind", "start")
    if item["kind"] not in ("start", "resume"):
        raise Refusal(f"tasks file line {n}: kind must be start or resume"
                      + ("; for a review use kind 'start' with sandbox 'read-only'" if item["kind"] == "review" else ""),
                      got=item["kind"], arguments=True)
    # Under --resume-from the target comes from the pairing, so an unnamed resume is normal there.
    if item["kind"] == "resume" and not item.get("resume") and not getattr(args, "resume_from", None):
        raise Refusal(f"tasks file line {n}: kind 'resume' needs a 'resume' field naming a run id or thread id", arguments=True)
    return item


def task_args(base_args, item):
    """A member's options: the group's as defaults, the task's own fields over them."""
    ns = argparse.Namespace(**vars(base_args))
    ns.prompt = item.get("prompt")
    ns.prompt_file = None
    for field in ("label", "model", "effort", "sandbox", "cwd"):
        if item.get(field) is not None:
            setattr(ns, field, item[field])
    if item.get("schema") is not None:
        ns.schema = item["schema"]
    ns.image = item.get("image") or []
    ns.add_dir = getattr(base_args, "add_dir", None) or []
    return ns


def check_task_settings(tasks, args, runs_dir):
    """Refuse a model or effort any task would adopt, before the group name is claimed and with one catalog lookup, rather than at the eighth member with seven already running."""
    user = user_defaults()
    adopted = []
    for n, item in enumerate(tasks, 1):
        ns = task_args(args, item)
        base = find_run(runs_dir, item["resume"])[1] if item["kind"] == "resume" else None
        adopted.append((n, settings.resolve(
            sandbox=ns.sandbox, model=ns.model, effort=ns.effort, priority=getattr(ns, "priority", None),
            inherit_config=getattr(ns, "inherit_config", False), base=base, user=user)["adopted"]))
    if not any(a["model"] or a["effort"] for _n, a in adopted):
        return
    catalog = model_catalog()
    for n, a in adopted:
        if a["model"] or a["effort"]:
            try:
                check_model_effort(a["model"], a["effort"], catalog=catalog,
                                   model_source=a["model_source"], effort_source=a["effort_source"])
            except Refusal as e:
                raise Refusal(f"task {n}: {e.error}", arguments=e.arguments, **e.fields) from None
