"""Module for the different PR queries."""

from enum import Enum
import json
from typing import Any, Optional
import jq
from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher
from mega_snake.config_environment.models.vscode_input import VscodeInput, JAVA_DEBUG_PREFIX


TASKS_TASKS_QUERY = ".tasks.tasks"
TASKS_VERSION_QUERY = ".tasks.version"
TASKS_INPUT_QUERY = ".tasks.inputs"
GRADLE_LABEL_BUILD_NO_TEST = "Gradle Build No Test"
GRADLE_LABEL_NO_BUILD = "No Build"
GRADLE_LABEL_BUILD = "Gradle Build"
JAVA_LABEL_REMOTE_DEBUG = "Java Remote Debug Start"
DEBUG_LABEL_BUILD_NO_TEST = f"1 - {JAVA_DEBUG_PREFIX}{GRADLE_LABEL_BUILD_NO_TEST}"
DEBUG_LABEL_NO_BUILD = f"2 - {JAVA_DEBUG_PREFIX}{GRADLE_LABEL_NO_BUILD}"
DEBUG_LABEL_BUILD = f"3 - {JAVA_DEBUG_PREFIX}{GRADLE_LABEL_BUILD}"
GRADLE_CONFIG = "config:java.import.gradle.home"
GRADLE_LOC = f"${{{GRADLE_CONFIG}}}/bin/gradle"
GRADLE_WINDOWS_LOC = f"{GRADLE_LOC}.bat"
GRADLE_BUILD_NO_TEST_ARGS = ["clean", "build", "-x", "test"]
GRADLE_BUILD_ARGS = ["clean", "build"]
MAVEN_LOC = "${config:maven.executable.path}"
MAVEN_LABEL_CLEAN_INSTALL = "Maven Clean Install"
MAVEN_LABEL_TEST = "Maven Test"
MAVEN_LABEL_VERIFY = "Maven Verify"
MAVEN_LABEL_DEPENDENCY_TREE = "Maven Dependency Tree"
MAVEN_LABEL_SPRING_BOOT = "Maven Spring Boot Run"
MAVEN_CLEAN_INSTALL_ARGS = ["clean", "install"]
MAVEN_TEST_ARGS = ["test"]
MAVEN_VERIFY_ARGS = ["verify"]
MAVEN_DEPENDENCY_TREE_ARGS = ["dependency:tree"]
MAVEN_SPRING_BOOT_ARGS = ["spring-boot:run"]


