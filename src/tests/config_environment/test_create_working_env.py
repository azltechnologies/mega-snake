"""Test the java_set module."""

import builtins
import json
from unittest.mock import MagicMock, patch, mock_open
from typing import Generator, Any
import jq
from click.testing import CliRunner
import pytest
from mega_snake.config_environment.create_working_env import (
    create_working_env,
    get_recommended_extensions,
    _get_workspace_file as get_workspace_file,
    _git_exclude as git_exclude,
    _add_default_settings as add_default_settings,
    _configure_tools as configure_tools,
    _launch_substituter as launch_substituter,
    EXTENSIONS_QUERY,
    GIT_BLAME_QUERY,
    DEFAULT_PROPS,
    FILE_ASSOCIATION_QUERY,
)
from mega_snake.config_environment.models.github_queries import (
    PrQueries,
    IssuesQueries,
    GH_PR_QUERY,
    GH_ISSUES_QUERY,
)
from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher, LOG_WATCHER_QUERY
from mega_snake.config_environment.models.vscode_task import (
    VscodeTask,
    TASKS_INPUT_QUERY,
    TASKS_TASKS_QUERY,
    TASKS_VERSION_QUERY,
)
from mega_snake.config_environment.models.vscode_launch import (
    VscodeLaunch,
    LAUNCH_CONFIG_QUERY,
    LAUNCH_VERSION_QUERY,
    LAUNCH_INPUT_QUERY,
)
from mega_snake.config_environment.models.vscode_input import VscodeInput, InputType
from mega_snake.config_environment.models.project_stack import ProjectStack, filter_by_stack, sort_stacks
from mega_snake.util.util import load_json_with_comments
from mega_snake.util.formatting import UserDeclinedError


ALL_STACKS: set[ProjectStack] = set(ProjectStack)
PYTHON_STACKS: set[ProjectStack] = {ProjectStack.COMMON, ProjectStack.PYTHON}
GRADLE_CMD_NAME = "gradle_command"
WK_FILE = "some_file.txt"
WK_PARENTH_PATH = "/root/parent_folder"
WK_BASENAME_PATH = "some_path"
WK_PATH = f"{WK_PARENTH_PATH}/{WK_BASENAME_PATH}"
CURRENT_PATH = "my_path"
FOLDER = "folder_name"
NEW_WORKSPACE_CONTENTS = {"prop": "value", "another_prop": 2}
EMPTY_WK_FILE: str = "src/tests/gradle/empty.code-workspace"
DARWIN_WK_FILE: str = "src/tests/gradle/darwin.code-workspace"
OS = "Windows"

real_open = builtins.open


@pytest.fixture(name="shutil_which")
def fixture_shutil_copyfile() -> Generator[MagicMock, None, None]:
    """Mock shutil.which"""
    with patch("mega_snake.config_environment.create_working_env.shutil") as mock:
        yield mock.which


@pytest.fixture(name="get_validated_input")
def fixture_get_validated_input() -> Generator[MagicMock, None, None]:
    """Mock get_validated_input"""
    with patch("mega_snake.config_environment.create_working_env.get_validated_input") as mock:
        yield mock


@pytest.fixture(name="ws_warning")
def fixture_ws_warning() -> Generator[MagicMock, None, None]:
    """Mock ws_warning"""
    with patch("mega_snake.config_environment.create_working_env.ws_warning") as mock:
        yield mock


@pytest.fixture(name="ws_success")
def fixture_ws_success() -> Generator[MagicMock, None, None]:
    """Mock ws_success"""
    with patch("mega_snake.config_environment.create_working_env.ws_success") as mock:
        yield mock


@pytest.fixture(name="ws_advice")
def fixture_ws_advice() -> Generator[MagicMock, None, None]:
    """Mock ws_advice"""
    with patch("mega_snake.config_environment.create_working_env.ws_advice") as mock:
        yield mock


@pytest.fixture(name="get_command_return_code")
def fixture_get_command_return_code() -> Generator[MagicMock, None, None]:
    """Mock get_command_return_code"""
    with patch("mega_snake.config_environment.create_working_env.get_command_return_code", autospec=True) as mock:
        yield mock


@pytest.fixture(name="mk_get_workspace_file")
def fixture_mk_get_workspace_file() -> Generator[MagicMock, None, None]:
    """Mock _get_workspace_file"""
    with patch("mega_snake.config_environment.create_working_env._get_workspace_file") as mock:
        yield mock


