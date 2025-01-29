"""This module provides functions to set a specific Java version as the default version on the workspace."""

import os
import platform
import re
import json
import shutil
from typing import Any, Optional
import typing
import jq
import click
from codename_snake.config_environment.util import get_local_file, update_workspace, get_version_number
from codename_snake.config_environment.models.tools_version import (
    ToolVersion,
    select_version,
    set_version_environment,
    set_version_path_for_query,
    find_local_tool_home,
)
from codename_snake.util.util import run_operation, load_json_with_comments
from codename_snake.util.props import get_property
from codename_snake.util.formatting import ws_info, ws_success, ws_advice, ws_warning


@click.command(
    name="setJava",
    short_help="Sets the default Java version on the workspace",
    help="Sets the default Java version on the workspace",
    epilog="""usage: snake setJava [OPTIONS]\n
    OPTIONS:\n
        -o | --override: Optional[bool] - Override the current Java version\n
    """,
)
@click.option("--override", "-o", is_flag=True, help="Override the current Java version")
def set_java_version(override: bool) -> None:
    """
    Calls the execute function to set the Java version for the project.

    Args:
        override (bool): A boolean value to override the current java version.
    """
    workspace_file: str = get_property("workspace_file")
    execute(override, workspace_file)


def execute(override: bool, workspace_file: str) -> None:
    """
    Sets the java version for the project.

    Args:
        override (bool): A boolean value to override the current java version.
        workspace_file (str): Path to the workspace settings file
    """
    working_path: str = get_property("working_path")
    resources_path: str = get_property("resources_path")
    local_file = get_local_file()
    shell = get_property("shell")
    _java_set(workspace_file, working_path, local_file, shell, override)
    _add_java_formatter(workspace_file, resources_path)


OS = platform.system()
OS_MAP = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}
ENV_VARIABLE = f"terminal.integrated.env.{OS_MAP[OS]}"
JAVA_JQ_QUERY = f'.settings["{ENV_VARIABLE}"].JAVA_HOME'
JAVA_RUNTIME_QUERY = '.settings.["java.configuration.runtimes"]'
JAVA_RUNTIME_PATH = (
    f"{JAVA_RUNTIME_QUERY} | map(select(.default == true)) | if length == 1 then .[0].path else null end"
)
JAVA_FORMAT_QUERY = '.settings["java.format.settings.url"]'
JAVA_GRADLEHOME_QUERY = '.settings["java.import.gradle.java.home"]'


class JavaVersion(ToolVersion):
    """JavaVersion class represents a Java installation.

    Attributes:
        version (str): The Java version number
        path (str): Installation path
        description (str): Additional description/details
    """

    description: str
    _id_counter: int = 0

    def __init__(self, version: str, path: str, description: str) -> None:
        super().__init__(version, path)
        self.description = description

    def __str__(self) -> str:
        return (
            f"Id: {self.id}\n\tJava Version: {self.version}\n\tpath: {self.path}\n\tDescription: {self.description}\n"
        )


def _java_set(workspace_file: str, working_path: str, local_file: str, shell: str, override: bool) -> None:
    """
    Configures the Java version to be used in the workspace.

    Args:
        workspace_file (str): Path to the workspace settings file
        working_path (str): Path to create a temporary file
        local_file (str): Path to the local settings file
        shell (str): The shell to use for setting the Java version
    """
    versions: list[JavaVersion] = _get_versions()
    if not versions:
        ws_warning("No Java versions found on the system. Please install a valid Java version")
        return

    json_data: Any = load_json_with_comments(workspace_file)
    version = _determine_java_version(versions, json_data, local_file, shell, override)

    if not version:
        ws_info("Selecting Java version to set as default on the workspace")
        version = typing.cast(JavaVersion, select_version(typing.cast(list[ToolVersion], versions)))
        version.default = True

    _update_configurations(versions, json_data, workspace_file, working_path, local_file, shell)
    ws_success(f"Java version {version.version} set as default on the workspace")


