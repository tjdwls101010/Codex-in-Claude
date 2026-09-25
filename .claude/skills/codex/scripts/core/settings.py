"""What a run will be: one precedence for every setting, used by `start`, `resume`, every batch member, batch pre-validation and the shared-tree warning."""

from __future__ import annotations


def resolve(*, sandbox=None, model=None, effort=None, priority=None, inherit_config=False, cwd=None,
            base=None, user=None):
    """Resolve a run's settings from the caller's flags, the run it continues (`base`, or None) and the user's config.toml defaults (`user`).

    Each setting: the flag, else what the continued thread recorded, else the config, else nothing (the server decides). The thread's record wins over the config only while isolation is unchanged — an empty record is a record, which is why this is not an `or` chain. The config is consulted only for an isolated run: under `--inherit-config` Codex reads it itself. The sandbox is never taken from the config.

    `adopted` holds the model and effort being taken up now rather than inherited, with where each came from; only those are checked against the catalog, so a model retired upstream cannot block the resume of an old thread.
    """
    isolated = base.get("isolated", True) if base else True
    if inherit_config:
        isolated = False
    inherits = bool(base) and isolated == base.get("isolated", True)
    user = {} if inherits or not isolated else (user or {})

    if priority is True:
        tier = "priority"
    elif priority is False:
        tier = None
    elif inherits:
        # A thread recorded before `service_tier` existed holds a boolean `priority`; a new record's None is a choice.
        tier = base["service_tier"] if "service_tier" in base else ("priority" if base.get("priority") else None)
    else:
        tier = user.get("service_tier")

    return {
        "isolated": isolated,
        "sandbox": sandbox or (base.get("sandbox") if base else None) or "workspace-write",
        "model": model or (base.get("model") if inherits else user.get("model")),
        "effort": effort or (base.get("effort") if inherits else user.get("effort")),
        "service_tier": tier,
        "cwd": cwd or (base.get("cwd") if base else None),
        "adopted": {"model": model or user.get("model"), "effort": effort or user.get("effort"),
                    "model_source": None if model else "config.toml",
                    "effort_source": None if effort else "config.toml"},
    }
