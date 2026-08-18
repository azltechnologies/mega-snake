"""Properties for the application"""

from dataclasses import dataclass, field
import glob
from configparser import ConfigParser
from importlib.resources import files
import shutil
from typing import Optional
import inspect
import os
from datetime import datetime
from mega_snake.util import formatting
from mega_snake.util.formatting import InternalStateError
from mega_snake.constants import SHELL_OPT, LOGGING_NAME_TO_LEVEL, LOGGING_LEVEL_TO_NANE, MODULE_NAME


def get_validated_input(p_prompt: str, valid_values: list[str]) -> str:
    """Proxy to keep this symbol patchable in tests and avoid import cycles."""
    from mega_snake.util.util import get_validated_input as util_get_validated_input

    return util_get_validated_input(p_prompt, valid_values)


def _get_package_root() -> str:
    """Get the root of the package.

    Returns:
        str: The absolute path to the package resources directory.

    Raises:
        ModuleNotFoundError: If the package module cannot be found or accessed.
    """
    try:
        python_path: str = str(files(MODULE_NAME))
        if not python_path:
            raise ValueError("Package root path is empty")
        return python_path
    except (ModuleNotFoundError, TypeError, ValueError) as e:
        raise ModuleNotFoundError(
            f"Cannot access package resources for module '{MODULE_NAME}'. "
            "Ensure the package is properly installed with all required dependencies."
        ) from e


# Methods allowed to run initialization-only operations. "complete_initialization" is part of the
# initialization too: it is the second half of an __init__ that light-weight mode left unfinished
# because the working path did not exist yet.
INITIALIZATION_METHODS: tuple[str, ...] = ("__init__", "complete_initialization")


def _check_forbidden_execution(
    method: str, message: str, reload: bool = False, props: Optional["AppProperties"] = None
) -> None:
    # Get call stack
    frames = inspect.stack()
    allowed: tuple[str, ...] = INITIALIZATION_METHODS if method == "__init__" else (method,)
    # Check if called from __init__ (or from the deferred completion of that same initialization)
    called_from_init: bool = any(frame.function in allowed for frame in frames[2:])  # Skip current frame
    if not called_from_init:
        if not reload:
            raise PermissionError(f"Operation not permitted: {message} is only allowed during initialization")
        if not props:
            raise ValueError("properties must be set when reloading properties")
        # Only reconfigure logging when there is a log file to point it at: an initialization
        # deferred by light-weight mode has no "log_file" yet, and reloading must not invent one.
        if props.is_fully_initialized():
            formatting.config_log(
                props._retrieve_property("log_file"),
                props.log_level,
            )
        formatting.ws_advice(f"Properties reloaded by: {message}")


