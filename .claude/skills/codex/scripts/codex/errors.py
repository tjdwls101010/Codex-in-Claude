"""The one way a command says no, from anywhere below the command surface: `cli.py` renders it as the reply."""

from __future__ import annotations


class Refusal(Exception):
    """A command refused, or failed, for a reason the caller can act on. `error` is the reply's `error`; `fields` join it in the reply.

    `error` is positional-only because a field can itself be called `message`.
    """

    def __init__(self, error: str, /, **fields):
        super().__init__(error)
        self.error = error
        self.fields = fields
