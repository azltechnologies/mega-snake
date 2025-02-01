"""Module for the different PR queries."""

from enum import Enum
import json
import os
from typing import Any, Callable, Optional
import jq
from codename_snake.constants import MODULE_NAME, INTERPRETER_PATH
from codename_snake.config_environment.models.log_viewer_watcher import LogWatcher
from codename_snake.config_environment.models.vscode_task import VscodeTask

LAUNCH_CONFIG_QUERY = ".launch.configurations"
LAUNCH_VERSION_QUERY = ".launch.version"
LAUNCH_INPUT_QUERY = ".launch.inputs"
SUBSTITUTE_SHELL_TAG = "[SUBS_SHELL]"
SUBSTITUTE_PROJECT_TAG = "[SUBS_PROJECT]"
REMOTE_DEBUG_PORT_QUERY = "snake.java.remoteDebug.port"


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
    )
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
            "python": f"{os.getenv("PYTHONPATH")}/{INTERPRETER_PATH}",
            "console": "integratedTerminal",
        },
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
    ):
        self.task_name = task_name
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
        self.add_logger_args(working_path)
        if self.args:
            if self.task_type == "debugpy":
                result["args"] = " ".join(self.args)
            else:
                result["args"] = self.args
        for key, value in self.extra_args.items():
            result[key] = value
        return result

    def add_logger_args(self, working_path: str) -> None:
        """Adds the redirect arg to the task."""
        if self.watcher:
            output: str = self.watcher.get_pattern_date(working_path)
            self.args.extend(output.split(" "))

    @staticmethod
    def add_launch_version(json_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Adds the query to the workspace settings."""
        result = jq.compile(LAUNCH_VERSION_QUERY).input(json_data).first()
        if result:
            return None
        return jq.compile(f"{LAUNCH_VERSION_QUERY} = {json.dumps("0.2.0")}").input(json_data).first()

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
