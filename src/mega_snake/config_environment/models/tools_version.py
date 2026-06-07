"""This module contains utility functions for the configuration environment."""

from dataclasses import dataclass, field
from typing import Optional
import os
import platform
import re
import json
import jq
from mega_snake.util.util import get_validated_input
from mega_snake.util.formatting import ws_advice, ws_success, ws_warning, ws_info

OS = platform.system()
OS_MAP = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}


def verify_os() -> None:
    """Verify if the OS is supported."""
    if OS not in OS_MAP:
        raise NotImplementedError(f"Unsupported OS: {OS}")


verify_os()


class VersionSetException(Exception):
    """Custom exception to terminate execution."""


@dataclass(unsafe_hash=True)
class ToolVersion:
    """ToolVersion class represents a Tool installation.

    Attributes:
        version (str): The Tool version number
        path (str): Installation path
    """

    version: str
    _path: str
    default: bool = field(default=False)
    id: int = field(init=False)

    @property
    def path(self) -> str:
        """Get the installation path with normalized slashes."""
        return self._path.replace("\\", "/")

    @path.setter
    def path(self, value: str) -> None:
        self._path = value

    _id_counter: int = 0  # Class variable to keep track of the count

    def __post_init__(self) -> None:
        """Assign the next sequential ID to this instance."""
        type(self)._id_counter += 1
        self.id = type(self)._id_counter


def select_version(versions: list[ToolVersion]) -> ToolVersion:
    """
    Prompts the user to select a valid Tool version from the list of available versions.

    Args:
        versions (list[ToolVersion]): List of ToolVersion objects

    Returns:
        ToolVersion: The selected Tool version
    """
    if not versions:
        raise RuntimeError("No Tool versions found")
    version_list: list[str] = [str(v.id) for v in versions]
    prompt = "Select a Tool version to set as default on the workspace"
    prompt += "\nAvailable versions:\n"
    for v in versions:
        prompt += f"{v}"
    prompt += "\nSelect a version by entering its Id"
    selection: str = get_validated_input(prompt, version_list)
    version = next((v for v in versions if v.id == int(selection)), None)
    if not version:
        raise RuntimeError(f"Tool version with id {selection} not found")
    return version


def set_version_path_for_query(versions: list[ToolVersion], json_data: dict, tool_jq_query: str) -> Optional[str]:
    """
    The provided version is set as the default version on the workspace.

    Args:
        versions (ToolVersion): List of Tool versions
        json_data (dict): Workspace settings data
        tool_jq_query (str): JQ query to set the Tool version

    Returns:
        str: Updated JSON data
    """
    vers_list: list[ToolVersion] = [v for v in versions if v.default]
    if not vers_list:
        raise RuntimeError("Default Tool version not found in the list of Tool versions")
    if len(vers_list) > 1:
        raise RuntimeError("Multiple default Tool versions found in the list of Tool versions")
    vers: ToolVersion = vers_list[0]
    jq_query = f"{tool_jq_query} = {json.dumps(str(vers.path))}"
    updated_json_data: Optional[str] = jq.compile(jq_query).input(json_data).first()
    return updated_json_data


def find_local_tool_home(path: str, shell: str, var: str) -> Optional[str]:
    """Find the Tool in the local settings file.

    Args:
        path (str): Path to the local settings file
        shell (str): The shell to use for setting the Tool version

    Returns:
        str: Tool path
    """
    # Check if the local settings file exists
    if not os.path.exists(path):
        ws_advice(f"Local settings file not found at {path}")
        return None
    with open(path, "r", encoding="utf-8") as file:
        local_file_data = file.read()
    if local_file_data:
        match shell:
            case "powershell" | "pwsh":
                matches = re.findall(rf"\s*\$env:{var}\s*=\s*(.+)\s*", local_file_data)
                if matches:
                    return matches[0].replace('"', "").replace("'", "").strip()
            case "bash" | "zsh":
                matches = re.findall(rf"\s*export {var}=(.+)\s*", local_file_data)
                if matches:
                    return matches[0].replace('"', "").replace("'", "").strip()
    return None


def set_version_local_config(version: ToolVersion, local_parh: str, shell: str, var: str) -> None:
    """
    The provided version is set as the default version in the local settings file.

    Args:
        version (ToolVersion): The Tool version to set as default
        local_parh (str): Path to the local settings file
        shell (str): The shell to use for setting the Tool version
    """
    separator: str = ";" if OS.lower() == "windows" else ":"  # Windows uses semicolon, others use colon
    path_divider: str = "\\" if OS.lower() == "windows" else "/"  # Windows uses backslash, others use forward slash
    if os.path.exists(local_parh):
        new_line_tool: str
        new_line_update_path: str
        with open(local_parh, "r", encoding="utf-8") as file:
            local_file_data = file.read()
        match shell:
            case "powershell" | "pwsh":
                pattern = rf"^\s*\$env:{var}\s*=.+$"
                local_file_data = re.sub(pattern, "\n", local_file_data, flags=re.MULTILINE)
                pattern = rf"^\s*\$env:PATH\s*=\s*\"\$env:{var}\{path_divider}bin\{separator}\$env:PATH\"\s*$"
                local_file_data = re.sub(pattern, "\n", local_file_data, flags=re.MULTILINE)
                new_line_tool = f'$env:{var} = "{version.path}"'
                new_line_update_path = f'$env:PATH = "$env:{var}{path_divider}bin{separator}$env:PATH"'
            case "bash" | "zsh":
                pattern = rf"^\s*export {var}=.+$"
                local_file_data = re.sub(pattern, "\n", local_file_data, flags=re.MULTILINE)
                pattern = rf'^\s*export PATH="\${var}\{path_divider}bin\{separator}\$PATH"\s*$'
                local_file_data = re.sub(pattern, "\n", local_file_data, flags=re.MULTILINE)
                new_line_tool = f"export {var}='{version.path}'"
                new_line_update_path = f'export PATH="${var}{path_divider}bin{separator}$PATH"'
            case _:
                raise NotImplementedError(f"{shell} not supported for setting Tool version")
        while "\n\n" in local_file_data:
            local_file_data = local_file_data.replace("\n\n", "\n")
        with open(local_parh, "w", encoding="utf-8") as file:
            file.write(f"{new_line_tool}\n{new_line_update_path}\n{local_file_data}")
        ws_success(f"Tool version {version.version} stored in local settings as default")
    else:
        ws_advice(
            f"Local settings file not found at {local_parh}. Tool version {version.version} not set as default here"
        )


def determine_tool_version(version_list_found: list[Optional[ToolVersion]]) -> Optional[ToolVersion]:
    """
    Determines which Tool version to use based on existing configurations.

    Returns:
        Optional[ToolVersion]: The determined version or None if need to select new one
    """
    version_set_found: set[ToolVersion] = {v for v in version_list_found if v}

    if not version_set_found:
        ws_info("No Tool version found in the workspace settings. Please select a valid version")
        return None

    if len(version_set_found) == 1:
        if version_list_found.count(None) == 0:
            raise VersionSetException("All tool version are set to the same version")
        version = version_set_found.pop()
        version.default = True
        ws_info(f"Tool version {version.version} already set")
        return version

    ws_warning("Multiple Tool versions found in different settings. Please select a valid version")
    return None
