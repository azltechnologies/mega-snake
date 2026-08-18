"""This module contains functions for formatting output messages to the console."""

from enum import Enum
import subprocess
import sys
import os
import traceback
import re
import logging
from types import TracebackType
from typing import Optional
import click
from colorama import init, Fore, Style, Back

# Initialize colopiprama
init(autoreset=True)


class Color(Enum):
    """Color enumeration for console output"""

    RED = Fore.RED
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    BLUE = Fore.BLUE


# Exit code carried by a WorkspaceError whose cause has no entry in ERROR_CODES: an internal error
# nobody classified. It is a real, deliverable status — not a placeholder for "exit 1".
INTERNAL_ERROR_CODE: int = 100


class InternalStateError(Exception):
    """Raised when an invariant guaranteed upstream was violated: reaching the raise is a bug.

    Use it **only** where the situation was already ruled out earlier in the same flow — a resource
    validated during initialization, a value the code itself produced, a branch a previous graceful
    check made unreachable. Anything the user or their environment can legitimately cause is not
    this: a missing tool, an unconfigured remote, a declined prompt or bad input each get the
    specific built-in that describes them, so ``ERROR_CODES`` can resolve a meaningful status.

    Deliberately **not** a ``click.ClickException``. Those exist to give a user error clean,
    traceback-free output; a bug wants the opposite. Resolving to ``INTERNAL_ERROR_CODE`` makes
    ``_on_crash`` print the traceback, which is the only diagnostic that helps here.

    It replaces the ``assert`` statements this codebase used for the same purpose: ``assert`` is
    stripped by ``python -O``, which silently removed the check and let the failure surface later as
    something unrelated.

    **Deliberately absent from ``ERROR_CODES``.** It inherits ``INTERNAL_ERROR_CODE`` from
    ``resolve_error_code``'s default, which is exactly right: 100 already means "a bug in mgsnake",
    and this type only makes that diagnosis explicit at the raise site. Registering it would put 100
    in the table's values, and a status a registered type shares with the unmapped fallback tells a
    caller nothing the fallback did not already tell it.
    """


# Exit code of ValidationError / UserDeclinedError. They subclass click.ClickException so they keep
# the clean, traceback-free output Click gives a user error; only the status number changes.
VALIDATION_ERROR_CODE: int = 113
USER_DECLINED_ERROR_CODE: int = 114

# Exit status per exception type, resolved by walking the MRO (see resolve_error_code), so an
# unlisted subclass inherits the code of its nearest listed ancestor instead of falling back to
# INTERNAL_ERROR_CODE.
#
# MANDATORY: every custom exception introduced in this package must be registered here in the same
# change. Types owned by modules this one cannot import register themselves at their definition site
# (see VersionSetException in config_environment/models/tools_version.py); the invariant test in
# src/tests/test_exit_codes.py fails naming any custom exception that is left unmapped.
#
# 105 is deliberately vacant. It used to be assigned to IOError, which *is* OSError, the very same
# object EnvironmentError aliases — so the two entries collided silently and 105 was unreachable.
ERROR_CODES: dict[type[BaseException], int] = {
    RuntimeError: 101,
    FileNotFoundError: 102,
    ValueError: 103,
    NotImplementedError: 104,
    NotADirectoryError: 106,
    LookupError: 107,
    IndexError: 108,
    KeyError: 109,
    PermissionError: 110,
    subprocess.SubprocessError: 111,
    EnvironmentError: 112,
}

old_hook = sys.excepthook

logger = logging.getLogger(__name__)


class ErrorFilter(logging.Filter):
    """Allows only ERROR and CRITICAL levels."""

    def filter(self, record) -> bool:
        """Return True only for ERROR and CRITICAL log records."""
        return record.levelno >= logging.ERROR


class DefaultFilter(logging.Filter):
    """Allows only DEBUG, INFO, WARNING levels."""

    def filter(self, record) -> bool:
        """Return True only for DEBUG, INFO, and WARNING log records."""
        return record.levelno < logging.ERROR