@pytest.fixture(name="mk_get_working_path")
def fixture_get_working_path() -> Generator[MagicMock, None, None]:
    """Mock the shared ensure_working_path utility consumed by create_working_env"""
    with patch("mega_snake.config_environment.create_working_env.ensure_working_path") as mock:
        yield mock


@pytest.fixture(name="mk_git_exclude")
def fixture_git_exclude() -> Generator[MagicMock, None, None]:
    """Mock _git_exclude"""
    with patch("mega_snake.config_environment.create_working_env._git_exclude") as mock:
        yield mock


@pytest.fixture(name="initial_load")
def fixture_initial_load() -> Generator[MagicMock, None, None]:
    """Mock initial_load"""
    with patch("mega_snake.config_environment.create_working_env.initial_load") as mock:
        yield mock


@pytest.fixture(name="set_java")
def fixture_set_java() -> Generator[MagicMock, None, None]:
    """Mock set_java"""
    with patch("mega_snake.config_environment.create_working_env.set_java") as mock:
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock, None, None]:
    """Mock os"""
    with patch("mega_snake.config_environment.create_working_env.os") as mock:
        yield mock


@pytest.fixture(name="set_gradle")
def fixture_set_gradle() -> Generator[MagicMock, None, None]:
    """Mock set_gradle"""
    with patch("mega_snake.config_environment.create_working_env.set_gradle") as mock:
        yield mock


@pytest.fixture(name="_gradle_command")
def fixture_gradle_command() -> Generator[MagicMock, None, None]:
    """Mock gradle_command"""
    with patch("mega_snake.config_environment.create_working_env.gradle_command") as mock:
        mock.name = GRADLE_CMD_NAME
        yield mock


@pytest.fixture(name="set_maven")
def fixture_set_maven() -> Generator[MagicMock, None, None]:
    """Mock set_maven"""
    with patch("mega_snake.config_environment.create_working_env.set_maven") as mock:
        yield mock


@pytest.fixture(name="_maven_command")
def fixture_maven_command() -> Generator[MagicMock, None, None]:
    """Mock maven_command"""
    with patch("mega_snake.config_environment.create_working_env.maven_command") as mock:
        mock.name = "set-maven"
        yield mock


@pytest.fixture(name="_java_command")
def fixture_java_command() -> Generator[MagicMock, None, None]:
    """Mock java_command"""
    with patch("mega_snake.config_environment.create_working_env.java_command") as mock:
        mock.name = "set-java"
        yield mock


@pytest.fixture(name="ws_info")
def fixture_ws_info() -> Generator[MagicMock, None, None]:
    """Mock ws_info"""
    with patch("mega_snake.config_environment.create_working_env.ws_info") as mock:
        yield mock


@pytest.fixture(name="mk_resolve_stacks")
def fixture_mk_resolve_stacks() -> Generator[MagicMock, None, None]:
    """Mock resolve_stacks so the active stacks do not depend on the repository running the tests"""
    with patch("mega_snake.config_environment.create_working_env.resolve_stacks") as mock:
        mock.return_value = ALL_STACKS
        yield mock


@pytest.fixture(name="mk_add_recommended_extensions")
def fixture_add_recommended_extensions() -> Generator[MagicMock, None, None]:
    """Mock _add_recommended_extensions"""
    with patch("mega_snake.config_environment.create_working_env._add_recommended_extensions") as mock:
        yield mock


@pytest.fixture(name="mk_add_default_settings")
def fixture_mk_add_default_settings() -> Generator[MagicMock, None, None]:
    """Mock _add_default_settings"""
    with patch("mega_snake.config_environment.create_working_env._add_default_settings") as mock:
        yield mock


@pytest.fixture(name="execute")
def fixture_execute() -> Generator[MagicMock, None, None]:
    """Mock execute"""
    with patch("mega_snake.config_environment.create_working_env._execute") as mock:
        yield mock


@pytest.fixture(name="get_property")
def fixture_get_property() -> Generator[MagicMock, None, None]:
    """Mock get_property"""

    def f_side_effect(prop: str) -> str:
        """side effect for get_property_mock"""
        if prop == "workspace_file":
            return WK_FILE
        elif prop == "working_path":
            return WK_PATH
        elif prop == "shell":
            return OS

    with patch("mega_snake.config_environment.create_working_env.get_property", side_effect=f_side_effect) as mock:
        yield mock


@pytest.fixture(name="mk_json")
def fixture_mk_json() -> Generator[MagicMock, None, None]:
    """Mock json"""
    with patch("mega_snake.config_environment.create_working_env.json") as mock:
        yield mock


