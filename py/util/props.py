""" Properties for the application """

from dataclasses import dataclass, field
from typing import Optional
import inspect
import os
import logging as log
from datetime import datetime
from py.util import formatting, logger
from py.constants import SHELL_OPT

def _check_forbidden_execution(method: str, message:str, reload: bool = False) -> None:
    # Get call stack
    frames = inspect.stack()
    # Check if called from __init__
    called_from_init: bool = any(frame.function == method for frame in frames[2:])  # Skip current frame
    if not called_from_init:
        if not reload:
            raise PermissionError(f"Operation not permitted: {message} is only allowed during initialization")
        else:
            logger.config_log()
            formatting.ws_advice(f"Properties reloaded by: {message}")

@dataclass(init=False)
class AppProperties:
    """
    Application properties

    Attributes:
        log_level (int): The log level to use
        working_path (str): The working path for the application, used mainly for output files
    """

    _log_level: int = field(
        init=False,
    )
    _working_path: str = field(init=False)
    _log_file: str = field(init=True)
    _shell: str = field(init=True)
    def __new__(cls, log_level: str, working_path: str, shell: str) -> "AppProperties":
        _check_forbidden_execution("init_app_properties","AppProperties class instantiation ")
        return super().__new__(cls)

    @property
    def log_level(self) -> int:
        return self._log_level

    @log_level.setter
    def log_level(self, value: int):
        try:
            level: str = log._levelToName[value]
            if level is None:
                raise ValueError(f"Invalid log level: {value}")
            self._log_level = value
        except KeyError as e:
            raise KeyError(f"Invalid log level: {value}, must be one of {log._levelToName.keys()}") from e
        _check_forbidden_execution("__init__", "log_level setter method execution", True)
            

    def log_level_from_str(self, value: str):
        try:
            level: int = log._nameToLevel[value]
            if level is None:
                raise ValueError(f"Invalid log level: {value}")
        except KeyError as e:
            raise KeyError(f"Invalid log level: {value}, must be one of {log._nameToLevel.keys()}") from e
        self.log_level = level

    @property
    def working_path(self) -> str:
        return self._working_path

    @working_path.setter
    def working_path(self, value: str):
        # Convert the path to an absolute path
        working_path = os.path.abspath(value)
        # Check if the path exists
        if not os.path.exists(working_path):
            raise FileNotFoundError(f"Path {working_path} does not exist")
        # Check if the path is a directory
        if not os.path.isdir(working_path):
            raise NotADirectoryError(f"Path {working_path} is not a directory")
        # Check if the path is writable
        if not os.access(working_path, os.W_OK):
            raise PermissionError(f"Path {working_path} is not writable")
        self._working_path = working_path

    @property
    def log_file(self) -> str:
        return self._log_file

    @log_file.setter
    def log_file(self, value: str) -> None:
        _check_forbidden_execution("__init__", "log_file setter method execution")
        today = datetime.today()
        formatted_date: str = today.strftime("%Y-%m-%d")
        log_path: str = f"{self.working_path}/logs"
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        self._log_file = f"{log_path}/{value}_{formatted_date}.log"

    @property
    def shell(self) -> str:
        return self._shell
    
    @shell.setter
    def shell(self, value: str) -> None:
        _check_forbidden_execution("__init__", "shell setter method execution")
        if value not in SHELL_OPT:
            raise ValueError(f"Invalid shell: {value}, must be one of {SHELL_OPT}")
        self._shell = value

    def __init__(self, log_level: str, working_path: str, shell: str) -> None:
        """
        Initializes an instance of the AppProperties class

        Args:
            log_level (str): The log level to use
            working_path (str): The working path for the application, used mainly for output files
        """

        self.log_level_from_str(log_level)
        self.working_path = working_path
        self.log_file = "setup_environment"
        self.shell = shell
        self.__post_init__()

    def __post_init__(self) -> None:
        for attr_name, attr_value in vars(self).items():
            if attr_value is None:
                raise ValueError(f"{attr_name} has not been set")


# Single instance of the configuration object
APP_PROPERTIES: AppProperties


# Initialize the configuration object
def init_app_properties(log_level: str, working_path: Optional[str], shell: Optional[str]) -> None:
    """
    Setup the application properties and initialize the logger

    Args:
        log_level (str): The log level to use
        working_path (str): The working path for the application, used mainly for output files
    """
    global APP_PROPERTIES  # pylint: disable=W0603

    # Check if the environment variable WS_TEMP is set
    if not working_path:
        raise EnvironmentError("Environment variable 'WS_TEMP' is not set")
    if not shell:
        raise EnvironmentError("Environment variable 'WS_SHELL' is not set")
    APP_PROPERTIES = AppProperties(log_level, working_path, shell)
    logger.config_log()
    formatting.ws_advice(f"Set working path: {APP_PROPERTIES.working_path}")
    formatting.ws_advice(f"set log level: {APP_PROPERTIES.log_level}")
    formatting.ws_advice(f"Set log file: {APP_PROPERTIES.log_file}")
    formatting.ws_advice(f"Set shell: {APP_PROPERTIES.shell}")