def _determine_java_version(
    versions: list[JavaVersion], json_data: Any, local_file: str, shell: str, override: bool
) -> Optional[JavaVersion]:
    """
    Determines which Java version to use based on existing configurations.

    Returns:
        Optional[JavaVersion]: The determined version or None if need to select new one
    """
    if override:
        return None

    version_environment = _find_version_by_query(versions, json_data, JAVA_JQ_QUERY)
    version_runtime = _find_version_from_runtime(versions, json_data)
    version_local = _find_version_from_local(versions, local_file, shell)
    version_gradlehome = _find_version_by_query(versions, json_data, JAVA_GRADLEHOME_QUERY)

    versions_found: set[JavaVersion] = {
        v for v in [version_environment, version_runtime, version_local, version_gradlehome] if v
    }

    if not versions_found:
        ws_info("No Java version found in the workspace settings. Please select a valid version")
        return None

    if len(versions_found) == 1:
        version = versions_found.pop()
        version.default = True
        ws_info(f"Java version {version.version} found in the local settings")
        return version

    ws_warning("Multiple Java versions found in different settings. Please select a valid version")
    return None


def _find_version_by_query(versions: list[JavaVersion], json_data: Any, query: str) -> Optional[JavaVersion]:
    """Find version from JSON data using jq query."""
    result: Optional[str] = jq.compile(query).input(json_data).first()
    return next((v for v in versions if v.path == result), None)


def _find_version_from_runtime(versions: list[JavaVersion], json_data: Any) -> Optional[JavaVersion]:
    """Find version from runtime configuration."""
    if jq.compile(JAVA_RUNTIME_QUERY).input(json_data).first():
        result = jq.compile(JAVA_RUNTIME_PATH).input(json_data).first()
        if result:
            return next((v for v in versions if v.path == result), None)
    return None


def _find_version_from_local(versions: list[JavaVersion], local_file: str, shell: str) -> Optional[JavaVersion]:
    """Find version from local configuration file."""
    result = find_local_tool_home(local_file, shell, "JAVA_HOME")
    if result:
        return next((v for v in versions if v.path == result), None)
    return None


def _update_configurations(
    versions: list[JavaVersion], json_data: Any, workspace_file: str, working_path: str, local_file: str, shell: str
) -> None:
    """Update all configuration files with the selected version."""
    temp_file = f"{working_path}/java_versions.json"

    # Update JSON configuration
    json_data = _set_version_runtime(versions, json_data)
    json_data = set_version_environment(typing.cast(list[ToolVersion], versions), json_data, JAVA_JQ_QUERY)
    json_data = set_version_path_for_query(typing.cast(list[ToolVersion], versions), json_data, JAVA_GRADLEHOME_QUERY)
    update_workspace(json_data, temp_file, workspace_file)

    # Update local configuration
    version: Optional[JavaVersion] = next((v for v in versions if v.default), None)
    assert version, "Default Java version not found in the list of Java versions. This is a bug."
    _set_version_local_config(version, local_file, shell)


def _set_version_local_config(version: JavaVersion, local_parh: str, shell: str) -> None:
    """
    The provided version is set as the default version in the local settings file.

    Args:
        version (JavaVersion): The Java version to set as default
        local_parh (str): Path to the local settings file
        shell (str): The shell to use for setting the Java version
    """
    if os.path.exists(local_parh):
        new_line_java: str
        new_line_update_path: str
        with open(local_parh, "r", encoding="utf-8") as file:
            local_file_data = file.read()
        match shell:
            case "powershell":
                local_file_data = re.sub(r"^\s*\$env:JAVA_HOME\s*=.+$", "\n", local_file_data, flags=re.MULTILINE)
                local_file_data = re.sub(
                    r"^\s*\$env:PATH\s*=\s*\"\$env:JAVA_HOME\\bin:\$env:PATH\"$",
                    "\n",
                    local_file_data,
                    flags=re.MULTILINE,
                )
                new_line_java = f'$env:JAVA_HOME = "{version.path}"'
                new_line_update_path = '$env:PATH = "$env:JAVA_HOME\\bin:$env:PATH"'
            case "bash" | "zsh":
                local_file_data = re.sub(r"^\s*export JAVA_HOME=.+$", "\n", local_file_data, flags=re.MULTILINE)
                local_file_data = re.sub(
                    r"^\s*export PATH=\$JAVA_HOME/bin:\$PATH$", "\n", local_file_data, flags=re.MULTILINE
                )
                new_line_java = f"export JAVA_HOME='{version.path}'"
                new_line_update_path = "export PATH=$JAVA_HOME/bin:$PATH"
            case _:
                raise NotImplementedError(f"{shell} not supported for setting Java version")
        local_file_data = local_file_data.replace("\n\n", "")
        with open(local_parh, "w", encoding="utf-8") as file:
            file.write(f"{new_line_java}\n{new_line_update_path}\n{local_file_data}")
        ws_success(f"Java version {version.version} stored in local settings as default")
    else:
        ws_advice(
            f"Local settings file not found at {local_parh}. Java version {version.version} not set as default here"
        )


