"""This module provides functions to set a specific Gradle version as the default version on the workspace."""

import re
import json
from typing import Any, Callable, Optional
import typing
import jq
import click
from mega_snake.config_environment.util import get_local_file, update_workspace, get_version_number
from mega_snake.config_environment.models.tools_version import (
    ToolVersion,
    select_version,
    set_version_path_for_query,
    find_local_tool_home,
    set_version_local_config,
    determine_tool_version,
    OS,
    OS_MAP,
    VersionSetException,
)
from mega_snake.util.util import run_operation, load_json_with_comments
from mega_snake.util.props import get_property
from mega_snake.util.formatting import ws_info, ws_success, ws_warning


@click.command(
    name="setGradle",
    short_help="Sets the default Gradle version on the workspace",
    help="Sets the default Gradle version on the workspace",
    epilog="""usage: mgsnake setGradle [OPTIONS]\n
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
        """Return a human-readable string representation of the GradleVersion."""
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
    version_environment = _find_version_by_query(versions, json_data, GRADLE_JQ_QUERY)
    version_home = _find_version_by_query(versions, json_data, GRADLE_HOME_QUERY)
    version_local = _find_version_from_local(versions, local_file, shell)
    list_found: list[Optional[GradleVersion]] = [version_home, version_local, version_environment]
    try:
        version: Optional[ToolVersion] = (
            None if override else determine_tool_version(typing.cast(list[Optional[ToolVersion]], list_found))
        )
    except VersionSetException as e:
        ws_success(str(e))
        return
    if not version:
        ws_info("Selecting Gradle version to set as default on the workspace")
        version = select_version(typing.cast(list[ToolVersion], versions))
        version.default = True

    _update_configurations(versions, json_data, workspace_file, working_path, local_file, shell)
    ws_success(f"Gradle version {version.version} set as default on the workspace")


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
    json_data = set_version_path_for_query(typing.cast(list[ToolVersion], versions), json_data, GRADLE_JQ_QUERY)
    _workspace_update(json_data, temp_file, workspace_file)

    # Update local configuration
    version: Optional[GradleVersion] = next((v for v in versions if v.default), None)
    assert version, "Default Gradle version not found in the list of Gradle versions. This is a bug"
    set_version_local_config(version, local_file, shell, "GRADLE_HOME")


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


def _get_version_from_commnad(path: str, command: Callable[[str], str]) -> str:
    """Get Gradle version from the command output.

    Args:
        path (str): Path to the Gradle executable
    Returns:
        str: Gradle version details
    """
    output: str = run_operation(command(path), "Getting Gradle details").stdout.strip()
    return f"{path}\t{output}"


# pylint: disable=C3001
# flake8: noqa: E501
def _get_versions() -> list[GradleVersion]:
    """Get Gradle versions installed on the system.

    Returns:
        list[GradleVersion]: List of GradleVersion objects
    """
    version_list: list[GradleVersion] = []
    pattern: str = r"^(.+)\t(.+)$"

    def command_details(path: str) -> str:
        """Build the shell command to extract the Gradle version for a given installation path."""
        return f'echo "{path}/lib" | xargs ls | grep -oE "^gradle-core-[0-9\\.]+\\.jar" | sed "s:gradle-core-::" | sed "s:\\.jar::"'

    if OS == "Windows":
        command_paths = (
            'scoop list 6>&1 | Where-Object { $_.Name -like "gradle*" } | ForEach-Object { "$(scoop prefix $_.Name)" } '
        )

        def command_details(path: str) -> str:  # noqa: F811
            """Build the PowerShell command to extract the Gradle version for a given path."""
            return f"(Get-ChildItem \"{path}\\lib\\\" 6>&1 | Where-Object {{ $_.Name -match '^gradle-core-[0-9\\.]+\\.jar' }}).Name -replace 'gradle-core-', '' -replace '\\.jar', ''"

    if OS == "Linux":
        command_paths = "update-alternatives --list gradle | sed 's:/bin/gradle$::'"
    if OS == "Darwin":
        command_paths = "find $(brew --cellar) -type d -depth 2 2>/dev/null | grep gradle | sed -E 's/$/\\/libexec/'"
    paths: list[str] = run_operation(command_paths, "Getting Gradle versions").stdout.strip().splitlines()
    details: str = "\n".join(map(lambda path: _get_version_from_commnad(path, command_details), paths))
    matches = re.findall(pattern, details, re.MULTILINE)
    # order matches by version number
    matches = sorted(matches, key=lambda x: get_version_number(x[1].strip()), reverse=True)
    version_list = [GradleVersion(version=version[1].strip(), _path=version[0].strip()) for version in matches]
    return version_list
