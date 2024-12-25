""" This module contains utility functions for the configuration environment. """

from dataclasses import dataclass, field
import os
from typing import Any, Optional
import json
import jq
from py.util.util import get_validated_input
from py.util.formatting import ws_advice
from py.util.props import AppProperties


@dataclass(unsafe_hash=True)
class ToolVersion:
    """ToolVersion class represents a Tool installation.

    Attributes:
        version (str): The Tool version number
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


def get_local_file() -> str:
    """
    Returns the local configuration file path.

    Returns:
        str: The local configuration file path.
    """
    props_inst: AppProperties = AppProperties.get_instance()
    shell = props_inst.retrieve_property("shell")
    local_file: str = props_inst.retrieve_property("local_config_file")
    match shell:
        case "bash" | "zsh":
            local_file = f"{local_file}.sh"
        case "powershell":
            local_file = f"{local_file}.ps1"
        case _:
            raise NotImplementedError(f"Shell type not supported: {shell}")
    return local_file


def update_workspace(json_data: Any, temp_path: str, workspace_file: str) -> None:
    """
    Updates the workspace settings file with the selected Tool version.

    Args:
        json_data (Any): Workspace settings data
        temp_path (str): Path to the temporary file
        workspace_parh (str): Path to the workspace settings file
    """
    if not json_data:
        raise RuntimeError("Failed to set Tool version in workspace settings")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(json_data, file, indent=2)
    ws_advice(f"attemping to replace {workspace_file} with {temp_path}")
    try:
        os.replace(temp_path, workspace_file)
    except OSError as e:
        raise OSError(f"Failed to replace {workspace_file} with {temp_path} while setting Tool version") from e
    ws_advice(f"{temp_path} deleted after successful replacement")


def get_version_number(version: str) -> float:
    """Convert version string to numeric value for sorting.

    Returns:
        float: Numeric version value
    """
    parts = version.split(".")
    if len(parts) >= 2:
        return float(f"{parts[0]}.{parts[1]}")
    return float(parts[0])


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


def set_version_environment(versions: list[ToolVersion], json_data: dict, tool_jq_query: str) -> str:
    """
    The provided version is set as the default version on the workspace.

    Args:
        versions (ToolVersion): List of Tool versions
        json_data (dict): Workspace settings data
        tool_jq_query (str): JQ query to set the Tool version

    Returns:
        str: Updated JSON data
    """
    vers: Optional[ToolVersion] = next((v for v in versions if v.default), None)
    if not vers:
        raise RuntimeError("Default Tool version not found in the list of Tool versions")
    jq_query = f"{tool_jq_query} = {json.dumps(str(vers.path))}"
    updated_json_data: Optional[str] = jq.compile(jq_query).input(json_data).first()
    if not updated_json_data:
        raise RuntimeError("Failed to set Tool version in workspace settings")
    return updated_json_data
