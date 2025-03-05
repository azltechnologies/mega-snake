""" Test the java_set module. """

import builtins
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, call
from typing import Generator, Any
from click.testing import CliRunner
import pytest
from codename_snake.config_environment.create_working_env import (
    create_working_env,
    _get_workspace_file as get_workspace_file,
    _get_working_path as get_working_path,
    _git_exclude as git_exclude,
)
from codename_snake.util.util import load_json_with_comments
from codename_snake.constants import APP_NAME, WORKSPACE_EXTENSIONS


GRADLE_CMD_NAME = "gradle_command"
WK_FILE = "some_file.txt"
WK_PARENTH_PATH = "/root/parent_folder"
WK_BASENAME_PATH = "some_path"
WK_PATH = f"{WK_PARENTH_PATH}/{WK_BASENAME_PATH}"
CURRENT_PATH = "my_path"
FOLDER = "folder_name"
NEW_WORKSPACE_CONTENTS = {"prop": "value", "another_prop": 2}

real_open = builtins.open


@pytest.fixture(name="shutil_which")
def fixture_shutil_copyfile() -> Generator[MagicMock]:
    """Mock shutil.which"""
    with patch("codename_snake.config_environment.create_working_env.shutil") as mock:
        yield mock.which


@pytest.fixture(name="get_validated_input")
def fixture_get_validated_input() -> Generator[MagicMock]:
    """Mock get_validated_input"""
    with patch("codename_snake.config_environment.create_working_env.get_validated_input") as mock:
        yield mock


@pytest.fixture(name="ws_warning")
def fixture_ws_warning() -> Generator[MagicMock]:
    """Mock ws_warning"""
    with patch("codename_snake.config_environment.create_working_env.ws_warning") as mock:
        yield mock


@pytest.fixture(name="ws_success")
def fixture_ws_success() -> Generator[MagicMock]:
    """Mock ws_success"""
    with patch("codename_snake.config_environment.create_working_env.ws_success") as mock:
        yield mock


@pytest.fixture(name="ws_advice")
def fixture_ws_advice() -> Generator[MagicMock]:
    """Mock ws_advice"""
    with patch("codename_snake.config_environment.create_working_env.ws_advice") as mock:
        yield mock


@pytest.fixture(name="get_command_return_code")
def fixture_get_command_return_code() -> Generator[MagicMock]:
    """Mock get_command_return_code"""
    with patch("codename_snake.config_environment.create_working_env.get_command_return_code") as mock:
        yield mock


@pytest.fixture(name="mk_get_workspace_file")
def fixture_mk_get_workspace_file() -> Generator[MagicMock]:
    """Mock _get_workspace_file"""
    with patch("codename_snake.config_environment.create_working_env._get_workspace_file") as mock:
        yield mock


@pytest.fixture(name="mk_get_working_path")
def fixture_get_working_path() -> Generator[MagicMock]:
    """Mock _get_working_path"""
    with patch("codename_snake.config_environment.create_working_env._get_working_path") as mock:
        yield mock


@pytest.fixture(name="mk_git_exclude")
def fixture_git_exclude() -> Generator[MagicMock]:
    """Mock _git_exclude"""
    with patch("codename_snake.config_environment.create_working_env._git_exclude") as mock:
        yield mock


@pytest.fixture(name="initial_load")
def fixture_initial_load() -> Generator[MagicMock]:
    """Mock initial_load"""
    with patch("codename_snake.config_environment.create_working_env.initial_load") as mock:
        yield mock


@pytest.fixture(name="set_java")
def fixture_set_java() -> Generator[MagicMock]:
    """Mock set_java"""
    with patch("codename_snake.config_environment.create_working_env.set_java") as mock:
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock]:
    """Mock os"""
    with patch("codename_snake.config_environment.create_working_env.os") as mock:
        yield mock


@pytest.fixture(name="set_gradle")
def fixture_set_gradle() -> Generator[MagicMock]:
    """Mock set_gradle"""
    with patch("codename_snake.config_environment.create_working_env.set_gradle") as mock:
        yield mock