class VscodeTask(Enum):
    """Enum for the different vscode tasks."""

    NO_BUILD = (
        GRADLE_LABEL_NO_BUILD,
        True,
        "shell",
        "echo",
        ["Skipping Gradle Building"],
        "No build task",
        None,
        None,
        None,
    )
    GRADLE_BUILD_NO_TEST = (
        GRADLE_LABEL_BUILD_NO_TEST,
        True,
        "shell",
        GRADLE_LOC,
        GRADLE_BUILD_NO_TEST_ARGS,
        "Run a gradle clean build without tests",
        LogWatcher.GRADLE_BUILD_NO_TEST,
        None,
        {"group": "build", "windows": {"command": GRADLE_WINDOWS_LOC, "args": GRADLE_BUILD_NO_TEST_ARGS}},
    )
    GRADLE_BUILD = (
        GRADLE_LABEL_BUILD,
        True,
        "shell",
        GRADLE_LOC,
        GRADLE_BUILD_ARGS,
        "Run a gradle clean build",
        LogWatcher.GRADLE_BUILD,
        None,
        {"group": "build", "windows": {"command": GRADLE_WINDOWS_LOC, "args": GRADLE_BUILD_ARGS}},
    )
    JAVA_REMOTE_DEBUG = (
        JAVA_LABEL_REMOTE_DEBUG,
        True,
        "shell",
        "java",
        [
            "-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=${config:mgsnake.java.remoteDebug.port}",
            "-Dspring.profiles.active=${config:mgsnake.java.remoteDebug.profile}",
            "-jar",
            "${config:mgsnake.java.remoteDebug.jar}",
        ],
        "Start a Java Remote Debug execution",
        LogWatcher.JAVA_DEBUG,
        None,
        {"isBackground": False},
    )
    DEBUG_BUILD_NO_TEST = (
        DEBUG_LABEL_BUILD_NO_TEST,
        False,
        None,
        None,
        None,
        "Debug java while building gradle without tests",
        None,
        None,
        {
            "dependsOn": [GRADLE_LABEL_BUILD_NO_TEST, JAVA_LABEL_REMOTE_DEBUG],
            "dependsOrder": "sequence",
        },
    )
    DEBUG_NO_BUILD = (
        DEBUG_LABEL_NO_BUILD,
        False,
        None,
        None,
        None,
        "Debug java without building gradle",
        None,
        None,
        {"dependsOn": [GRADLE_LABEL_NO_BUILD, JAVA_LABEL_REMOTE_DEBUG], "dependsOrder": "sequence"},
    )
    DEBUG_BUILD = (
        DEBUG_LABEL_BUILD,
        False,
        None,
        None,
        None,
        "Debug java while building gradle",
        None,
        None,
        {"dependsOn": [GRADLE_LABEL_BUILD, JAVA_LABEL_REMOTE_DEBUG], "dependsOrder": "sequence"},
    )
    RUN_JAVA_DEBUG = (
        "Run Java Debug",
        False,
        "process",
        VscodeInput.SELECT_BUILD.get_input_call(),
        None,
        "Debug java application",
        None,
        None,
        None,
    )
    MAVEN_CLEAN_INSTALL = (
        MAVEN_LABEL_CLEAN_INSTALL,
        False,
        "shell",
        MAVEN_LOC,
        MAVEN_CLEAN_INSTALL_ARGS,
        "Run maven clean install",
        LogWatcher.MAVEN_CLEAN_INSTALL,
        None,
        {"group": "build"},
    )
    MAVEN_TEST = (
        MAVEN_LABEL_TEST,
        False,
        "shell",
        MAVEN_LOC,
        MAVEN_TEST_ARGS,
        "Run maven test",
        LogWatcher.MAVEN_TEST,
        None,
        {"group": "build"},
    )
    MAVEN_VERIFY = (
        MAVEN_LABEL_VERIFY,
        False,
        "shell",
        MAVEN_LOC,
        MAVEN_VERIFY_ARGS,
        "Run maven verify",
        LogWatcher.MAVEN_VERIFY,
        None,
        {"group": "build"},
    )
    MAVEN_DEPENDENCY_TREE = (
        MAVEN_LABEL_DEPENDENCY_TREE,
        False,
        "shell",
        MAVEN_LOC,
        MAVEN_DEPENDENCY_TREE_ARGS,
        "Run maven dependency:tree",
        LogWatcher.MAVEN_DEPENDENCY_TREE,
        None,
        {"group": "build"},
    )
    MAVEN_SPRING_BOOT = (
        MAVEN_LABEL_SPRING_BOOT,
        False,
        "shell",
        MAVEN_LOC,
        MAVEN_SPRING_BOOT_ARGS,
        "Run maven spring-boot:run",
        LogWatcher.MAVEN_SPRING_BOOT,
        None,
        {"group": "build"},
    )

    def __init__(
        self,
        label: str,
        hidden: bool,
        task_type: Optional[str],
        command: Optional[str],
        args: Optional[list[str]],
        detail: str,
        watcher: Optional[LogWatcher],
        problem_matcher: Optional[Any],
        extra_args: Optional[dict[str, Any]],
    ) -> None:
        """Initialize a VscodeTask enum member with all required VS Code task configuration fields."""
        self.label = label
        self.hidden = hidden
        self.task_type = task_type
        self.command = command
        self.args = args if args else []
        self.detail = detail
        self.watcher = watcher
        self.problem_matcher = problem_matcher if problem_matcher else []
        self.extra_args = extra_args if extra_args else {}

    def add_logger_args(self, working_path: str) -> None:
        """Adds the redirect arg to the task."""
        if self.watcher:
            output: str = self.watcher.get_pattern_date(working_path)
            self.args.extend(output.split(" "))

    def to_dict(self, working_path: str) -> dict[str, Any]:
        """Converts the enum to a dictionary."""
        result: dict[str, Any] = {
            "label": self.label,
            "hide": self.hidden,
            "detail": self.detail,
            "problemMatcher": self.problem_matcher,
        }
        if self.task_type:
            result["type"] = self.task_type
        if self.command:
            result["command"] = self.command
        self.add_logger_args(working_path)
        if self.args:
            result["args"] = self.args
        for key, value in self.extra_args.items():
            result[key] = value
        return result

    @staticmethod
    def add_tasks_version(json_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Adds the query to the workspace settings."""
        result = jq.compile(TASKS_VERSION_QUERY).input(json_data).first()
        if result:
            return None
        return jq.compile(f"{TASKS_VERSION_QUERY} = {json.dumps('2.0.0')}").input(json_data).first()

    def add_tasks_task(self, json_data: dict[str, Any], working_path: str) -> Optional[dict[str, Any]]:
        """Adds the query to the workspace settings."""
        json_input = json_data
        result = jq.compile(TASKS_TASKS_QUERY).input(json_data).first()
        search_query: str = f'{TASKS_TASKS_QUERY}| map(select(.label == "{self.label}"))'
        if result:
            length_query: str = f"{search_query} | length"
            result = jq.compile(length_query).input(json_data).first()
            if result == 1:
                return None
            if result > 1:
                delete_query = search_query.replace("==", "!=")
                result = jq.compile(delete_query).input(json_data).first()
                jq_query = f"{TASKS_TASKS_QUERY} = {json.dumps(result)}"
                json_input = jq.compile(jq_query).input(json_input).first()
        jq_query = f"{TASKS_TASKS_QUERY} += [{json.dumps(self.to_dict(working_path))}]"
        return jq.compile(jq_query).input(json_input).first()