def _set_version_runtime(versions: list[JavaVersion], json_data: Any) -> str:
    """
    The provided version is set as the default version on the workspace.

    Args:
        versions (JavaVersion): List of Java versions
        json_data (dict): Workspace settings data
    """
    # deleting the whole runtime list
    jq_query = f"{JAVA_RUNTIME_QUERY} = []"
    updated_json_data = jq.compile(jq_query).input(json_data).first()
    # adding each version to the list of runtimes
    for v in versions:
        vers_pattern: str = r"(\d+).*"
        java_version: Optional[re.Match[str]] = re.match(vers_pattern, v.version)
        if not java_version:
            raise RuntimeError(f"Failed to extract the Java version from {v.version}")
        java_name: str
        if java_version.group(1) == "1":
            vers_pattern = r"(1\.\d).*"
            java_version = re.match(vers_pattern, v.version)
            if not java_version:
                raise RuntimeError(f"Failed to extract the Java version from {v.version}")
        java_name = f"JavaSE-{java_version.group(1)}"
        jq_query = (
            f"{JAVA_RUNTIME_QUERY} |= . + "
            f'[{{"name": "{java_name}", "path": "{v.path}", "default": {str(v.default).lower()}}}]'
        )
        updated_json_data = jq.compile(jq_query).input(updated_json_data).first()
    if not updated_json_data:
        raise RuntimeError("Failed to set Java version in workspace settings")
    return updated_json_data


def _get_versions() -> list[JavaVersion]:
    """Get Java versions installed on the system.

    Returns:
        list[JavaVersion]: List of JavaVersion objects
    """
    version_list: list[JavaVersion] = []
    if OS == "Windows":
        # ToDO: Implement Windows version
        raise NotImplementedError("Windows version pending implementation")
    if OS == "Linux":
        # ToDO: Implement Linux version
        raise NotImplementedError("Linux version pending implementation")
    if OS == "Darwin":
        versions: str = run_operation("/usr/libexec/java_home -V 2>&1", "Getting Java versions").stdout.strip()
        matches = re.findall(r"^\s*([0-9\._]+)\s+(.+\")\s*(/.+$)", versions, re.MULTILINE)
        # order matches by version number
        matches = sorted(matches, key=lambda x: get_version_number(x[0].strip()), reverse=True)
        version_list = [
            JavaVersion(version=version[0].strip(), path=version[2].strip(), description=version[1].strip())
            for version in matches
        ]
    return version_list


def _add_java_formatter(workspace_file: str, resources_path: str) -> None:
    """Add Java formatter xml to the vscode folder"""
    formatter_path: str = f"{resources_path}/java-formatter.xml"
    assert os.path.exists(
        formatter_path
    ), f"Java formatter file not found at {formatter_path}. Its supposed to be in the resources folder. This is a bug."
    vscode_path: str = f"{os.getcwd()}/.vscode"
    if not os.path.exists(vscode_path):
        os.makedirs(vscode_path, exist_ok=True)
        ws_success(f"Created .vscode folder at {vscode_path}")
    local_formatter_path: str = f"{vscode_path}/java-formatter.xml"
    json_data: Any = load_json_with_comments(workspace_file)
    result: Optional[str] = jq.compile(JAVA_FORMAT_QUERY).input(json_data).first()
    if result:
        ws_info(f"Java formatter file already set in the workspace settings at {result}")
    else:
        jq_query = f"{JAVA_FORMAT_QUERY} = {json.dumps(local_formatter_path)}"
        updated_json_data: Optional[str] = jq.compile(jq_query).input(json_data).first()
        if not updated_json_data:
            raise RuntimeError("Failed to set Java formatter in workspace settings")
        temp_file = f"{vscode_path}/java_formatter.json"
        update_workspace(updated_json_data, temp_file, workspace_file)
    if os.path.exists(local_formatter_path):
        ws_info(f"Java formatter file already exists at {local_formatter_path}")
        return
    ws_info(f"Copying Java formatter file from {formatter_path} to {local_formatter_path}")
    shutil.copyfile(formatter_path, local_formatter_path)
    ws_success(f"Java formatter file copied to {local_formatter_path}")
