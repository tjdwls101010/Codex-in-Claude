"""`doctor` and `models`."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from codex.catalog import codex_version, model_catalog
from codex.config import codex_home, config_scalars, user_defaults
from core.groups import list_groups
from core.registry import is_live, iter_runs, reap, resolve_project, resolve_runs_dir, unreadable_runs
from core.runs import WRITING_SANDBOXES
from core.supervisor import ENTRY
from util import clip, emit, git_toplevel, is_within
from worktree import registered as worktrees_registered


def cmd_models(args):
    """The catalog is asked of Codex rather than written down: which efforts a model takes differs per model and per Codex version."""
    catalog = model_catalog()
    if catalog is None:
        emit({"models": None,
              "error": "could not read the catalog from `codex debug models`; "
                       "`doctor` reports why. Runs are unaffected — an invalid "
                       "--model or --effort is caught by the API instead.",
              "codex_path": shutil.which("codex")}, code=1)
    emit({"models": catalog, "codex_version": codex_version()})


def cmd_doctor(args):
    project = resolve_project(args.project)
    runs_dir = resolve_runs_dir(project, args.runs_dir)
    report, blockers, warnings = {}, [], []
    report["python"] = sys.version.split()[0]
    if sys.version_info < (3, 10):
        blockers.append(f"python {report['python']} is below the required 3.10")
    _check_codex(report, blockers, warnings)
    _check_config(report, warnings)
    report["skill_dir"] = str(ENTRY.parent.parent)
    report["bridge_path"] = str(ENTRY)
    report["plugin_root_env"] = os.environ.get("CLAUDE_PLUGIN_ROOT")
    report["project"] = str(project)
    report["project_is_git_repo"] = git_toplevel(project) is not None
    agents = project / "AGENTS.md"
    report["project_agents_md"] = str(agents) if agents.exists() else None
    if agents.exists():
        warnings.append(
            f"{agents} is injected into every Codex run started in this project. "
            "Project AGENTS.md survives --ignore-user-config (measured), so it is a "
            "briefing channel that works — and equally, its contents are in context "
            "whether or not that was intended.")
    _check_registry(report, blockers, warnings, project, runs_dir)
    report["blockers"] = blockers
    report["warnings"] = warnings
    report["ok"] = not blockers
    emit(report, code=0 if not blockers else 2)


def _check_codex(report, blockers, warnings):
    exe = shutil.which("codex")
    report["codex_path"] = exe
    report["codex_version"] = None
    if not exe:
        blockers.append("`codex` is not on PATH")
    else:
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
            report["codex_version"] = (r.stdout or r.stderr).strip() or None
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
    try:
        r = subprocess.run([exe, "login", "status"], capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
    except Exception as e:
        report["login_ok"] = None
        warnings.append(f"could not run `codex login status`: {e}")
        return
    report["login_status"] = (r.stdout or r.stderr).strip()[:400]
    report["login_ok"] = r.returncode == 0
    if r.returncode == 0:
        return
    # `codex login status` also fails when it cannot load config at all; calling that "not authenticated" would send the caller to `codex login`, which fails the same way.
    text = report["login_status"] or ""
    if re.search(r"(?i)error loading config|config\.toml|permission denied|invalid|parse", text):
        blockers.append(f"`codex login status` could not run at all — an "
                        f"environment or config problem, not an auth one, so "
                        f"`codex login` will fail the same way: {clip(text, 200)}")
    else:
        blockers.append("`codex login status` exited non-zero — not authenticated")


def _check_config(report, warnings):
    cfg = codex_home() / "config.toml"
    report["config_toml"] = str(cfg) if cfg.exists() else None
    scalars = config_scalars(("sandbox_mode", "approval_policy"), cfg)
    report["config_sandbox_mode"] = scalars.get("sandbox_mode")
    report["config_approval_policy"] = scalars.get("approval_policy")
    # What a run naming no model, effort or tier would be handed.
    report["effective_defaults"] = user_defaults()
    if report["config_sandbox_mode"] == "danger-full-access":
        warnings.append(
            'config.toml sets sandbox_mode = "danger-full-access". `codex exec resume` '
            "has no -s flag and falls back to this value, which is how a read-only "
            "thread becomes fully privileged on its second turn. "
            "This wrapper passes -c sandbox_mode= on every invocation, so that fallback "
            "is never reached — but a bare `codex` command you run yourself will hit it.")
    catalog = model_catalog()
    report["models_catalog"] = len(catalog) if catalog else None
    if catalog is None:
        warnings.append(
            "could not read `codex debug models`, so `start`/`resume`/`batch` "
            "cannot check --model or --effort before spawning. Runs still work; "
            "an invalid value is caught by the API instead, one wasted run later.")


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
            f"{len(bad)} run director(ies) have an unreadable meta.json and are "
            f"absent from every run listing: {', '.join(bad)}. Their bytes are "
            f"still counted in runs_dir_bytes. Nothing here writes a partial "
            f"meta.json — a truncated one means the disk filled or something "
            f"outside this skill edited it.")
    warnings.extend(_overlapping_writers(runs_dir))
    # Only checkouts this skill cut: `git worktree list` also lists the user's own.
    live_wt = [p for p in worktrees_registered(project) if p.exists() and is_within(str(p), str(runs_dir))]
    report["worktrees"] = len(live_wt)
    if live_wt:
        warnings.append(
            f"{len(live_wt)} git worktree(s) from batch runs are still "
            f"checked out under {runs_dir}. Each is a full working copy and "
            f"holds its run's uncommitted results; `batch clean --group "
            f"<name>` removes a group's once you have collected them.")


def _overlapping_writers(runs_dir):
    """Live runs whose recorded cwds overlap (either inside the other), where at least one can write — the same test `concurrent_writers` makes at creation."""
    live = [m for m in (reap(rd, m) for rd, m in iter_runs(runs_dir)) if is_live(m)]
    seen, out = set(), []
    for i, m in enumerate(live):
        group = [m] + [o for j, o in enumerate(live) if j != i
                       and (is_within(o.get("cwd"), m.get("cwd")) or is_within(m.get("cwd"), o.get("cwd")))]
        key = tuple(sorted(x.get("run_id") or "" for x in group))
        writers = [x for x in group if x.get("sandbox") in WRITING_SANDBOXES]
        if len(group) < 2 or key in seen or not writers:
            continue
        seen.add(key)
        out.append(f"{len(group)} live runs overlap in {m.get('cwd')}, "
                   f"{len(writers)} of which can write there: "
                   f"{', '.join(x.get('run_id') for x in group)}. None of them can "
                   f"tell another agent's change from its own. Runs in their own "
                   f"worktrees are exempt and will not appear here.")
    return out
