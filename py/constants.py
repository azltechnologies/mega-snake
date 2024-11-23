""" Constants for the package. """

from typing import Callable
from logging import _nameToLevel
from py.util import formatting

REMOTE_BRANCHES_OPT: list[str] = ["M", "U", "A"]
LOGGING_OPT: list[str] = list(_nameToLevel.keys())
SHELL_OPT: list[str] = ["bash", "zsh", "powershell"]

# global constants
MSG_OPT: dict[str, Callable] = {
    "S": formatting.ws_success,
    "I": formatting.ws_info,
    "W": formatting.ws_warning,
    "E": formatting.WorkspaceError.ws_error,
    "A": formatting.ws_advice,
    "T": formatting.ws_tip,
}
