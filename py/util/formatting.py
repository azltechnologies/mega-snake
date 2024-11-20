""" This module contains functions for formatting output messages to the console. """

from colorama import init, Fore, Style
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


def ws_error(message: str, error: Exception) -> None:
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
    print(Fore.GREEN + message)


def ws_tip(function_name: str, description: str) -> None:
    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    NC = Style.RESET_ALL  # No Color
    print(f"{GREEN}use the {RED}'{function_name}'{GREEN} function to {YELLOW}{description}{NC}")
