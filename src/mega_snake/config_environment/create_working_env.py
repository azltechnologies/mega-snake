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
    type=click.Choice(selectable_keys(), case_sensitive=False),
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
    _configure_tools(workspace_file, active_stacks, bool(stacks))
    _add_default_settings(workspace_file, working_path, active_stacks)


def _configure_tools(workspace_file: str, stacks: set[ProjectStack], explicit: bool) -> None:
    """Run the Java, Gradle and Maven configuration steps of the active stacks.

    The stacks that are not active are collected and reported together, once, instead of one message
    each: `working-env` is the friendly entry point, and a repository with no JVM build file used to
    be told about Java, Gradle *and* Maven on every single run -- the Java-centric default this
    module set out to remove, moved from the settings file into the console. Nothing went wrong when
    a stack is absent, so the report goes through `ws_advice` rather than `ws_warning`.

    Parameters:
        workspace_file: Path to the workspace settings file.
        stacks: The active stacks.
        explicit: Whether the stacks were selected through --stack instead of being detected; the
            skip reason reported to the user depends on it.

    Raises:
        None

    Returns:
        None
    """
    skipped: list[tuple[ProjectStack, Optional[str]]] = []
    if ProjectStack.JAVA in stacks:
        set_java(False, workspace_file)
    else:
        skipped.append((ProjectStack.JAVA, java_command.name))
    if ProjectStack.GRADLE in stacks:
        set_gradle(False, workspace_file)
    else:
        skipped.append((ProjectStack.GRADLE, gradle_command.name))
    if ProjectStack.MAVEN in stacks:
        set_maven(None, workspace_file)
    else:
        skipped.append((ProjectStack.MAVEN, maven_command.name))
    _skipped_stacks_advice(skipped, explicit)


def _skipped_stacks_advice(skipped: list[tuple[ProjectStack, Optional[str]]], explicit: bool) -> None:
    """Report the stacks that were skipped, in a single message, and how to configure them anyway.

    The reason has to follow the selection: an explicit --stack replaces the detection entirely, so
    blaming a missing marker file there would send the user looking for a build file that may well
    be sitting in the directory. The per-stack marker names are therefore only listed when the
    stacks were detected.

    `force` is passed to `ws_advice` because the message is addressed to the user, not to a
    developer debugging the tool: without it the line is only printed at DEBUG level, and the way to
    configure a skipped stack would be invisible to everyone running `working-env` normally.

    Parameters:
        skipped: The stacks left out, paired with the name of the command that configures each one
            on demand, as click knows it.
        explicit: Whether the stacks were selected through --stack instead of being detected.

    Raises:
        None

    Returns:
        None
    """
    if not skipped:
        return
    names: str = ", ".join(stack.key for stack, _ in skipped)
    if explicit:
        reason: str = "they are not part of the stacks selected with --stack"
    else:
        reason = "no marker file revealed them in the current directory"
    details: list[str] = []
    for stack, command_name in skipped:
        hint: str = f"'{APP_NAME} {command_name}' configures it anyway"
        if not explicit:
            markers: str = ", ".join(stack.markers)
            found: str = f"no {markers}" if markers else "no build file declares it"
            hint = f"{found} -- {hint}"
        details.append(f"\t{stack.key}: {hint}")
    details.append(f"\tor '{APP_NAME} {create_working_env.name} --stack <stack>' for a whole stack")
    ws_advice(f"Skipping the {names} configuration: {reason}.\n" + "\n".join(details), force=True)


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


def _add_default_settings(workspace_file: str, working_path: str, active_stacks: set[ProjectStack]) -> None:
    """
    Adds default settings to the workspace file.

    Args:
        workspace_file (str): The workspace file path
        working_path (str): The working path
        active_stacks (set[ProjectStack]): The active stacks, so that every artifact written belongs
            to a stack the project actually uses. Required: a default would let a caller that forgets
            it write a workspace ignoring the user's --stack selection, with nothing to reveal it
    """
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


def _get_recommended_extensions(stacks: set[ProjectStack]) -> list[str]:
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
    workspace_extensions: list[str] = _get_recommended_extensions(stacks)
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
    """Register the log watchers of the active stacks in the workspace file.

    Entries already present are kept: `add_watcher` deduplicates by title, so a watcher a
    previous run wrote for a stack that is no longer selected is never taken away.

    Parameters:
        json_data: The parsed workspace file to update in place.
        working_path: Path of the working folder the entries are anchored to.
        stacks: The active stacks; every member of an inactive stack is left out.

    Raises:
        None

    Returns:
        tuple[dict[str, Any], bool]: The workspace data, and whether anything was added.
    """
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
    """Write the VS Code tasks of the active stacks, plus the inputs those tasks call.

    The `tasks` block itself is only scaffolded when at least one task survives the stack
    filter: a workspace with nothing to run must not be given a bare `version` key and an
    input nothing interpolates.

    Parameters:
        json_data: The parsed workspace file to update in place.
        working_path: Path of the working folder the entries are anchored to.
        stacks: The active stacks; every member of an inactive stack is left out.

    Raises:
        None

    Returns:
        tuple[dict[str, Any], bool]: The workspace data, and whether anything was added.
    """
    updated = False

    # The version and the inputs are the container of the tasks, and nothing else consumes them:
    # `todayTimestamp` is only ever interpolated into a task command. Writing them for a workspace
    # with no active task would leave a `"version": "2.0.0"` block holding an input nobody calls,
    # which is what the module promises not to do.
    active_tasks: list[VscodeTask] = filter_by_stack(VscodeTask, stacks)
    if not active_tasks:
        return json_data, False

    res = VscodeTask.add_tasks_version(json_data)
    if res:
        updated = True
        json_data = res

    for input_type in [a for a in filter_by_stack(VscodeInput, stacks) if a.enum_type != InputType.LAUNCH]:
        res = input_type.add_tasks_input(json_data, TASKS_INPUT_QUERY)
        if res:
            updated = True
            json_data = res

    for task in active_tasks:
        res = task.add_tasks_task(json_data, working_path)
        if res:
            updated = True
            json_data = res

    return json_data, updated


def _update_vscode_launch(
    json_data: dict[str, Any], working_path: str, stacks: set[ProjectStack]
) -> tuple[dict[str, Any], bool]:
    """Write the VS Code launch configurations of the active stacks, plus their inputs.

    Mirrors `_update_vscode_tasks`, including the empty-block guard: the `launch` key is
    only created when a configuration actually belongs to one of the active stacks.

    Parameters:
        json_data: The parsed workspace file to update in place.
        working_path: Path of the working folder the entries are anchored to.
        stacks: The active stacks; every member of an inactive stack is left out.

    Raises:
        None

    Returns:
        tuple[dict[str, Any], bool]: The workspace data, and whether anything was added.
    """
    updated = False

    # Same reasoning as the tasks above: the inputs of this block are only referenced by the launch
    # configurations themselves, through the log redirect their watcher builds.
    active_launches: list[VscodeLaunch] = filter_by_stack(VscodeLaunch, stacks)
    if not active_launches:
        return json_data, False

    res = VscodeLaunch.add_launch_version(json_data)
    if res:
        updated = True
        json_data = res

    for input_type in [a for a in filter_by_stack(VscodeInput, stacks) if a.enum_type != InputType.TASK]:
        res = input_type.add_tasks_input(json_data, LAUNCH_INPUT_QUERY)
        if res:
            updated = True
            json_data = res

    for launch in active_launches:
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
                prompt: str = f"Enter a value for {key}"
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
