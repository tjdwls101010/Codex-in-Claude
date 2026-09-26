"""This install's model catalog, read from `codex debug models`, and the pre-spawn check of a model or effort against it."""

from __future__ import annotations

import json
import shutil
import subprocess

from codex.errors import Refusal

# A `codex` slower than this to answer a local cache read is not answering; the check is skipped rather than holding up every run start.
CATALOG_TIMEOUT = 5.0

# One lookup per process: a `batch start` of N members would otherwise pay N+1 identical subprocess calls.
_CATALOG_CACHE = []


def codex_version():
    exe = shutil.which("codex")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20,
                           stdin=subprocess.DEVNULL)
    except Exception:
        return None
    return (r.stdout or r.stderr).strip() or None


def model_catalog():
    """What this Codex install offers, trimmed to the fields a caller chooses from, or None if it cannot be read.

    Every failure answers None — no binary, non-zero exit, output that is not JSON, JSON of the wrong shape — and callers treat None as "cannot check", never "invalid": a check that blocks a run because its own lookup broke is worse than no check.
    """
    if _CATALOG_CACHE:
        return _CATALOG_CACHE[0]
    _CATALOG_CACHE.append(None)
    exe = shutil.which("codex")
    if not exe:
        return None
    # One try around the shaping loop too: valid JSON with a wrong-typed field must also answer None rather than escape as an internal error.
    try:
        r = subprocess.run([exe, "debug", "models"], capture_output=True, text=True,
                           timeout=CATALOG_TIMEOUT, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            return None
        models = json.loads(r.stdout)["models"]
        if not isinstance(models, list):
            return None
        out = []
        for m in models:
            if not isinstance(m, dict) or not m.get("slug"):
                continue
            levels = m.get("supported_reasoning_levels")
            # These fields only: the raw payload is mostly each model's `base_instructions`.
            out.append({
                "slug": m["slug"],
                "display_name": m.get("display_name"),
                "default_effort": m.get("default_reasoning_level"),
                "efforts": [lv["effort"] for lv in (levels if isinstance(levels, list) else [])
                            if isinstance(lv, dict) and lv.get("effort")],
                "context_window": m.get("context_window"),
                "visibility": m.get("visibility"),
                "supported_in_api": m.get("supported_in_api"),
            })
    except Exception:
        return None
    _CATALOG_CACHE[0] = out or None
    return _CATALOG_CACHE[0]


def check_model_effort(model, effort, *, catalog, model_source=None, effort_source=None):
    """Refuse a model or effort this install does not offer.

    Callers pass only values being adopted now, never one inherited from the thread being resumed: a model retired upstream must not turn every resume of an old thread into a refusal. `*_source` names where a value came from when it was not typed, per value, so the caller is sent to the right file.
    """
    if not catalog or (not model and not effort):
        return
    ms = f" (from {model_source})" if model_source else ""
    es = f" (from {effort_source})" if effort_source else ""
    by_slug = {m["slug"]: m for m in catalog}
    if model and model not in by_slug:
        raise Refusal(f"unknown model {model!r}{ms}: not in this install's catalog, which refreshes on every Codex run",
                      known_models=sorted(by_slug),
                      hint="`models` prints the catalog with each model's efforts")
    if not effort:
        return
    if model:
        allowed = by_slug[model]["efforts"]
        if allowed and effort not in allowed:
            raise Refusal(f"model {model!r} does not accept effort {effort!r}{es}", model=model, valid_efforts=allowed,
                          default_effort=by_slug[model].get("default_effort"))
        return
    # No model named, so no single list governs; the union still catches a typo.
    union = sorted({e for m in catalog for e in m["efforts"]})
    if union and effort not in union:
        raise Refusal(f"unknown effort {effort!r}{es}: no model in this install accepts it",
                      valid_efforts=union,
                      hint="efforts are per-model; `models` shows which model takes which")
