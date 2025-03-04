""" This module contains utility functions for the configuration environment. """

import os
from typing import Any
import json
from codename_snake.util.formatting import ws_advice
from codename_snake.util.props import get_property


def get_local_file() -> str:
    """
    Returns the local configuration file path.

    Returns:
        str: The local configuration file path.
    """
    shell = get_property("shell")
    local_file: str = get_property("local_config_file")
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


def get_version_number(s_str: str) -> int:
    """Convert version string to numeric value for sorting.

    Returns:
        int: Numeric value of the version string
    """
    arr_s = s_str.split(".")
    # Remove any non-numeric characters
    arr_s = ["".join(filter(str.isdigit, s)) for s in arr_s]
    arr_s = arr_s + ["0"] * (3 - len(arr_s)) if len(arr_s) < 3 else arr_s
    i_s = int(arr_s[0]) * 100 + int(arr_s[1]) * 10 + int(arr_s[2])
    return i_s
