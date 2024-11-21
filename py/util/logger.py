"""Module responsible for configuring the logger."""
import logging
import traceback
import re
from py.util import props as properties

log = logging

def config_log() -> None:
    """
    Configures the logger at the specified level.

    Returns:
        None
    """
    log_format = (
        "%(asctime)25s –– [%(levelname)-8s] %(filename)25s"
        + ":[%(funcName)-42s]:%(lineno)-6d  –– %(message)s"
    )
    props = properties.APP_PROPERTIES
    path: str = props.log_file
    log_level = props.log_level
    log.basicConfig(
        filename=path,
        encoding="utf-8",
        level=log_level,
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
    # Pattern and replacement
    pattern = r'\.py", line (\d+)'
    replacement = r'.py:\1"'
    tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))

    # Perform substitution
    result = re.sub(pattern, replacement, tb_str)
    return result
