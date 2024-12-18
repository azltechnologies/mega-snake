""" Contains multiple functions to configure the environment for development with vscode. """

import os
from typing import Optional, Callable
from py.util.formatting import ws_advice
from py.constants import MSG_OPT, GCLOUD_LOGGIN_OPT
from py.util.props import AppProperties
from py.config_environment.graphql_schema import create_schema
from py.config_environment.gcloud import gcloud_login
from py.config_environment.java_set import java_set
from py.config_environment.gradle_set import gradle_set

def get_local_file() -> str:
    """
    Returns the local configuration file path.

    Returns:
        str: The local configuration file path.
    """
    props_inst: AppProperties = AppProperties.get_instance()
    shell = props_inst.retrieve_property("shell")
    local_file:str = props_inst.retrieve_property("local_config_file")
    match shell:
        case "bash" | "zsh":
            local_file = f"{local_file}.sh"
        case "powershell":
            local_file = f"{local_file}.ps1"
        case _:
            raise NotImplementedError(f"Shell type not supported: {shell}")
    return local_file

def echo(message: str, epilog: Optional[str], type_msg: str) -> None:  # previously echo
    """
    Prints a message to the console and logs it into the workspace configuration log file.

    Args:
        message (str): The message to be printed.
        epilog (Optional[str]): An optional ending message as a second argument.
        type (str): The type of message to be printed.

    Returns:
        None
    """
    fun_dict: dict[str, Callable] = MSG_OPT
    valid_filters: set[str] = set(fun_dict.keys())
    if type_msg not in valid_filters:
        raise ValueError(f"Invalid message type: {type_msg}; message type value must be one of:\n {' | '.join(valid_filters)}")
    msg: str = f"{message}\n{epilog}" if epilog else message
    if type_msg == "A":
        fun_dict[type_msg](msg, True)
    if type_msg == "T":
        fun_dict[type_msg](message, epilog)
    else:
        fun_dict[type_msg](msg)


def create_graphql_schema(schema_path: str) -> None:
    """
    Creates a GraphQL schema file in the working directory.
    """
    props_inst: AppProperties = AppProperties.get_instance()
    schema_abs: str = os.path.abspath(schema_path)
    # verify that the schema path exists and is a directory
    if not os.path.isdir(schema_abs):
        raise NotADirectoryError(f"Schema path is not a directory: {schema_abs}")
    # verify that the schema path is not empty
    if not os.listdir(schema_abs):
        raise FileNotFoundError(f"Schema path is empty: {schema_abs}")
    output_file: str = props_inst.retrieve_property("graphql_schema_file")
    # if the schema file already exists, delete it
    if os.path.exists(output_file):
        os.remove(output_file)

    create_schema(schema_abs, output_file)


def initial_load(override: bool) -> None:  # previously initialLoad
    """
    Initializes the configuration system by creating a local config file if it doesn't exist,
    then loads its contents into the environment.

    Args:
        override (bool): A boolean value to override the current gradle version.
    """
    props_inst: AppProperties = AppProperties.get_instance()
    local_file = get_local_file()
    if not os.path.exists(local_file) or override:
        shell = props_inst.retrieve_property("shell")
        contents: str = "# This file is used to store local configurations for the project.\n"
        contents += "# You can add custom functions and configurations here.\n"
        match shell:
            case "bash" | "zsh":
                contents += "example() {\n    set_env msg 'Hello, World!'\n}\nexport SOME_VAR='some value'\n"
            case "powershell":
                contents = "function example {\n    set_env msg 'Hello, World!'\n}\n$env:SOME_VAR = 'some value'\n"
            case _:
                return
        with open(local_file, "w", encoding="utf-8") as file:
            file.write(contents)


def set_gradle_version(override: bool) -> None:  # previously gradleSet
    """
    Sets the gradle version for the project.

    Args:
        override (bool): A boolean value to override the current gradle version.
    """
    props_inst: AppProperties = AppProperties.get_instance()
    workspace_file: str = props_inst.retrieve_property("workspace_file")
    working_path: str = props_inst.retrieve_property("working_path")
    local_file = get_local_file()
    shell = props_inst.retrieve_property("shell")
    gradle_set(workspace_file, working_path, local_file, shell, override)


def set_java_version(override: bool) -> None:  # previously javaSet
    """
    Sets the java version for the project.

    Args:
        override (bool): A boolean value to override the current java version.
    """
    props_inst: AppProperties = AppProperties.get_instance()
    workspace_file: str = props_inst.retrieve_property("workspace_file")
    working_path: str = props_inst.retrieve_property("working_path")
    local_file = get_local_file()
    shell = props_inst.retrieve_property("shell")
    java_set(workspace_file, working_path, local_file, shell, override)


def gcloud_login_env(project: Optional[str], type_login: str) -> None:
    """
    Logs into the gcloud account.

    Returns:
        None
    """
    valid_filters: set[str] = set(GCLOUD_LOGGIN_OPT.keys())
    if type_login not in valid_filters:
        raise ValueError(f"Invalid loggin type: {type_login}; logging type value must be one of:\n {' | '.join(valid_filters)}")
    # checking if gcloud is installed
    exit_status: int = os.system("gcloud --version")
    if exit_status == 0:
        ws_advice("gcloud is installed and the version command ran successfully.")
    else:
        raise RuntimeError("There was an error running the gcloud version command.")
    gcloud_login(type_login, project)


def setting_workspace() -> None:  # previously untrackGradleProps
    """
    Sets the workspace for the project.

    Returns:
        None
    """
    pass
