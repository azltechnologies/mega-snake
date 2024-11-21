""" This module contains functions for formatting output messages to the console. """

from colorama import init, Fore, Style
from py.util.props import get_log_level
from py.util import logger

# Initialize colopiprama
init(autoreset=True)


def ws_success(message: str) -> None:
    """Print a success message"""
    print(Fore.CYAN + message)
    logger.log.info(message)


def ws_info(message: str) -> None:
    """Print an informational message"""
    print(Fore.BLUE + message)
    logger.log.info(message)


def ws_warning(message: str) -> None:
    """Print a warning message"""
    print(Fore.YELLOW + message)
    logger.log.warning(message)

# specify that this function raises an exception
def ws_error(message: str, error: Exception) -> ValueError:
    """Print an error message"""
    print(Fore.RED + message)
    logger.log.error(
        f"{message}; %s: %s\n\n%s",
        error.__class__,
        str(error),
        logger.get_traceback(error)
    )
    raise SystemExit(error) from error


def ws_advice(message: str) -> None:
    """Print an advice message if LOG_LEVEL is set to DEBUG"""
    # check if LOG_LEVEL is set to DEBUG
    log_level = get_log_level()
    if log_level == "DEBUG":
        print(Fore.GREEN + message)
        logger.log.debug(message)


def ws_tip(function_name: str, description: str) -> None:
    """Print a tip message"""
    green = Fore.GREEN
    red = Fore.RED
    yellow = Fore.YELLOW
    nc = Style.RESET_ALL  # No Color
    print(f"{green}use the {red}'{function_name}'{green} function to {yellow}{description}{nc}")
