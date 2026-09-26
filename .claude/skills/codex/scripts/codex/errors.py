"""The one way a command says no, from anywhere below the command surface: `cli.py` renders it as the reply."""

from __future__ import annotations


class Refusal(Exception):
    """A command refused, or failed, for a reason the caller can act on. `error` is the reply's `error`; `fields` join it in the reply.

    `arguments` says the command line itself must change — a flag combination, a value's rule, a file, commit or model it names that does not exist — as against a refusal by the registry's state or a failure, where the command line was right. `error` is positional-only because a field can itself be called `message`.
    """

    def __init__(self, error: str, /, *, arguments: bool = False, **fields):
        super().__init__(error)
        self.error = error
        self.arguments = arguments
        self.fields = fields
