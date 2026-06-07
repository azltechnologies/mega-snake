""" Test the java_set module. """

import builtins
from unittest.mock import MagicMock, patch, mock_open, call
from typing import Generator, Any
from click.testing import CliRunner
import pytest
from codename_snake.config_environment.java_set import set_java_version, execute, JavaVersion, _set_version_runtime
from codename_snake.util.util import load_json_with_comments

FILE_WK = "wk_file"
PATH_WK = "wk_path"
LOCAL_FILE = "local_file"
RESOURCE_PATH = "resources_path"
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
    JavaVersion._id_counter = 0  # pylint: disable=protected-access


@pytest.fixture(name="_mk_os_darwin")
def fixture_mk_os_darwin() -> Generator[MagicMock]:
    """Mock _mk_os_darwin"""
    with patch("codename_snake.config_environment.java_set.OS", "Darwin") as mock:
        yield mock


@pytest.fixture(name="mk_execute")
def fixture_execute() -> Generator[MagicMock]:
    """Mock mk_execute"""
    with patch("codename_snake.config_environment.java_set.execute", wraps=execute) as mock:
        yield mock


@pytest.fixture(name="java_set")
def fixture__java_set() -> Generator[MagicMock]:
    """Mock java_set"""
    with patch("codename_snake.config_environment.java_set._java_set") as mock:
        yield mock


@pytest.fixture(name="add_java_formatter")
def fixture__java_formatter() -> Generator[MagicMock]:
    """Mock add_java_formatter"""
    with patch("codename_snake.config_environment.java_set._add_java_formatter") as mock:
        yield mock


@pytest.fixture(name="get_property")
def fixture_get_property() -> Generator[MagicMock]:
    """Mock get_property"""

    def prop_side_effect(prop: str) -> Any:
        if prop == "workspace_file":
            return FILE_WK
        elif prop == "resources_path":
            return RESOURCE_PATH
        elif prop == "working_path":
            return PATH_WK
        elif prop == "shell":
            return SHELL
        else:
            raise ValueError("Invalid property")

    with patch("codename_snake.config_environment.java_set.get_property", side_effect=prop_side_effect) as mock:
        yield mock


@pytest.fixture(name="get_local_file")
def fixture_get_local_file() -> Generator[MagicMock]:
    """Mock get_local_file"""
    with patch("codename_snake.config_environment.java_set.get_local_file") as mock:
        mock.return_value = LOCAL_FILE
        yield mock


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock]:
    """Mock run_operation"""
    return_value = """
Matching Java Virtual Machines (8):\n
    21.0.5 (arm64) "Eclipse Adoptium" - "OpenJDK 21.0.5" /Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home\n
    21.0.2 (arm64) "Oracle Corporation" - "OpenJDK 21.0.2" /Users/carlosmorales/Library/Java/JavaVirtualMachines/openjdk-21.0.2/Contents/Home\n
    19.0.2 (arm64) "Eclipse Adoptium" - "OpenJDK 19.0.2" /Users/carlosmorales/Library/Java/JavaVirtualMachines/temurin-19.0.2/Contents/Home\n
    17.0.13 (arm64) "Eclipse Adoptium" - "OpenJDK 17.0.13" /Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home\n
    17.0.7 (arm64) "Oracle Corporation" - "Java SE 17.0.7" /Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home\n
    11.0.22 (arm64) "Eclipse Adoptium" - "OpenJDK 11.0.22" /Users/carlosmorales/Library/Java/JavaVirtualMachines/temurin-11.0.22/Contents/Home\n
    11.0.2 (x86_64) "Oracle Corporation" - "OpenJDK 11.0.2" /Library/Java/JavaVirtualMachines/jdk-11.0.2.jdk/Contents/Home\n
    1.8.0_402 (arm64) "Amazon" - "Amazon Corretto 8" /Users/carlosmorales/Library/Java/JavaVirtualMachines/corretto-1.8.0_402/Contents/Home\n
/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home\n
    """
    with patch("codename_snake.config_environment.java_set.run_operation") as mock:
        mock.return_value.stdout = return_value
        yield mock


@pytest.fixture(name="ws_warning")
def fixture_ws_warning() -> Generator[MagicMock]:
    """Mock ws_warning"""
    with patch("codename_snake.config_environment.java_set.ws_warning") as mock:
        yield mock


