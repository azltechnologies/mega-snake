"""This module provides functions to set a specific Maven version as the default version on the workspace."""

import json
import os
import re
import shutil
from typing import Any, Optional
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
from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher
from mega_snake.config_environment.models.vscode_task import VscodeTask, TASKS_INPUT_QUERY, TASKS_TASKS_QUERY
from mega_snake.config_environment.models.vscode_input import VscodeInput
from mega_snake.util.util import run_operation, load_json_with_comments
from mega_snake.util.props import get_property
from mega_snake.util.formatting import ws_info, ws_success, ws_warning

MAVEN_ENV_VAR = "M2_HOME"
ENV_VARIABLE = f"terminal.integrated.env.{OS_MAP[OS]}"
MAVEN_HOME_QUERY = f'.settings["{ENV_VARIABLE}"].{MAVEN_ENV_VAR}'
MAVEN_EXEC_QUERY = '.settings["maven.executable.path"]'
MAVEN_EXECUTABLE = "mvn.cmd" if OS == "Windows" else "mvn"

MAVEN_TASKS: list[VscodeTask] = [
    VscodeTask.MAVEN_CLEAN_INSTALL,
    VscodeTask.MAVEN_TEST,
    VscodeTask.MAVEN_VERIFY,
    VscodeTask.MAVEN_DEPENDENCY_TREE,
    VscodeTask.MAVEN_SPRING_BOOT,
]

MAVEN_WATCHERS: list[LogWatcher] = [
    LogWatcher.MAVEN_CLEAN_INSTALL,
    LogWatcher.MAVEN_TEST,
    LogWatcher.MAVEN_VERIFY,
    LogWatcher.MAVEN_DEPENDENCY_TREE,
    LogWatcher.MAVEN_SPRING_BOOT,
]


@click.command(
    name="set-maven",
    short_help="Sets Maven home and executable in workspace and local shell config",
    help="Detects Maven installation (or uses --maven-home) and sets Maven paths for VS Code and local shell config.",
    epilog="""usage: mgsnake set-maven [OPTIONS]\n
    OPTIONS:\n
        -m | --maven-home: Optional[str] - Explicit Maven home path (for example /opt/apache-maven-3.9.8)\n
    """,
)
@click.option("--maven-home", "-m", type=click.STRING, default=None, help="Explicit Maven home directory")
def set_maven_version(maven_home: Optional[str]) -> None:
    """Configure Maven paths for the current workspace."""
    workspace_file: str = get_property("workspace_file")
    execute(maven_home, workspace_file)


def execute(maven_home: Optional[str], workspace_file: str) -> None:
    """
    Sets the Maven version for the project.

    Args:
        maven_home (Optional[str]): Explicit Maven home path.
        workspace_file (str): Path to the workspace settings file
    """
    working_path: str = get_property("working_path")
    local_file = get_local_file()
    shell = get_property("shell")
    _maven_set(workspace_file, working_path, local_file, shell, maven_home)


@click.command(
    name="maven-project-setup",
    short_help="Configures Maven tasks and logs in workspace settings",
    help="Creates or updates Maven tasks and log watchers in the current code-workspace when pom.xml is present.",
    epilog="""usage: mgsnake maven-project-setup [OPTIONS]\n
    OPTIONS:\n
        -o | --override: bool - Recreate Maven tasks and watchers even if they already exist in workspace\n
    """,
)
@click.option("--override", "-o", is_flag=True, help="Recreate existing Maven tasks and log watchers")
def maven_project_setup(override: bool) -> None:
    """Create VS Code Maven task definitions and log watchers for local development."""
    pom_path = os.path.join(os.getcwd(), "pom.xml")
    if not os.path.exists(pom_path):
        raise FileNotFoundError("pom.xml file not found in the current directory.")
    workspace_file: str = get_property("workspace_file")
    working_path: str = get_property("working_path")
    json_data: dict[str, Any] = load_json_with_comments(workspace_file)
    updated_json, updated = _update_maven_tasks(json_data, working_path, override)
    if not updated:
        ws_info("Maven tasks and log watchers are already configured in workspace settings.")
        return
    temp_file = f"{working_path}/maven_tasks.json"
    update_workspace(updated_json, temp_file, workspace_file)
    ws_success("Maven tasks and log watchers configured successfully")


class MavenVersion(ToolVersion):
    """MavenVersion class represents a Maven installation.

    Attributes:
        version (str): The Maven version number
        path (str): Installation path
    """

    _id_counter: int = 0

    def __str__(self) -> str:
        """Return a human-readable string representation of the MavenVersion."""
        return f"Id: {self.id}\n\tMaven Version: {self.version}\n\tpath: {self.path}\n"