@pytest.fixture(name="_mk_folder_const")
def fixture_mk_folder_const() -> Generator[MagicMock, None, None]:
    """Mock FOLDER constant"""
    with patch("mega_snake.config_environment.create_working_env.FOLDER", FOLDER) as mock:
        yield mock


@pytest.fixture(name="_mk_new_wk_contents")
def fixture_mk_new_wk_contents() -> Generator[MagicMock, None, None]:
    """Mock NEW_WORKSPACE_CONTENTS constant"""
    with patch(
        "mega_snake.config_environment.create_working_env.NEW_WORKSPACE_CONTENTS", NEW_WORKSPACE_CONTENTS
    ) as mock:
        yield mock


@pytest.fixture(name="mk_exclude_from_git")
def fixture_mk_exclude_from_git() -> Generator[MagicMock, None, None]:
    """Mock the shared exclude_from_git utility consumed by create_working_env"""
    with patch("mega_snake.config_environment.create_working_env.exclude_from_git") as mock:
        yield mock


@pytest.fixture(name="mk_input")
def fixture_mk_input() -> Generator[MagicMock, None, None]:
    """Mock input"""
    with patch("builtins.input") as mock:
        yield mock


@pytest.fixture(name="os_replace")
def fixture_os_replace() -> Generator[MagicMock, None, None]:
    """Mock os_replace"""
    with patch("mega_snake.config_environment.util.os") as mock:
        yield mock.replace


@pytest.fixture(name="get_remote_url")
def fixture_get_remote_url() -> Generator[MagicMock, None, None]:
    """Mock get_remote_url"""
    with patch("mega_snake.config_environment.create_working_env.Repo.get_remote_url") as mock:
        yield mock


def reset_mocks(*mocks: MagicMock) -> None:
    """Reset all mocks"""
    for mock in mocks:
        mock.reset_mock()


def flat_default_props(stacks: set[ProjectStack]) -> dict[str, Any]:
    """Flatten the per-stack default properties in the order the command writes them"""
    props: dict[str, Any] = {}
    for stack in sort_stacks(stacks):
        props.update(DEFAULT_PROPS.get(stack, {}))
    return props


def flat_file_associations(stacks: set[ProjectStack]) -> dict[str, str]:
    """Flatten the per-stack file associations in the order the command writes them"""
    associations: dict[str, str] = {}
    for stack in sort_stacks(stacks):
        associations.update(stack.file_associations)
    return associations


def written_workspace(write_mock: MagicMock) -> dict[str, Any]:
    """Rebuild the workspace contents from every write performed on the mocked file"""
    contents: list[str] = []
    for current_call in write_mock.mock_calls:
        args = [arg for arg in current_call.args if arg]
        if args:
            contents.append("".join(set(current_call.args)))
    return json.loads("".join(contents))


def test_command(
    shutil_which: MagicMock,
    get_validated_input: MagicMock,
    ws_warning: MagicMock,
    get_command_return_code: MagicMock,
    execute: MagicMock,
) -> None:
    """Test gradle command"""

    runner = CliRunner()
    result = None

    def mocks_reset() -> None:
        """reset Mocks"""
        nonlocal result
        result = None
        reset_mocks(
            shutil_which,
            get_validated_input,
            ws_warning,
            get_command_return_code,
            execute,
        )

    # Test when git is installed and git repo exists
    shutil_which.return_value = True
    get_command_return_code.return_value = 0
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_command_return_code.assert_called_once()
    get_validated_input.assert_not_called()
    ws_warning.assert_not_called()
    execute.assert_called_once_with(True, ())
    mocks_reset()

    # Test that the requested stacks are forwarded to the execution
    shutil_which.return_value = True
    get_command_return_code.return_value = 0
    result = runner.invoke(create_working_env, ["--stack", "java", "-s", "node"])
    assert result.exit_code == 0
    execute.assert_called_once_with(True, ("java", "node"))
    mocks_reset()

    # Test that an unknown stack is rejected before anything is configured
    result = runner.invoke(create_working_env, ["--stack", "cobol"])
    assert result.exit_code == 2
    execute.assert_not_called()
    mocks_reset()

    # Test when git is not installed and user chooses not to proceed in creating the workspace
    shutil_which.return_value = False
    get_validated_input.return_value = "n"
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_called_once()
    ws_warning.assert_called_once_with("Git is required to configure the workspace. Exiting...")
    get_command_return_code.assert_not_called()
    execute.assert_not_called()
    mocks_reset()

    # Test when git is installed but there's no repo and user chooses not to proceed in creating the workspace
    shutil_which.return_value = True
    get_command_return_code.return_value = 1
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_called_once()
    get_command_return_code.assert_called_once()
    ws_warning.assert_called_once_with("Not inside a git repository. Exiting...")
    execute.assert_not_called()
    mocks_reset()

    # Test when git is not installed and user chooses to proceed in creating the workspace
    shutil_which.return_value = False
    get_validated_input.return_value = "y"
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_called_once()
    ws_warning.assert_not_called()
    get_command_return_code.assert_not_called()
    execute.assert_called_once_with(False, ())
    mocks_reset()

    # Test when git is installed but there's no repo and user chooses to proceed in creating the workspace
    shutil_which.return_value = True
    get_command_return_code.return_value = 1
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_called_once()
    get_command_return_code.assert_called_once()
    ws_warning.assert_not_called()
    execute.assert_called_once_with(False, ())
    mocks_reset()


