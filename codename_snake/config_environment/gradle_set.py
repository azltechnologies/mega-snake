"""This module provides functions to set a specific Gradle version as the default version on the workspace."""

import os
import platform
import re
import json
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
    name="setGradle",
    short_help="Sets the default Gradle version on the workspace",
    help="Sets the default Gradle version on the workspace",
    epilog="""usage: snake setGradle [OPTIONS]\n
    OPTIONS:\n
        -o | --override: Optional[bool] - Override the current Gradle version\n
    """,
)
@click.option("--override", "-o", is_flag=True, help="Override the current Gradle version")
def set_gradle_version(override: bool) -> None:  # previously gradleSet
    """
    Calls the execute function to set the Gradle version on the workspace.

    Args:
        override (bool): A boolean value to override the current gradle version.
    """
    workspace_file: str = get_property("workspace_file")
    execute(override, workspace_file)


def execute(override: bool, workspace_file: str) -> None:
    """
    Sets the gradle version for the project.

    Args:
        override (bool): A boolean value to override the current gradle version.
        workspace_file (str): Path to the workspace settings file
    """
    working_path: str = get_property("working_path")
    local_file = get_local_file()
    shell = get_property("shell")
    _gradle_set(workspace_file, working_path, local_file, shell, override)


OS = platform.system()
OS_MAP = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}
ENV_VARIABLE = f"terminal.integrated.env.{OS_MAP[OS]}"
GRADLE_HOME_QUERY = '.settings["java.import.gradle.home"]'
GRADLE_JQ_QUERY = f'.settings["{ENV_VARIABLE}"].GRADLE_HOME'
GRADLE_WRAPPER_QUERY = '.settings["java.import.gradle.wrapper.enabled"]'


class GradleVersion(ToolVersion):
    """GradleVersion class represents a Gradle installation.

    Attributes:
        version (str): The Gradle version number
        path (str): Installation path
    """

    _id_counter: int = 0  # Class variable to keep track of the count

    def __str__(self) -> str:
        return f"Id: {self.id}\n\tGradle Version: {self.version}\n\tpath: {self.path}\n"


def _gradle_set(workspace_file: str, working_path: str, local_file: str, shell: str, override: bool) -> None:
    """
    Configures the Gradle version to be used in the workspace.

    Args:
        workspace_file (str): Path to the workspace settings file
        working_path (str): Path to create a temporary file
        local_file (str): Path to the local settings file
        shell (str): The shell to use for setting the Gradle version
    """
    versions: list[GradleVersion] = _get_versions()
    if not versions:
        ws_warning("No Gradle versions found on the system. Please install a valid version")
        return

    json_data: Any = load_json_with_comments(workspace_file)
    version: Optional[GradleVersion] = _determine_gradle_version(versions, json_data, local_file, shell, override)

    if not version:
        ws_info("Selecting Gradle version to set as default on the workspace")
        version = typing.cast(GradleVersion, select_version(typing.cast(list[ToolVersion], versions)))
        version.default = True

    _update_configurations(versions, json_data, workspace_file, working_path, local_file, shell)
    ws_success(f"Gradle version {version.version} set as default on the workspace")


def _determine_gradle_version(versions: list[GradleVersion], json_data: Any, local_file: str, shell: str, override: bool) -> Optional[GradleVersion]:
    """
    Determines which Gradle version to use based on existing configurations.

    Returns:
        Optional[GradleVersion]: The determined version or None if need to select new one
    """
    if override:
        return None

    version_environment = _find_version_by_query(versions, json_data, GRADLE_JQ_QUERY)
    version_home = _find_version_by_query(versions, json_data, GRADLE_HOME_QUERY)
    version_local = _find_version_from_local(versions, local_file, shell)

    versions_found: set[GradleVersion] = {v for v in [version_home, version_local, version_environment] if v}

    if not versions_found:
        ws_info("No Gradle version found in the workspace settings. Please select a valid version")
        return None

    if len(versions_found) == 1:
        version = versions_found.pop()
        version.default = True
        ws_info(f"Gradle version {version.version} found in the local settings")
        return version

    ws_warning("Multiple Gradle versions found in different settings. Please select a valid version")
    return None


def _find_version_by_query(versions: list[GradleVersion], json_data: Any, query: str) -> Optional[GradleVersion]:
    """Find version from JSON data using jq query."""
    result: Optional[str] = jq.compile(query).input(json_data).first()
    return next((v for v in versions if v.path == result), None)


def _find_version_from_local(versions: list[GradleVersion], local_file: str, shell: str) -> Optional[GradleVersion]:
    """Find version from local configuration file."""
    result = find_local_tool_home(local_file, shell, "GRADLE_HOME")
    if result:
        return next((v for v in versions if v.path == result), None)
    return None


