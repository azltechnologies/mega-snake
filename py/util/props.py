""" Properties for the application """

from dataclasses import dataclass, field
from configparser import ConfigParser
from typing import Optional
import inspect
import os
import logging as log
from datetime import datetime
from py.util import formatting, logger
from py.constants import SHELL_OPT


def _check_forbidden_execution(method: str, message: str, reload: bool = False) -> None:
    # Get call stack
    frames = inspect.stack()
    # Check if called from __init__
    called_from_init: bool = any(frame.function == method for frame in frames[2:])  # Skip current frame
    if not called_from_init:
        if not reload:
            raise PermissionError(f"Operation not permitted: {message} is only allowed during initialization")
        logger.config_log()
        formatting.ws_advice(f"Properties reloaded by: {message}")


def check_property(prop: str, dic: dict[str, str]) -> str:
    """
    Check if a property is set in the dictionary

    Args:
        prop (str): The property to check
        dic (dict[str, str]): The dictionary to check
    """
    value: Optional[str] = dic.get(prop)
    if not value:
        raise KeyError(f"property {prop} has not been set in the properties file")
    return value


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
    _props: dict[str, str] = field(default_factory=dict)

    def __new__(cls, log_level: str, shell: str, properties: dict[str, str]) -> "AppProperties":
        _check_forbidden_execution("init_app_properties", "AppProperties class instantiation ")
        return super().__new__(cls)

    @property
    def props(self) -> dict[str, str]:
        """Get the properties map"""
        try:
            _check_forbidden_execution("__init__", "properties map access")
        except PermissionError:
            _check_forbidden_execution("retrieve_property", "properties map access")
        return self._props

    def retrieve_property(self, prop: str) -> str:
        """Retrieve a property from the properties map"""
        try:
            return self._props[prop]
        except KeyError as e:
            raise KeyError(f"Property {prop} not found in the properties file") from e

    @property
    def log_level(self) -> int:
        """Get the log level"""
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
        """Set the log level from a string"""
        try:
            level: int = log._nameToLevel[value]
            if level is None:
                raise ValueError(f"Invalid log level: {value}")
        except KeyError as e:
            raise KeyError(f"Invalid log level: {value}, must be one of {log._nameToLevel.keys()}") from e
        self.log_level = level

    def __working_path_validator(self, value: str):
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
        self.props["working_path"] = working_path

    def __log_file_validator(self, value: str) -> None:
        _check_forbidden_execution("__init__", "log_file setter method execution")
        today = datetime.today()
        formatted_date: str = today.strftime("%Y-%m-%d")
        log_path: str = f"{self.props["working_path"]}/logs"
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        self.props["log_file"] = f"{log_path}/{value}_{formatted_date}.log"

    def __shell_validator(self, value: str) -> None:
        _check_forbidden_execution("__init__", "shell setter method execution")
        if value not in SHELL_OPT:
            raise ValueError(f"Invalid shell: {value}, must be one of {SHELL_OPT}")
        self.props["shell"] = value

    def __local_config_file_validator(self, value: str) -> None:
        _check_forbidden_execution("__init__", "local_config_file setter method execution")
        self.props["local_config_file"] = f"{self.props["working_path"]}/{value}"

    def __init__(self, log_level: str, shell: str, properties: dict[str, str]) -> None:
        """
        Initializes an instance of the AppProperties class

        Args:
            log_level (str): The log level to use
            shell (str): The shell in use by the user
            props (dict[str, str]): The properties to use
        """
        self._props = {}
        # Check if the required properties are set
        working_path: str = check_property("working_path", properties)
        log_file: str = check_property("log_file_name", properties)
        local_config_file: str = check_property("local_config_file_name", properties)
        self.log_level_from_str(log_level)
        self.__working_path_validator(working_path)
        self.__log_file_validator(log_file)
        self.__shell_validator(shell)
        self.__local_config_file_validator(local_config_file)
        self.__post_init__()

    def __post_init__(self) -> None:
        for attr_name, attr_value in vars(self).items():
            if attr_value is None:
                raise ValueError(f"{attr_name} has not been set")


# Single instance of the configuration object
APP_PROPERTIES: AppProperties


def read_properties(file_path: str) -> dict:
    """
    Read a properties file and return a dictionary

    Args:
        file_path (str): The path to the properties file
    """
    # Create parser with Java properties format
    parser = ConfigParser()
    with open(file_path, "r", encoding="utf-8") as f:
        # Add section header since ConfigParser requires it
        config_string = "[DEFAULT]\n" + f.read()
        parser.read_string(config_string)

    # Convert to dictionary
    return dict(parser["DEFAULT"])


# Initialize the configuration object
def init_app_properties(log_level: str, shell: Optional[str]) -> None:
    """
    Setup the application properties and initialize the logger

    Args:
        log_level (str): The log level to use
        shell (Optional[str]): The shell in use by the user
    """
    global APP_PROPERTIES  # pylint: disable=W0603

    prop_file: str = f'{os.getenv("PYTHONPATH")}/config.properties'
    # check if the properties file exists
    if not os.path.exists(prop_file):
        raise FileNotFoundError(f"Properties file not found: {prop_file}")

    properties = read_properties(prop_file)

    # check if dictionary is empty
    if not properties:
        raise ValueError("Properties file is empty")

    if not shell:
        raise EnvironmentError("Environment variable 'WS_SHELL' is not set")
    APP_PROPERTIES = AppProperties(log_level, shell, properties)
    APP_PROPERTIES.retrieve_property("working_path")
    logger.config_log()
    formatting.ws_advice(f"set log level: {APP_PROPERTIES.log_level}")
    formatting.ws_advice(f"Set working path: {APP_PROPERTIES.retrieve_property("working_path")}")
    formatting.ws_advice(f"Set log file: {APP_PROPERTIES.retrieve_property("log_file")}")
    formatting.ws_advice(f"Set shell: {APP_PROPERTIES.retrieve_property("shell")}")
    formatting.ws_advice(f"Set local config file: {APP_PROPERTIES.retrieve_property("local_config_file")}")