def test_execute(
    shutil_which: MagicMock,
    get_validated_input: MagicMock,
    ws_warning: MagicMock,
    ws_info: MagicMock,
    mk_get_workspace_file: MagicMock,
    mk_get_working_path: MagicMock,
    get_command_return_code: MagicMock,
    mk_git_exclude: MagicMock,
    initial_load: MagicMock,
    set_java: MagicMock,
    _java_command: MagicMock,
    set_gradle: MagicMock,
    _gradle_command: MagicMock,
    set_maven: MagicMock,
    _maven_command: MagicMock,
    mk_resolve_stacks: MagicMock,
    mk_add_default_settings: MagicMock,
) -> None:
    """Test the workspace configuration flow, including the stacks it configures"""

    runner = CliRunner()
    mk_get_workspace_file.return_value = WK_FILE
    mk_get_working_path.return_value = WK_PATH
    result = None

    def mocks_reset() -> None:
        nonlocal result
        result = None
        reset_mocks(
            shutil_which,
            get_validated_input,
            ws_warning,
            ws_info,
            mk_get_workspace_file,
            mk_get_working_path,
            get_command_return_code,
            mk_git_exclude,
            initial_load,
            set_java,
            set_gradle,
            set_maven,
            mk_resolve_stacks,
            mk_add_default_settings,
        )
        mk_resolve_stacks.return_value = ALL_STACKS

    # Test when git_repo is false and every stack is active
    shutil_which.return_value = False
    get_validated_input.return_value = "y"
    mk_resolve_stacks.return_value = ALL_STACKS
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_called_once()
    get_command_return_code.assert_not_called()
    mk_get_workspace_file.assert_called_once()
    mk_get_working_path.assert_called_once()
    mk_git_exclude.assert_not_called()
    initial_load.assert_called_once()
    mk_resolve_stacks.assert_called_once_with(())
    ws_info.assert_called_once()
    set_java.assert_called_once_with(False, WK_FILE)
    set_gradle.assert_called_once_with(False, WK_FILE)
    set_maven.assert_called_once_with(None, WK_FILE)
    mk_add_default_settings.assert_called_once_with(WK_FILE, WK_PATH, ALL_STACKS)
    ws_warning.assert_not_called()
    mocks_reset()

    # Test when git_repo is True and no JVM stack is active: no tool is configured
    shutil_which.return_value = True
    get_command_return_code.return_value = 0
    mk_resolve_stacks.return_value = PYTHON_STACKS
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_not_called()
    get_command_return_code.assert_called_once()
    mk_get_workspace_file.assert_called_once()
    mk_get_working_path.assert_called_once()
    mk_git_exclude.assert_called_once_with(WK_PATH)
    initial_load.assert_called_once()
    set_java.assert_not_called()
    set_gradle.assert_not_called()
    set_maven.assert_not_called()
    assert ws_warning.call_count == 3  # one for java, one for gradle, one for maven
    mk_add_default_settings.assert_called_once_with(WK_FILE, WK_PATH, PYTHON_STACKS)
    mocks_reset()

    # Test that the stacks requested on the command line reach the resolution
    result = runner.invoke(create_working_env, ["-s", "maven"])
    assert result.exit_code == 0
    mk_resolve_stacks.assert_called_once_with(("maven",))
    mocks_reset()


