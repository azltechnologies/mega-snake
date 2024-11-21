"""Module responsible for configuring the logger."""
import logging
import traceback
from py.util.props import get_log_level

log = logging


def config_log(path: str) -> None:
    """
    Configures the logger at the specified level.

    Args:
        path (str): path to save the log file

    Returns:
        None
    """
    log_format = (
        "%(asctime)25s –– [%(levelname)-8s] %(filename)25s"
        + ":[%(funcName)-42s]:%(lineno)-6d  –– %(message)s"
    )
    log_level = logging._nameToLevel[get_log_level()]  # pylint: disable=W0212
    log.basicConfig(
        filename=path,
        encoding="utf-8",
        level=log_level,  # pylint: disable=W0212
        format=log_format,
        force=True
    )


def get_traceback(e: Exception) -> str:
    """
    Retrieves the traceback from an exception.

    Args:
        e (Exception): exception to retrieve the traceback

    Returns:
        str: Exception's traceback.
    """
    return "".join(
        traceback.format_exception(type(e), e, e.__traceback__)
    )
