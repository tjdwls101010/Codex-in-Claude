"""What a run will be: one precedence for every setting, used by `start`, `resume`, every batch member, batch pre-validation and the shared-tree warning."""

from __future__ import annotations

# Notes for a read-only run that gets the stricter sandbox for a reason of its own; a reason the install or directory gives comes in as `read_only_blocker`.
KEPT_STRICT = ("this thread recorded the stricter read-only, which cannot write even a temporary file, and keeps it: tests and builds that need one fail. "
               "`resume --sandbox read-only` moves it to the read-only that writes TMPDIR and ~/.cache")
LOADS_CONFIG = ("this run loads your config.toml, which could change the read-only profile, so it gets the stricter read-only, "
                "which cannot write even a temporary file: tests and builds that need one fail")


def settings_for(*, sandbox=None, model=None, effort=None, priority=None, inherit_config=False, cwd=None,
            base=None, user=None, read_only_blocker=None):
    """Resolve a run's settings from the caller's flags, the run it continues (`base`, or None) and the user's config.toml defaults (`user`).

    Each setting: the flag, else what the continued thread recorded, else the config, else nothing (the server decides). The thread's record wins over the config only while isolation is unchanged — an empty record is a record, which is why this is not an `or` chain. The config is consulted only for an isolated run: under `--inherit-config` Codex reads it itself. The sandbox is never taken from the config.

    `adopted` holds the model and effort being taken up now rather than inherited, with where each came from; only those are checked against the catalog, so a model retired upstream cannot block the resume of an old thread.

    `read_only` is which read-only a read-only run gets (None for a writing one): `scratch` writes TMPDIR and ~/.cache, `strict` is the legacy sandbox, with `read_only_note` saying why. A run takes scratch up only when it is new or names `--sandbox read-only`, and only isolated, since a loaded config.toml could add to the profile; a thread that recorded scratch keeps it; any other read-only thread, recorded before scratch existed or strict, keeps the strict sandbox, so no thread's permissions widen unasked. `read_only_blocker` is why this install or directory cannot use scratch at all.
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

    resolved = sandbox or (base.get("sandbox") if base else None) or "workspace-write"
    read_only, note = None, None
    if resolved == "read-only":
        if not isolated:
            read_only, note = "strict", LOADS_CONFIG
        elif not (sandbox == "read-only" or not base or base.get("read_only") == "scratch"):
            read_only, note = "strict", KEPT_STRICT
        elif read_only_blocker:
            read_only, note = "strict", read_only_blocker
        else:
            read_only = "scratch"

    return {
        "isolated": isolated,
        "sandbox": resolved,
        "model": model or (base.get("model") if inherits else user.get("model")),
        "effort": effort or (base.get("effort") if inherits else user.get("effort")),
        "service_tier": tier,
        "cwd": cwd or (base.get("cwd") if base else None),
        "read_only": read_only, "read_only_note": note,
        "adopted": {"model": model or user.get("model"), "effort": effort or user.get("effort"),
                    "model_source": None if model else "config.toml",
                    "effort_source": None if effort else "config.toml"},
    }