def test_configure_tools(
    ws_warning: MagicMock,
    set_java: MagicMock,
    _java_command: MagicMock,
    set_gradle: MagicMock,
    _gradle_command: MagicMock,
    set_maven: MagicMock,
    _maven_command: MagicMock,
) -> None:
    """Test that _configure_tools only runs the setup of the active stacks"""
    # Java without a build tool: only the Java version is configured
    configure_tools(WK_FILE, {ProjectStack.COMMON, ProjectStack.JAVA})
    set_java.assert_called_once_with(False, WK_FILE)
    set_gradle.assert_not_called()
    set_maven.assert_not_called()
    assert ws_warning.call_count == 2  # one for gradle, one for maven
    reset_mocks(ws_warning, set_java, set_gradle, set_maven)

    # Gradle project: Java and Gradle are configured, Maven is reported as skipped
    configure_tools(WK_FILE, {ProjectStack.COMMON, ProjectStack.JAVA, ProjectStack.GRADLE})
    set_java.assert_called_once_with(False, WK_FILE)
    set_gradle.assert_called_once_with(False, WK_FILE)
    set_maven.assert_not_called()
    ws_warning.assert_called_once()
    # the warning names the missing marker and the command that configures the stack anyway
    message: str = ws_warning.call_args.args[0]
    assert ProjectStack.MAVEN.markers[0] in message
    assert "set-maven" in message
    reset_mocks(ws_warning, set_java, set_gradle, set_maven)

    # Maven project: Java and Maven are configured, Gradle is reported as skipped
    configure_tools(WK_FILE, {ProjectStack.COMMON, ProjectStack.JAVA, ProjectStack.MAVEN})
    set_java.assert_called_once_with(False, WK_FILE)
    set_maven.assert_called_once_with(None, WK_FILE)
    set_gradle.assert_not_called()
    ws_warning.assert_called_once()
    reset_mocks(ws_warning, set_java, set_gradle, set_maven)

    # No JVM stack at all: the Java warning explains that no build file revealed it
    configure_tools(WK_FILE, PYTHON_STACKS)
    set_java.assert_not_called()
    assert ws_warning.call_count == 3
    java_message: str = ws_warning.call_args_list[0].args[0]
    assert "no build file revealed it" in java_message
    assert "set-java" in java_message


def test_get_workspace_file(
    get_property: MagicMock,
    mk_os: MagicMock,
    ws_warning: MagicMock,
    mk_json: MagicMock,
    _mk_folder_const: MagicMock,
    _mk_new_wk_contents: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
) -> None:
    """test the _get_workspace_file private method"""
    file_content: str = "mocked file content"

    os_getcwd: MagicMock = mk_os.getcwd
    os_getcwd.return_value = CURRENT_PATH
    os_path_exists: MagicMock = mk_os.path.exists
    os_path_exists.return_value = True
    m_open: MagicMock = mock_open(read_data=file_content)
    file_mock: MagicMock = m_open.return_value
    read_mock: MagicMock = file_mock.read
    write_mock: MagicMock = file_mock.write
    json_dump: MagicMock = mk_json.dump
    result: str = None

    def mocks_reset() -> None:
        """reset mocks"""
        nonlocal result
        result = None
        reset_mocks(
            get_property,
            mk_os,
            os_getcwd,
            os_path_exists,
            m_open,
            ws_warning,
            file_mock,
            read_mock,
            write_mock,
            mk_json,
            json_dump,
            ws_success,
            get_validated_input,
        )

    with patch("builtins.open", m_open):
        # test when property and file exist
        result = get_workspace_file()
        get_property.assert_called_once()
        ws_warning.assert_not_called()
        json_dump.assert_not_called()
        ws_success.assert_not_called()
        get_validated_input.assert_not_called()
        assert result == WK_FILE
        mocks_reset()

        # test when property exist but file is empty
        read_mock.return_value = ""
        result = get_workspace_file()
        get_property.assert_called_once()
        ws_warning.assert_called_once_with("Vscode workspace file is empty")
        m_open.assert_any_call(f"{CURRENT_PATH}/{FOLDER}.code-workspace", "w", encoding="utf-8")
        m_open.assert_any_call(WK_FILE, "r", encoding="utf-8")
        assert m_open.call_count == 2
        json_dump.assert_called_once_with(NEW_WORKSPACE_CONTENTS, file_mock, indent=4)
        get_validated_input.assert_not_called()
        ws_success.assert_called_once()
        mocks_reset()

        # test when property exists but file doesn't
        os_path_exists.return_value = False
        with pytest.raises(FileNotFoundError):
            get_workspace_file()
        get_property.assert_called_once()
        ws_warning.assert_not_called()
        json_dump.assert_not_called()
        get_validated_input.assert_not_called()
        ws_success.assert_not_called()
        mocks_reset()

        # test when property is empty and accept to create workspace file
        get_property.side_effect = None
        get_property.return_value = ""
        get_validated_input.return_value = "y"
        result = get_workspace_file()
        assert result == f"{CURRENT_PATH}/{FOLDER}.code-workspace"
        get_property.assert_called_once()
        ws_warning.assert_called_once_with("Vscode workspace file not found in current directory")
        get_validated_input.assert_called_once()
        m_open.assert_called_once_with(result, "w", encoding="utf-8")
        json_dump.assert_called_once_with(NEW_WORKSPACE_CONTENTS, file_mock, indent=4)
        ws_success.assert_called_once()
        mocks_reset()

        # test when property is empty and denied to create workspace file
        get_validated_input.return_value = "n"
        with pytest.raises(UserDeclinedError, match="Vscode workspace file is required"):
            get_workspace_file()
        get_property.assert_called_once()
        ws_warning.assert_called_once_with("Vscode workspace file not found in current directory")
        get_validated_input.assert_called_once()
        m_open.assert_not_called()
        json_dump.assert_not_called()
        ws_success.assert_not_called()
        mocks_reset()


