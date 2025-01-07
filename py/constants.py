""" Constants for the package. """

from typing import Callable
from logging import WARNING, INFO, DEBUG, NOTSET, ERROR
from py.util import formatting

# Constants

APP_NAME: str = "snake"
MODULE_NAME: str = "py"
INTERPRETER_PATH: str = ".venv/bin/python3.13"

REMOTE_BRANCHES_OPT: list[str] = ["M", "U", "A"]

LOGGING_NAME_TO_LEVEL = {
    "ERROR": ERROR,
    "WARNING": WARNING,
    "INFO": INFO,
    "DEBUG": DEBUG,
    "NOTSET": NOTSET,
}
LOGGING_LEVEL_TO_NANE = {
    ERROR: "ERROR",
    WARNING: "WARNING",
    INFO: "INFO",
    DEBUG: "DEBUG",
    NOTSET: "NOTSET",
}
LOGGING_OPT: list[str] = list(LOGGING_NAME_TO_LEVEL.keys())
SHELL_OPT: list[str] = ["bash", "zsh", "powershell"]

MSG_OPT: dict[str, Callable] = {
    "S": formatting.ws_success,
    "I": formatting.ws_info,
    "W": formatting.ws_warning,
    "E": formatting.ws_error,
    "A": formatting.ws_advice,
    "T": formatting.ws_tip,
}

RELEASE_TYPE_OPT: dict[str, str] = {"p": "--prerelease", "r": "--latest=false", "l": "--latest"}

GCLOUD_LOGGIN_OPT: dict[str, str] = {"U": "user", "A": "application", "B": "both"}

WORKSPACE_EXTENSIONS: list[str] = [
    "augustocdias.tasks-shell-input",
    "berublan.vscode-log-viewer",
    "bradzacher.vscode-copy-filename",
    "github.vscode-github-actions",
    "github.vscode-pull-request-github",
    "graphql.vscode-graphql-syntax",
    "graphql.vscode-graphql",
    "letmaik.git-tree-compare",
    "mhutchie.git-graph",
    "natqe.reload",
    "sandcastle.vscode-open",
    "solomonkinard.git-blame",
    "vscjava.vscode-gradle",
    "vscjava.vscode-java-pack",
]
