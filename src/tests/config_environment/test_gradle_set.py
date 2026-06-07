""" Test the gradle_set module. """

import builtins
from unittest.mock import MagicMock, patch, mock_open, call
from typing import Generator, Any
from click.testing import CliRunner
import pytest
from mega_snake.config_environment.gradle_set import set_gradle_version, execute, GradleVersion
from mega_snake.util.util import load_json_with_comments

FILE_WK = "wk_file"
PATH_WK = "wk_path"
LOCAL_FILE = "local_file"
SHELL = "bash"

EMPTY_WK_FILE: str = "src/tests/gradle/empty.code-workspace"
EMPTY_SH_FILE: str = "src/tests/gradle/empty_local_file.sh"

DARWIN_FILES: dict[str, str] = {
    "wk_file": "src/tests/gradle/darwin.code-workspace",
    "local_file": "src/tests/gradle/bash_local_file.sh",
}

real_open = builtins.open


def reset_mocks(*mocks: MagicMock) -> None:
    """Reset all mocks"""
    for mock in mocks:
        mock.reset_mock()


@pytest.fixture(autouse=True)
def run_after_each_test() -> Generator[None, None, None]:
    """Reset the counter after each test"""
    # setup code here
    yield
    GradleVersion._id_counter = 0 # pylint: disable=protected-access


@pytest.fixture(name="_mk_os_darwin")
def fixture_mk_os_darwin() -> Generator[MagicMock]:
    """Mock _mk_os_darwin"""
    with patch("mega_snake.config_environment.gradle_set.OS", "Darwin") as mock:
        yield mock


@pytest.fixture(name="mk_execute")
def fixture_execute() -> Generator[MagicMock]:
    """Mock mk_execute"""
    with patch("mega_snake.config_environment.gradle_set.execute", wraps=execute) as mock:
        yield mock


@pytest.fixture(name="gradle_set")
def fixture__gradle_set() -> Generator[MagicMock]:
    """Mock gradle_set"""
    with patch("mega_snake.config_environment.gradle_set._gradle_set") as mock:
        yield mock


@pytest.fixture(name="get_property")
def fixture_get_property() -> Generator[MagicMock]:
    """Mock get_property"""

    def prop_side_effect(prop: str) -> Any:
        if prop == "workspace_file":
            return FILE_WK
        elif prop == "working_path":
            return PATH_WK
        elif prop == "shell":
            return SHELL
        else:
            raise ValueError("Invalid property")

    with patch("mega_snake.config_environment.gradle_set.get_property", side_effect=prop_side_effect) as mock:
        yield mock


@pytest.fixture(name="get_local_file")
def fixture_get_local_file() -> Generator[MagicMock]:
    """Mock get_local_file"""
    with patch("mega_snake.config_environment.gradle_set.get_local_file") as mock:
        mock.return_value = LOCAL_FILE
        yield mock


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock]:
    """Mock run_operation"""
    return_value = """
/opt/homebrew/Cellar/gradle@8.5/8.5\n
/opt/homebrew/Cellar/gradle@8.11.1/8.11.1\n
/opt/homebrew/Cellar/gradle@8.4/8.4\n
/opt/homebrew/Cellar/gradle@8.12.1/8.12.1\n
/opt/homebrew/Cellar/gradle@7.6.2/7.6.2\n
/opt/homebrew/Cellar/gradle@7/7.6.4\n
/opt/homebrew/Cellar/gradle@6/6.9.4\n
/opt/homebrew/Cellar/gradle/8.11\n
/opt/homebrew/Cellar/gradle@8.9/8.9\n
/opt/homebrew/Cellar/gradle@7.6.1/7.6.1\n
    """
    with patch("mega_snake.config_environment.gradle_set.run_operation") as mock:
        mock.return_value.stdout = return_value
        yield mock


@pytest.fixture(name="ws_warning")
def fixture_ws_warning() -> Generator[MagicMock]:
    """Mock ws_warning"""
    with patch("mega_snake.config_environment.gradle_set.ws_warning") as mock:
        yield mock


@pytest.fixture(name="ws_success")
def fixture_ws_success() -> Generator[MagicMock]:
    """Mock ws_success"""
    with patch("mega_snake.config_environment.gradle_set.ws_success") as mock:
        yield mock


@pytest.fixture(name="get_validated_input")
def fixture_get_validated_input() -> Generator[MagicMock]:
    """Mock get_validated_input"""
    with patch("mega_snake.config_environment.models.tools_version.get_validated_input") as mock:
        mock.return_value = "6"  # Return the third version 8.4
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock]:
    """Mock os"""
    with patch("mega_snake.config_environment.models.tools_version.os") as mock:
        yield mock


@pytest.fixture(name="os_replace")
def fixture_os_replace() -> Generator[MagicMock]:
    """Mock os_replace"""
    with patch("mega_snake.config_environment.util.os") as mock:
        yield mock.replace