def test_git_exclude(
    mk_exclude_from_git: MagicMock,
) -> None:
    """testing _git_exclude private method delegates to the shared exclude_from_git utility"""
    git_exclude(WK_PATH)
    mk_exclude_from_git.assert_called_once_with(
        [
            (".vscode/", ".vscode folder"),
            (f"{WK_BASENAME_PATH}/", f"{WK_BASENAME_PATH} folder"),
            ("/*.code-workspace", "root code-workspace file"),
        ]
    )


def test_add_default_settings(
    get_property: MagicMock,
    mk_input: MagicMock,
    os_replace: MagicMock,
    ws_success: MagicMock,
    ws_advice: MagicMock,
    get_remote_url: MagicMock,
) -> None:
    """testing _add_default_settings private method"""
    remote_repo = "https://github.com/dummy_user/dummy_repo"

    def git_remote_side_effect() -> None:
        """git remote side effect"""
        nonlocal remote_repo
        return remote_repo

    result = None
    result_lines = None
    data = None
    get_remote_url.side_effect = git_remote_side_effect
    m_open: MagicMock = mock_open()
    file_mock: MagicMock = m_open.return_value
    read_mock: MagicMock = file_mock.read
    write_mock: MagicMock = file_mock.write
    # empty_wk_file_content = load_json_with_comments(EMPTY_WK_FILE)

    def mocks_reset() -> None:
        """reset mocks"""
        nonlocal result
        nonlocal result_lines
        result = None
        result_lines = None
        nonlocal data
        data = None
        reset_mocks(
            get_property,
            m_open,
            read_mock,
            write_mock,
            mk_input,
            os_replace,
            ws_success,
            ws_advice,
            get_remote_url,
        )

    def read_side_effect() -> str:
        """Read side effect"""
        nonlocal m_open
        read_content = m_open.call_args.args[0]
        with real_open(read_content, "r", encoding="utf-8") as file:
            return file.read()

    read_mock.side_effect = read_side_effect

    def evaluate_happy_path(file: str, default_prop_value: Any) -> None:
        """Evaluate the happy path"""
        if isinstance(default_prop_value, list):
            mk_input.return_value = None
            mk_input.side_effect = list(map(str, default_prop_value))
        else:
            mk_input.side_effect = None
            mk_input.return_value = default_prop_value
        with patch("builtins.open", m_open):
            add_default_settings(file, WK_PATH, ALL_STACKS)
            result_data = written_workspace(write_mock)
            # verify recommended extensions are added
            data: dict[str, Any] = jq.compile(EXTENSIONS_QUERY).input(result_data).first()
            for ext in get_recommended_extensions(ALL_STACKS):
                assert ext in data
            # verify git blame is added
            data = jq.compile(GIT_BLAME_QUERY).input(result_data).first()
            assert remote_repo.replace("git@", "").replace(".com:", ".com/") in data
            # verify PR queries are added
            data = jq.compile(GH_PR_QUERY).input(result_data).first()
            for query in PrQueries:
                assert query.label in list(map(lambda x: x["label"], data))
            # verify Issues queries are added
            data = jq.compile(GH_ISSUES_QUERY).input(result_data).first()
            for query in IssuesQueries:
                assert query.label in list(map(lambda x: x["label"], data))
            # verify log watchers are added
            data = jq.compile(LOG_WATCHER_QUERY).input(result_data).first()
            for query in LogWatcher:
                assert query.title in list(map(lambda x: x["title"], data))
            # verify vscode tasks are added
            data = jq.compile(TASKS_TASKS_QUERY).input(result_data).first()
            for task in VscodeTask:
                assert task.label in list(map(lambda x: x["label"], data))
            # verify vscode Task version is added
            data = jq.compile(TASKS_VERSION_QUERY).input(result_data).first()
            assert data
            # verify vscode Launch configurations are added
            data = jq.compile(LAUNCH_CONFIG_QUERY).input(result_data).first()
            for launch in VscodeLaunch:
                assert launch.task_name in list(map(lambda x: x["name"], data))
            # verify vscode Launch version is added2
            data = jq.compile(LAUNCH_VERSION_QUERY).input(result_data).first()
            assert data
            # verify vscode Input for tasks and launch are added
            data = jq.compile(TASKS_INPUT_QUERY).input(result_data).first()
            for input_tasks in list((x for x in VscodeInput if x.enum_type != InputType.LAUNCH)):
                assert input_tasks.input_id in list(map(lambda x: x["id"], data))
            data = jq.compile(LAUNCH_INPUT_QUERY).input(result_data).first()
            for input_launch in list((x for x in VscodeInput if x.enum_type != InputType.TASK)):
                assert input_launch.input_id in list(map(lambda x: x["id"], data))
            # verify default properties are added
            counter: int = 0
            for key, value in flat_default_props(ALL_STACKS).items():
                data = jq.compile(f'.settings.["{key}"]').input(result_data).first()
                if isinstance(default_prop_value, list):
                    value = default_prop_value[counter]
                    assert data == value
                    counter += 1
                else:
                    assert data == value
            # verify file associations are added
            for key, value in flat_file_associations(ALL_STACKS).items():
                data = jq.compile(f'{FILE_ASSOCIATION_QUERY}.["{key}"]').input(result_data).first()
                assert data == value
            ws_success.assert_called_once()
            ws_advice.assert_not_called()
            mocks_reset()

    # test empty file when suggested settings are default
    evaluate_happy_path(EMPTY_WK_FILE, "")

    # test empty file when suggested settings value is changed
    dummy_values: list[Any] = []
    counter: int = 0
    v: Any = None
    for _prop, value in flat_default_props(ALL_STACKS).items():
        counter += 1
        # if value is boolean use True
        if isinstance(value, bool):
            v = True
        # if value is numeric use counter
        elif isinstance(value, int):
            v = counter
        # if value is string use f"dummy_value{counter}"
        elif isinstance(value, str):
            v = f"dummy_value{counter}"
        dummy_values.append(v)
    evaluate_happy_path(EMPTY_WK_FILE, dummy_values)

    # test updated file
    add_default_settings(DARWIN_WK_FILE, WK_PATH, ALL_STACKS)
    write_mock.assert_not_called()
    ws_advice.assert_called_once()
    ws_success.assert_not_called()
    mocks_reset()

    # test file when some recommended extensions exists but not all
    list_ext: list[str] = get_recommended_extensions(ALL_STACKS)
    # remove first and last extension
    list_ext.pop(0)
    list_ext.pop(-1)
    json_query = f"{EXTENSIONS_QUERY} = {json.dumps(list_ext)}"
    data = load_json_with_comments(EMPTY_WK_FILE)
    data = jq.compile(json_query).input(data).first()
    with patch("mega_snake.config_environment.create_working_env.load_json_with_comments", return_value=data):
        evaluate_happy_path(EMPTY_WK_FILE, "")

    # test file when get_remote_url starts with git@
    remote_repo = "git@github.com:dummy_user/dummy_repo"
    evaluate_happy_path(EMPTY_WK_FILE, "")


