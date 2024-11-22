""" This module contains functions for formatting output messages to the console. """

import sys
from typing import Optional
from colorama import init, Fore, Style
from py.util import logger
from py.util import props as properties

# Initialize colopiprama
init(autoreset=True)


def ws_success(message: str) -> None:
    """Print a success message"""
    print(Fore.CYAN + message)
    logger.log.info(message, stacklevel=2)


def ws_info(message: str) -> None:
    """Print an informational message"""
    print(Fore.BLUE + message)
    logger.log.info(message, stacklevel=2)


def ws_warning(message: str) -> None:
    """Print a warning message"""
    print(Fore.YELLOW + message)
    logger.log.warning(message, stacklevel=2)


# specify that this function raises an exception
def _ws_error(error: BaseException, message: Optional[str] = None) -> None:
    """Print an error message"""
    if not message:
        message = str(error)
    print(Fore.RED + message)
    logger.log.error(f"{message}; %s: %s\n\n%s", error.__class__, str(error), logger.get_traceback(error), stacklevel=3)


def ws_advice(message: str, force: bool = False) -> None:
    """Print an advice message if LOG_LEVEL is set to DEBUG"""
    # check if LOG_LEVEL is set to DEBUG
    props = properties.APP_PROPERTIES
    log_level = props.log_level
    if log_level == logger.log.DEBUG or force:
        print(Fore.GREEN + message)
        logger.log.debug(message, stacklevel=2)


def ws_tip(prologue: str, epilogue: str) -> None:
    """Print a tip message"""
    green = Fore.GREEN
    red = Fore.RED
    yellow = Fore.YELLOW
    nc = Style.RESET_ALL  # No Color
    tip: str = f"{green}Hey! {red}'{prologue}'{green} {yellow}{epilogue}{nc}."
    print(tip)
    logger.log.info(f"{prologue} {epilogue}", stacklevel=2)


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
