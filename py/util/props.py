""" Properties for the application """

from dataclasses import dataclass, field
import os
import logging as log
from py.util import formatting, logger
from datetime import datetime


@dataclass
class AppProperties:
    """
    Application properties

    Attributes:
        log_level (int): The log level to use
        working_path (str): The working path for the application, used mainly for output files
    """

    log_level: int = field(default=None)
    working_path: str = field(default=None)
    log_file: str = field(default=None)

    def __init__(self, log_level: str, working_path: str):
        """
        Initializes an instance of the AppProperties class

        Args:
            log_level (str): The log level to use
            working_path (str): The working path for the application, used mainly for output files
        """
        try:
            level: int = log._nameToLevel[log_level]  # pylint: disable=W0212
            if level is None:
                raise ValueError(f"Invalid log level: {log_level}")
            self.log_level = level
        except KeyError as e:
            raise KeyError(f"Invalid log level: {log_level}, must be one of {log._nameToLevel.keys()}") from e  # pylint: disable=W0212

        # Check if the environment variable WS_TEMP is set
        if not working_path:
            raise EnvironmentError("Environment variable 'WS_TEMP' is not set")
        # Convert the path to an absolute path
        working_path = os.path.abspath(working_path)
        # Check if the path exists
        if not os.path.exists(working_path):
            raise FileNotFoundError(f"Path {working_path} does not exist")
        # Check if the path is a directory
        if not os.path.isdir(working_path):
            raise NotADirectoryError(f"Path {working_path} is not a directory")
        # Check if the path is writable
        if not os.access(working_path, os.W_OK):
            raise PermissionError(f"Path {working_path} is not writable")
        self.working_path = working_path
        today = datetime.today()
        formatted_date: str = today.strftime("%Y-%m-%d")
        log_path: str = f"{working_path}/logs"
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        self.log_file = f"{log_path}/setup_environment_{formatted_date}.log"

    def __post_init__(self):
        if self.log_level is None:
            raise ValueError("log_level has not been set")
        if self.working_path is None:
            raise ValueError("working_path has not been set")


# Single instance of the configuration object
APP_PROPERTIES: AppProperties


# Initialize the configuration object
def init_app_properties(log_level: str, working_path: str) -> None:
    """
    Setup the application properties and initialize the logger

    Args:
        log_level (str): The log level to use
        working_path (str): The working path for the application, used mainly for output files
    """
    global APP_PROPERTIES  # pylint: disable=W0603
    APP_PROPERTIES = AppProperties(log_level, working_path)
    logger.config_log()
    formatting.ws_info(f"Set working path: {APP_PROPERTIES.working_path}")
    formatting.ws_info(f"set log level: {APP_PROPERTIES.log_level}")
    formatting.ws_tip("Set log file:", APP_PROPERTIES.log_file)