def _check_property(prop: str, dic: dict[str, str]) -> str:
    """
    Check if a property is set in the dictionary

    Args:
        prop (str): The property to check
        dic (dict[str, str]): The dictionary to check
    """
    value: Optional[str] = dic.get(prop)
    if not value:
        # Read from the distribution's own properties file, which ships with the package: a missing
        # key is a packaging defect, not something the user can supply.
        raise InternalStateError(f"property {prop} has not been set in the properties file. This is a bug.")
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
            _check_forbidden_execution("_retrieve_property", "properties map access")
        return self._props

    def _retrieve_property(self, prop: str) -> str:
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
        resources_path = f"{_get_package_root()}/{value}"
        # Check if the path exists
        # The properties file this path comes from is internal to the distribution, not something a
        # user can edit or fix: a missing resources folder means the package was built or installed
        # wrong, never that the user is missing something.
        if not os.path.exists(resources_path):
            raise InternalStateError(
                f"Path {resources_path} does not exist in PYTHONPATH, please check the "
                "properties file as it should be a relative path. This is a bug."
            )
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
        log_path: str = f"{self.props['working_path']}/logs"
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
        Initializes an instance of the AppProperties class.

        This constructor follows a critical sequence to support both full initialization and
        light-weight mode (used in create-release and similar commands that don't need a workspace).

        Initialization Flow:
            1. Validates resources_path (must exist and be readable)
            2. Attempts to validate working_path and locate workspace_file:
               - If working_path exists: locates .code-workspace file in parent directory
               - If working_path does NOT exist: enters exception handler (see below)
            3. On FileNotFoundError (working_path missing):
               - Sets local_config_file and shell as fallback properties
               - Attempts workspace_file search one more time (best-effort)
               - Sets workspace_file to empty string if not found
               - Relays the exception to init_app_properties for handling
            4. If no exceptions: completes full initialization with all remaining properties

        Light-weight Mode Support:
            When working_path doesn't exist, this class partially initializes and propagates
            the FileNotFoundError. The init_app_properties function checks the light_weight flag:
            - If light_weight=True: catches the error and returns (partial props are available)
            - If light_weight=False: re-raises the error

        This design allows create-release commands to access local_config_file and shell
            without requiring a valid workspace directory.

        Args:
            log_level (str): The log level to use (e.g., 'DEBUG', 'INFO')
            shell (str): The shell in use by the user ('bash', 'zsh', 'powershell', 'pwsh')
            properties (dict[str, str]): The configuration dictionary from config.properties

        Raises:
            FileNotFoundError: If working_path does not exist (caught and handled by init_app_properties)
            NotADirectoryError: If a required path exists but is not a directory
            PermissionError: If a required path is not readable/writable
            ValueError: If shell or other validation fails
        """
        self._props = {}
        # Kept so an initialization deferred by light-weight mode can be finished later, once the
        # working path exists, without having to read the properties file again
        self._pending_properties = properties
        self._pending_log_level = log_level
        # Check if the required properties are set
        resources_path: str = _check_property("resources_path", properties)
        working_path: str = _check_property("working_path", properties)
        log_file: str = _check_property("log_file_name", properties)
        local_config_file: str = _check_property("local_config_file_name", properties)
        local_env_file: str = _check_property("local_env_file_name", properties)
        graphql_schema_file: str = _check_property("graphql_schema_file_name", properties)
        self.__resources_path_validator(resources_path)
        try:
            self.__working_path_validator(working_path)
            self.__adding_prop_validator(
                "workspace_file", _find_code_workspace_files(f"{self.props['working_path']}/..")
            )
        except FileNotFoundError as e:
            self.__adding_prop_validator("local_config_file", f"{self.props['working_path']}/{local_config_file}")
            self.__adding_prop_validator("local_env_file", f"{self.props['working_path']}/{local_env_file}")
            self.__shell_validator(shell)
            try:
                self.__adding_prop_validator(
                    "workspace_file", _find_code_workspace_files(f"{self.props['working_path']}/..")
                )
            except FileNotFoundError:
                self.props["workspace_file"] = ""
            raise e
        self.log_level_from_str(log_level)
        self.__log_file_validator(log_file)
        self.__shell_validator(shell)
        self.__adding_prop_validator("local_config_file", f"{self.props['working_path']}/{local_config_file}")
        self.__adding_prop_validator("local_env_file", f"{self.props['working_path']}/{local_env_file}")
        self.__adding_prop_validator("graphql_schema_file", f"{self.props['working_path']}/{graphql_schema_file}")
        self.__post_init__()

    def is_fully_initialized(self) -> bool:
        """Check whether the initialization completed, as opposed to being deferred.

        Parameters:
            None

        Raises:
            None

        Returns:
            bool: True when every property is set, False when light-weight mode stopped the
                initialization half way because the working path did not exist.
        """
        return "log_file" in self._props

    def complete_initialization(self) -> None:
        """Set the properties that were skipped when the working path did not exist yet.

        Light-weight mode lets a command start without a working path, so the properties that live
        inside that folder (the log file above all) could not be resolved. Once the folder is there,
        this finishes exactly where ``__init__`` stopped, leaving the instance in the same state a
        full initialization would have produced.

        Parameters:
            None

        Raises:
            FileNotFoundError: If the working path still does not exist.
            NotADirectoryError: If the working path exists but is not a directory.
            PermissionError: If the working path is not writable.

        Returns:
            None
        """
        log_file: str = _check_property("log_file_name", self._pending_properties)
        graphql_schema_file: str = _check_property("graphql_schema_file_name", self._pending_properties)
        self.__working_path_validator(self._props["working_path"])
        self.log_level_from_str(self._pending_log_level)
        self.__log_file_validator(log_file)
        self.__adding_prop_validator("graphql_schema_file", f"{self.props['working_path']}/{graphql_schema_file}")
        self.__post_init__()

    def __post_init__(self) -> None:
        """Raise InternalStateError if any attribute is still None after initialisation."""
        for attr_name, attr_value in vars(self).items():
            if attr_value is None:
                # Every attribute is assigned by the initialization that just ran; one left as None
                # means that initialization has a hole in it.
                raise InternalStateError(f"{attr_name} has not been set. This is a bug.")

    @staticmethod
    def get_instance() -> "AppProperties":
        """
        Get the instance of the class

        Raises:
            InternalStateError: If the instance has not been initialized yet

        Returns:
            AppProperties: The instance of the class
        """
        if AppProperties._instance is None:
            # cli() initializes the singleton before dispatching to any command, so asking for it
            # first means a caller ran outside that order.
            raise InternalStateError("Properties Singleton not initialized yet. This is a bug.")
        return AppProperties._instance

    def __new__(cls, log_level: str, shell: str, properties: dict[str, str]) -> "AppProperties":
        """Create and return the singleton AppProperties instance; raise if already initialized."""
        _check_forbidden_execution("init_app_properties", "AppProperties class instantiation")
        if not cls._instance:
            cls._instance = super().__new__(cls)
            return cls._instance
        raise InternalStateError("Properties Singleton already initialized. This is a bug.")


def _read_properties(file_path: str) -> dict:
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

    prop_file: str = f"{_get_package_root()}/config.properties"
    # check if the properties file exists
    if not os.path.exists(prop_file):
        raise FileNotFoundError(f"Properties file not found: {prop_file}")

    properties = _read_properties(prop_file)

    # check if dictionary is empty
    if not properties:
        raise ValueError("Properties file is empty")

    if not shell:
        raise EnvironmentError("Environment variable 'MEGA_SNAKE_SHELL' is not set")
    if not shutil.which(shell):
        if shell == "powershell" and shutil.which("pwsh"):
            shell = "pwsh"
        elif shell == "pwsh" and shutil.which("powershell"):
            shell = "powershell"
        else:
            raise ValueError(f"Shell '{shell}' not found in PATH")
    try:
        AppProperties(log_level, shell, properties)
    except FileNotFoundError as e:
        if light_weight:
            return
        raise e
    app_props: AppProperties = AppProperties.get_instance()
    path: str = app_props._retrieve_property("log_file")
    level: int = app_props.log_level
    formatting.config_log(path, level)
    formatting.ws_advice(f"set log level: {app_props.log_level}")
    formatting.ws_advice(f"Set working path: {app_props._retrieve_property('working_path')}")
    formatting.ws_advice(f"Set log file: {app_props._retrieve_property('log_file')}")
    formatting.ws_advice(f"Set shell: {app_props._retrieve_property('shell')}")
    formatting.ws_advice(f"Set local config file: {app_props._retrieve_property('local_config_file')}")


def complete_app_properties() -> None:
    """Finish an initialization that light-weight mode deferred, and start logging to file.

    Console output never depended on this: every ``ws_*`` helper prints before logging, so a
    light-weight command that runs without a working path still talks to the user normally, it just
    has nowhere to write its log file. Commands that do end up with a working path (because it
    already existed, or because the user accepted creating it) call this to get the rest of the
    properties and the file handlers that a full initialization would have set up.

    It is idempotent and safe to call when the initialization already completed.

    Parameters:
        None

    Raises:
        InternalStateError: If the properties singleton was never initialized.

    Returns:
        None
    """
    app_props: AppProperties = AppProperties.get_instance()
    if app_props.is_fully_initialized():
        return
    app_props.complete_initialization()
    formatting.config_log(app_props._retrieve_property("log_file"), app_props.log_level)
    formatting.ws_advice(f"Deferred initialization completed; log file: {app_props._retrieve_property('log_file')}")


def _find_code_workspace_files(directory: str) -> str:
    """
    Find the .code-workspace file in the specified directory
    """
    directory = os.path.abspath(directory)
    # Find all .code-workspace files in the specified directory
    workspace_files = glob.glob(os.path.join(directory, "*.code-workspace"))

    # Check if there is more than one .code-workspace file
    if len(workspace_files) > 1:
        options: list[str] = [str(i) for i in range(0, len(workspace_files))]
        prompt: str = "Multiple .code-workspace files found. Please select one:\n"
        for index, workspace_file in enumerate(workspace_files):
            prompt += f"\t{index}: {workspace_file}\n"
        wk_file = workspace_files[int(get_validated_input(prompt, options))]
        return os.path.abspath(wk_file)
    if len(workspace_files) == 0:
        raise FileNotFoundError("No .code-workspace file found.")

    # Return the absolute path of the .code-workspace file
    return os.path.abspath(workspace_files[0])


def get_property(prop: str) -> str:
    """
    Get a property from the properties file

    Args:
        prop (str): The property to get
    """
    return AppProperties.get_instance()._retrieve_property(prop)
