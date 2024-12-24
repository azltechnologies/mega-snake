""" Properties for the application """

from dataclasses import dataclass, field
import glob
from configparser import ConfigParser
from typing import Optional
import inspect
import os
from datetime import datetime
from py.util import formatting
from py.constants import SHELL_OPT, LOGGING_NAME_TO_LEVEL, LOGGING_LEVEL_TO_NANE


def _check_forbidden_execution(method: str, message: str, reload: bool = False, props: Optional["AppProperties"] = None) -> None:
    # Get call stack
    frames = inspect.stack()
    # Check if called from __init__
    called_from_init: bool = any(frame.function == method for frame in frames[2:])  # Skip current frame
    if not called_from_init:
        if not reload:
            raise PermissionError(f"Operation not permitted: {message} is only allowed during initialization")
        if not props:
            raise ValueError("properties must be set when reloading properties")
        formatting.config_log(props.retrieve_property("local_config_file"), props.log_level)
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
    Singleton class to hold the properties of the application

    Attributes:
        _instance (AppProperties): The instance of the class
        log_level (int): The log level to use
        working_path (str): The working path for the application, used mainly for output files
    """

    _instance: Optional["AppProperties"] = None

    _log_level: int = field(
        init=False,
    )
    _props: dict[str, str] = field(default_factory=dict)

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
    def log_level(self, value: int) -> None:
        try:
            level: str = LOGGING_LEVEL_TO_NANE[value]
            if level is None:
                raise ValueError(f"Invalid log level: {value}")
            self._log_level = value
        except KeyError as e:
            raise KeyError(f"Invalid log level: {value}, must be one of {LOGGING_LEVEL_TO_NANE.keys()}") from e
        _check_forbidden_execution("__init__", "log_level setter method execution", True, self)

    def log_level_from_str(self, value: str) -> None:
        """Set the log level from a string"""
        try:
            level: int = LOGGING_NAME_TO_LEVEL[value]
            if level is None:
                raise ValueError(f"Invalid log level: {value}")
        except KeyError as e:
            raise KeyError(f"Invalid log level: {value}, must be one of {LOGGING_NAME_TO_LEVEL.keys()}") from e
        self.log_level = level

    def __resources_path_validator(self, value: str) -> None:
        resources_path = f'{os.getenv("PYTHONPATH")}/{value}'
        # Check if the path exists
        assert os.path.exists(resources_path),f"Path {resources_path} does not exist in PYTHONPATH, please check the properties file as it should be a relative path. This is a bug."
        # Check if the path is a directory
        if not os.path.isdir(resources_path):
            raise NotADirectoryError(f"Path {resources_path} is not a directory")
        # Check if the path is readable
        if not os.access(resources_path, os.R_OK):
            raise PermissionError(f"Path {resources_path} is not readable")
        self.props["resources_path"] = resources_path

    def __working_path_validator(self, value: str) -> None:
        # Convert the path to an absolute path
        working_path = os.path.abspath(value)
        # Check if the path exists
        if not os.path.exists(working_path):
            self.props["working_path"] = working_path
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

    def __adding_prop_validator(self, key: str, value: str) -> None:
        _check_forbidden_execution("__init__", "new property setter method execution")
        if not value:
            raise ValueError(f"Property {key} is not set")
        self.props[key] = value

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
        resources_path: str = check_property("resources_path", properties)
        working_path: str = check_property("working_path", properties)
        log_file: str = check_property("log_file_name", properties)
        local_config_file: str = check_property("local_config_file_name", properties)
        graphql_schema_file: str = check_property("graphql_schema_file_name", properties)
        self.__resources_path_validator(resources_path)
        try:
            self.__working_path_validator(working_path)
        except FileNotFoundError as e:
            self.__adding_prop_validator("local_config_file", f"{self.props["working_path"]}/{local_config_file}")
            self.__shell_validator(shell)
            try:
                self.__adding_prop_validator("workspace_file", find_code_workspace_files(f"{self.props["working_path"]}/.."))
            except FileNotFoundError:
                self.props["workspace_file"] = ""
            raise e
        self.log_level_from_str(log_level)
        self.__log_file_validator(log_file)
        self.__shell_validator(shell)
        self.__adding_prop_validator("local_config_file", f"{self.props["working_path"]}/{local_config_file}")
        self.__adding_prop_validator("graphql_schema_file", f"{self.props["working_path"]}/{graphql_schema_file}")
        self.__adding_prop_validator("workspace_file", find_code_workspace_files(f"{self.props["working_path"]}/.."))
        self.__post_init__()

    def __post_init__(self) -> None:
        for attr_name, attr_value in vars(self).items():
            if attr_value is None:
                raise ValueError(f"{attr_name} has not been set")

    @staticmethod
    def get_instance() -> "AppProperties":
        """
        Get the instance of the class

        Returns:
            AppProperties: The instance of the class
        """
        if AppProperties._instance is None:
            raise RuntimeError("Properties Singleton not initialized yet")
        return AppProperties._instance

    def __new__(cls, log_level: str, shell: str, properties: dict[str, str]) -> "AppProperties":
        _check_forbidden_execution("init_app_properties", "AppProperties class instantiation")
        if not cls._instance:
            cls._instance = super().__new__(cls)
            return cls._instance
        raise RuntimeError("Properties Singleton already initialized")


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
def init_app_properties(log_level: str, shell: Optional[str], light_weight: bool) -> None:
    """
    Setup the application properties and initialize the logger

    Args:
        log_level (str): The log level to use
        shell (Optional[str]): The shell in use by the user
    """

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
    try:
        AppProperties(log_level, shell, properties)
    except FileNotFoundError as e:
        if light_weight:
            return
        raise e
    app_props: AppProperties = AppProperties.get_instance()
    path: str = app_props.retrieve_property("log_file")
    level: int = app_props.log_level
    formatting.config_log(path, level)
    formatting.ws_advice(f"set log level: {app_props.log_level}")
    formatting.ws_advice(f"Set working path: {app_props.retrieve_property("working_path")}")
    formatting.ws_advice(f"Set log file: {app_props.retrieve_property("log_file")}")
    formatting.ws_advice(f"Set shell: {app_props.retrieve_property("shell")}")
    formatting.ws_advice(f"Set local config file: {app_props.retrieve_property("local_config_file")}")


def find_code_workspace_files(directory: str) -> str:
    """
    Find the .code-workspace file in the specified directory
    """
    directory = os.path.abspath(directory)
    # Find all .code-workspace files in the specified directory
    workspace_files = glob.glob(os.path.join(directory, "*.code-workspace"))

    # Check if there is more than one .code-workspace file
    if len(workspace_files) > 1:
        raise RuntimeError("Multiple .code-workspace files found.")
    if len(workspace_files) == 0:
        raise FileNotFoundError("No .code-workspace file found.")

    # Return the absolute path of the .code-workspace file
    return os.path.abspath(workspace_files[0])