@pytest.fixture(name="_gradle_command")
def fixture_gradle_command() -> Generator[MagicMock]:
    """Mock gradle_command"""
    with patch("codename_snake.config_environment.create_working_env.gradle_command") as mock:
        mock.name = GRADLE_CMD_NAME
        yield mock


@pytest.fixture(name="add_recommended_extensions")
def fixture_add_recommended_extensions() -> Generator[MagicMock]:
    """Mock _add_recommended_extensions"""
    with patch("codename_snake.config_environment.create_working_env._add_recommended_extensions") as mock:
        yield mock


@pytest.fixture(name="add_default_settings")
def fixture_add_default_settings() -> Generator[MagicMock]:
    """Mock _add_default_settings"""
    with patch("codename_snake.config_environment.create_working_env._add_default_settings") as mock:
        yield mock


@pytest.fixture(name="execute")
def fixture_execute() -> Generator[MagicMock]:
    """Mock execute"""
    with patch("codename_snake.config_environment.create_working_env._execute") as mock:
        yield mock


@pytest.fixture(name="get_property")
def fixture_get_property() -> Generator[MagicMock]:
    """Mock get_property"""

    def f_side_effect(prop: str) -> str:
        """side effect for get_property_mock"""
        if prop == "workspace_file":
            return WK_FILE
        elif prop == "working_path":
            return WK_PATH
        elif prop == "shell":
            return "Windows"

    with patch("codename_snake.config_environment.create_working_env.get_property", side_effect=f_side_effect) as mock:
        yield mock


@pytest.fixture(name="json")
def fixture_json() -> Generator[MagicMock]:
    """Mock json"""
    with patch("codename_snake.config_environment.create_working_env.json") as mock:
        yield mock


@pytest.fixture(name="_mk_folder_const")
def fixture_mk_folder_const() -> Generator[MagicMock]:
    """Mock FOLDER constant"""
    with patch("codename_snake.config_environment.create_working_env.FOLDER", FOLDER) as mock:
        yield mock


@pytest.fixture(name="_mk_new_wk_contents")
def fixture_mk_new_wk_contents() -> Generator[MagicMock]:
    """Mock NEW_WORKSPACE_CONTENTS constant"""
    with patch(
        "codename_snake.config_environment.create_working_env.NEW_WORKSPACE_CONTENTS", NEW_WORKSPACE_CONTENTS
    ) as mock:
        yield mock


@pytest.fixture(name="mk_path")
def fixture_mk_path() -> Generator[MagicMock]:
    """Mock path"""
    with patch("codename_snake.config_environment.create_working_env.Path") as mock:
        yield mock


def reset_mocks(*mocks: MagicMock) -> None:
    """Reset all mocks"""
    for mock in mocks:
        mock.reset_mock()


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
    execute.assert_called_once_with(True)
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
    execute.assert_called_once_with(False)
    mocks_reset()

    # Test when git is installed but there's no repo and user chooses to proceed in creating the workspace
    shutil_which.return_value = True
    get_command_return_code.return_value = 1
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_called_once()
    get_command_return_code.assert_called_once()
    ws_warning.assert_not_called()
    execute.assert_called_once_with(False)
    mocks_reset()


