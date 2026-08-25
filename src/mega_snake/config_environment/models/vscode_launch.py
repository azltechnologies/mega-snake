"""Module for the different PR queries."""

from enum import Enum
import json
import os
from typing import Any, Callable, Optional
import jq
from mega_snake.constants import MODULE_NAME, INTERPRETER_PATH
from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher
from mega_snake.config_environment.models.project_stack import ProjectStack
from mega_snake.config_environment.models.vscode_task import VscodeTask

LAUNCH_CONFIG_QUERY = ".launch.configurations"
LAUNCH_VERSION_QUERY = ".launch.version"
LAUNCH_INPUT_QUERY = ".launch.inputs"
SUBSTITUTE_SHELL_TAG = "[SUBS_SHELL]"
SUBSTITUTE_PROJECT_TAG = "[SUBS_PROJECT]"
REMOTE_DEBUG_PORT_QUERY = "mgsnake.java.remoteDebug.port"


class VscodeLaunch(Enum):
    """Enum for the different PR queries."""

    DEBUG_JAVA = (
        "JAVA DEBUG (Attach)",
        "java",
        "attach",
        None,
        None,
        None,
        [VscodeTask.JAVA_REMOTE_DEBUG],
        {
            "port": f"${{config:{REMOTE_DEBUG_PORT_QUERY}}}",
            "hostName": "localhost",
            "projectName": SUBSTITUTE_PROJECT_TAG,
        },
        ProjectStack.JAVA,
    )
    # Debugs the mega-snake CLI itself, so it belongs to the opt-in development stack: without the
    # marker file it is written to no workspace at all, which is what keeps it out of a user's
    # Python project (§1 of the copilot instructions).
    DEBUG_PYTHON_SNAKE = (
        "PYTHON DEBUG (Snake)",
        "debugpy",
        "launch",
        None,
        ["--shell", SUBSTITUTE_SHELL_TAG, "-l", "debug", "msg", "hello world!"],
        None,
        None,
        {
            "module": MODULE_NAME,
            "python": f"{os.getenv('PYTHONPATH')}/{INTERPRETER_PATH}",
            "console": "integratedTerminal",
        },
        ProjectStack.SNAKE,
    )
    DEBUG_PYTHON_FILE = (
        "PYTHON DEBUG (File)",
        "debugpy",
        "launch",
        None,
        None,
        LogWatcher.GENERIC,
        None,
        {"program": "${file}"},
        ProjectStack.PYTHON,
    )
    DEBUG_PYTHON_MODULE = (
        "PYTHON DEBUG (Module)",
        "debugpy",
        "launch",
        {"PYTHONPATH": "${fileDirnameBasename}"},
        None,
        LogWatcher.GENERIC,
        None,
        {"module": "${fileDirnameBasename}"},
        ProjectStack.PYTHON,
    )

    def __init__(
        self,
        task_name: str,
        task_type: str,
        request: str,
        env: Optional[dict[str, str]],
        args: Optional[list[str]],
        watcher: Optional[LogWatcher],
        depends_on: Optional[list[VscodeTask]],
        extra_args: Optional[dict[str, Any]],
        stack: ProjectStack,
    ) -> None:
        """Initialize a VscodeLaunch enum member with all required VS Code launch configuration fields.

        Parameters:
            task_name: The configuration name VS Code shows in the debug picker.
            task_type: The debug adapter type.
            request: The debug request kind (`launch` or `attach`).
            env: Environment variables handed to the debuggee.
            args: The arguments passed to the debuggee.
            watcher: The log watcher the configuration redirects its output into, when it has one.
            depends_on: The tasks that must run before this configuration.
            extra_args: Extra keys copied verbatim into the emitted configuration.
        stack: The stack the member belongs to. Explicit for every member on purpose: with a
            `ProjectStack.COMMON` default, an untagged member and a deliberately shared one were
            byte-identical, so forgetting the tag silently wrote the artifact into every workspace.

        Raises:
            None

        Returns:
            None
        """
        self.task_name = task_name
        self.stack = stack
        self.task_type = task_type
        self.request = request
        self.env = env if env else {}
        self.args = args if args else []
        self.watcher = watcher
        self.depends_on = depends_on if depends_on else []
        self.extra_args = extra_args if extra_args else {}

    def to_dict(self, working_path: str) -> dict[str, Any]:
        """Converts the enum to a dictionary."""
        result: dict[str, Any] = {"name": self.task_name, "type": self.task_type, "request": self.request}
        if self.env:
            result["env"] = self.env
        # A new list, never `self.args` itself -- see `logger_args` below.
        args: list[str] = [*self.args, *self.logger_args(working_path)]
        if args:
            if self.task_type == "debugpy":
                result["args"] = " ".join(args)
            else:
                result["args"] = args
        for key, value in self.extra_args.items():
            result[key] = value
        return result

    def logger_args(self, working_path: str) -> list[str]:
        """Build the redirect arguments the configuration's watcher wants appended to its args.

        Returned rather than appended to `self.args`, for the reason spelled out in full on
        `VscodeTask.logger_args`: an enum member is a process-wide singleton, so extending its own
        `args` welded the redirect onto the configuration for the rest of the process. This
        `to_dict` joins the arguments with `" "` for the `debugpy` type, which is why the two call
        sites had to be turned into pure builders together -- they do not compose the emitted value
        identically and could not be changed one at a time.

        Parameters:
            working_path: Path of the working folder the log file is anchored to.

        Raises:
            None

        Returns:
            list[str]: The redirect arguments, empty when the configuration has no watcher.
        """
        if not self.watcher:
            return []
        return self.watcher.get_pattern_date(working_path).split(" ")

    @staticmethod
    def add_launch_version(json_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Adds the query to the workspace settings."""
        result = jq.compile(LAUNCH_VERSION_QUERY).input(json_data).first()
        if result:
            return None
        return jq.compile(f"{LAUNCH_VERSION_QUERY} = {json.dumps('0.2.0')}").input(json_data).first()

    def add_launch_config(
        self, json_data: dict[str, Any], string_substituter: Callable[[str], str], working_path: str
    ) -> Optional[dict[str, Any]]:
        """Adds the query to the workspace settings."""
        json_input = json_data
        result = jq.compile(LAUNCH_CONFIG_QUERY).input(json_data).first()
        search_query: str = f'{LAUNCH_CONFIG_QUERY}| map(select(.name == "{self.task_name}"))'
        if result:
            length_query: str = f"{search_query} | length"
            result = jq.compile(length_query).input(json_data).first()
            if result == 1:
                return None
            if result > 1:
                delete_query = search_query.replace("==", "!=")
                result = jq.compile(delete_query).input(json_data).first()
                jq_query = f"{LAUNCH_CONFIG_QUERY} = {json.dumps(result)}"
                json_input = jq.compile(jq_query).input(json_input).first()
        jq_query = f"{LAUNCH_CONFIG_QUERY} += [{string_substituter(json.dumps(self.to_dict(working_path)))}]"
        return jq.compile(jq_query).input(json_input).first()
