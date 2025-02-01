"""This module contains the class representing a task/lanch input."""

from enum import Enum, auto
import json
from typing import Any, Optional, TYPE_CHECKING
import jq

if TYPE_CHECKING:
    from codename_snake.config_environment.models.vscode_task import VscodeTask

JAVA_DEBUG_PREFIX = "Java-debug: "


class InputType(Enum):
    """Enum class representing the input type."""

    TASK = auto()
    LAUNCH = auto()
    BOTH = auto()


class VscodeInput(Enum):
    """Enum class representing a task/lanch input."""

    TODAY_TIMESTAMP = (
        "todayTimestamp",
        "command",
        "shellCommand.execute",
        {
            "command": "python3 -c 'from datetime import datetime; print(datetime.now().strftime(\"%Y-%m-%d\"));'",
            "useSingleResult": True,
        },
        None,
        InputType.BOTH,
    )
    SELECT_BUILD = (
        "selectBuildTask",
        "command",
        "workbench.action.tasks.runTask",
        {"task": JAVA_DEBUG_PREFIX},
        None,
        InputType.TASK,
    )

    input_id: str
    input_type: str
    input_command: Optional[str]
    input_args: Optional[dict[str, str]]
    input_options: Optional[list[str]]
    input_default: Optional[str]
    input_description: Optional[str]
    enum_type: InputType

    def __init__(
        self,
        input_id: str,
        input_type: str,
        input_command: Optional[str],
        input_args: Optional[dict[str, str]],
        input_description: str,
        enum_type: InputType,
    ):
        self.input_id = input_id
        self.input_type = input_type
        self.input_command = input_command
        self.input_args = input_args
        self.input_options = None
        self.input_default = None
        self.input_description = input_description
        self.enum_type = enum_type

    def to_dict(self) -> dict[str, Any]:
        """Converts the enum to a dictionary."""
        result: dict[str, Any] = {
            "id": self.input_id,
            "type": self.input_type,
        }
        if self.input_command:
            result["command"] = self.input_command
        if self.input_args:
            result["args"] = self.input_args
        if self.input_default:
            result["default"] = self.input_default
        if self.input_options:
            result["options"] = self.input_options
        if self.input_description:
            result["description"] = self.input_description
        return result

    def get_input_call(self) -> str:
        """Returns the input call."""
        return f"${{input:{self.input_id}}}"

    def add_task_arg(self, task: "VscodeTask") -> None:
        """Adds the task arg to the input."""
        if not self.input_args:
            self.input_args = {}
        self.input_args["task"] = task.label

    def add_tasks_input(self, json_data: dict[str, Any], input_query: str) -> Optional[dict[str, Any]]:
        """Adds the query to the workspace settings."""
        json_input = json_data
        result = jq.compile(input_query).input(json_data).first()
        search_query: str = f'{input_query}| map(select(.id == "{self.input_id}"))'
        if result:
            length_query: str = f"{search_query} | length"
            result = jq.compile(length_query).input(json_data).first()
            if result == 1:
                return None
            if result > 1:
                delete_query = search_query.replace("==", "!=")
                result = jq.compile(delete_query).input(json_data).first()
                jq_query = f"{input_query} = {json.dumps(result)}"
                json_input = jq.compile(jq_query).input(json_input).first()
        jq_query = f"{input_query} += [{json.dumps(self.to_dict())}]"
        return jq.compile(jq_query).input(json_input).first()