@pytest.fixture(name="ws_success")
def fixture_ws_success() -> Generator[MagicMock]:
    """Mock ws_success"""
    with patch("codename_snake.config_environment.java_set.ws_success") as mock:
        yield mock


@pytest.fixture(name="get_validated_input")
def fixture_get_validated_input() -> Generator[MagicMock]:
    """Mock get_validated_input"""
    with patch("codename_snake.config_environment.models.tools_version.get_validated_input") as mock:
        mock.return_value = "3"  # Return the third version 8.4
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock]:
    """Mock os"""
    with patch("codename_snake.config_environment.models.tools_version.os") as mock:
        yield mock


@pytest.fixture(name="mk_os_java")
def fixture_mk_os_java() -> Generator[MagicMock]:
    """Mock os"""
    with patch("codename_snake.config_environment.java_set.os") as mock:
        yield mock


@pytest.fixture(name="os_replace")
def fixture_os_replace() -> Generator[MagicMock]:
    """Mock os_replace"""
    with patch("codename_snake.config_environment.util.os") as mock:
        yield mock.replace


@pytest.fixture(name="set_version_runtime")
def fixture_set_version_runtime() -> Generator[MagicMock]:
    """Mock _set_version_runtime"""
    with patch("codename_snake.config_environment.java_set._set_version_runtime", wraps=_set_version_runtime) as mock:
        yield mock

@pytest.fixture(name="shutil_copyfile")
def fixture_shutil_copyfile() -> Generator[MagicMock]:
    """Mock shutil_copyfile"""
    with patch("codename_snake.config_environment.java_set.shutil") as mock:
        yield mock.copyfile

def test_command(
    mk_execute: MagicMock,
    get_property: MagicMock,
    java_set: MagicMock,
    get_local_file: MagicMock,
    add_java_formatter: MagicMock,
) -> None:
    """Test gradle command"""

    # Test when no parameters are passed
    runner = CliRunner()
    result = runner.invoke(set_java_version)
    assert result.exit_code == 0
    get_property.assert_has_calls(
        [call("workspace_file"), call("working_path"), call("resources_path"), call("shell")]
    )
    assert get_property.call_count == 4
    get_local_file.assert_called_once()
    mk_execute.assert_called_once_with(False, FILE_WK)
    java_set.assert_called_once_with(FILE_WK, PATH_WK, LOCAL_FILE, SHELL, False)
    add_java_formatter.assert_called_once_with(FILE_WK, RESOURCE_PATH)
    reset_mocks(get_property, get_local_file, mk_execute, java_set, add_java_formatter)

    # Test when a parameter is passed
    result = runner.invoke(set_java_version, ["-o"])
    assert result.exit_code == 0
    get_property.assert_has_calls(
        [call("workspace_file"), call("working_path"), call("resources_path"), call("shell")]
    )
    assert get_property.call_count == 4
    get_local_file.assert_called_once()
    mk_execute.assert_called_once_with(True, FILE_WK)
    java_set.assert_called_once_with(FILE_WK, PATH_WK, LOCAL_FILE, SHELL, True)
    add_java_formatter.assert_called_once_with(FILE_WK, RESOURCE_PATH)
    reset_mocks(get_property, get_local_file, mk_execute, java_set)


def test_gradle_version_srt() -> None:
    """Test JavaVersion.__str__"""
    version = "1.2.3"
    path = "path"
    description = "description"

    gradle_version = JavaVersion(version, path, description)
    result = str(gradle_version)
    assert "Id: 1" in result
    assert f"Java Version: {version}" in result
    assert f"path: {path}" in result
    assert f"Description: {description}" in result