def test_command(
    mk_execute: MagicMock, get_property: MagicMock, gradle_set: MagicMock, get_local_file: MagicMock
) -> None:
    """Test gradle command"""

    # Test when no parameters are passed
    runner = CliRunner()
    result = runner.invoke(set_gradle_version)
    assert result.exit_code == 0
    get_property.assert_has_calls([call("workspace_file"), call("working_path"), call("shell")])
    assert get_property.call_count == 3
    get_local_file.assert_called_once()
    mk_execute.assert_called_once_with(False, FILE_WK)
    gradle_set.assert_called_once_with(FILE_WK, PATH_WK, LOCAL_FILE, SHELL, False)
    reset_mocks(get_property, get_local_file, mk_execute, gradle_set)

    # Test when a parameter is passed
    result = runner.invoke(set_gradle_version, ["-o"])
    assert result.exit_code == 0
    get_property.assert_has_calls([call("workspace_file"), call("working_path"), call("shell")])
    assert get_property.call_count == 3
    get_local_file.assert_called_once()
    mk_execute.assert_called_once_with(True, FILE_WK)
    gradle_set.assert_called_once_with(FILE_WK, PATH_WK, LOCAL_FILE, SHELL, True)
    reset_mocks(get_property, get_local_file, mk_execute, gradle_set)


def test_gradle_version_srt() -> None:
    """Test GradleVersion.__str__"""
    version = "1.2.3"
    path = "path"

    gradle_version = GradleVersion(version, path)
    result = str(gradle_version)
    assert "Id: 1" in result
    assert f"Gradle Version: {version}" in result
    assert f"path: {path}" in result


def test_set_gradle_version_darwin_empty_files(
    _mk_os_darwin: MagicMock,
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
) -> None:
    """Test _gradle_set"""
    os_path_exists: MagicMock = mk_os.path.exists
    empty_wk_file_content = load_json_with_comments(EMPTY_WK_FILE)
    m_open: MagicMock = mock_open()
    local_file = EMPTY_SH_FILE

    def read_side_effect() -> str:
        """Read side effect"""
        with real_open(local_file, "r", encoding="utf-8") as file:
            return file.read()

    with patch("builtins.open", m_open):
        file_mock: MagicMock = m_open.return_value
        write_mock: MagicMock = file_mock.write
        read_mock: MagicMock = file_mock.read
        read_mock.side_effect = read_side_effect

        # Test when no parameters are passed, workspace file is empty and local file is empty
        with patch(
            "mega_snake.config_environment.gradle_set.load_json_with_comments",
            return_value=empty_wk_file_content,
        ):
            runner = CliRunner()
            result = runner.invoke(set_gradle_version)
            assert result.exit_code == 0
            assert get_property.call_count == 3
            assert any(call.args[1] == "Getting Gradle versions" for call in run_operation.call_args_list)
            get_local_file.assert_called_once()
            assert read_mock.call_count >= 1
            write_mock.assert_called()
            os_replace.assert_called_once()
            assert os_path_exists.call_count == 2
            get_validated_input.assert_called_once()
            ws_warning.assert_not_called()
            ws_success.assert_called_once()
            local_file_content: str = write_mock.mock_calls.pop().args[0]
            local_file_content_lines = [line.strip() for line in local_file_content.splitlines() if line]
            assert any(line.startswith("export GRADLE_HOME='") for line in local_file_content_lines)
            assert 'export PATH="$GRADLE_HOME/bin:$PATH"' in local_file_content_lines
            wk_file_content_array = []
            for current_call in write_mock.mock_calls:
                args = [arg for arg in current_call.args if arg]
                if args:
                    wk_file_content_array.append("".join(set(current_call.args)))
            wk_content = "".join(wk_file_content_array)
            wk_content_lines = [line.strip().rstrip(",") for line in wk_content.splitlines() if line]
            assert '"java.import.gradle.wrapper.enabled": false' in wk_content_lines
            assert any(line.startswith('"java.import.gradle.home": "') for line in wk_content_lines)
            assert any(line.startswith('"GRADLE_HOME": "') for line in wk_content_lines)


