""" Constants for the package. """

from typing import Callable
from logging import WARNING, INFO, DEBUG, NOTSET, ERROR
from py.util import formatting

REMOTE_BRANCHES_OPT: list[str] = ["M", "U", "A"]

LOGGING_NAME_TO_LEVEL = {
    'ERROR': ERROR,
    'WARNING': WARNING,
    'INFO': INFO,
    'DEBUG': DEBUG,
    'NOTSET': NOTSET,
}
LOGGING_LEVEL_TO_NANE = {
    ERROR: 'ERROR',
    WARNING: 'WARNING',
    INFO: 'INFO',
    DEBUG: 'DEBUG',
    NOTSET: 'NOTSET',
}
LOGGING_OPT: list[str] = list(LOGGING_NAME_TO_LEVEL.keys())
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
