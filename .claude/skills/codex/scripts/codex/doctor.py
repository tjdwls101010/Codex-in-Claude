"""`doctor` and `models`: the environment a run would start in, and the models this Codex install offers."""

from __future__ import annotations

import os
import shutil
import sys

from codex.codex_cli import (
    WRITING_SANDBOXES, codex_home, codex_version, config_summary, login_status, model_catalog, read_only_blocker,
    refuse_without_isolation, user_defaults,
)
from codex.git import git_toplevel, resolve_project, worktrees_registered
from codex.errors import Refusal
from codex.registry import iter_runs, list_groups, live_runs, resolve_runs_dir, unreadable_runs
from codex.util import ENTRY, clip, is_within


def models(args):
    """The catalog is asked of Codex rather than written down: which efforts a model takes differs per model and per Codex version."""
    catalog = model_catalog()
    if catalog is None:
        raise Refusal("could not read the catalog from `codex debug models`; `doctor` reports why. Runs still start, and an invalid --model or --effort then fails the run",
                      models=None, codex_path=shutil.which("codex"))
    return {"models": catalog, "codex_version": codex_version()}


def doctor(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    report, blockers, warnings = {}, [], []
    report["python"] = sys.version.split()[0]
    if sys.version_info < (3, 11):
        blockers.append(f"python {report['python']} is below the required 3.11")
    _check_codex(report, blockers, warnings)
    _check_config(report, warnings)
    report["skill_dir"] = str(ENTRY.parent.parent)
    report["entry"] = str(ENTRY)
    report["plugin_root_env"] = os.environ.get("CLAUDE_PLUGIN_ROOT")
    report["project"] = str(project)
    report["project_is_git_repo"] = git_toplevel(project) is not None
    if report["codex_path"]:
        _check_runs_it_can_start(report, blockers, warnings, project)
    agents = project / "AGENTS.md"
    report["project_agents_md"] = str(agents) if agents.exists() else None
    if agents.exists():
        warnings.append(
            f"{agents} is given to every Codex run started in this project, isolated or not")
    _check_registry(report, blockers, warnings, project, runs_dir)
    # The verdict first, then what it rests on.
    return {"ok": not blockers, "blockers": blockers, "warnings": warnings, **report}


def _check_codex(report, blockers, warnings):
    exe = shutil.which("codex")
    report["codex_path"] = exe
    report["codex_version"] = None
    if not exe:
        blockers.append("`codex` is not on PATH")
    else:
        try:
            report["codex_version"] = codex_version(strict=True)
        except Exception as e:
            warnings.append(f"could not read `codex --version`: {e}")
    home = codex_home()
    report["codex_home"] = str(home)
    report["codex_home_from_env"] = bool(os.environ.get("CODEX_HOME"))
    report["codex_home_exists"] = home.is_dir()
    if not home.is_dir():
        blockers.append(f"CODEX_HOME does not exist: {home}")
    if not exe:
        return
    login = login_status()
    if login["cause"] == "unavailable":
        report["login_ok"] = None
        warnings.append(f"could not run `codex login status`: {login['detail']}")
        return
    report["login_status"] = login["detail"]
    report["login_ok"] = login["ok"]
    if login["cause"] == "environment":
        blockers.append(f"`codex login status` could not run at all — an "
                        f"environment or config problem, not an auth one, so "
                        f"`codex login` will fail the same way: {clip(login['detail'], 200)}")
    elif login["cause"] == "unauthenticated":
        blockers.append("`codex login status` exited non-zero — not authenticated")


def _check_runs_it_can_start(report, blockers, warnings, project):
    """Whether this Codex can start an isolated run at all, and which read-only a read-only run in the project would get."""
    try:
        refuse_without_isolation()
    except Refusal as e:
        blockers.append(e.error)
    note = read_only_blocker(project)
    report["read_only"] = "strict" if note else "scratch"
    if note:
        warnings.append(f"read-only runs here: {note}")


def _check_config(report, warnings):
    cfg = config_summary()
    report["config_toml"] = cfg["path"]
    report["config_sandbox_mode"] = cfg["sandbox_mode"]
    report["config_approval_policy"] = cfg["approval_policy"]
    # What a run naming no model, effort or tier would be handed.
    report["effective_defaults"] = user_defaults()
    if report["config_sandbox_mode"] == "danger-full-access":
        warnings.append(
            'config.toml sets sandbox_mode = "danger-full-access", which a bare `codex exec resume` falls back to; runs started here always pass their own sandbox')
    catalog = model_catalog()
    report["models_catalog"] = len(catalog) if catalog else None
    if catalog is None:
        warnings.append(
            "could not read `codex debug models`, so --model and --effort are not checked before spawning; an invalid value fails the run instead")


def _check_registry(report, blockers, warnings, project, runs_dir):
    report["runs_dir"] = str(runs_dir)
    report["runs_dir_exists"] = runs_dir.is_dir()
    # Probed without creating it: a diagnostic must not change what it diagnoses.
    target = runs_dir if runs_dir.is_dir() else runs_dir.parent
    probe = target / f".codex-write-probe-{os.getpid()}"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        report["runs_dir_writable"] = True
    except Exception as e:
        report["runs_dir_writable"] = False
        blockers.append(f"runs dir is not writable ({target}): {e}")
    if not runs_dir.is_dir():
        return
    report["runs_dir_bytes"] = sum(p.stat().st_size for p in runs_dir.rglob("*") if p.is_file())
    report["runs_dir_runs"] = sum(1 for _ in iter_runs(runs_dir))
    report["groups"] = list_groups(runs_dir)
    bad = unreadable_runs(runs_dir)
    report["runs_unreadable"] = len(bad)
    if bad:
        warnings.append(
            f"{len(bad)} run director(ies) have a meta.json that will not parse and are missing from every listing, though counted in runs_dir_bytes: {', '.join(bad)}")
    warnings.extend(_overlapping_writers(runs_dir))
    # Only checkouts this skill cut: `git worktree list` also lists the user's own.
    live_wt = [p for p in worktrees_registered(project) if p.exists() and is_within(str(p), str(runs_dir))]
    report["worktrees"] = len(live_wt)
    if live_wt:
        warnings.append(
            f"{len(live_wt)} batch worktree(s) are still checked out under {runs_dir}, holding their runs' uncommitted results; `clean --group <name>` removes a group's once collected")


def _overlapping_writers(runs_dir):
    """Live runs whose recorded cwds overlap (either inside the other), where at least one can write — the same test `concurrent_writers` makes at creation."""
    live = [m for _rd, m in live_runs(runs_dir)]
    seen, out = set(), []
    for i, m in enumerate(live):
        group = [m] + [o for j, o in enumerate(live) if j != i
                       and (is_within(o.get("cwd"), m.get("cwd")) or is_within(m.get("cwd"), o.get("cwd")))]
        key = tuple(sorted(x.get("run_id") or "" for x in group))
        writers = [x for x in group if x.get("sandbox") in WRITING_SANDBOXES]
        if len(group) < 2 or key in seen or not writers:
            continue
        seen.add(key)
        out.append(f"{len(group)} live runs overlap in {m.get('cwd')} and {len(writers)} of them can write there, "
                   f"unable to tell each other's changes apart: {', '.join(x.get('run_id') for x in group)}")
    return out
