""" This module contains the functions for setting the workspace for the project. """

import os
from pathlib import Path
import shutil
import json
import re
from typing import Any
import click
import jq
from py.constants import APP_NAME, WORKSPACE_EXTENSIONS
from py.util.props import AppProperties
from py.util.formatting import ws_success
from py.config_environment.util import update_workspace
from py.config_environment.models.github_queries import PrQueries, IssuesQueries
from py.config_environment.models.log_viewer_watcher import LogWatcher
from py.config_environment.models.vscode_task import VscodeTask, TASKS_INPUT_QUERY
from py.config_environment.models.vscode_input import VscodeInput, InputType
from py.config_environment.models.vscode_launch import VscodeLaunch, LAUNCH_INPUT_QUERY, SUBSTITUTE_SHELL_TAG, SUBSTITUTE_PROJECT_TAG
from py.config_environment.java_set import execute as set_java
from py.config_environment.gradle_set import execute as set_gradle, set_gradle_version as gradle_command
from py.config_environment.local_config import execute as initial_load
from py.util.formatting import ws_advice, ws_info, ws_warning
from py.util.util import get_command_return_code, get_validated_input, cli_metadata, get_remote_url, load_json_with_comments, get_input_or_default


@click.command(
    name="createWorkingEnv",
    short_help="Configures the VSCode workspace environment",
    help="Sets up the VSCode workspace with recommended extensions, default settings, tasks, launch configurations, and git exclusions. "
         "Also configures Java and Gradle if applicable.",
    epilog="""This command will:
    - Create/update VSCode workspace file
    - Configure git exclusions for workspace files
    - Set up Java and Gradle configurations
    - Add recommended extensions
    - Configure default settings and file associations
    - Set up tasks and launch configurations
    - Configure log watchers and GitHub queries

    usage: snake createWorkingEnv
    """
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

    workspace_file: str = _get_workspace_file()
    working_path: str = _get_working_path()
    if git_repo:
        _git_exclude(working_path)
    initial_load(False)
    set_java(False, workspace_file)
    # verifying if build.gradle or build.gradle.kts exists
    build_file: str = f"{os.getcwd()}/build.gradle"
    build_kts_file: str = f"{os.getcwd()}/build.gradle.kts"
    if not os.path.exists(build_file) and not os.path.exists(build_kts_file):
        ws_warning(
            f"build.gradle or build.gradle.kts file not found in the current directory. "
            f"Please run '{APP_NAME} {gradle_command.name}' command if you want to set the gradle version anyway."
        )
    else:
        set_gradle(False, workspace_file)
    _add_recommended_extensions(workspace_file)
    _add_default_settings(workspace_file, working_path)


FOLDER = os.path.basename(os.getcwd())
GIT_BLAME_QUERY = '.settings.["git-blame.gitWebUrl"]'
EXTENSIONS_QUERY = ".extensions.recommendations"
DEFAULT_PROPS: dict[str, Any] = {
    "snake.java.remoteDebug.port": 5005,
    "snake.java.remoteDebug.profile": "dev",
    "snake.java.remoteDebug.jar": "build/libs/*.jar",
    "terminal.integrated.scrollback": 9000,
    "editor.largeFileOptimizations": False,
    "editor.maxTokenizationLineLength": 2000000,
    "logViewer.followTailMode": "auto",
    "logViewer.chunkSizeKb": 81920,
    "java.jdt.ls.vmargs": "-XX:+UseParallelGC -XX:GCTimeRatio=4 -XX:AdaptiveSizePolicyWeight=90 -Dsun.zip.disableMemoryMapping=true -Xmx4G -Xms100m -Xlog:disable",
}
FILE_ASSOCIATIONS: dict[str, str] = {"**/.github/workflows/*.yml": "github-actions-workflow", "*.yml": "yaml", "*.gradle": "gradle"}


def _get_workspace_file() -> str:
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
    workspace_content: dict[str, Any] = {"folders": [{"name": "main", "path": "."}], "settings": {}}
    workspace_file = f"{os.getcwd()}/{FOLDER}.code-workspace"
    with open(workspace_file, "w", encoding="utf-8") as file:
        json.dump(workspace_content, file, indent=4)
    ws_success(f"Vscode workspace file created at {workspace_file}")
    return workspace_file


def _get_working_path() -> str:
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
    os.makedirs(working_path, exist_ok=True)
    ws_success(f"Working path created at {working_path}")
    return working_path


def _git_exclude(working_path: str) -> None:
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


def _add_recommended_extensions(workspace_file: str) -> None:
    """
    Adds recommended extensions to the workspace file.

    Args:
        workspace_file (str): The workspace file path
    """
    update_file: bool = False
    json_data: dict[str, Any] = load_json_with_comments(workspace_file)
    result = jq.compile(EXTENSIONS_QUERY).input(json_data).all()
    if not result or not result[0]:
        jq_query = f"{EXTENSIONS_QUERY} = {json.dumps(WORKSPACE_EXTENSIONS)}"
        json_data = jq.compile(jq_query).input(json_data).first()
        update_file = True
    else:
        ext_list: list[str] = []
        for ext in WORKSPACE_EXTENSIONS:
            if ext not in result[0]:
                ext_list.append(ext)
        if ext_list:
            jq_query = f"{EXTENSIONS_QUERY} += {json.dumps(ext_list)}"
            json_data = jq.compile(jq_query).input(json_data).first()
            update_file = True
    if update_file:
        temp_file = f"{os.path.dirname(workspace_file)}/extensions.json"
        update_workspace(json_data, temp_file, workspace_file)
        ws_success("Recommended extensions added to the workspace file")


def _add_default_settings(workspace_file: str, working_path: str) -> None:
    """
    Adds default settings to the workspace file.

    Args:
        workspace_file (str): The workspace file path
        working_path (str): The working path
    """
    json_data: dict[str, Any] = load_json_with_comments(workspace_file)
    update_file: bool = False

    json_data, updated = _update_git_blame(json_data)
    update_file = update_file or updated

    json_data, updated = _update_github_queries(json_data)
    update_file = update_file or updated

    json_data, updated = _update_log_watchers(json_data, working_path)
    update_file = update_file or updated

    json_data, updated = _update_vscode_tasks(json_data, working_path)
    update_file = update_file or updated

    json_data, updated = _update_vscode_launch(json_data, working_path)
    update_file = update_file or updated

    json_data, updated = _update_input_props(json_data)
    update_file = update_file or updated

    json_data, updated = _update_file_associations(json_data)
    update_file = update_file or updated

    if update_file:
        temp_file = f"{working_path}/blame.json"
        update_workspace(json_data, temp_file, workspace_file)
        ws_success("Workspace settings updated successfully")
    else:
        ws_advice("Workspace settings already up-to-date")


def _update_git_blame(json_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Update git blame settings in workspace"""
    result = jq.compile(GIT_BLAME_QUERY).input(json_data).first()
    if not result:
        jq_query = f'{GIT_BLAME_QUERY} = "{get_remote_url()}/tree/$ID"'
        json_data = jq.compile(jq_query).input(json_data).first()
        return json_data, True
    return json_data, False


def _update_github_queries(json_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Update GitHub PR and Issues queries"""
    updated = False
    for pr_query in PrQueries:
        res = pr_query.add_query(json_data)
        if res:
            updated = True
            json_data = res

    for issue_query in IssuesQueries:
        res = issue_query.add_query(json_data)
        if res:
            updated = True
            json_data = res

    return json_data, updated


def _update_log_watchers(json_data: dict[str, Any], working_path: str) -> tuple[dict[str, Any], bool]:
    """Update log watchers configuration"""
    updated = False
    for watcher in LogWatcher:
        res = watcher.add_watcher(json_data, working_path)
        if res:
            updated = True
            json_data = res
    return json_data, updated


def _update_vscode_tasks(json_data: dict[str, Any], working_path: str) -> tuple[dict[str, Any], bool]:
    """Update VSCode tasks configuration"""
    updated = False

    res = VscodeTask.add_tasks_version(json_data)
    if res:
        updated = True
        json_data = res

    for input_type in [a for a in VscodeInput if a.enum_type != InputType.LAUNCH]:
        res = input_type.add_tasks_input(json_data, TASKS_INPUT_QUERY)
        if res:
            updated = True
            json_data = res

    for task in VscodeTask:
        res = task.add_tasks_task(json_data, working_path)
        if res:
            updated = True
            json_data = res

    return json_data, updated


def _update_vscode_launch(json_data: dict[str, Any], working_path: str) -> tuple[dict[str, Any], bool]:
    """Update VSCode launch configuration"""
    updated = False

    res = VscodeLaunch.add_launch_version(json_data)
    if res:
        updated = True
        json_data = res

    for input_type in [a for a in VscodeInput if a.enum_type != InputType.TASK]:
        res = input_type.add_tasks_input(json_data, LAUNCH_INPUT_QUERY)
        if res:
            updated = True
            json_data = res

    for launch in VscodeLaunch:
        res = launch.add_launch_config(json_data, _launch_substituter, working_path)
        if res:
            updated = True
            json_data = res

    return json_data, updated


def _update_input_props(json_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Update VSCode input properties"""
    updated = False
    for key, value in DEFAULT_PROPS.items():
        snake_query: str = f'.settings.["{key}"]'
        result = jq.compile(snake_query).input(json_data).first()
        if result is None:
            prompt: str = f"Enter the value a value for {key}"
            value = get_input_or_default(prompt, value)
            jq_query = f"{snake_query} = {json.dumps(value)}"
            json_data = jq.compile(jq_query).input(json_data).first()
            updated = True

    return json_data, updated


def _update_file_associations(json_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Update file associations in workspace"""
    updated = False
    for key, value in FILE_ASSOCIATIONS.items():
        file_query: str = f'.settings.["files.associations"].["{key}"]'
        result = jq.compile(file_query).input(json_data).first()
        if not result:
            jq_query = f"{file_query} = {json.dumps(value)}"
            json_data = jq.compile(jq_query).input(json_data).first()
            updated = True
    return json_data, updated


def _launch_substituter(launch: str) -> str:
    """
    Substitutes launch tags with values
    """
    # verify if the launch contains the tags
    if SUBSTITUTE_SHELL_TAG in launch:
        launch = launch.replace(SUBSTITUTE_SHELL_TAG, AppProperties.get_instance().retrieve_property("shell"))
    if SUBSTITUTE_PROJECT_TAG in launch:
        launch = launch.replace(SUBSTITUTE_PROJECT_TAG, FOLDER)
    return launch
