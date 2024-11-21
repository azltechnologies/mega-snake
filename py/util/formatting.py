""" This module contains functions for formatting output messages to the console. """

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
def ws_error(message: str, error: Exception) -> ValueError:
    """Print an error message"""
    print(Fore.RED + message)
    logger.log.error(f"{message}; %s: %s\n\n%s", error.__class__, str(error), logger.get_traceback(error),stacklevel=2)
    raise SystemExit(error) from error


def ws_advice(message: str) -> None:
    """Print an advice message if LOG_LEVEL is set to DEBUG"""
    # check if LOG_LEVEL is set to DEBUG
    props = properties.APP_PROPERTIES
    log_level = props.log_level
    if log_level == logger.log.DEBUG:
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
