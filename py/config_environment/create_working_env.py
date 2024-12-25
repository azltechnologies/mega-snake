""" This module contains the functions for setting the workspace for the project. """

import os
from pathlib import Path
import shutil
import json
import re
from typing import Any, Optional
import click
import jq
from py.constants import APP_NAME
from py.util.props import AppProperties
from py.util.formatting import ws_success
from py.config_environment.util import get_local_file, update_workspace
from py.config_environment.java_set import execute as set_java
from py.config_environment.gradle_set import execute as set_gradle, set_gradle_version as gradle_command
from py.config_environment.local_config import execute as initial_load
from py.util.formatting import ws_advice, ws_info, ws_warning
from py.util.util import get_command_return_code, get_validated_input, cli_metadata, get_main_branch, get_remote_url, load_json_with_comments


@click.command(
    name="createWorkingEnv",
    short_help="Sets the default Java version on the workspace",
    help="Sets the default Java version on the workspace",
    epilog="""usage: set_env setJava [OPTIONS]\n
    OPTIONS:\n
        -o | --override: Optional[bool] - Override the current Java version\n
    """,
)
@cli_metadata(flags={"skip"})
def create_working_env() -> None:  # previously untrackGradleProps
    """
    Sets the workspace for the project.

    Returns:
        None
    """
    git_repo: bool = True
    if not shutil.which("git"):
        git_repo = False
        if get_validated_input("Git is not installed. Would you like to configure the workspace without git?", ["y", "n"]).lower() == "n":
            ws_warning("Git is required to configure the workspace. Exiting...")
            return
    else:
        if get_command_return_code("git rev-parse --is-inside-work-tree") != 0:
            git_repo = False
            if get_validated_input("Not inside a git repository. Would you like to configure the workspace anyway?", ["y", "n"]).lower() == "n":
                ws_warning("Not inside a git repository. Exiting...")
                return

    workspace_file: str = get_workspace_file()
    working_path: str = get_working_path()
    if git_repo:
        git_exclude(working_path)
    initial_load(False)
    set_java(False, workspace_file)
    # verifying if build.gradle or build.gradle.kts exists
    build_file: str = f"{os.getcwd()}/build.gradle"
    build_kts_file: str = f"{os.getcwd()}/build.gradle.kts"
    if not os.path.exists(build_file) and not os.path.exists(build_kts_file):
        ws_warning(
            f"build.gradle or build.gradle.kts file not found in the current directory. "
            f"Please run '{gradle_command.name}' command if you want to set the gradle version anyway."
        )
    else:
        set_gradle(False, workspace_file)
    add_default_settings(workspace_file, working_path)


FOLDER = os.path.basename(os.getcwd())
GIT_BLAME_QUERY = '.settings.["git-blame.gitWebUrl"]'


def get_workspace_file() -> str:
    """
    Gets the workspace file for the project. If not found, creates a new one.

    Returns:
        str - The workspace file path
    """
    workspace_file: str = AppProperties.get_instance().retrieve_property("workspace_file")
    if workspace_file:
        ws_info(f"Vscode workspace file found: {workspace_file}")
        return workspace_file
    ws_warning("Vscode workspace file not found in current directory")
    if get_validated_input("Would you like to create a new default workspace file?", ["y", "n"]).lower() == "n":
        raise RuntimeError("Vscode workspace file is required to configure the working environment. Exiting...")
    else:
        workspace_content: dict[str, Any] = {"folders": [{"name": "main", "path": "."}], "settings": {}}
        workspace_file = f"{os.getcwd()}/{FOLDER}.code-workspace"
        with open(workspace_file, "w", encoding="utf-8") as file:
            json.dump(workspace_content, file, indent=4)
        ws_success(f"Vscode workspace file created at {workspace_file}")
        return workspace_file


def get_working_path() -> str:
    """
    Gets the working path for the project. If not found, creates a new one.

    Returns:
        str - The working path
    """
    working_path: str = AppProperties.get_instance().retrieve_property("working_path")
    assert working_path, "Working path is required to configure the working environment, but not found in the properties. This is a bug."
    assert Path(working_path).resolve().is_relative_to(Path.cwd().resolve()), "Working path is not in the current directory. This is a bug."
    if os.path.exists(working_path):
        ws_info(f"Working path found: {working_path}")
        return working_path
    ws_warning("Working path not found in current directory")
    if get_validated_input("Would you like to create a new default working path?", ["y", "n"]).lower() == "n":
        raise RuntimeError("Working path is required to configure the working environment. Exiting...")
    else:
        os.makedirs(working_path, exist_ok=True)
        ws_success(f"Working path created at {working_path}")
        return working_path


def git_exclude(working_path: str) -> None:
    """
    Excludes the .vscode folder and the working path from git.
    """
    working_path = os.path.basename(working_path)
    ex_file: str = ".git/info/exclude"
    # Reading git exclude file
    with open(ex_file, "r", encoding="utf-8") as file:
        exclude: str = file.read()
    if not exclude.endswith("\n"):
        exclude += "\n"
    regex = re.compile(r"^\s*\.vscode/?\s*$", re.MULTILINE)
    if regex.search(exclude):
        ws_advice(f".vscode folder already excluded in {ex_file}")
    else:
        exclude += ".vscode/\n"
        ws_success(f"Excluded .vscode folder in {ex_file}")
    regex = re.compile(rf"^\s*{working_path}/?\s*$", re.MULTILINE)
    if regex.search(exclude):
        ws_advice(f"{working_path} folder already excluded in {ex_file}")
    else:
        exclude += f"{working_path}/\n"
        ws_success(f"Excluded {working_path} folder in {ex_file}")
    if not exclude.endswith("\n"):
        exclude += "\n"
    # Writing git exclude file
    with open(ex_file, "w", encoding="utf-8") as file:
        file.write(exclude)


def add_default_settings(workspace_file: str, working_path: str) -> None:
    """
    Adds default settings to the workspace file.

    Args:
        workspace_file (str): The workspace file path
    """
    json_data: dict[str, Any] = load_json_with_comments(workspace_file)
    result = jq.compile(GIT_BLAME_QUERY).input(json_data).first()
    if not result:
        jq_query = f'{GIT_BLAME_QUERY} = "{get_remote_url()}/tree/$ID"'
        json_data = jq.compile(jq_query).input(json_data).first()
        temp_file = f"{working_path}/blame.json"
        update_workspace(json_data, temp_file, workspace_file)