def _maven_set(
    workspace_file: str, working_path: str, local_file: str, shell: str, maven_home: Optional[str]
) -> None:
    """
    Configures the Maven version to be used in the workspace.

    Args:
        workspace_file (str): Path to the workspace settings file
        working_path (str): Path to create a temporary file
        local_file (str): Path to the local settings file
        shell (str): The shell to use for setting the Maven version
        maven_home (Optional[str]): Explicit Maven home path
    """
    versions: list[MavenVersion] = _get_versions(maven_home)
    if not versions:
        ws_warning("No Maven versions found on the system. Please install a valid Maven version")
        return

    json_data: Any = load_json_with_comments(workspace_file)
    version_environment = _find_version_by_query(versions, json_data, MAVEN_HOME_QUERY)
    version_executable = _find_version_from_executable(versions, json_data)
    version_local = _find_version_from_local(versions, local_file, shell)
    list_found: list[Optional[MavenVersion]] = [version_environment, version_executable, version_local]
    try:
        version: Optional[ToolVersion] = determine_tool_version(typing.cast(list[Optional[ToolVersion]], list_found))
    except VersionSetException as e:
        ws_success(str(e))
        return
    if not version:
        ws_info("Selecting Maven version to set as default on the workspace")
        version = select_version(typing.cast(list[ToolVersion], versions))
        version.default = True

    _update_configurations(versions, json_data, workspace_file, working_path, local_file, shell)
    ws_success(f"Maven version {version.version} set as default on the workspace")


def _find_version_by_query(versions: list[MavenVersion], json_data: Any, query: str) -> Optional[MavenVersion]:
    """Find Maven version from JSON data using jq query."""
    result: Optional[str] = jq.compile(query).input(json_data).first()
    return next((v for v in versions if v.path == result), None)


def _find_version_from_executable(versions: list[MavenVersion], json_data: Any) -> Optional[MavenVersion]:
    """Find Maven version from executable path in workspace settings."""
    executable_path: Optional[str] = jq.compile(MAVEN_EXEC_QUERY).input(json_data).first()
    if not executable_path:
        return None
    normalized = executable_path.replace("\\", "/")
    if "/bin/" in normalized:
        normalized = normalized.rsplit("/bin/", 1)[0]
    else:
        normalized = os.path.dirname(os.path.dirname(normalized))
    return next((v for v in versions if v.path == normalized), None)


def _find_version_from_local(versions: list[MavenVersion], local_file: str, shell: str) -> Optional[MavenVersion]:
    """Find Maven version from local shell configuration file."""
    result = find_local_tool_home(local_file, shell, MAVEN_ENV_VAR)
    if result:
        return next((v for v in versions if v.path == result), None)
    return None


def _update_configurations(
    versions: list[MavenVersion], json_data: Any, workspace_file: str, working_path: str, local_file: str, shell: str
) -> None:
    """Update workspace and local shell with selected Maven default."""
    temp_file = f"{working_path}/maven_versions.json"
    json_data = set_version_path_for_query(typing.cast(list[ToolVersion], versions), json_data, MAVEN_HOME_QUERY)
    version: Optional[MavenVersion] = next((v for v in versions if v.default), None)
    assert version, "Default Maven version not found in the list of Maven versions. This is a bug."
    executable_path = os.path.join(version.path, "bin", MAVEN_EXECUTABLE).replace("\\", "/")
    json_data = jq.compile(f"{MAVEN_EXEC_QUERY} = {json.dumps(executable_path)}").input(json_data).first()
    update_workspace(json_data, temp_file, workspace_file)
    set_version_local_config(version, local_file, shell, MAVEN_ENV_VAR)


def _detect_maven_home() -> Optional[str]:
    """Detect Maven home from `mvn -v` output or from PATH."""
    if not (mvn_path := shutil.which("mvn")):
        return None
    output = run_operation("mvn -v", "Getting Maven details", check=False).stdout.strip()
    if output:
        if match := re.search(r"^Maven home:\s*(.+)$", output, re.MULTILINE):
            return match.group(1).strip().replace("\\", "/")
    return os.path.dirname(os.path.dirname(mvn_path)).replace("\\", "/")


