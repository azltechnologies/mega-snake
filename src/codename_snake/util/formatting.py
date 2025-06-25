""" This module contains functions for formatting output messages to the console. """

from enum import Enum
import subprocess
import sys
import os
import traceback
import re
import logging
from types import TracebackType
from typing import Optional
from colorama import init, Fore, Style, Back

# Initialize colopiprama
init(autoreset=True)


class Color(Enum):
    """Color enumeration for console output"""

    RED = Fore.RED
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    BLUE = Fore.BLUE


ERROR_CODES: dict[type, int] = {
    RuntimeError: 101,
    FileNotFoundError: 102,
    ValueError: 103,
    NotImplementedError: 104,
    IOError: 105,
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
        return record.levelno >= logging.ERROR


class DefaultFilter(logging.Filter):
    """Allows only DEBUG, INFO, WARNING levels."""

    def filter(self, record) -> bool:
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

    # Create a file handler with encoding
    default_file_handler = logging.FileHandler(path, encoding="utf-8")
    default_file_handler.setLevel(logging.DEBUG)
    default_file_handler.setFormatter(default_formatter)
    default_file_handler.addFilter(DefaultFilter())
    error_file_handler = logging.FileHandler(path, encoding="utf-8")
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(error_formatter)
    error_file_handler.addFilter(ErrorFilter())
    logger.addHandler(error_file_handler)
    logger.addHandler(default_file_handler)
    logger.setLevel(level)


def _on_crash(exctype: type[BaseException], value: BaseException, trace: TracebackType | None) -> None:
    """
    Custom exception hook to handle exceptions and exit with the appropriate error code.
    """
    if exctype == WorkspaceError:
        err_code: int = getattr(value, "error_code")
        if err_code != 100:
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


def ws_success(message: str) -> None:
    """Print a success message"""
    print(Fore.BLUE + Back.CYAN + message)
    logger.info(message, stacklevel=2)


def ws_info(message: str) -> None:
    """Print an informational message"""
    print(Fore.WHITE + Back.BLUE + message)
    logger.info(message, stacklevel=2)


def ws_warning(message: str) -> None:
    """Print a warning message"""
    print(Fore.YELLOW + Back.BLACK + message)
    if logger.hasHandlers():
        logger.warning(message, stacklevel=2)


# specify that this function raises an exception
def _ws_error(error: BaseException, message: Optional[str] = None) -> None:
    """Print an error message"""
    if not message:
        message = str(error)
    print(Back.BLACK + Fore.RED + message)
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
    """Print an advice message if LOG_LEVEL is set to DEBUG"""
    # check if LOG_LEVEL is set to DEBUG
    log_level = logger.level
    if log_level == logging.DEBUG or force:
        print(Fore.GREEN + Back.BLACK + message)
        logger.debug(message, stacklevel=2)


def ws_tip(messages: dict[Color, str]) -> None:
    """Print a tip message"""
    msg: str = ""
    for color, message in messages.items():
        msg += f"{color.value}{message}"
    nc = Style.RESET_ALL  # No Color
    tip: str = f"{Back.BLACK}{msg}{nc}"
    print(tip)
    logger.info(msg, stacklevel=2)


def ws_error(message: str, exception: Optional[BaseException] = None) -> None:
    """Log and print an exception while removing the stack trace"""
    if not exception:
        exception = BaseException(message)
    exception.__traceback__ = None
    _ws_error(exception, message)


class WorkspaceError(Exception):
    """Custom exception for workspace operations"""

    def __init__(self, message: str, parent_exception: BaseException, error_code: int = 100) -> None:
        sys.excepthook = _on_crash
        self.message = message
        self.parent_exception = parent_exception
        self.error_code = error_code

        if type(parent_exception) in ERROR_CODES:
            self.error_code = ERROR_CODES[type(parent_exception)]
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
        return (
            f"[ WorkspaceError: {self.message} ] —— [ code: {self.error_code} ] —— "
            f"[ type: {self.parent_exception.__class__.__name__} ] —— [ Message: {str(self.parent_exception)} ]"
        )
