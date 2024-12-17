"""This module provides functions to set a specific Java version as the default version on the workspace."""

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
JAVA_JQ_QUERY = f'.settings["{ENV_VARIABLE}"].JAVA_HOME'
JAVA_RUNTIME_QUERY = '.settings.["java.configuration.runtimes"]'
JAVA_RUNTIME_PATH = f"{JAVA_RUNTIME_QUERY} | map(select(.default == true)) | if length == 1 then .[0].path else null end"


@dataclass(unsafe_hash=True)
class JavaVersion:
    """JavaVersion class represents a Java installation.

    Attributes:
        version (str): The Java version number
        path (str): Installation path
        description (str): Additional description/details
    """

    version: str
    path: str
    description: str
    default: bool = field(default=False)
    id: int = field(init=False)

    _id_counter: int = 0  # Class variable to keep track of the count

    def __post_init__(self) -> None:
        type(self)._id_counter += 1
        self.id = type(self)._id_counter

    def __str__(self) -> str:
        return f"Id: {self.id}\n\tJava Version: {self.version}\n\tpath: {self.path}\n\tDescription: {self.description}\n"


def get_version_number(version: str) -> float:
    """Convert version string to numeric value for sorting.

    Returns:
        float: Numeric version value
    """
    parts = version.split(".")
    if len(parts) >= 2:
        return float(f"{parts[0]}.{parts[1]}")
    return float(parts[0])


def java_set(workspace_file: str, working_path: str, local_file: str, shell: str, override: bool) -> None:
    """
    Configures the Java version to be used in the workspace. If the Java version is not found in the workspace settings,
    the user is prompted to select a valid version. The selected version is then set as the default version on the workspace.

    Args:
        workspace_file (str): Path to the workspace settings file
        working_path (str): Path to create a temporary file
        local_file (str): Path to the local settings file
        shell (str): The shell to use for setting the Java version
    """

    versions: list[JavaVersion] = get_versions()
    json_data: Any = load_json_with_comments(workspace_file)
    version: Optional[JavaVersion] = None
    version_local: Optional[JavaVersion] = None
    version_environment: Optional[JavaVersion] = None
    version_runtime: Optional[JavaVersion] = None
    if not override:

        # Check if the Java version is already set in the workspace settings
        result: Optional[str] = jq.compile(JAVA_JQ_QUERY).input(json_data).first()
        version_environment = next((v for v in versions if v.path == result), None)
        if jq.compile(JAVA_RUNTIME_QUERY).input(json_data).first():
            result = jq.compile(JAVA_RUNTIME_PATH).input(json_data).first()
            if result:
                version_runtime = next((v for v in versions if v.path == result), None)
        result = find_local_java_home(local_file, shell)
        if result:
            version_local = next((v for v in versions if v.path == result), None)

        versions_found: set[JavaVersion] = {v for v in [version_environment, version_runtime, version_local] if v}

        if not versions_found:
            ws_info("No Java version found in the workspace settings. Please select a valid version")
        elif len(versions_found) == 1:
            version = versions_found.pop()
            version.default = True
            ws_info(f"Java version {version.version} found in the local settings")
        else:
            version_local = None
            version_runtime = None
            version_environment = None
            ws_warning("Multiple Java versions found in different settings. Please select a valid version")

    if not version:
        ws_info("Selecting Java version to set as default on the workspace")
        version = select_version(versions)
        version.default = True
    if not version_local:
        set_version_local_config(version, local_file, shell)
    if not version_runtime or not version_environment:
        temp_file = f"{working_path}/java_versions.json"
        if not version_runtime:
            json_data = set_version_runtime(versions, json_data)
        if not version_environment:
            json_data = set_version_environment(versions, json_data)
        update_workspace(json_data, temp_file, workspace_file)
    ws_success(f"Java version {version.version} set as default on the workspace")


