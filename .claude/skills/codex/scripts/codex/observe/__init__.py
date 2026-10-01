"""Watching and collecting runs: `status`, `log`, `show` and `result`, for one run and for a group."""

from codex.observe.collect import GROUP_MESSAGE_CAP
from codex.observe.log import log
from codex.observe.result import result
from codex.observe.rows import STALL_SECONDS
from codex.observe.show import SHOW_MAX_BYTES, show
from codex.observe.status import LISTING_ROWS, status

__all__ = [
    # the commands
    "status", "log", "show", "result",
    # the limits their --help states
    "STALL_SECONDS", "LISTING_ROWS", "GROUP_MESSAGE_CAP", "SHOW_MAX_BYTES",
]
