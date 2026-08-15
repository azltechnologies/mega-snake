"""This module contains the functions for setting the workspace for the project."""

import os
import shutil
import json
import re
from typing import Any, Optional
import click
import jq
from mega_snake.constants import APP_NAME
from mega_snake.util.props import get_property
from mega_snake.util.formatting import ws_success
from mega_snake.config_environment.util import update_workspace
from mega_snake.config_environment.models.github_queries import PrQueries, IssuesQueries
from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher
from mega_snake.config_environment.models.project_stack import (
    ProjectStack,
    describe_stacks,
    filter_by_stack,
    resolve_stacks,
    selectable_keys,
    sort_stacks,
)
from mega_snake.config_environment.models.vscode_task import VscodeTask, TASKS_INPUT_QUERY
from mega_snake.config_environment.models.vscode_input import VscodeInput, InputType
from mega_snake.config_environment.models.vscode_launch import (
    VscodeLaunch,
    LAUNCH_INPUT_QUERY,
    SUBSTITUTE_SHELL_TAG,
    SUBSTITUTE_PROJECT_TAG,
    REMOTE_DEBUG_PORT_QUERY,
)
from mega_snake.config_environment.java_set import execute as set_java, set_java_version as java_command
from mega_snake.config_environment.gradle_set import execute as set_gradle, set_gradle_version as gradle_command
from mega_snake.config_environment.maven_set import execute as set_maven, set_maven_version as maven_command
from mega_snake.config_environment.local_config import execute as initial_load
from mega_snake.util.formatting import UserDeclinedError, ws_advice, ws_info, ws_warning
from mega_snake.util.util import (
    get_command_return_code,
    get_validated_input,
    cli_metadata,
    ensure_working_path,
    exclude_from_git,
    get_remote_url,
    load_json_with_comments,
    get_input_or_default,
)


@click.command(
    name="working-env",
    short_help="Configures the VS Code workspace environment",
    help="Sets up the VS Code workspace with recommended extensions, default settings, tasks, launch configurations,"
    " and git exclusions. Only the stacks found in the repository are configured: the Java, Gradle and Maven steps —"
    " along with their tasks, launch configurations, log watchers and extensions — are skipped unless a build file"
    " reveals them, or --stack asks for them explicitly.",
    epilog="usage: mgsnake working-env [OPTIONS]",
)
@click.option(
    "--stack",
    "-s",
    "stacks",
    multiple=True,
    type=click.Choice(selectable_keys()),
    help="Configure this stack regardless of what the repository looks like, instead of detecting it from the build"
    " files in the current directory. Repeat the option to select several stacks, or pass 'all' to configure every"
    " one of them. A build tool implies its language, so 'gradle' and 'maven' both bring 'java' along.",
)
@cli_metadata(flags={"skip"}, reloads_environment=True)
def create_working_env(stacks: tuple[str, ...]) -> None:  # previously untrackGradleProps
    """
    Sets up the VS Code workspace for the project.

    Verifies that git is installed and that the current directory is a git repository — offering
    to continue without git otherwise — and then delegates the workspace configuration to _execute.

    Parameters:
        stacks: The stack keys requested through --stack; empty to detect them from the repository.

    Returns:
        None
    """
    git_repo: bool = True
    if not shutil.which("git"):
        git_repo = False
        if (
            get_validated_input(
                "Git is not installed. Would you like to configure the workspace without git?", ["y", "n"]
            ).lower()
            == "n"
        ):
            ws_warning("Git is required to configure the workspace. Exiting...")
            return
    else:
        if get_command_return_code("git rev-parse --is-inside-work-tree") != 0:
            git_repo = False
            if (
                get_validated_input(
                    "Not inside a git repository. Would you like to configure the workspace anyway?", ["y", "n"]
                ).lower()
                == "n"
            ):
                ws_warning("Not inside a git repository. Exiting...")
                return
    _execute(git_repo, stacks)