def test_add_default_settings_only_writes_active_stacks(
    get_property: MagicMock,
    mk_input: MagicMock,
    os_replace: MagicMock,
    ws_success: MagicMock,
    ws_advice: MagicMock,
    get_remote_url: MagicMock,
    mk_resolve_stacks: MagicMock,
) -> None:
    """Nothing belonging to an inactive stack reaches the workspace file"""
    get_remote_url.return_value = "https://github.com/dummy_user/dummy_repo"
    mk_input.return_value = ""
    m_open: MagicMock = mock_open()
    file_mock: MagicMock = m_open.return_value
    write_mock: MagicMock = file_mock.write

    def read_side_effect() -> str:
        """Read the real fixture file behind the mocked open call"""
        with real_open(m_open.call_args.args[0], "r", encoding="utf-8") as file:
            return file.read()

    file_mock.read.side_effect = read_side_effect

    with patch("builtins.open", m_open):
        # the stacks are detected when the caller does not provide them
        mk_resolve_stacks.return_value = PYTHON_STACKS
        add_default_settings(EMPTY_WK_FILE, WK_PATH)
        mk_resolve_stacks.assert_called_once_with()
        result_data: dict[str, Any] = written_workspace(write_mock)

    # only the extensions of the active stacks are recommended
    extensions: list[str] = jq.compile(EXTENSIONS_QUERY).input(result_data).first()
    assert extensions == get_recommended_extensions(PYTHON_STACKS)
    assert "vscjava.vscode-java-pack" not in extensions
    assert "vscjava.vscode-gradle" not in extensions

    # every Java, Gradle and Maven task is left out, and no other task is active for Python
    assert not jq.compile(TASKS_TASKS_QUERY).input(result_data).first()

    # only the Python launch configurations are written
    launches: list[dict[str, Any]] = jq.compile(LAUNCH_CONFIG_QUERY).input(result_data).first()
    assert [launch["name"] for launch in launches] == [
        member.task_name for member in filter_by_stack(VscodeLaunch, PYTHON_STACKS)
    ]
    assert VscodeLaunch.DEBUG_JAVA.task_name not in [launch["name"] for launch in launches]

    # only the log watchers of the active stacks are registered
    watchers: list[dict[str, Any]] = jq.compile(LOG_WATCHER_QUERY).input(result_data).first()
    assert [watcher["title"] for watcher in watchers] == [
        member.title for member in filter_by_stack(LogWatcher, PYTHON_STACKS)
    ]

    # the Gradle-only input is not registered either
    task_inputs: list[dict[str, Any]] = jq.compile(TASKS_INPUT_QUERY).input(result_data).first()
    assert VscodeInput.SELECT_BUILD.input_id not in [entry["id"] for entry in task_inputs]
    assert VscodeInput.TODAY_TIMESTAMP.input_id in [entry["id"] for entry in task_inputs]

    # the Java settings are not prompted for, the shared ones still are
    for key in DEFAULT_PROPS[ProjectStack.JAVA]:
        assert jq.compile(f'.settings.["{key}"]').input(result_data).first() is None
    for key in DEFAULT_PROPS[ProjectStack.COMMON]:
        assert jq.compile(f'.settings.["{key}"]').input(result_data).first() is not None

    # the Gradle file association is not written, the shared ones are
    assert jq.compile(f'{FILE_ASSOCIATION_QUERY}.["*.gradle"]').input(result_data).first() is None
    assert jq.compile(f'{FILE_ASSOCIATION_QUERY}.["*.yml"]').input(result_data).first() == "yaml"


