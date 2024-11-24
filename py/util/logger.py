"""Module responsible for configuring the logger."""
import logging

log = logging

def config_log(path:str, level: int) -> None:
    """
    Configures the logger at the specified level.

    Returns:
        None
    """
    log_format = (
        "%(asctime)25s –– [%(levelname)-8s] %(filename)25s"
        + ":[%(funcName)-42s]:%(lineno)-6d  –– %(message)s"
    )
    log.basicConfig(
        filename=path,
        encoding="utf-8",
        level=level,
        format=log_format,
        force=True
    )