def _execute(git_repo: bool, stacks: tuple[str, ...] = ()) -> None:  # previously untrackGradleProps
    """
    Configures the workspace: git exclusions, local config load, the tool setup of every active
    stack, and the default workspace settings that belong to those stacks.

    Args:
        git_repo (bool): Whether the current directory is a git repository.
        stacks (tuple[str, ...]): The stack keys requested by the user; empty to detect them.

    Returns:
        None
    """
    workspace_file: str = _get_workspace_file()
    working_path: str = ensure_working_path("Working path is required to configure the working environment. Exiting...")
    active_stacks: set[ProjectStack] = resolve_stacks(stacks)
    ws_info(f"Configuring the workspace for the following stacks:\n{describe_stacks(active_stacks)}")
    if git_repo:
        _git_exclude(working_path)
    initial_load(False)
    _configure_tools(workspace_file, active_stacks)
    _add_default_settings(workspace_file, working_path, active_stacks)


def _configure_tools(workspace_file: str, stacks: set[ProjectStack]) -> None:
    """Run the Java, Gradle and Maven configuration steps of the active stacks.

    A stack that is not active is reported instead of configured, pointing at the command that sets
    its version on demand — those commands stay unconditional, so nothing is lost when the detection
    does not match the repository layout.

    Parameters:
        workspace_file: Path to the workspace settings file.
        stacks: The active stacks.

    Raises:
        None

    Returns:
        None
    """
    if ProjectStack.JAVA in stacks:
        set_java(False, workspace_file)
    else:
        _skipped_stack_warning(ProjectStack.JAVA, java_command.name)
    if ProjectStack.GRADLE in stacks:
        set_gradle(False, workspace_file)
    else:
        _skipped_stack_warning(ProjectStack.GRADLE, gradle_command.name)
    if ProjectStack.MAVEN in stacks:
        set_maven(None, workspace_file)
    else:
        _skipped_stack_warning(ProjectStack.MAVEN, maven_command.name)


def _skipped_stack_warning(stack: ProjectStack, command_name: Optional[str]) -> None:
    """Report a stack that was skipped and how to configure it anyway.

    Parameters:
        stack: The stack that is not part of the workspace.
        command_name: Name of the command that configures the stack on demand, as click knows it.

    Raises:
        None

    Returns:
        None
    """
    markers: str = ", ".join(stack.markers)
    reason: str = f"no {markers} file found in the current directory" if markers else "no build file revealed it"
    ws_warning(
        f"Skipping the {stack.key} configuration: {reason}. "
        f"Run '{APP_NAME} {command_name}' to set the {stack.key} version anyway, "
        f"or '{APP_NAME} {create_working_env.name} --stack {stack.key}' to configure the whole stack."
    )


FOLDER = os.path.basename(os.getcwd())
GIT_BLAME_QUERY = '.settings.["git-blame.gitWebUrl"]'
EXTENSIONS_QUERY = ".extensions.recommendations"
# Kept here instead of on ProjectStack — unlike the extensions and the file associations, these
# entries are built from the query constants owned by the vscode_launch model, and importing them
# from the stack model would close an import cycle.
DEFAULT_PROPS: dict[ProjectStack, dict[str, Any]] = {
    ProjectStack.COMMON: {
        "terminal.integrated.scrollback": 9000,
        "editor.largeFileOptimizations": False,
        "editor.maxTokenizationLineLength": 2000000,
        "logViewer.followTailMode": "auto",
        "logViewer.chunkSizeKb": 81920,
    },
    ProjectStack.JAVA: {
        REMOTE_DEBUG_PORT_QUERY: 5005,
        "mgsnake.java.remoteDebug.profile": "dev",
        "mgsnake.java.remoteDebug.jar": "build/libs/*.jar",
        "java.jdt.ls.vmargs": "-XX:+UseParallelGC -XX:GCTimeRatio=4 -XX:AdaptiveSizePolicyWeight=90"
        " -Dsun.zip.disableMemoryMapping=true -Xmx4G -Xms100m -Xlog:disable",
    },
}
FILE_ASSOCIATION_QUERY = '.settings.["files.associations"]'
NEW_WORKSPACE_CONTENTS: dict[str, Any] = {"folders": [{"name": "main", "path": "."}], "settings": {}}