def select_version(versions: list[JavaVersion]) -> JavaVersion:
    """
    Prompts the user to select a valid Java version from the list of available versions.

    Args:
        versions (list[JavaVersion]): List of JavaVersion objects

    Returns:
        JavaVersion: The selected Java version
    """
    version_list: list[str] = [str(v.id) for v in versions]
    prompt = "Select a Java version to set as default on the workspace"
    prompt += "\nAvailable versions:\n"
    for v in versions:
        prompt += f"{v}"
    prompt += f"\nSelect a version by entering its Id:\n{' | '.join(version_list)}\n"
    selection: str = get_validated_input(prompt, version_list)
    version = next((v for v in versions if v.id == int(selection)), None)
    if not version:
        raise RuntimeError(f"Java version with id {selection} not found")
    return version


def set_version_local_config(version: JavaVersion, local_parh: str, shell: str) -> None:
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
                new_line_java = f'$env:JAVA_HOME = "{version.path}"'
                new_line_update_path = '$env:PATH = "$env:JAVA_HOME\\bin;$env:PATH"'
            case "bash" | "zsh":
                new_line_java = f"export JAVA_HOME='{version.path}'"
                new_line_update_path = "export PATH=$JAVA_HOME/bin:$PATH"
            case _:
                raise NotImplementedError(f"{shell} not supported for setting Java version")
        with open(local_parh, "w", encoding="utf-8") as file:
            file.write(f"{new_line_java}\n{new_line_update_path}\n{local_file_data}")
        ws_success(f"Java version {version.version} stored in local settings as default")
    else:
        ws_advice(f"Local settings file not found at {local_parh}. Java version {version.version} not set as default here")


def set_version_runtime(versions: list[JavaVersion], json_data: Any) -> str:
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
        jq_query = f'{JAVA_RUNTIME_QUERY} |= . + [{{"name": "{java_name}", "path": "{v.path}", "default": {str(v.default).lower()}}}]'
        updated_json_data = jq.compile(jq_query).input(updated_json_data).first()
    if not updated_json_data:
        raise RuntimeError("Failed to set Java version in workspace settings")
    return updated_json_data


def set_version_environment(versions: list[JavaVersion], json_data: dict) -> str:
    """
    The provided version is set as the default version on the workspace.

    Args:
        versions (JavaVersion): List of Java versions
        json_data (dict): Workspace settings data

    Returns:
        str: Updated JSON data
    """
    vers: Optional[JavaVersion] = next((v for v in versions if v.default), None)
    if not vers:
        raise RuntimeError("Default Java version not found in the list of Java versions")
    jq_query = f"{JAVA_JQ_QUERY} = {json.dumps(str(vers.path))}"
    updated_json_data: Optional[str] = jq.compile(jq_query).input(json_data).first()
    if not updated_json_data:
        raise RuntimeError("Failed to set Java version in workspace settings")
    return updated_json_data


def update_workspace(json_data: Any, temp_parh: str, workspace_file: str) -> None:
    """
    Updates the workspace settings file with the selected Java version.

    Args:
        json_data (Any): Workspace settings data
        temp_parh (str): Path to the temporary file
        workspace_parh (str): Path to the workspace settings file
    """
    if not json_data:
        raise RuntimeError("Failed to set Java version in workspace settings")
    with open(temp_parh, "w", encoding="utf-8") as file:
        json.dump(json_data, file, indent=2)
    ws_advice(f"attemping to replace {workspace_file} with {temp_parh}")
    try:
        os.replace(temp_parh, workspace_file)
    except OSError as e:
        raise OSError(f"Failed to replace {workspace_file} with {temp_parh} while setting Java version") from e
    ws_advice(f"{temp_parh} deleted after successful replacement")


def get_versions() -> list[JavaVersion]:
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
        version_list = [JavaVersion(version=version[0].strip(), path=version[2].strip(), description=version[1].strip()) for version in matches]
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


def find_local_java_home(path: str, shell: str) -> Optional[str]:
    """Find the JAVA_HOME in the local settings file.

    Args:
        path (str): Path to the local settings file
        shell (str): The shell to use for setting the Java version

    Returns:
        str: JAVA_HOME path
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
                matches = re.findall(r"^\s*\$env:JAVA_HOME\s*=\s*(.+)\s*$", local_file_data)
                if matches:
                    return matches[0].strip
            case "bash" | "zsh":
                matches = re.findall(r"^\s*export JAVA_HOME=(.+)\s*$", local_file_data)
                if matches:
                    return matches[0].strip()
    return None