def test_set_java_version_darwin_empty_files(
    _mk_os_darwin: MagicMock,
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
    add_java_formatter: MagicMock,
) -> None:
    """Test _java_set"""
    runner = CliRunner()
    os_path_exists: MagicMock = mk_os.path.exists
    empty_wk_file_content = load_json_with_comments(EMPTY_WK_FILE)
    m_open: MagicMock = mock_open()
    local_file = EMPTY_SH_FILE

    # Realistic paths returned by "Getting Java versions" (3 entries; get_validated_input returns "3")
    java_paths_stdout = "\n".join([
        "/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home/bin/java",
        "/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home/bin/java",
        "/Users/user/Library/Java/JavaVirtualMachines/temurin-11.0.22/Contents/Home/bin/java",
    ])
    java_detail_stdout = (
        'openjdk version "21.0.5" 2024-10-15\n'
        'OpenJDK Runtime Environment (build 21.0.5)\n'
        'OpenJDK 64-Bit Server VM (build 21.0.5, mixed mode)'
    )

    def run_op_side_effect(cmd: str, msg: str) -> MagicMock:
        """Return Java paths on the first call and per-path version details on subsequent calls.

        Parameters:
            cmd: The shell command string (unused by this side effect).
            msg: The descriptive message passed to run_operation; used to distinguish call type.

        Returns:
            MagicMock whose `.stdout` contains Java executable paths when *msg* is
            "Getting Java versions", or a synthetic `java -version` output otherwise.
        """
        result: MagicMock = MagicMock()
        result.stdout = java_paths_stdout if msg == "Getting Java versions" else java_detail_stdout
        return result

    run_operation.side_effect = run_op_side_effect

    def read_side_effect() -> str:
        """Read the local shell config file from disk so write assertions can inspect its content.

        Returns:
            The current text content of the local configuration file.
        """
        with real_open(local_file, "r", encoding="utf-8") as file:
            return file.read()

    with patch("builtins.open", m_open):
        file_mock: MagicMock = m_open.return_value
        write_mock: MagicMock = file_mock.write
        read_mock: MagicMock = file_mock.read
        read_mock.side_effect = read_side_effect

        # Test when no parameters are passed, workspace file is empty and local file is empty.
        # With a proper run_operation mock, _get_versions() returns real versions, so the full
        # configuration flow executes (version selection, workspace + local config updates, ws_success).
        with patch(
            "codename_snake.config_environment.java_set.load_json_with_comments",
            return_value=empty_wk_file_content,
        ):
            result = runner.invoke(set_java_version)
            assert result.exit_code == 0
            assert get_property.call_count == 4
            add_java_formatter.assert_called_once()
            assert any(call.args[1] == "Getting Java versions" for call in run_operation.call_args_list)
            get_local_file.assert_called_once()
            read_mock.assert_called()
            write_mock.assert_called()
            os_replace.assert_called()
            os_path_exists.assert_called()
            get_validated_input.assert_called()
            ws_warning.assert_not_called()
            ws_success.assert_called()
            local_file_content: str = write_mock.mock_calls[-1].args[0]
            local_file_content_lines = [line.strip() for line in local_file_content.splitlines() if line]
            assert any(line.startswith("export JAVA_HOME='") for line in local_file_content_lines)
            assert 'export PATH="$JAVA_HOME/bin:$PATH"' in local_file_content_lines