def test_execute(
    shutil_which: MagicMock,
    get_validated_input: MagicMock,
    ws_warning: MagicMock,
    mk_get_workspace_file: MagicMock,
    mk_get_working_path: MagicMock,
    get_command_return_code: MagicMock,
    mk_git_exclude: MagicMock,
    initial_load: MagicMock,
    set_java: MagicMock,
    mk_os: MagicMock,
    set_gradle: MagicMock,
    _gradle_command: MagicMock,
    add_recommended_extensions: MagicMock,
    add_default_settings: MagicMock,
) -> None:
    """Test gradle command"""

    runner = CliRunner()
    os_getcwd: MagicMock = mk_os.getcwd
    os_path_exists: MagicMock = mk_os.path.exists
    mk_get_workspace_file.return_value = WK_FILE
    mk_get_working_path.return_value = WK_PATH
    os_getcwd.return_value = CURRENT_PATH
    result = None

    def mocks_reset() -> None:
        nonlocal result
        result = None
        reset_mocks(
            shutil_which,
            get_validated_input,
            ws_warning,
            mk_get_workspace_file,
            mk_get_working_path,
            get_command_return_code,
            mk_git_exclude,
            initial_load,
            set_java,
            mk_os,
            os_getcwd,
            os_path_exists,
            set_gradle,
            add_recommended_extensions,
            add_default_settings,
        )

    # Test when git_repo is false and build.gradle exists
    shutil_which.return_value = False
    get_validated_input.return_value = "y"
    os_path_exists.return_value = True
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_called_once()
    get_command_return_code.assert_not_called()
    mk_get_workspace_file.assert_called_once()
    mk_get_working_path.assert_called_once()
    mk_git_exclude.assert_not_called()
    initial_load.assert_called_once()
    set_java.assert_called_once()
    os_path_exists.assert_called_once_with(f"{CURRENT_PATH}/build.gradle")
    set_gradle.assert_called_once_with(False, WK_FILE)
    add_recommended_extensions.assert_called_once_with(WK_FILE)
    add_default_settings.assert_called_once_with(WK_FILE, WK_PATH)
    ws_warning.assert_not_called()
    mocks_reset()

    # Test when git_repo is True and build.gradle doesn't exist
    shutil_which.return_value = True
    get_command_return_code.return_value = 0
    os_path_exists.return_value = False
    result = runner.invoke(create_working_env)
    assert result.exit_code == 0
    get_validated_input.assert_not_called()
    get_command_return_code.assert_called_once()
    mk_get_workspace_file.assert_called_once()
    mk_get_working_path.assert_called_once()
    mk_git_exclude.assert_called_once_with(WK_PATH)
    initial_load.assert_called_once()
    set_java.assert_called_once()
    os_path_exists.assert_has_calls([call(f"{CURRENT_PATH}/build.gradle"), call(f"{CURRENT_PATH}/build.gradle.kts")])
    ws_warning.assert_called_once()
    set_gradle.assert_not_called()
    add_recommended_extensions.assert_called_once_with(WK_FILE)
    add_default_settings.assert_called_once_with(WK_FILE, WK_PATH)
    mocks_reset()


def test_get_workspace_file(
    get_property: MagicMock,
    mk_os: MagicMock,
    ws_warning: MagicMock,
    json: MagicMock,
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
    json_dump: MagicMock = json.dump
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
            json,
            json_dump,
            ws_success,
            get_validated_input,
        )

    # test when property and file exist
    with patch("builtins.open", m_open):
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
        with pytest.raises(RuntimeError):
            get_workspace_file()
        get_property.assert_called_once()
        ws_warning.assert_called_once_with("Vscode workspace file not found in current directory")
        get_validated_input.assert_called_once()
        m_open.assert_not_called()
        json_dump.assert_not_called()
        ws_success.assert_not_called()
        mocks_reset()


