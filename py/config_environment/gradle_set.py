"""This module provides functions to set a specific Gradle version as the default version on the workspace."""

from dataclasses import dataclass, field
import os
import platform
import re
import json
from typing import Any, Optional
import jq
from jsoncomment import JsonComment
from py.util.util import run_operation, get_validated_input
from py.util.formatting import ws_info, ws_success, ws_advice, ws_warning


OS = platform.system()
OS_MAP = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}
ENV_VARIABLE = f"terminal.integrated.env.{OS_MAP[OS]}"
GRADLE_NUMBER_QUERY = '.settings["java.import.gradle.version"]'
GRADLE_HOME_QUERY = '.settings["java.import.gradle.home"]'
GRADLE_JQ_QUERY = f'.settings["{ENV_VARIABLE}"].GRADLE_HOME'
GRADLE_WRAPPER_QUERY = '.settings["java.import.gradle.wrapper.enabled"]'


@dataclass(unsafe_hash=True)
class GradleVersion:
    """GradleVersion class represents a Gradle installation.

    Attributes:
        version (str): The Gradle version number
        path (str): Installation path
    """

    version: str
    path: str
    default: bool = field(default=False)
    id: int = field(init=False)

    _id_counter: int = 0  # Class variable to keep track of the count

    def __post_init__(self) -> None:
        type(self)._id_counter += 1
        self.id = type(self)._id_counter

    def __str__(self) -> str:
        return f"Id: {self.id}\n\tGradle Version: {self.version}\n\tpath: {self.path}\n"


def get_version_number(version: str) -> float:
    """Convert version string to numeric value for sorting.

    Returns:
        float: Numeric version value
    """
    parts = version.split(".")
    if len(parts) >= 2:
        return float(f"{parts[0]}.{parts[1]}")
    return float(parts[0])


def gradle_set(workspace_file: str, working_path: str, local_file: str, shell: str, override: bool) -> None:
    """
    Configures the Gradle version to be used in the workspace. If the Gradle version is not found in the workspace settings,
    the user is prompted to select a valid version. The selected version is then set as the default version on the workspace.

    Args:
        workspace_file (str): Path to the workspace settings file
        working_path (str): Path to create a temporary file
        local_file (str): Path to the local settings file
        shell (str): The shell to use for setting the Gradle version
    """

    versions: list[GradleVersion] = get_versions()
    json_data: Any = load_json_with_comments(workspace_file)
    version: Optional[GradleVersion] = None
    version_local: Optional[GradleVersion] = None
    version_environment: Optional[GradleVersion] = None
    version_number: Optional[GradleVersion] = None
    version_home: Optional[GradleVersion] = None
    if not override:

        # Check if the Gradle version is already set in the workspace settings
        result: Optional[str] = jq.compile(GRADLE_JQ_QUERY).input(json_data).first()
        version_environment = next((v for v in versions if v.path == result), None)
        result = jq.compile(GRADLE_NUMBER_QUERY).input(json_data).first()
        version_number = next((v for v in versions if v.version == result), None)
        result = jq.compile(GRADLE_HOME_QUERY).input(json_data).first()
        version_home = next((v for v in versions if v.path == result), None)
        result = find_local_gradle_home(local_file, shell)
        if result:
            version_local = next((v for v in versions if v.path == result), None)

        versions_found: set[GradleVersion] = {v for v in [version_number, version_home, version_local, version_environment] if v}

        if not versions_found:
            ws_info("No Gradle version found in the workspace settings. Please select a valid version")
        elif len(versions_found) == 1:
            version = versions_found.pop()
            version.default = True
            ws_info(f"Gradle version {version.version} found in the local settings")
        else:
            version_local = None
            version_home = None
            version_number = None
            version_environment = None
            ws_warning("Multiple Gradle versions found in different settings. Please select a valid version")

    if not version:
        ws_info("Selecting Gradle version to set as default on the workspace")
        version = select_version(versions)
        version.default = True
    if not version_local:
        set_version_local_config(version, local_file, shell)
    if not version_home or not version_number or not version_environment:
        temp_file = f"{working_path}/gradle_versions.json"
        if not version_home:
            json_data = set_version_home(versions, json_data)
        if not version_number:
            json_data = set_version_number(versions, json_data)
        if not version_environment:
            json_data = set_version_environment(versions, json_data)
        update_workspace(json_data, temp_file, workspace_file)
    ws_success(f"Gradle version {version.version} set as default on the workspace")


def select_version(versions: list[GradleVersion]) -> GradleVersion:
    """
    Prompts the user to select a valid Gradle version from the list of available versions.

    Args:
        versions (list[GradleVersion]): List of GradleVersion objects

    Returns:
        GradleVersion: The selected Gradle version
    """
    version_list: list[str] = [str(v.id) for v in versions]
    prompt = "Select a Gradle version to set as default on the workspace"
    prompt += "\nAvailable versions:\n"
    for v in versions:
        prompt += f"{v}"
    prompt += f"\nSelect a version by entering its Id:\n{' | '.join(version_list)}\n"
    selection: str = get_validated_input(prompt, version_list)
    version = next((v for v in versions if v.id == int(selection)), None)
    if not version:
        raise RuntimeError(f"Gradle version with id {selection} not found")
    return version


