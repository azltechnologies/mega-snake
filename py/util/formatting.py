""" This module contains functions for formatting output messages to the console. """

import sys
import traceback
import re
from typing import Optional
from colorama import init, Fore, Style
from logging import info, warning, debug, error as log_error, DEBUG, root

# Initialize colopiprama
init(autoreset=True)


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
    print(Fore.CYAN + message)
    info(message, stacklevel=2)


def ws_info(message: str) -> None:
    """Print an informational message"""
    print(Fore.BLUE + message)
    info(message, stacklevel=2)


def ws_warning(message: str) -> None:
    """Print a warning message"""
    print(Fore.YELLOW + message)
    warning(message, stacklevel=2)


# specify that this function raises an exception
def _ws_error(error: BaseException, message: Optional[str] = None) -> None:
    """Print an error message"""
    if not message:
        message = str(error)
    print(Fore.RED + message)
    log_error(f"{message}; %s: %s\n\n%s", error.__class__, str(error), get_traceback(error), stacklevel=3)


def ws_advice(message: str, force: bool = False) -> None:
    """Print an advice message if LOG_LEVEL is set to DEBUG"""
    # check if LOG_LEVEL is set to DEBUG
    log_level = root.level
    if log_level == DEBUG or force:
        print(Fore.GREEN + message)
        debug(message, stacklevel=2)


def ws_tip(prologue: str, epilogue: Optional[str]) -> None:
    """Print a tip message"""
    epilogue = f" {epilogue}" if epilogue else ""
    green = Fore.GREEN
    red = Fore.RED
    yellow = Fore.YELLOW
    nc = Style.RESET_ALL  # No Color
    tip: str = f"{green}Hey! {red}'{prologue}'{green}{yellow}{epilogue}{nc}."
    print(tip)
    info(f"{prologue} {epilogue}", stacklevel=2)


class WorkspaceError(BaseException):
    """Custom exception for workspace operations"""

    def __init__(self, message: str, parent_exception: BaseException, error_code: int = 1) -> None:
        self.message = message
        self.parent_exception = parent_exception
        self.error_code = error_code
        _, _, tb = sys.exc_info()
        self.__traceback__ = tb
        super().__init__(self.message)
        _ws_error(self)

    def __str__(self) -> str:
        return f"WorkspaceError: {self.message} (code: {self.error_code}) from {self.parent_exception.__class__}: {str(self.parent_exception)}"

    @staticmethod
    def ws_error(message: str,exception: Optional[BaseException] = None) -> None:
        if not exception:
            exception = BaseException(message)
        """Log and print an exception"""
        _ws_error(exception, message)