def config_log(path: str, level: int) -> None:
    """
    Configures the logger at the specified level.

    Returns:
        None
    """
    # Define formatters
    error_format = "%(asctime)25s –– [%(levelname)-8s] %(namefile)25s" + ":[%(func)-42s]:%(line)-6d  –– %(message)s"
    default_format = (
        "%(asctime)25s –– [%(levelname)-8s] %(filename)25s" + ":[%(funcName)-42s]:%(lineno)-6d  –– %(message)s"
    )
    default_formatter = logging.Formatter(default_format)
    error_formatter = logging.Formatter(error_format)

    # Reconfiguring replaces the handlers instead of stacking them: without this, calling config_log
    # again (a properties reload) would attach a second pair of handlers to the same file and every
    # record would be written twice from that point on.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    # Create a file handler with encoding
    default_file_handler = logging.FileHandler(path, encoding="utf-8", delay=True)
    default_file_handler.setLevel(logging.DEBUG)
    default_file_handler.setFormatter(default_formatter)
    default_file_handler.addFilter(DefaultFilter())
    error_file_handler = logging.FileHandler(path, encoding="utf-8", delay=True)
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(error_formatter)
    error_file_handler.addFilter(ErrorFilter())
    logger.addHandler(error_file_handler)
    logger.addHandler(default_file_handler)
    logger.setLevel(level)


def resolve_error_code(exception: BaseException, default: int = INTERNAL_ERROR_CODE) -> int:
    """Resolve the exit status for an exception by walking its method resolution order.

    An exact ``type(e) in ERROR_CODES`` lookup only recognises the types written in the table, which
    left every unlisted subclass falling through to the generic code: a ``CalledProcessError`` is a
    ``SubprocessError``, and a caller raising ``OSError`` gets nothing from an entry keyed on
    ``EnvironmentError``. Walking the MRO makes a subclass inherit the code of its nearest listed
    ancestor, while a type listed in its own right still wins over that ancestor (``FileNotFoundError``
    resolves to 102, not to the 112 of the ``OSError`` it derives from).

    Parameters:
        exception: The exception whose exit status is needed.
        default: Status returned when neither the type nor any of its ancestors is registered.

    Raises:
        None

    Returns:
        int: The registered exit status for the nearest mapped ancestor, or ``default``.
    """
    for ancestor in type(exception).__mro__:
        code: Optional[int] = ERROR_CODES.get(ancestor)
        if code is not None:
            return code
    return default


class ValidationError(click.ClickException):
    """Raised when a validation reports stale or invalid content.

    Subclasses ``click.ClickException`` so the user still gets the clean, traceback-free message
    Click prints for a user-facing error; only the exit status differs, which is what lets a caller
    (a CI job running ``generate-docs --check``, say) tell "the content is stale" apart from "the
    command was invoked wrong".
    """

    exit_code = VALIDATION_ERROR_CODE


class UserDeclinedError(click.ClickException):
    """Raised when the user declines an action the command cannot continue without.

    Declining a prompt is not a misuse of the CLI, so it does not deserve the invocation-error
    status: it gets its own code, which a script can branch on to stop retrying.
    """

    exit_code = USER_DECLINED_ERROR_CODE


def _on_crash(exctype: type[BaseException], value: BaseException, trace: Optional[TracebackType]) -> None:
    """Translate an unhandled WorkspaceError into its registered exit status.

    Installed as ``sys.excepthook`` by ``WorkspaceError.__init__``. ``sys.exit`` called from inside
    an except hook does set the process status, which is what carries the code out to the shell.

    An unmapped cause (``INTERNAL_ERROR_CODE``) is an error nobody classified, so the traceback is
    printed first: it is the only diagnostic the user has on the console for it. A mapped cause was
    anticipated and already reported through ``_ws_error``, so it exits without the noise.

    Parameters:
        exctype: The class of the unhandled exception.
        value: The unhandled exception instance.
        trace: The traceback of the unhandled exception, if any.

    Raises:
        SystemExit: Always, for a WorkspaceError, carrying its ``error_code``.

    Returns:
        None
    """
    if isinstance(value, WorkspaceError):
        err_code: int = getattr(value, "error_code", INTERNAL_ERROR_CODE)
        if err_code == INTERNAL_ERROR_CODE:
            old_hook(exctype, value, trace)
        sys.exit(err_code)
    old_hook(exctype, value, trace)


def get_traceback(e: BaseException) -> str:
    """
    Retrieves the traceback from an exception.

    Args:
        e (Exception): exception to retrieve the traceback

    Returns:
        str: Exception's traceback.
    """
    # Pattern and replacement
    pattern = r'\.py", line (\d+)'
    replacement = r'.py:\1"'
    tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))

    # Perform substitution
    result = re.sub(pattern, replacement, tb_str)
    return result