def set_version_local_config(version: GradleVersion, local_parh: str, shell: str) -> None:
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
                local_file_data = re.sub(r"^\s*\$env:GRADLE_HOME\s*=.+$", "", local_file_data, flags=re.MULTILINE)
                local_file_data = re.sub(r"^\s*\$env:PATH\s*=\s*\"\$env:GRADLE_HOME\\bin:\$env:PATH\"$", "", local_file_data, flags=re.MULTILINE)
                new_line_gradle = f'$env:GRADLE_HOME = "{version.path}"'
                new_line_update_path = '$env:PATH = "$env:GRADLE_HOME\\bin:$env:PATH"'
            case "bash" | "zsh":
                local_file_data = re.sub(r"^\s*export GRADLE_HOME=.+$", "", local_file_data, flags=re.MULTILINE)
                local_file_data = re.sub(r"^\s*export PATH=\$GRADLE_HOME/bin:\$PATH$", "", local_file_data, flags=re.MULTILINE)
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


def set_version_home(versions: list[GradleVersion], json_data: Any) -> str:
    """
    The provided version is set as the default version on the workspace.

    Args:
        versions (GradleVersion): List of Gradle versions
        json_data (dict): Workspace settings data
    """
    vers: Optional[GradleVersion] = next((v for v in versions if v.default), None)
    if not vers:
        raise RuntimeError("Default Gradle version not found in the list of Gradle versions")
    # deleting the whole runtime list
    jq_query = f"{GRADLE_HOME_QUERY} = {json.dumps(str(vers.path))}"
    updated_json_data = jq.compile(jq_query).input(json_data).first()
    if not updated_json_data:
        raise RuntimeError("Failed to set Gradle version in workspace settings")
    return updated_json_data


def set_version_number(versions: list[GradleVersion], json_data: dict) -> str:
    """
    The provided version is set as the default version on the workspace.

    Args:
        versions (GradleVersion): List of Gradle versions
        json_data (dict): Workspace settings data

    Returns:
        str: Updated JSON data
    """
    vers: Optional[GradleVersion] = next((v for v in versions if v.default), None)
    if not vers:
        raise RuntimeError("Default Gradle version not found in the list of Gradle versions")
    jq_query = f"{GRADLE_NUMBER_QUERY} = {json.dumps(str(vers.version))}"
    updated_json_data: Optional[str] = jq.compile(jq_query).input(json_data).first()
    if not updated_json_data:
        raise RuntimeError("Failed to set Gradle version in workspace settings")
    return updated_json_data


def set_version_environment(versions: list[GradleVersion], json_data: dict) -> str:
    """
    The provided version is set as the default version on the workspace.

    Args:
        versions (GradleVersion): List of Gradle versions
        json_data (dict): Workspace settings data

    Returns:
        str: Updated JSON data
    """
    vers: Optional[GradleVersion] = next((v for v in versions if v.default), None)
    if not vers:
        raise RuntimeError("Default Java version not found in the list of Java versions")
    jq_query = f"{GRADLE_JQ_QUERY} = {json.dumps(str(vers.path))}"
    updated_json_data: Optional[str] = jq.compile(jq_query).input(json_data).first()
    if not updated_json_data:
        raise RuntimeError("Failed to set Java version in workspace settings")
    return updated_json_data


def update_workspace(json_data: Any, temp_parh: str, workspace_file: str) -> None:
    """
    Updates the workspace settings file with the selected Gradle version.

    Args:
        json_data (Any): Workspace settings data
        temp_parh (str): Path to the temporary file
        workspace_parh (str): Path to the workspace settings file
    """
    jq_query = f"{GRADLE_WRAPPER_QUERY} = {json.dumps(False)}"
    updated_json_data = jq.compile(jq_query).input(json_data).first()
    if not updated_json_data:
        raise RuntimeError("Failed to set Gradle version in workspace settings")
    with open(temp_parh, "w", encoding="utf-8") as file:
        json.dump(updated_json_data, file, indent=2)
    ws_advice(f"attemping to replace {workspace_file} with {temp_parh}")
    try:
        os.replace(temp_parh, workspace_file)
    except OSError as e:
        raise OSError(f"Failed to replace {workspace_file} with {temp_parh} while setting Gradle version") from e
    ws_advice(f"{temp_parh} deleted after successful replacement")


def get_versions() -> list[GradleVersion]:
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


def load_json_with_comments(file_path: str) -> dict:
    """Load a JSON file with comments.

    Args:
        file_path (str): Path to the JSON file

    Returns:
        dict: JSON data
    """
    with open(file_path, "r", encoding="utf-8") as file:
        json_str = file.read()
        parser = JsonComment(json)
        return parser.loads(json_str)


def find_local_gradle_home(path: str, shell: str) -> Optional[str]:
    """Find the GRADLE_HOME in the local settings file.

    Args:
        path (str): Path to the local settings file
        shell (str): The shell to use for setting the Gradle version

    Returns:
        str: GRADLE_HOME path
    """
    # Check if the local settings file exists
    if not os.path.exists(path):
        ws_advice(f"Local settings file not found at {path}")
        return None
    with open(path, "r", encoding="utf-8") as file:
        local_file_data = file.read()
    if local_file_data:
        match shell:
            case "powershell":
                matches = re.findall(r"^\s*\$env:GRADLE_HOME\s*=\s*(.+)\s*$", local_file_data)
                if matches:
                    return matches[0].strip
            case "bash" | "zsh":
                matches = re.findall(r"^\s*export GRADLE_HOME=(.+)\s*$", local_file_data)
                if matches:
                    return matches[0].strip()
    return None