def _get_versions(maven_home: Optional[str]) -> list[MavenVersion]:
    """Get Maven versions installed on the system.

    Returns:
        list[MavenVersion]: List of MavenVersion objects
    """
    if maven_home:
        if not os.path.isdir(maven_home):
            raise NotADirectoryError(f"Maven home is not a valid directory: {maven_home}")
        return [MavenVersion(version="custom", _path=maven_home, default=True)]
    if OS == "Windows":
        command_paths = (
            'scoop list 6>&1 | Where-Object { $_.Name -like "maven*" } | ForEach-Object { "$(scoop prefix $_.Name)" }'
        )
    elif OS == "Linux":
        command_paths = "update-alternatives --list mvn 2>/dev/null | sed 's:/bin/mvn$::'"
    elif OS == "Darwin":
        command_paths = "find $(brew --cellar) -type d -depth 2 2>/dev/null | grep maven | sed -E 's/$/\\/libexec/'"
    else:
        raise NotImplementedError(f"OS not supported: {OS}")
    paths = run_operation(command_paths, "Getting Maven versions", check=False).stdout.strip().splitlines()
    version_data: list[tuple[str, str]] = []
    for path in paths:
        normalized = path.strip().replace("\\", "/")
        if not normalized:
            continue
        output = _get_maven_version_from_path(normalized)
        match = re.search(r"Apache Maven\s+([0-9][0-9A-Za-z.\-_]*)", output)
        version = match.group(1) if match else "0.0.0"
        version_data.append((normalized, version))
    version_data = sorted(version_data, key=lambda x: get_version_number(x[1]), reverse=True)
    return [MavenVersion(version=version, _path=path) for path, version in version_data]


def _get_maven_version_from_path(path: str) -> str:
    """Get Maven version output from a Maven installation path."""
    executable = os.path.join(path, "bin", MAVEN_EXECUTABLE).replace("\\", "/")
    return run_operation(f'"{executable}" -v', "Getting Maven details", check=False).stdout.strip()


def _update_maven_tasks(json_data: dict[str, Any], working_path: str, override: bool) -> tuple[dict[str, Any], bool]:
    """Update workspace tasks and log watchers for Maven development commands."""
    updated = False

    # Add tasks version if not present
    res = VscodeTask.add_tasks_version(json_data)
    if res:
        json_data = res
        updated = True

    # Add todayTimestamp input
    res = VscodeInput.TODAY_TIMESTAMP.add_tasks_input(json_data, TASKS_INPUT_QUERY)
    if res:
        json_data = res
        updated = True

    # Add Maven tasks using the VscodeTask enum pattern
    for task in MAVEN_TASKS:
        res = _add_maven_task(json_data, task, working_path, override)
        if res:
            json_data = res
            updated = True

    # Add Maven log watchers using the LogWatcher enum pattern
    for watcher in MAVEN_WATCHERS:
        res = watcher.add_watcher(json_data, working_path)
        if res:
            json_data = res
            updated = True

    return json_data, updated


def _add_maven_task(
    json_data: dict[str, Any], task: VscodeTask, working_path: str, override: bool
) -> Optional[dict[str, Any]]:
    """Add one Maven task entry to workspace tasks, handling override logic."""
    json_input = json_data
    result = jq.compile(TASKS_TASKS_QUERY).input(json_data).first()
    search_query: str = f'{TASKS_TASKS_QUERY}| map(select(.label == "{task.label}"))'
    if result:
        length_query: str = f"{search_query} | length"
        count = jq.compile(length_query).input(json_data).first()
        if count == 1 and not override:
            return None
        if count >= 1:
            delete_query = search_query.replace("==", "!=")
            filtered = jq.compile(delete_query).input(json_data).first()
            jq_query = f"{TASKS_TASKS_QUERY} = {json.dumps(filtered)}"
            json_input = jq.compile(jq_query).input(json_input).first()
    task_dict = _build_maven_task_dict(task, working_path)
    jq_query = f"{TASKS_TASKS_QUERY} += [{json.dumps(task_dict)}]"
    return jq.compile(jq_query).input(json_input).first()


def _build_maven_task_dict(task: VscodeTask, working_path: str) -> dict[str, Any]:
    """Build a Maven task dict without mutating enum state."""
    result: dict[str, Any] = {
        "label": task.label,
        "hide": task.hidden,
        "detail": task.detail,
        "problemMatcher": task.problem_matcher,
    }
    if task.task_type:
        result["type"] = task.task_type
    if task.command:
        result["command"] = task.command
    # Build args with log redirect without mutating the enum
    args = list(task.args) if task.args else []
    if task.watcher:
        log_output: str = task.watcher.get_pattern_date(working_path)
        args.extend(log_output.split(" "))
    if args:
        result["args"] = args
    for key, value in task.extra_args.items():
        result[key] = value
    return result