# Every ws_* helper writes to stderr, never to stdout.
#
# stdout belongs to whatever a command *produces* — the value a caller consumes. Progress, status
# and diagnostics are not that, and POSIX puts them on stderr precisely so a caller can separate
# the two: `mgsnake cmd 2>/dev/null` keeps the payload, and `$(mgsnake cmd)` captures the payload
# alone. Both are impossible while a status line shares the stream with the result.
#
# This used to hold for ws_advice only, which left errors leaking into every pipe and made stdout
# unusable as a data channel for any command that logged anything. Keeping it uniform is what lets
# a command emit a value on stdout without auditing every helper it might reach.
#
# The user sees no difference: an interactive terminal shows both streams.
def ws_success(message: str) -> None:
    """Print a success message to stderr"""
    print(Fore.BLUE + Back.CYAN + message, file=sys.stderr)
    logger.info(message, stacklevel=2)


def ws_info(message: str) -> None:
    """Print an informational message to stderr"""
    print(Fore.WHITE + Back.BLUE + message, file=sys.stderr)
    logger.info(message, stacklevel=2)


def ws_warning(message: str) -> None:
    """Print a warning message to stderr"""
    print(Fore.YELLOW + Back.BLACK + message, file=sys.stderr)
    if logger.hasHandlers():
        logger.warning(message, stacklevel=2)


# specify that this function raises an exception
def _ws_error(error: BaseException, message: Optional[str] = None) -> None:
    """Print an error message to stderr"""
    if not message:
        message = str(error) if str(error) else "unknown error"
    print(Back.BLACK + Fore.RED + message, file=sys.stderr)
    # Capture the traceback
    tb = traceback.extract_tb(error.__traceback__)
    func_name: str = "unknown function"
    line_no: int = 0
    filename: str = "unknown file"
    tb_str: str = ""
    if tb:
        # Get the last frame where the exception occurred
        last_frame = tb[-1]
        # Extract the function name and other details
        func_name = last_frame.name
        line_no = last_frame.lineno if last_frame.lineno else 0
        filename = os.path.basename(last_frame.filename)
        tb_str = get_traceback(error)
    logger.error(
        f"{message}; %s: %s\n\n%s",
        error.__class__.__name__,
        str(error),
        tb_str,
        extra={
            "func": func_name,
            "line": line_no,
            "namefile": filename,
        },
    )


def ws_advice(message: str, force: bool = False) -> None:
    """Print an advice message to stderr if LOG_LEVEL is set to DEBUG.

    Like every other ws_* helper, this writes to stderr (see the note above them). It was the first
    one to do so, because `local-config-path` is read with `$(...)` in `config_setup.sh` and its
    value was polluted by these lines whenever the CLI ran at DEBUG level.

    Parameters:
        message: The advice message to print and log.
        force: When True, print regardless of the current log level.

    Raises:
        None

    Returns:
        None
    """
    # check if LOG_LEVEL is set to DEBUG
    log_level = logger.level
    if log_level == logging.DEBUG or force:
        print(Fore.GREEN + Back.BLACK + message, file=sys.stderr)
        logger.debug(message, stacklevel=2)


def ws_tip(messages: dict[Color, str]) -> None:
    """Print a tip message to stderr"""
    msg: str = ""
    for color, message in messages.items():
        msg += f"{color.value}{message}"
    nc = Style.RESET_ALL  # No Color
    tip: str = f"{Back.BLACK}{msg}{nc}"
    print(tip, file=sys.stderr)
    logger.info(msg, stacklevel=2)


def ws_error(message: str, exception: Optional[BaseException] = None) -> None:
    """Log and print an exception while removing the stack trace"""
    if not exception:
        exception = BaseException(message)
    exception.__traceback__ = None
    _ws_error(exception, message)


class WorkspaceError(Exception):
    """Custom exception for workspace operations"""

    def __init__(self, message: str, parent_exception: BaseException, error_code: int = INTERNAL_ERROR_CODE) -> None:
        """Initialize a WorkspaceError with a message, the causing exception, and an optional error code."""
        sys.excepthook = _on_crash
        self.message = message
        self.parent_exception = parent_exception
        # A registered type wins over the caller's suggestion, so the same cause always leaves the
        # process with the same status no matter which call site wrapped it.
        self.error_code = resolve_error_code(parent_exception, error_code)
        # Get filename from FileHandler if it exists
        filename = None
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler):
                filename = handler.baseFilename
                break
        if not filename:
            ws_error(str(parent_exception), parent_exception)
            super().__init__(self.message)
            return
        self.__traceback__ = parent_exception.__traceback__
        super().__init__(self.message)
        _ws_error(parent_exception, str(self))

    def __str__(self) -> str:
        """Return a structured string representation including the message, error code, and cause."""
        return (
            f"[ WorkspaceError: {self.message} ] —— [ code: {self.error_code} ] —— "
            f"[ type: {self.parent_exception.__class__.__name__} ] —— [ Message: {str(self.parent_exception)} ]"
        )
