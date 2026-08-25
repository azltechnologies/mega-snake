"""Module for the different PR queries."""

from enum import Enum
import json
from typing import Any, Optional
import jq
from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher
from mega_snake.config_environment.models.project_stack import ProjectStack
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
        ProjectStack.GRADLE,
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
        ProjectStack.GRADLE,
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
        ProjectStack.GRADLE,
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
        ProjectStack.JAVA,
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
        ProjectStack.GRADLE,
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
        ProjectStack.GRADLE,
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
        ProjectStack.GRADLE,
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
        ProjectStack.GRADLE,
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
        ProjectStack.MAVEN,
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
        ProjectStack.MAVEN,
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
        ProjectStack.MAVEN,
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
        ProjectStack.MAVEN,
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
        ProjectStack.MAVEN,
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
        stack: ProjectStack,
    ) -> None:
        """Initialize a VscodeTask enum member with all required VS Code task configuration fields.

        Parameters:
            label: The task label VS Code shows and other entries depend on.
            hidden: Whether the task is hidden from the task picker.
            task_type: The VS Code task type, when the task declares one.
            command: The command the task runs.
            args: The arguments passed to the command.
            detail: The description shown next to the label.
            watcher: The log watcher the task redirects its output into, when it has one.
            problem_matcher: The VS Code problem matcher, emitted verbatim.
            extra_args: Extra keys copied verbatim into the emitted task.
        stack: The stack the member belongs to. Explicit for every member on purpose: with a
            `ProjectStack.COMMON` default, an untagged member and a deliberately shared one were
            byte-identical, so forgetting the tag silently wrote the artifact into every workspace.

        Raises:
            None

        Returns:
            None
        """
        self.label = label
        self.stack = stack
        self.hidden = hidden
        self.task_type = task_type
        self.command = command
        self.args = args if args else []
        self.detail = detail
        self.watcher = watcher
        self.problem_matcher = problem_matcher if problem_matcher else []
        self.extra_args = extra_args if extra_args else {}

    def logger_args(self, working_path: str) -> list[str]:
        """Build the redirect arguments the task's watcher wants appended to its command line.

        Returned rather than appended to `self.args`: an enum member is a process-wide singleton, so
        `self.args.extend(...)` never decorated a copy of the task, it decorated *the* task for
        everything that touched it afterwards. A second `to_dict` on the same member emitted the
        redirect twice (`... > log 2>&1 > log 2>&1`, which VS Code would have run verbatim), and
        inside a single pytest process the growth leaked between test modules --
        `test_launch_input_calls_stay_inside_their_own_stacks` once shipped green over an empty loop
        for exactly that reason, its outcome decided by pytest's collection order.

        The redirect is rendered on every call instead of being memoized on the member: the whole
        point of this method is that a member carries nothing a previous call left behind, and a
        cache keyed on `working_path` would put that state straight back -- to save two
        `str.replace` calls. `reference_text` renders it a second time to find the `${input:...}`
        the redirect interpolates; that is the price of deciding which inputs to write before the
        members that call them, and it is cheaper than either sharing state through the enum or
        threading a pre-rendered string through every `to_dict` caller.

        Parameters:
            working_path: Path of the working folder the log file is anchored to.

        Raises:
            None

        Returns:
            list[str]: The redirect arguments, empty when the task has no watcher.
        """
        if not self.watcher:
            return []
        return self.watcher.get_pattern_date(working_path).split(" ")

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
        # A new list, never `self.args` itself: the emitted dict travels straight into `json.dumps`
        # and out to the caller, and aliasing the member's own list is how the redirect used to end
        # up welded onto the task permanently.
        args: list[str] = [*self.args, *self.logger_args(working_path)]
        if args:
            result["args"] = args
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