def test_set_java_version_darwin_defined_versions(
    _mk_os_darwin: MagicMock,
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
    add_java_formatter: MagicMock,
) -> None:
    """Test _java_set"""
    os_path_exists: MagicMock = mk_os.path.exists
    wk_file_content = load_json_with_comments(DARWIN_FILES["wk_file"])
    m_open: MagicMock = mock_open()
    local_file = DARWIN_FILES["local_file"]

    # 5 realistic paths (including temurin-19.0.2 which matches the workspace/local file);
    # get_validated_input returns "5" for the override scenario so we need exactly 5 entries.
    java_paths_stdout = "\n".join([
        "/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home/bin/java",
        "/Users/carlosmorales/Library/Java/JavaVirtualMachines/openjdk-21.0.2/Contents/Home/bin/java",
        "/Users/carlosmorales/Library/Java/JavaVirtualMachines/temurin-19.0.2/Contents/Home/bin/java",
        "/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home/bin/java",
        "/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/bin/java",
    ])
    java_detail_stdout = (
        'openjdk version "21.0.5" 2024-10-15\n'
        'OpenJDK Runtime Environment (build 21.0.5)\n'
        'OpenJDK 64-Bit Server VM (build 21.0.5, mixed mode)'
    )

    def run_op_side_effect(cmd: str, msg: str) -> MagicMock:
        """Return Java paths on the first call and per-path version details on subsequent calls.

        Parameters:
            cmd: The shell command string (unused by this side effect).
            msg: The descriptive message passed to run_operation; used to distinguish call type.

        Returns:
            MagicMock whose `.stdout` contains Java executable paths when *msg* is
            "Getting Java versions", or a synthetic `java -version` output otherwise.
        """
        result: MagicMock = MagicMock()
        result.stdout = java_paths_stdout if msg == "Getting Java versions" else java_detail_stdout
        return result

    run_operation.side_effect = run_op_side_effect

    def read_side_effect() -> str:
        """Read the local shell config file from disk so write assertions can inspect its content.

        Returns:
            The current text content of the local configuration file.
        """
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
                add_java_formatter,
            )

        # Test when no parameters are passed, workspace file and local file have versions.
        # The workspace and local file both point to temurin-19.0.2; determine_tool_version
        # should identify it automatically without requiring user selection.
        with patch(
            "codename_snake.config_environment.java_set.load_json_with_comments",
            return_value=wk_file_content,
        ):
            runner = CliRunner()
            result = runner.invoke(set_java_version)
            assert result.exit_code == 0
            assert get_property.call_count == 4
            add_java_formatter.assert_called_once()
            assert any(call.args[1] == "Getting Java versions" for call in run_operation.call_args_list)
            get_local_file.assert_called_once()
            read_mock.assert_called()
            write_mock.assert_called()
            os_replace.assert_called()
            os_path_exists.assert_called()
            get_validated_input.assert_not_called()
            ws_warning.assert_not_called()
            ws_success.assert_called()
            mocks_reset()
            run_operation.side_effect = run_op_side_effect  # restore after reset

            # Test when override and workspace file and local file have versions
            get_validated_input.return_value = "5"  # Return the first version 8.5
            JavaVersion._id_counter = 0  # pylint: disable=protected-access
            result = runner.invoke(set_java_version, ["-o"])
            assert result.exit_code == 0
            assert get_property.call_count == 4
            add_java_formatter.assert_called_once()
            assert any(call.args[1] == "Getting Java versions" for call in run_operation.call_args_list)
            get_local_file.assert_called_once()
            read_mock.assert_called()
            write_mock.assert_called()
            os_replace.assert_called()
            os_path_exists.assert_called()
            get_validated_input.assert_called_once()
            ws_warning.assert_not_called()
            ws_success.assert_called()
            local_file_content: str = write_mock.mock_calls[-1].args[0]
            local_file_content_lines = [line.strip() for line in local_file_content.splitlines() if line]
            assert any(line.startswith("export JAVA_HOME='") for line in local_file_content_lines)
            assert 'export PATH="$JAVA_HOME/bin:$PATH"' in local_file_content_lines


