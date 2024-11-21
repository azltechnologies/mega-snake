""" Properties for the application """
# pylint: disable=global-statement
log_level: str

def set_log_level(level: str) -> None:
    """ Set the log level """
    global log_level
    log_level = level

def get_log_level() -> str:
    """ Get the log level """
    return log_level