def test_get_working_path(
    get_property: MagicMock,
    mk_path: MagicMock,
    mk_os: MagicMock,
    ws_warning: MagicMock,
    get_validated_input: MagicMock,
    ws_success: MagicMock,
) -> None:
    """testing get_working_path private method"""
    cwd_resolve: MagicMock = mk_path.cwd().resolve
    cwd_resolve.return_value = WK_PARENTH_PATH
    os_path_exists: MagicMock = mk_os.path.exists
    os_path_exists.return_value = True
    os_makedirs: MagicMock = mk_os.makedirs
    mk_path.side_effect = Path
    result: str = "None"

    def mocks_reset() -> None:
        """reset mocks"""
        nonlocal result
        result = None
        reset_mocks(
            get_property,
            mk_path,
            cwd_resolve,
            mk_os,
            ws_warning,
            get_validated_input,
            os_makedirs,
            ws_success,
        )

    # test when working path exists
    result = get_working_path()
    assert result == WK_PATH
    mk_path.assert_called_once_with(WK_PATH)
    cwd_resolve.assert_called_once()
    os_path_exists.assert_called_once_with(WK_PATH)
    ws_warning.assert_not_called()
    os_makedirs.assert_not_called()
    ws_success.assert_not_called()
    mocks_reset()

    # test when working path doesn't exist and denied to create workspace the directory
    get_validated_input.return_value = "n"
    os_path_exists.return_value = False
    with pytest.raises(RuntimeError):
        get_working_path()
    mk_path.assert_called_once_with(WK_PATH)
    cwd_resolve.assert_called_once()
    os_path_exists.assert_called_once_with(WK_PATH)
    ws_warning.assert_called_once()
    os_makedirs.assert_not_called()
    ws_success.assert_not_called()
    mocks_reset()

    # test when working path doesn't exist and accept to create workspace the directory
    get_validated_input.return_value = "y"
    os_path_exists.return_value = False
    result = get_working_path()
    assert result == WK_PATH
    mk_path.assert_called_once_with(WK_PATH)
    cwd_resolve.assert_called_once()
    os_path_exists.assert_called_once_with(WK_PATH)
    ws_warning.assert_called_once()
    os_makedirs.assert_called_once()
    ws_success.assert_called_once()
    mocks_reset()

    # test when working path is not subpath of current directory
    cwd_resolve.return_value = "/x/y/z"
    with pytest.raises(AssertionError):
        get_working_path()
    mk_path.assert_called_once_with(WK_PATH)
    cwd_resolve.assert_called_once()
    os_path_exists.assert_not_called()
    ws_warning.assert_not_called()
    os_makedirs.assert_not_called()
    ws_success.assert_not_called()
    mocks_reset()

    # test when property is empty
    get_property.side_effect = None
    get_property.return_value = ""
    with pytest.raises(AssertionError):
        get_working_path()
    mk_path.assert_not_called()
    cwd_resolve.assert_not_called()
    os_path_exists.assert_not_called()
    ws_warning.assert_not_called()
    os_makedirs.assert_not_called()
    ws_success.assert_not_called()
    mocks_reset()


def test_git_exclude(
    ws_advice: MagicMock,
    ws_success: MagicMock,
) -> None:
    """testing _git_exclude private method"""
    empty_file_content = "# comments here\n# comments there"
    final_file_content = "# comments here\n# comments there\n.vscode/\nsome_path/\n/*.code-workspace\n"

    result: str = None
    m_open: MagicMock = mock_open(read_data=empty_file_content)
    file_mock: MagicMock = m_open.return_value
    read_mock: MagicMock = file_mock.read
    write_mock: MagicMock = file_mock.write

    def mocks_reset() -> None:
        """reset mocks"""
        nonlocal result
        result = None
        reset_mocks(m_open, file_mock, read_mock, write_mock, ws_advice, ws_success)

    with patch("builtins.open", m_open):
        # tests when file is empty
        git_exclude(WK_PATH)
        read_mock.assert_called_once()
        write_mock.assert_called_once()
        result = write_mock.call_args.args[0]
        lines: list[str] = result.splitlines()
        assert ".vscode/" in lines
        assert f"{WK_BASENAME_PATH}/" in lines
        assert "/*.code-workspace" in lines
        assert ws_success.call_count == 3
        ws_advice.assert_not_called()
        mocks_reset()

        # tests when file is updated
        read_mock.return_value = final_file_content
        git_exclude(WK_PATH)
        read_mock.assert_called_once()
        write_mock.assert_called_once()
        result = write_mock.call_args.args[0]
        lines: list[str] = result.splitlines()
        assert ".vscode/" in lines
        assert f"{WK_BASENAME_PATH}/" in lines
        assert "/*.code-workspace" in lines
        assert ws_advice.call_count == 3
        ws_success.assert_not_called()
        mocks_reset()