def test_get_recommended_extensions() -> None:
    """Test that the recommended extensions are collected once and in stack order"""
    result: list[str] = get_recommended_extensions(ALL_STACKS)
    assert len(result) == len(set(result))
    expected: list[str] = []
    for stack in sort_stacks(ALL_STACKS):
        expected.extend(ext for ext in stack.extensions if ext not in expected)
    assert result == expected
    # a stack that contributes nothing does not change the outcome
    assert get_recommended_extensions({ProjectStack.COMMON, ProjectStack.MAVEN}) == ProjectStack.COMMON.extensions


def test_launch_substituter(
    _mk_folder_const: MagicMock,
    get_property: MagicMock,
) -> None:
    """testing _launch_substituter private method"""
    # test project sample data
    project_sample_data = (
        '{"name": "JAVA DEBUG (Attach)", "type": "java", "request": "attach",'
        ' "port": "${config:mgsnake.java.remoteDebug.port}", "hostName": "localhost", "projectName": "[SUBS_PROJECT]"}'
    )
    result = launch_substituter(project_sample_data)
    assert f'"projectName": "{FOLDER}"' in result
    get_property.assert_not_called()

    # test shell sample data
    shell_sample_data = (
        '{"name": "PYTHON DEBUG (Snake)", "type": "debugpy", "request": "launch",'
        ' "args": "--shell [SUBS_SHELL] -l debug msg hello world!", "module": "py",'
        ' "python": "/Users/carlosmorales/IdeaProjects/stuff/.venv/bin/python3.13", "console": "integratedTerminal"}'
    )
    result = launch_substituter(shell_sample_data)
    assert f'"args": "--shell {OS} -l debug msg hello world!"' in result
    get_property.assert_called_once_with("shell")