def test_set_gradle_version_darwin_defined_versions(
    _mk_os_darwin: MagicMock,
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
) -> None:
    """Test _gradle_set"""
    os_path_exists: MagicMock = mk_os.path.exists
    wk_file_content = load_json_with_comments(DARWIN_FILES["wk_file"])
    m_open: MagicMock = mock_open()
    local_file = DARWIN_FILES["local_file"]

    def read_side_effect() -> str:
        """Read side effect"""
        with real_open(local_file, "r", encoding="utf-8") as file:
            return file.read()

    with patch("builtins.open", m_open):
        file_mock: MagicMock = m_open.return_value
        write_mock: MagicMock = file_mock.write
        read_mock: MagicMock = file_mock.read
        read_mock.side_effect = read_side_effect

        def mocks_reset() -> None:
            """Reset the mocks."""
            reset_mocks(
                get_property,
                run_operation,
                get_local_file,
                ws_warning,
                ws_success,
                get_validated_input,
                mk_os,
                os_replace,
                os_path_exists,
                m_open,
                file_mock,
                write_mock,
                read_mock,
            )

        # Test when no parameters are passed, workspace file and local file have versions
        with patch(
            "mega_snake.config_environment.gradle_set.load_json_with_comments",
            return_value=wk_file_content,
        ):
            runner = CliRunner()
            result = runner.invoke(set_gradle_version)
            assert result.exit_code == 0
            assert get_property.call_count == 3
            assert any(call.args[1] == "Getting Gradle versions" for call in run_operation.call_args_list)
            get_local_file.assert_called_once()
            assert read_mock.call_count >= 1
            write_mock.assert_called()
            os_replace.assert_called_once()
            assert os_path_exists.call_count >= 1
            get_validated_input.assert_called_once()
            ws_warning.assert_not_called()
            ws_success.assert_called_once()
            mocks_reset()

            # Test when override and workspace file and local file have versions
            get_validated_input.return_value = "8"  # Return the first version 8.5
            GradleVersion._id_counter = 0  # pylint: disable=protected-access
            result = runner.invoke(set_gradle_version, ["-o"])
            assert result.exit_code == 0
            assert get_property.call_count == 3
            assert any(call.args[1] == "Getting Gradle versions" for call in run_operation.call_args_list)
            get_local_file.assert_called_once()
            assert read_mock.call_count == 2
            write_mock.assert_called()
            os_replace.assert_called_once()
            assert os_path_exists.call_count == 2
            get_validated_input.assert_called_once()
            ws_warning.assert_not_called()
            ws_success.assert_called_once()
            local_file_content: str = write_mock.mock_calls.pop().args[0]
            local_file_content_lines = [line.strip() for line in local_file_content.splitlines() if line]
            assert any(line.startswith("export GRADLE_HOME='") for line in local_file_content_lines)
            assert 'export PATH="$GRADLE_HOME/bin:$PATH"' in local_file_content_lines
            wk_file_content_array = []
            for current_call in write_mock.mock_calls:
                args = [arg for arg in current_call.args if arg]
                if args:
                    wk_file_content_array.append("".join(set(current_call.args)))
            wk_content = "".join(wk_file_content_array)
            wk_content_lines = [line.strip().rstrip(",") for line in wk_content.splitlines() if line]
            assert '"java.import.gradle.wrapper.enabled": false' in wk_content_lines
            assert any(line.startswith('"java.import.gradle.home": "') for line in wk_content_lines)
            assert any(line.startswith('"GRADLE_HOME": "') for line in wk_content_lines)


def test_set_gradle_version_failing_scenarios(
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
) -> None:
    """Test _gradle_set"""
    runner = CliRunner()
    os_path_exists: MagicMock = mk_os.path.exists
    wk_file_content = load_json_with_comments(DARWIN_FILES["wk_file"])
    m_open: MagicMock = mock_open()
    local_file = DARWIN_FILES["local_file"]

    def read_side_effect() -> str:
        """Read side effect"""
        with real_open(local_file, "r", encoding="utf-8") as file:
            return file.read()

    with patch("builtins.open", m_open):
        file_mock: MagicMock = m_open.return_value
        write_mock: MagicMock = file_mock.write
        read_mock: MagicMock = file_mock.read
        read_mock.side_effect = read_side_effect

        def mocks_reset() -> None:
            """Reset the mocks."""
            reset_mocks(
                get_property,
                run_operation,
                get_local_file,
                ws_warning,
                ws_success,
                get_validated_input,
                mk_os,
                os_replace,
                os_path_exists,
                m_open,
                file_mock,
                write_mock,
                read_mock,
            )

        with patch("mega_snake.config_environment.gradle_set.OS", "Darwin"):
            # Test when no versions are found
            run_operation.return_value.stdout = ""
            with patch(
                "mega_snake.config_environment.gradle_set.load_json_with_comments",
                return_value=wk_file_content,
            ):
                result = runner.invoke(set_gradle_version, ["-o"])
                assert result.exit_code == 0
                assert get_property.call_count == 3
                assert any(call.args[1] == "Getting Gradle versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()

        with patch("mega_snake.config_environment.gradle_set.OS", "Windows"):
            # Test when no versions are found
            run_operation.return_value.stdout = ""
            with patch(
                "mega_snake.config_environment.gradle_set.load_json_with_comments",
                return_value=wk_file_content,
            ):
                result = runner.invoke(set_gradle_version, ["-o"])
                assert result.exit_code == 0
                assert get_property.call_count == 3
                assert any(call.args[1] == "Getting Gradle versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()

        with patch("mega_snake.config_environment.gradle_set.OS", "Linux"):
            # Test when no versions are found
            run_operation.return_value.stdout = ""
            with patch(
                "mega_snake.config_environment.gradle_set.load_json_with_comments",
                return_value=wk_file_content,
            ):
                result = runner.invoke(set_gradle_version, ["-o"])
                assert result.exit_code == 0
                assert get_property.call_count == 3
                assert any(call.args[1] == "Getting Gradle versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()
