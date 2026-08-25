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

    # TODO(#55-followup): stop mutating the enum member; build the args locally instead.
    #
    # `self.args.extend(...)` writes into the enum member, and an enum member is a process-wide
    # singleton -- so the redirect is not appended to a copy of the task, it is appended to *the*
    # task, permanently, for everything that touches it afterwards.
    #
    # Confirmed, not suspected:
    #
    #     >>> t = VscodeTask.GRADLE_BUILD
    #     >>> t.args
    #     ['clean', 'build']
    #     >>> t.to_dict("wp")["args"][-3:]
    #     ['>', "'wp/logs/clean_build_${input:todayTimestamp}.log'", '2>&1']
    #     >>> t.to_dict("wp")["args"].count("2>&1")
    #     2
    #
    # Two consequences, one latent and one that has already cost us:
    #
    # 1. NOT LATENT IN THE SUITE, only in production: a second `to_dict` on the same member emits
    #    the redirect twice, which VS Code would run as `... > log 2>&1 > log 2>&1`. No *user* has
    #    seen it -- `_update_vscode_tasks` and `_update_vscode_launch` iterate each member exactly
    #    once per run, and the process exits afterwards. Inside one pytest process it already
    #    happens: `test_create_working_env.py` drives `update_vscode_launch(..., PYTHON_STACKS)`
    #    from more than one test, so `DEBUG_PYTHON_FILE`/`DEBUG_PYTHON_MODULE` do accumulate the
    #    redirect. Nothing catches it because the only assertion on the emitted `args` compares
    #    `result["args"]` against `member.args` *after* the mutation, which is true either way; the
    #    first exact-value assertion anyone writes on a task's args turns collection-order
    #    dependent. That is the same accumulation as point 2, reached from the other direction.
    #
    # 2. ALREADY BIT US: within a single pytest process the mutation leaks between test modules.
    #    `test_launch_input_calls_stay_inside_their_own_stacks` shipped green over an empty loop
    #    because in a fresh interpreter `args` does not contain the redirect, while any earlier test
    #    that called `to_dict` would have retroactively put it there -- making the test's result
    #    depend on pytest's collection order. `reference_text` in
    #    `src/mega_snake/config_environment/models/reference_text.py` (used from both this module's
    #    caller and `test_stack_references.py`) now asks the watcher for the rendered redirect rather
    #    than reading `args`, precisely to stay out of this.
    #
    # The fix is small and local: leave `self.args` alone and have `to_dict` compose the value it
    # emits, e.g. `args = [*self.args, *self._logger_args(working_path)]`, turning this method into a
    # pure builder. `VscodeLaunch.add_logger_args` is the same code and needs the same treatment, and
    # its `to_dict` joins the list with `" "` for `debugpy`, so both call sites must be updated
    # together.
    #
    # Deliberately not done in this pull request: it changes a model shared by every emitted task and
    # launch configuration, in a change set already several review rounds deep, and it is orthogonal
    # to stack detection. It needs its own commit and its own test -- one that calls `to_dict` twice
    # and asserts the redirect appears exactly once, which is the assertion nothing makes today.
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