def _get_workspace_file() -> str:
    """
    Gets the workspace file for the project. If not found, creates a new one.

    Returns:
        str - The workspace file path
    """
    workspace_file: str = get_property("workspace_file")
    if workspace_file:
        ws_info(f"Vscode workspace file found: {workspace_file}")
        # Check if the workspace file is in the current directory
        if not os.path.exists(workspace_file):
            raise FileNotFoundError(f"No workspace file found at {workspace_file}")
        # Check if the workspace file is not empty
        with open(workspace_file, "r", encoding="utf-8") as file:
            if file.read().strip():
                return workspace_file
            ws_warning("Vscode workspace file is empty")
    else:
        ws_warning("Vscode workspace file not found in current directory")
        if get_validated_input("Would you like to create a new default workspace file?", ["y", "n"]).lower() == "n":
            # Declining a prompt is a decision, not a failure: it carries the same status as every
            # other declined prompt so a script can tell it apart and stop retrying.
            raise UserDeclinedError(
                "Vscode workspace file is required to configure the working environment. Exiting..."
            )
    workspace_file = f"{os.getcwd()}/{FOLDER}.code-workspace"
    with open(workspace_file, "w", encoding="utf-8") as file:
        json.dump(NEW_WORKSPACE_CONTENTS, file, indent=4)
    ws_success(f"Vscode workspace file created at {workspace_file}")
    return workspace_file


def _git_exclude(working_path: str) -> None:
    """Exclude the .vscode folder, the working path and the root workspace file from git.

    Parameters:
        working_path: The working path folder; only its basename is excluded.

    Raises:
        None

    Returns:
        None
    """
    folder: str = os.path.basename(working_path)
    exclude_from_git(
        [
            (".vscode/", ".vscode folder"),
            (f"{folder}/", f"{folder} folder"),
            ("/*.code-workspace", "root code-workspace file"),
        ]
    )


def _add_default_settings(
    workspace_file: str, working_path: str, stacks: Optional[set[ProjectStack]] = None
) -> None:
    """
    Adds default settings to the workspace file.

    Args:
        workspace_file (str): The workspace file path
        working_path (str): The working path
        stacks (Optional[set[ProjectStack]]): The active stacks; detected from the repository when
            not provided, so that every artifact written belongs to a stack the project actually uses
    """
    active_stacks: set[ProjectStack] = stacks if stacks else resolve_stacks()
    json_data: dict[str, Any] = load_json_with_comments(workspace_file)
    update_file: bool = False

    json_data, updated = _add_recommended_extensions(json_data, active_stacks)
    update_file = update_file or updated

    json_data, updated = _update_git_blame(json_data)
    update_file = update_file or updated

    json_data, updated = _update_github_queries(json_data)
    update_file = update_file or updated

    json_data, updated = _update_log_watchers(json_data, working_path, active_stacks)
    update_file = update_file or updated

    json_data, updated = _update_vscode_tasks(json_data, working_path, active_stacks)
    update_file = update_file or updated

    json_data, updated = _update_vscode_launch(json_data, working_path, active_stacks)
    update_file = update_file or updated

    json_data, updated = _update_input_props(json_data, active_stacks)
    update_file = update_file or updated

    json_data, updated = _update_file_associations(json_data, active_stacks)
    update_file = update_file or updated

    if update_file:
        temp_file = f"{working_path}/blame.json"
        update_workspace(json_data, temp_file, workspace_file)
        ws_success("Workspace settings updated successfully")
    else:
        ws_advice("Workspace settings already up-to-date")


def get_recommended_extensions(stacks: set[ProjectStack]) -> list[str]:
    """Collect the recommended extensions contributed by the active stacks.

    Parameters:
        stacks: The active stacks.

    Raises:
        None

    Returns:
        list[str]: The extension ids, without duplicates and in stack declaration order.
    """
    extensions: list[str] = []
    for stack in sort_stacks(stacks):
        for extension in stack.extensions:
            if extension not in extensions:
                extensions.append(extension)
    return extensions


def _add_recommended_extensions(json_data: dict[str, Any], stacks: set[ProjectStack]) -> tuple[dict[str, Any], bool]:
    """
    Adds the recommended extensions of the active stacks to the json contents.

    Extensions already listed in the workspace are never removed, so a workspace configured before a
    stack was dropped keeps whatever the developer has been using.

    Args:
        json_data (dict): The workspace file contents
        stacks (set[ProjectStack]): The active stacks
    """
    update_file: bool = False
    workspace_extensions: list[str] = get_recommended_extensions(stacks)
    result = jq.compile(EXTENSIONS_QUERY).input(json_data).all()
    if not result or not result[0]:
        jq_query = f"{EXTENSIONS_QUERY} = {json.dumps(workspace_extensions)}"
        json_data = jq.compile(jq_query).input(json_data).first()
        update_file = True
    else:
        ext_list: list[str] = []
        for ext in workspace_extensions:
            if ext not in result[0]:
                ext_list.append(ext)
        if ext_list:
            jq_query = f"{EXTENSIONS_QUERY} += {json.dumps(ext_list)}"
            json_data = jq.compile(jq_query).input(json_data).first()
            update_file = True
    return json_data, update_file