def test_set_java_version_failing_scenarios(
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
    add_java_formatter: MagicMock,
    set_version_runtime: MagicMock,
) -> None:
    """Test _java_set"""
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
            JavaVersion._id_counter = 0  # pylint: disable=protected-access
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
                add_java_formatter,
                set_version_runtime,
            )

        with patch("codename_snake.config_environment.java_set.OS", "Darwin"):
            with patch(
                "codename_snake.config_environment.java_set.load_json_with_comments",
                return_value=wk_file_content,
            ):

                # Test when version is not numeric
                def side_effect_func1(versions: list[JavaVersion], json_data: Any) -> str:
                    """Side effect"""
                    versions[-1].version = "non_numeric"
                    return _set_version_runtime(versions, json_data)

                set_version_runtime.side_effect = side_effect_func1
                result = runner.invoke(set_java_version, ["-o"])
                assert result.exit_code == 0
                assert get_property.call_count == 4
                add_java_formatter.assert_called_once()
                assert any(call.args[1] == "Getting Java versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()

                # Test when version starts with 1 and then is not numeric
                def side_effect_func2(versions: list[JavaVersion], json_data: Any) -> str:
                    """Side effect"""
                    versions[-1].version = "1.non_numeric"
                    return _set_version_runtime(versions, json_data)

                set_version_runtime.side_effect = side_effect_func2
                result = runner.invoke(set_java_version, ["-o"])
                assert result.exit_code == 0
                assert get_property.call_count == 4
                add_java_formatter.assert_called_once()
                assert any(call.args[1] == "Getting Java versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()

                # Test when no versions are found
                run_operation.return_value.stdout = ""
                result = runner.invoke(set_java_version, ["-o"])
                assert result.exit_code == 0
                assert get_property.call_count == 4
                add_java_formatter.assert_called_once()
                assert any(call.args[1] == "Getting Java versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()

        with patch("codename_snake.config_environment.java_set.OS", "Windows"):
            # Test when no versions are found
            run_operation.return_value.stdout = ""
            with patch(
                "codename_snake.config_environment.java_set.load_json_with_comments",
                return_value=wk_file_content,
            ):
                result = runner.invoke(set_java_version, ["-o"])
                assert result.exit_code == 0
                assert get_property.call_count == 4
                add_java_formatter.assert_called_once()
                assert any(call.args[1] == "Getting Java versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()

        with patch("codename_snake.config_environment.java_set.OS", "Linux"):
            # Test when no versions are found
            run_operation.return_value.stdout = ""
            with patch(
                "codename_snake.config_environment.java_set.load_json_with_comments",
                return_value=wk_file_content,
            ):
                result = runner.invoke(set_java_version, ["-o"])
                assert result.exit_code == 0
                assert get_property.call_count == 4
                add_java_formatter.assert_called_once()
                assert any(call.args[1] == "Getting Java versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()


def test_add_java_formatter(
    get_property: MagicMock,
    java_set: MagicMock,
    get_local_file: MagicMock,
    mk_os_java: MagicMock,
    os_replace: MagicMock,
    ws_success: MagicMock,
    shutil_copyfile: MagicMock,
) -> None:
    """Test gradle command"""

    runner = CliRunner()
    os_path_exists: MagicMock = mk_os_java.path.exists
    os_getcwd: MagicMock = mk_os_java.getcwd
    os_makedirs: MagicMock = mk_os_java.makedirs
    m_open: MagicMock = mock_open()
    xml_path = f"{RESOURCE_PATH}/java-formatter.xml"
    cwd_path = "cwd_path"
    cwd_vscode_path = f"{cwd_path}/.vscode"
    local_xml_path = f"{cwd_vscode_path}/java-formatter.xml"
    empty_wk_file_content = load_json_with_comments(EMPTY_WK_FILE)
    wk_file_content = load_json_with_comments(DARWIN_FILES["wk_file"])
    os_getcwd.return_value = cwd_path
    with patch("builtins.open", m_open):
        file_mock: MagicMock = m_open.return_value
        write_mock: MagicMock = file_mock.write

        def mocks_reset() -> None:
            """Reset the mocks."""
            JavaVersion._id_counter = 0  # pylint: disable=protected-access
            reset_mocks(
                get_property,
                get_local_file,
                java_set,
                mk_os_java,
                os_replace,
                ws_success,
                shutil_copyfile,
                os_path_exists,
                os_getcwd,
                os_makedirs,
                m_open,
                file_mock,
                write_mock,
            )

        os_path_exists.return_value = False
        result = runner.invoke(set_java_version)
        assert result.exit_code == 1
        assert isinstance(result.exception, AssertionError)
        assert get_property.call_count == 4
        get_local_file.assert_called_once()
        java_set.assert_called_once()
        os_path_exists.assert_called_once_with(xml_path)
        os_getcwd.assert_not_called()
        os_makedirs.assert_not_called()
        write_mock.assert_not_called()
        os_replace.assert_not_called()
        ws_success.assert_not_called()
        mocks_reset()

        # Test when settings are not updated and xml file exists
        with patch(
            "codename_snake.config_environment.java_set.load_json_with_comments",
            return_value=empty_wk_file_content,
        ):
            os_path_exists.return_value = True
            result = runner.invoke(set_java_version)
            assert result.exit_code == 0
            assert get_property.call_count == 4
            get_local_file.assert_called_once()
            java_set.assert_called_once()
            os_path_exists.assert_has_calls([call(xml_path), call(cwd_vscode_path), call(local_xml_path)])
            os_getcwd.assert_called_once()
            os_makedirs.assert_not_called()
            os_replace.assert_called_once()
            shutil_copyfile.assert_not_called()
            ws_success.assert_not_called()
            wk_file_content_array = []
            for current_call in write_mock.mock_calls:
                args = [arg for arg in current_call.args if arg]
                if args:
                    wk_file_content_array.append("".join(set(current_call.args)))
            wk_content = "".join(wk_file_content_array)
            wk_content_lines = [line.strip().rstrip(",") for line in wk_content.splitlines() if line]
            assert '"java.format.settings.url": "cwd_path/.vscode/java-formatter.xml"' in wk_content_lines
            mocks_reset()

        # Test when settings are not updated, xml file exists and resource path don't exist
        count = 0

        def side_effect_func2(_x: str) -> bool:
            """Side effect"""
            nonlocal count
            count += 1
            if count == 2:
                return False
            return True

        os_path_exists.side_effect = side_effect_func2
        with patch(
            "codename_snake.config_environment.java_set.load_json_with_comments",
            return_value=empty_wk_file_content,
        ):
            os_path_exists.return_value = True
            result = runner.invoke(set_java_version)
            assert result.exit_code == 0
            assert get_property.call_count == 4
            get_local_file.assert_called_once()
            java_set.assert_called_once()
            os_path_exists.assert_has_calls([call(xml_path), call(cwd_vscode_path), call(local_xml_path)])
            os_getcwd.assert_called_once()
            os_makedirs.assert_called_once()
            os_replace.assert_called_once()
            shutil_copyfile.assert_not_called()
            ws_success.assert_called_once()
            wk_file_content_array = []
            for current_call in write_mock.mock_calls:
                args = [arg for arg in current_call.args if arg]
                if args:
                    wk_file_content_array.append("".join(set(current_call.args)))
            wk_content = "".join(wk_file_content_array)
            wk_content_lines = [line.strip().rstrip(",") for line in wk_content.splitlines() if line]
            assert '"java.format.settings.url": "cwd_path/.vscode/java-formatter.xml"' in wk_content_lines
            mocks_reset()

        # Test when settings are not updated, xml file and resource path don't exist
        count = 0

        def side_effect_func3(_x: str) -> bool:
            """Side effect"""
            nonlocal count
            count += 1
            if count == 1:
                return True
            return False

        os_path_exists.side_effect = side_effect_func3
        with patch(
            "codename_snake.config_environment.java_set.load_json_with_comments",
            return_value=empty_wk_file_content,
        ):
            os_path_exists.return_value = True
            result = runner.invoke(set_java_version)
            assert result.exit_code == 0
            assert get_property.call_count == 4
            get_local_file.assert_called_once()
            java_set.assert_called_once()
            os_path_exists.assert_has_calls([call(xml_path), call(cwd_vscode_path), call(local_xml_path)])
            os_getcwd.assert_called_once()
            os_makedirs.assert_called_once()
            os_replace.assert_called_once()
            shutil_copyfile.assert_called_once_with(xml_path, local_xml_path)
            assert ws_success.call_count == 2
            wk_file_content_array = []
            for current_call in write_mock.mock_calls:
                args = [arg for arg in current_call.args if arg]
                if args:
                    wk_file_content_array.append("".join(set(current_call.args)))
            wk_content = "".join(wk_file_content_array)
            wk_content_lines = [line.strip().rstrip(",") for line in wk_content.splitlines() if line]
            assert '"java.format.settings.url": "cwd_path/.vscode/java-formatter.xml"' in wk_content_lines
            mocks_reset()

        # Test when settings are updated, xml file and resource path don't exist
        count = 0
        os_path_exists.side_effect = side_effect_func3
        with patch(
            "codename_snake.config_environment.java_set.load_json_with_comments",
            return_value=wk_file_content,
        ):
            os_path_exists.return_value = True
            result = runner.invoke(set_java_version)
            assert result.exit_code == 0
            assert get_property.call_count == 4
            get_local_file.assert_called_once()
            java_set.assert_called_once()
            os_path_exists.assert_has_calls([call(xml_path), call(cwd_vscode_path), call(local_xml_path)])
            os_getcwd.assert_called_once()
            os_makedirs.assert_called_once()
            os_replace.assert_not_called()
            shutil_copyfile.assert_called_once_with(xml_path, local_xml_path)
            assert ws_success.call_count == 2
            write_mock.assert_not_called()
            mocks_reset()
