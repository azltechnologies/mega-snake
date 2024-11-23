"""Module responsible for configuring the logger."""
import logging
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