def _update_configurations(
    versions: list[GradleVersion], json_data: Any, workspace_file: str, working_path: str, local_file: str, shell: str
) -> None:
    """Update all configuration files with the selected version."""
    temp_file = f"{working_path}/gradle_versions.json"

    # Update JSON configuration
    json_data = set_version_path_for_query(typing.cast(list[ToolVersion], versions), json_data, GRADLE_HOME_QUERY)
    json_data = set_version_environment(typing.cast(list[ToolVersion], versions), json_data, GRADLE_JQ_QUERY)
    _workspace_update(json_data, temp_file, workspace_file)

    # Update local configuration
    version: Optional[GradleVersion] = next((v for v in versions if v.default), None)
    assert version, "Default Gradle version not found in the list of Gradle versions. This is a bug"
    _set_version_local_config(version, local_file, shell)


def _workspace_update(json_data: Any, temp_path: str, workspace_file: str) -> None:
    """
    Updates the workspace settings file with the selected Gradle version.

    Args:
        json_data (Any): Workspace settings data
        temp_path (str): Path to the temporary file
        workspace_parh (str): Path to the workspace settings file
    """
    jq_query = f"{GRADLE_WRAPPER_QUERY} = {json.dumps(False)}"
    updated_json_data = jq.compile(jq_query).input(json_data).first()
    update_workspace(updated_json_data, temp_path, workspace_file)


def _set_version_local_config(version: GradleVersion, local_parh: str, shell: str) -> None:
    """
    The provided version is set as the default version in the local settings file.

    Args:
        version (GradleVersion): The Gradle version to set as default
        local_parh (str): Path to the local settings file
        shell (str): The shell to use for setting the Gradle version
    """
    if os.path.exists(local_parh):
        new_line_gradle: str
        new_line_update_path: str
        with open(local_parh, "r", encoding="utf-8") as file:
            local_file_data = file.read()
        match shell:
            case "powershell":
                local_file_data = re.sub(r"^\s*\$env:GRADLE_HOME\s*=.+$", "\n", local_file_data, flags=re.MULTILINE)
                local_file_data = re.sub(r"^\s*\$env:PATH\s*=\s*\"\$env:GRADLE_HOME\\bin:\$env:PATH\"$", "\n", local_file_data, flags=re.MULTILINE)
                new_line_gradle = f'$env:GRADLE_HOME = "{version.path}"'
                new_line_update_path = '$env:PATH = "$env:GRADLE_HOME\\bin:$env:PATH"'
            case "bash" | "zsh":
                local_file_data = re.sub(r"^\s*export GRADLE_HOME=.+$", "\n", local_file_data, flags=re.MULTILINE)
                local_file_data = re.sub(r"^\s*export PATH=\$GRADLE_HOME/bin:\$PATH$", "\n", local_file_data, flags=re.MULTILINE)
                new_line_gradle = f"export GRADLE_HOME='{version.path}'"
                new_line_update_path = "export PATH=$GRADLE_HOME/bin:$PATH"
            case _:
                raise NotImplementedError(f"{shell} not supported for setting Gradle version")
        local_file_data = local_file_data.replace("\n\n", "")
        with open(local_parh, "w", encoding="utf-8") as file:
            file.write(f"{new_line_gradle}\n{new_line_update_path}\n{local_file_data}")
        ws_success(f"Gradle version {version.version} stored in local settings as default")
    else:
        ws_advice(f"Local settings file not found at {local_parh}. Gradle version {version.version} not set as default here")


def _get_versions() -> list[GradleVersion]:
    """Get Gradle versions installed on the system.

    Returns:
        list[GradleVersion]: List of GradleVersion objects
    """
    version_list: list[GradleVersion] = []
    if OS == "Windows":
        # ToDO: Implement Windows version
        raise NotImplementedError("Windows version pending implementation")
    if OS == "Linux":
        # ToDO: Implement Linux version
        raise NotImplementedError("Linux version pending implementation")
    if OS == "Darwin":
        versions: str = run_operation("find $(brew --cellar) -type d -depth 2 2>/dev/null | grep gradle", "Getting Gradle versions").stdout.strip()
        matches = re.findall(r"(^.*/([0-9\._]+))$", versions, re.MULTILINE)
        # order matches by version number
        matches = sorted(matches, key=lambda x: get_version_number(x[1].strip()), reverse=True)
        version_list = [GradleVersion(version=version[1].strip(), path=version[0].strip() + "/libexec") for version in matches]
    return version_list