def _update_git_blame(json_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Update git blame settings in workspace"""
    result = jq.compile(GIT_BLAME_QUERY).input(json_data).first()
    remote_url = get_remote_url()
    if not result and remote_url:
        remote_url = re.sub(r"^git@", "https://", remote_url)
        match = re.match(r"https\://\w+\.\w+\:", remote_url)
        if match:
            repl = re.sub(r"\:$", "/", match.group())
            remote_url = remote_url.replace(match.group(), repl)
        jq_query = f'{GIT_BLAME_QUERY} = "{remote_url}/tree/$ID"'
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


def _update_log_watchers(
    json_data: dict[str, Any], working_path: str, stacks: set[ProjectStack]
) -> tuple[dict[str, Any], bool]:
    """Update the log watchers configuration of the active stacks"""
    updated = False
    for watcher in filter_by_stack(LogWatcher, stacks):
        res = watcher.add_watcher(json_data, working_path)
        if res:
            updated = True
            json_data = res
    return json_data, updated


def _update_vscode_tasks(
    json_data: dict[str, Any], working_path: str, stacks: set[ProjectStack]
) -> tuple[dict[str, Any], bool]:
    """Update the VSCode tasks configuration of the active stacks"""
    updated = False

    res = VscodeTask.add_tasks_version(json_data)
    if res:
        updated = True
        json_data = res

    for input_type in [a for a in filter_by_stack(VscodeInput, stacks) if a.enum_type != InputType.LAUNCH]:
        res = input_type.add_tasks_input(json_data, TASKS_INPUT_QUERY)
        if res:
            updated = True
            json_data = res

    for task in filter_by_stack(VscodeTask, stacks):
        res = task.add_tasks_task(json_data, working_path)
        if res:
            updated = True
            json_data = res

    return json_data, updated


def _update_vscode_launch(
    json_data: dict[str, Any], working_path: str, stacks: set[ProjectStack]
) -> tuple[dict[str, Any], bool]:
    """Update the VSCode launch configuration of the active stacks"""
    updated = False

    res = VscodeLaunch.add_launch_version(json_data)
    if res:
        updated = True
        json_data = res

    for input_type in [a for a in filter_by_stack(VscodeInput, stacks) if a.enum_type != InputType.TASK]:
        res = input_type.add_tasks_input(json_data, LAUNCH_INPUT_QUERY)
        if res:
            updated = True
            json_data = res

    for launch in filter_by_stack(VscodeLaunch, stacks):
        res = launch.add_launch_config(json_data, _launch_substituter, working_path)
        if res:
            updated = True
            json_data = res

    return json_data, updated


def _update_input_props(json_data: dict[str, Any], stacks: set[ProjectStack]) -> tuple[dict[str, Any], bool]:
    """Update the VSCode input properties of the active stacks"""
    updated = False
    for stack in sort_stacks(stacks):
        for key, value in DEFAULT_PROPS.get(stack, {}).items():
            snake_query: str = f'.settings.["{key}"]'
            result = jq.compile(snake_query).input(json_data).first()
            if result is None:
                prompt: str = f"Enter the value a value for {key}"
                value = get_input_or_default(prompt, value)
                jq_query = f"{snake_query} = {json.dumps(value)}"
                json_data = jq.compile(jq_query).input(json_data).first()
                updated = True

    return json_data, updated


def _update_file_associations(json_data: dict[str, Any], stacks: set[ProjectStack]) -> tuple[dict[str, Any], bool]:
    """Update the file associations of the active stacks in workspace"""
    updated = False
    for stack in sort_stacks(stacks):
        for key, value in stack.file_associations.items():
            file_query: str = f'{FILE_ASSOCIATION_QUERY}.["{key}"]'
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
        launch = launch.replace(SUBSTITUTE_SHELL_TAG, get_property("shell"))
    if SUBSTITUTE_PROJECT_TAG in launch:
        launch = launch.replace(SUBSTITUTE_PROJECT_TAG, FOLDER)
    return launch
