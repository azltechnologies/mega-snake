"""Test the maven_set module."""

import builtins
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Generator
from unittest.mock import MagicMock, call, mock_open, patch

import pytest
from click.testing import CliRunner

from mega_snake.config_environment.maven_set import (
    ENV_VARIABLE,
    MAVEN_ENV_VAR,
    MAVEN_EXEC_QUERY,
    MAVEN_HOME_QUERY,
    MavenVersion,
    _detect_maven_home,
    _maven_set,
    execute,
    maven_project_setup,
    set_maven_version,
)
from mega_snake.util.util import load_json_with_comments

FILE_WK = "wk_file"
PATH_WK = "wk_path"
LOCAL_FILE = "local_file"
SHELL = "bash"

EMPTY_WK_FILE: str = "src/tests/maven/empty.code-workspace"
EMPTY_SH_FILE: str = "src/tests/maven/empty_local_file.sh"

DARWIN_FILES: dict[str, str] = {
    "wk_file": "src/tests/maven/darwin.code-workspace",
    "local_file": "src/tests/maven/bash_local_file.sh",
}

TESTS_ROOT = Path(__file__).resolve().parents[1]

real_open = builtins.open


def reset_mocks(*mocks: MagicMock) -> None:
    """Reset all mocks"""
    for mock in mocks:
        mock.reset_mock()


@pytest.fixture(autouse=True)
def run_after_each_test() -> Generator[None, None, None]:
    """Reset the counter, Maven task args, and watcher methods after each test"""
    from mega_snake.config_environment.models.vscode_task import (
        VscodeTask,
        MAVEN_CLEAN_INSTALL_ARGS,
        MAVEN_TEST_ARGS,
        MAVEN_VERIFY_ARGS,
        MAVEN_DEPENDENCY_TREE_ARGS,
        MAVEN_SPRING_BOOT_ARGS,
    )
    from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher

    # Reset Maven VscodeTask enum args to avoid mutation from previous tests
    VscodeTask.MAVEN_CLEAN_INSTALL.args = list(MAVEN_CLEAN_INSTALL_ARGS)
    VscodeTask.MAVEN_TEST.args = list(MAVEN_TEST_ARGS)
    VscodeTask.MAVEN_VERIFY.args = list(MAVEN_VERIFY_ARGS)
    VscodeTask.MAVEN_DEPENDENCY_TREE.args = list(MAVEN_DEPENDENCY_TREE_ARGS)
    VscodeTask.MAVEN_SPRING_BOOT.args = list(MAVEN_SPRING_BOOT_ARGS)

    # Restore methods on Maven LogWatcher members (may be monkeypatched by other tests)
    original_get_pattern_date = LogWatcher.get_pattern_date
    original_to_dict = LogWatcher.to_dict
    for member in [LogWatcher.MAVEN_CLEAN_INSTALL, LogWatcher.MAVEN_TEST,
                   LogWatcher.MAVEN_VERIFY, LogWatcher.MAVEN_DEPENDENCY_TREE,
                   LogWatcher.MAVEN_SPRING_BOOT]:
        member.get_pattern_date = original_get_pattern_date.__get__(member, LogWatcher)
        member.to_dict = original_to_dict.__get__(member, LogWatcher)
    yield
    MavenVersion._id_counter = 0  # pylint: disable=protected-access


@pytest.fixture(name="_mk_os_linux")
def fixture_mk_os_linux() -> Generator[MagicMock, None, None]:
    """Mock OS to Linux"""
    with patch("mega_snake.config_environment.maven_set.OS", "Linux") as mock:
        yield mock


@pytest.fixture(name="mk_execute")
def fixture_execute() -> Generator[MagicMock, None, None]:
    """Mock mk_execute"""
    with patch("mega_snake.config_environment.maven_set.execute", wraps=execute) as mock:
        yield mock


@pytest.fixture(name="maven_set")
def fixture__maven_set() -> Generator[MagicMock, None, None]:
    """Mock _maven_set"""
    with patch("mega_snake.config_environment.maven_set._maven_set") as mock:
        yield mock


@pytest.fixture(name="get_property")
def fixture_get_property() -> Generator[MagicMock, None, None]:
    """Mock get_property"""

    def prop_side_effect(prop: str) -> Any:
        if prop == "workspace_file":
            return FILE_WK
        elif prop == "working_path":
            return PATH_WK
        elif prop == "shell":
            return SHELL
        else:
            raise ValueError(f"Invalid property: {prop}")

    with patch("mega_snake.config_environment.maven_set.get_property", side_effect=prop_side_effect) as mock:
        yield mock


@pytest.fixture(name="get_local_file")
def fixture_get_local_file() -> Generator[MagicMock, None, None]:
    """Mock get_local_file"""
    with patch("mega_snake.config_environment.maven_set.get_local_file") as mock:
        mock.return_value = LOCAL_FILE
        yield mock


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock, None, None]:
    """Mock run_operation"""
    return_value = """/opt/apache-maven-3.9.6/libexec\n/opt/apache-maven-3.9.8/libexec\n/opt/apache-maven-3.8.8/libexec\n"""
    with patch("mega_snake.config_environment.maven_set.run_operation") as mock:
        mock.return_value.stdout = return_value
        yield mock


@pytest.fixture(name="ws_warning")
def fixture_ws_warning() -> Generator[MagicMock, None, None]:
    """Mock ws_warning"""
    with patch("mega_snake.config_environment.maven_set.ws_warning") as mock:
        yield mock


@pytest.fixture(name="ws_success")
def fixture_ws_success() -> Generator[MagicMock, None, None]:
    """Mock ws_success"""
    with patch("mega_snake.config_environment.maven_set.ws_success") as mock:
        yield mock


@pytest.fixture(name="get_validated_input")
def fixture_get_validated_input() -> Generator[MagicMock, None, None]:
    """Mock get_validated_input"""
    with patch("mega_snake.config_environment.models.tools_version.get_validated_input") as mock:
        mock.return_value = "1"
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock, None, None]:
    """Mock os"""
    with patch("mega_snake.config_environment.models.tools_version.os") as mock:
        yield mock


@pytest.fixture(name="os_replace")
def fixture_os_replace() -> Generator[MagicMock, None, None]:
    """Mock os_replace"""
    with patch("mega_snake.config_environment.util.os") as mock:
        yield mock.replace


# --- Command invocation tests ---


def test_command(
    mk_execute: MagicMock, get_property: MagicMock, maven_set: MagicMock, get_local_file: MagicMock
) -> None:
    """Test set-maven command invocation delegates correctly."""
    runner = CliRunner()

    # Test with no parameters
    result = runner.invoke(set_maven_version)
    assert result.exit_code == 0
    get_property.assert_has_calls([call("workspace_file"), call("working_path"), call("shell")])
    assert get_property.call_count == 3
    get_local_file.assert_called_once()
    mk_execute.assert_called_once_with(None, FILE_WK)
    maven_set.assert_called_once_with(FILE_WK, PATH_WK, LOCAL_FILE, SHELL, None)
    reset_mocks(get_property, get_local_file, mk_execute, maven_set)

    # Test with --maven-home parameter
    result = runner.invoke(set_maven_version, ["--maven-home", "/opt/maven"])
    assert result.exit_code == 0
    get_property.assert_has_calls([call("workspace_file"), call("working_path"), call("shell")])
    assert get_property.call_count == 3
    get_local_file.assert_called_once()
    mk_execute.assert_called_once_with("/opt/maven", FILE_WK)
    maven_set.assert_called_once_with(FILE_WK, PATH_WK, LOCAL_FILE, SHELL, "/opt/maven")
    reset_mocks(get_property, get_local_file, mk_execute, maven_set)

    # Test with -m short option
    result = runner.invoke(set_maven_version, ["-m", "/usr/local/maven"])
    assert result.exit_code == 0
    mk_execute.assert_called_once_with("/usr/local/maven", FILE_WK)


# --- MavenVersion tests ---


def test_maven_version_str() -> None:
    """Test MavenVersion.__str__"""
    version = "3.9.8"
    path = "/opt/apache-maven-3.9.8"

    maven_version = MavenVersion(version, path)
    result = str(maven_version)
    assert "Id: 1" in result
    assert f"Maven Version: {version}" in result
    assert f"path: {path}" in result


# --- Empty workspace file tests ---


def test_set_maven_version_linux_empty_files(
    _mk_os_linux: MagicMock,
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
) -> None:
    """Test _maven_set with empty workspace and local file."""
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

        with patch(
            "mega_snake.config_environment.maven_set.load_json_with_comments",
            return_value=empty_wk_file_content,
        ):
            runner = CliRunner()
            result = runner.invoke(set_maven_version)
            assert result.exit_code == 0
            assert get_property.call_count == 3
            assert any(call.args[1] == "Getting Maven versions" for call in run_operation.call_args_list)
            get_local_file.assert_called_once()
            assert read_mock.call_count >= 1
            write_mock.assert_called()
            os_replace.assert_called_once()
            assert os_path_exists.call_count == 2
            get_validated_input.assert_called_once()
            ws_warning.assert_not_called()
            ws_success.assert_called_once()
            # Verify local file content has M2_HOME
            local_file_content: str = write_mock.mock_calls.pop().args[0]
            local_file_content_lines = [line.strip() for line in local_file_content.splitlines() if line]
            assert any(line.startswith("export M2_HOME='") for line in local_file_content_lines)
            assert 'export PATH="$M2_HOME/bin:$PATH"' in local_file_content_lines
            # Verify workspace file content has Maven settings
            wk_file_content_array = []
            for current_call in write_mock.mock_calls:
                args = [arg for arg in current_call.args if arg]
                if args:
                    wk_file_content_array.append("".join(set(current_call.args)))
            wk_content = "".join(wk_file_content_array)
            wk_content_lines = [line.strip().rstrip(",") for line in wk_content.splitlines() if line]
            assert any(line.startswith('"M2_HOME": "') for line in wk_content_lines)
            assert any(line.startswith('"maven.executable.path": "') for line in wk_content_lines)


# --- Defined version workspace file tests ---


def test_set_maven_version_linux_defined_versions(
    _mk_os_linux: MagicMock,
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
) -> None:
    """Test _maven_set with workspace and local file that already have Maven versions."""
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

        # Test when workspace and local file already have versions
        with patch(
            "mega_snake.config_environment.maven_set.load_json_with_comments",
            return_value=wk_file_content,
        ):
            runner = CliRunner()
            result = runner.invoke(set_maven_version)
            assert result.exit_code == 0
            assert get_property.call_count == 3
            assert any(call.args[1] == "Getting Maven versions" for call in run_operation.call_args_list)
            get_local_file.assert_called_once()
            assert read_mock.call_count >= 1
            write_mock.assert_called()
            os_replace.assert_called_once()
            assert os_path_exists.call_count >= 1
            get_validated_input.assert_called_once()
            ws_warning.assert_not_called()
            ws_success.assert_called_once()
            mocks_reset()

            # Test selecting a different version with --maven-home
            MavenVersion._id_counter = 0  # pylint: disable=protected-access
            with patch("mega_snake.config_environment.maven_set.os.path.isdir", return_value=True):
                result = runner.invoke(set_maven_version, ["-m", "/opt/apache-maven-3.9.8/libexec"])
            assert result.exit_code == 0
            assert get_property.call_count == 3
            get_local_file.assert_called_once()
            assert read_mock.call_count >= 1
            write_mock.assert_called()
            os_replace.assert_called_once()
            ws_warning.assert_not_called()
            ws_success.assert_called_once()
            # Verify local file content has M2_HOME set to the selected version
            local_file_content: str = write_mock.mock_calls.pop().args[0]
            local_file_content_lines = [line.strip() for line in local_file_content.splitlines() if line]
            assert any(line.startswith("export M2_HOME='") for line in local_file_content_lines)
            assert 'export PATH="$M2_HOME/bin:$PATH"' in local_file_content_lines
            # Verify workspace file content
            wk_file_content_array = []
            for current_call in write_mock.mock_calls:
                args = [arg for arg in current_call.args if arg]
                if args:
                    wk_file_content_array.append("".join(set(current_call.args)))
            wk_content = "".join(wk_file_content_array)
            wk_content_lines = [line.strip().rstrip(",") for line in wk_content.splitlines() if line]
            assert any(line.startswith('"M2_HOME": "') for line in wk_content_lines)
            assert any(line.startswith('"maven.executable.path": "') for line in wk_content_lines)


# --- Failing scenarios ---


def test_set_maven_version_failing_scenarios(
    get_property: MagicMock,
    run_operation: MagicMock,
    get_local_file: MagicMock,
    ws_warning: MagicMock,
    ws_success: MagicMock,
    get_validated_input: MagicMock,
    mk_os: MagicMock,
    os_replace: MagicMock,
) -> None:
    """Test _maven_set with failing scenarios."""
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

        with patch("mega_snake.config_environment.maven_set.OS", "Linux"):
            # Test when no versions are found
            run_operation.return_value.stdout = ""
            with patch(
                "mega_snake.config_environment.maven_set.load_json_with_comments",
                return_value=wk_file_content,
            ):
                result = runner.invoke(set_maven_version)
                assert result.exit_code == 0
                assert get_property.call_count == 3
                assert any(call.args[1] == "Getting Maven versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()

        with patch("mega_snake.config_environment.maven_set.OS", "Darwin"):
            # Test when no versions are found on Darwin
            run_operation.return_value.stdout = ""
            with patch(
                "mega_snake.config_environment.maven_set.load_json_with_comments",
                return_value=wk_file_content,
            ):
                result = runner.invoke(set_maven_version)
                assert result.exit_code == 0
                assert get_property.call_count == 3
                assert any(call.args[1] == "Getting Maven versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()

        with patch("mega_snake.config_environment.maven_set.OS", "Windows"):
            # Test when no versions are found on Windows
            run_operation.return_value.stdout = ""
            with patch(
                "mega_snake.config_environment.maven_set.load_json_with_comments",
                return_value=wk_file_content,
            ):
                result = runner.invoke(set_maven_version)
                assert result.exit_code == 0
                assert get_property.call_count == 3
                assert any(call.args[1] == "Getting Maven versions" for call in run_operation.call_args_list)
                get_local_file.assert_called_once()
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                os_replace.assert_not_called()
                os_path_exists.assert_not_called()
                get_validated_input.assert_not_called()
                ws_warning.assert_called_once()
                ws_success.assert_not_called()
                mocks_reset()


# --- maven-project-setup tests with code-workspace updates ---


def test_maven_project_setup_updates_workspace_tasks_and_watchers() -> None:
    """maven-project-setup should write Maven tasks and log watchers into code-workspace."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pom.xml").write_text(
            (TESTS_ROOT / "maven" / "pom.xml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        workspace = Path("test.code-workspace")
        fixture_workspace = TESTS_ROOT / "test.code-workspace"
        workspace.write_text(fixture_workspace.read_text(encoding="utf-8"), encoding="utf-8")
        Path("workdir").mkdir(parents=True, exist_ok=True)

        def property_side_effect(name: str) -> str:
            mapping = {"workspace_file": str(workspace), "working_path": "workdir"}
            return mapping[name]

        with patch("mega_snake.config_environment.maven_set.get_property", side_effect=property_side_effect):
            result = runner.invoke(maven_project_setup)

        assert result.exit_code == 0
        updated = load_json_with_comments(str(workspace))

        # Verify all Maven tasks were added
        labels = [task["label"] for task in updated["tasks"]["tasks"]]
        assert "Maven Clean Install" in labels
        assert "Maven Test" in labels
        assert "Maven Verify" in labels
        assert "Maven Dependency Tree" in labels
        assert "Maven Spring Boot Run" in labels

        # Verify task structure
        clean_install = next(task for task in updated["tasks"]["tasks"] if task["label"] == "Maven Clean Install")
        assert clean_install["command"] == "${config:maven.executable.path}"
        assert clean_install["type"] == "shell"
        assert clean_install["group"] == "build"
        assert "clean" in clean_install["args"]
        assert "install" in clean_install["args"]
        assert "'workdir/logs/maven_clean_install_${input:todayTimestamp}.log'" in clean_install["args"]
        assert ">" in clean_install["args"]
        assert "2>&1" in clean_install["args"]

        # Verify Maven Test task
        test_task = next(task for task in updated["tasks"]["tasks"] if task["label"] == "Maven Test")
        assert test_task["command"] == "${config:maven.executable.path}"
        assert "test" in test_task["args"]
        assert "'workdir/logs/maven_test_${input:todayTimestamp}.log'" in test_task["args"]

        # Verify Spring Boot Run task
        spring_task = next(task for task in updated["tasks"]["tasks"] if task["label"] == "Maven Spring Boot Run")
        assert "spring-boot:run" in spring_task["args"]
        assert "'workdir/logs/maven_spring_boot_${input:todayTimestamp}.log'" in spring_task["args"]

        # Verify log watchers were added
        watcher_titles = [watcher["title"] for watcher in updated["settings"]["logViewer.watch"]]
        assert "MAVEN CLEAN INSTALL" in watcher_titles
        assert "MAVEN TEST" in watcher_titles
        assert "MAVEN VERIFY" in watcher_titles
        assert "MAVEN DEPENDENCY TREE" in watcher_titles
        assert "MAVEN SPRING BOOT RUN" in watcher_titles

        # Verify watcher structure
        clean_watcher = next(
            w for w in updated["settings"]["logViewer.watch"] if w["title"] == "MAVEN CLEAN INSTALL"
        )
        assert "workdir/logs/maven_clean_install_*.log" in clean_watcher["pattern"]
        assert clean_watcher["autoScroll"] is True

        # Verify tasks version
        assert updated["tasks"]["version"] == "2.0.0"

        # Verify todayTimestamp input was added
        inputs = updated["tasks"]["inputs"]
        assert any(inp["id"] == "todayTimestamp" for inp in inputs)


def test_maven_project_setup_with_existing_workspace_tasks() -> None:
    """maven-project-setup should work alongside pre-existing workspace tasks."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pom.xml").write_text(
            (TESTS_ROOT / "maven" / "pom.xml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        workspace = Path("test.code-workspace")
        # Use a workspace that already has Gradle tasks (from darwin fixture)
        fixture_workspace = TESTS_ROOT / "gradle" / "darwin.code-workspace"
        workspace.write_text(fixture_workspace.read_text(encoding="utf-8"), encoding="utf-8")
        Path("workdir").mkdir(parents=True, exist_ok=True)

        def property_side_effect(name: str) -> str:
            mapping = {"workspace_file": str(workspace), "working_path": "workdir"}
            return mapping[name]

        with patch("mega_snake.config_environment.maven_set.get_property", side_effect=property_side_effect):
            result = runner.invoke(maven_project_setup)

        assert result.exit_code == 0
        updated = load_json_with_comments(str(workspace))
        labels = [task["label"] for task in updated["tasks"]["tasks"]]

        # Gradle tasks should still exist
        assert "Gradle Build No Test" in labels
        assert "Gradle Build" in labels

        # Maven tasks should be added alongside
        assert "Maven Clean Install" in labels
        assert "Maven Test" in labels
        assert "Maven Verify" in labels
        assert "Maven Dependency Tree" in labels
        assert "Maven Spring Boot Run" in labels

        # Gradle watchers should still exist
        watcher_titles = [w["title"] for w in updated["settings"]["logViewer.watch"]]
        assert "GRADLE CLEAN BUILD NO TEST" in watcher_titles
        assert "GRADLE CLEAN BUILD" in watcher_titles

        # Maven watchers should be added alongside
        assert "MAVEN CLEAN INSTALL" in watcher_titles
        assert "MAVEN TEST" in watcher_titles


def test_maven_project_setup_is_idempotent_without_override() -> None:
    """Repeated maven-project-setup should not duplicate Maven tasks and watchers."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pom.xml").write_text(
            (TESTS_ROOT / "maven" / "pom.xml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        workspace = Path("test.code-workspace")
        workspace.write_text(
            json.dumps({"folders": [{"path": ".", "name": "main"}], "settings": {}}), encoding="utf-8"
        )
        Path("workdir").mkdir(parents=True, exist_ok=True)

        def property_side_effect(name: str) -> str:
            mapping = {"workspace_file": str(workspace), "working_path": "workdir"}
            return mapping[name]

        with patch("mega_snake.config_environment.maven_set.get_property", side_effect=property_side_effect):
            # First invocation
            result = runner.invoke(maven_project_setup)
            assert result.exit_code == 0
            # Second invocation (idempotent)
            result = runner.invoke(maven_project_setup)
            assert result.exit_code == 0

        updated = load_json_with_comments(str(workspace))
        labels = [task["label"] for task in updated["tasks"]["tasks"]]
        assert labels.count("Maven Clean Install") == 1
        assert labels.count("Maven Test") == 1
        assert labels.count("Maven Verify") == 1
        assert labels.count("Maven Dependency Tree") == 1
        assert labels.count("Maven Spring Boot Run") == 1
        watcher_titles = [watcher["title"] for watcher in updated["settings"]["logViewer.watch"]]
        assert watcher_titles.count("MAVEN CLEAN INSTALL") == 1
        assert watcher_titles.count("MAVEN TEST") == 1
        assert watcher_titles.count("MAVEN VERIFY") == 1
        assert watcher_titles.count("MAVEN DEPENDENCY TREE") == 1
        assert watcher_titles.count("MAVEN SPRING BOOT RUN") == 1


def test_maven_project_setup_override_replaces_existing_tasks() -> None:
    """maven-project-setup with --override should replace existing Maven tasks."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pom.xml").write_text(
            (TESTS_ROOT / "maven" / "pom.xml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        workspace = Path("test.code-workspace")
        # Use the pre-configured Maven workspace fixture
        fixture_workspace = TESTS_ROOT / "maven" / "darwin.code-workspace"
        workspace.write_text(fixture_workspace.read_text(encoding="utf-8"), encoding="utf-8")
        Path("workdir").mkdir(parents=True, exist_ok=True)

        def property_side_effect(name: str) -> str:
            mapping = {"workspace_file": str(workspace), "working_path": "workdir"}
            return mapping[name]

        with patch("mega_snake.config_environment.maven_set.get_property", side_effect=property_side_effect):
            result = runner.invoke(maven_project_setup, ["--override"])

        assert result.exit_code == 0
        updated = load_json_with_comments(str(workspace))
        labels = [task["label"] for task in updated["tasks"]["tasks"]]
        # Still exactly one of each after override
        assert labels.count("Maven Clean Install") == 1
        assert labels.count("Maven Test") == 1
        assert labels.count("Maven Verify") == 1
        assert labels.count("Maven Dependency Tree") == 1
        assert labels.count("Maven Spring Boot Run") == 1

        # Verify the tasks were updated (working_path is "workdir" not the original path)
        clean_install = next(task for task in updated["tasks"]["tasks"] if task["label"] == "Maven Clean Install")
        assert "'workdir/logs/maven_clean_install_${input:todayTimestamp}.log'" in clean_install["args"]


def test_maven_project_setup_requires_pom_file() -> None:
    """maven-project-setup should fail when pom.xml is missing."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(maven_project_setup)
        assert result.exit_code != 0
        assert isinstance(result.exception, FileNotFoundError)


def test_maven_project_setup_from_empty_workspace() -> None:
    """maven-project-setup from a completely empty workspace should create all structures."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pom.xml").write_text(
            (TESTS_ROOT / "maven" / "pom.xml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        workspace = Path("test.code-workspace")
        # Use Maven empty workspace fixture (has comments)
        fixture_workspace = TESTS_ROOT / "maven" / "empty.code-workspace"
        workspace.write_text(fixture_workspace.read_text(encoding="utf-8"), encoding="utf-8")
        Path("workdir").mkdir(parents=True, exist_ok=True)

        def property_side_effect(name: str) -> str:
            mapping = {"workspace_file": str(workspace), "working_path": "workdir"}
            return mapping[name]

        with patch("mega_snake.config_environment.maven_set.get_property", side_effect=property_side_effect):
            result = runner.invoke(maven_project_setup)

        assert result.exit_code == 0
        updated = load_json_with_comments(str(workspace))

        # tasks section created from scratch
        assert "tasks" in updated
        assert updated["tasks"]["version"] == "2.0.0"
        assert len(updated["tasks"]["tasks"]) == 5
        assert len(updated["tasks"]["inputs"]) >= 1

        # settings.logViewer.watch created from scratch
        assert "logViewer.watch" in updated["settings"]
        assert len(updated["settings"]["logViewer.watch"]) == 5


# --- _maven_set internal function tests ---


def test_maven_set_updates_workspace_and_local_config() -> None:
    """_maven_set should update workspace queries and local M2_HOME setting."""
    versions = [MavenVersion(version="3.9.9", _path="/opt/maven-3.9.9", default=False)]

    with patch("mega_snake.config_environment.maven_set._get_versions", return_value=versions), patch(
        "mega_snake.config_environment.maven_set.determine_tool_version", return_value=None
    ), patch("mega_snake.config_environment.maven_set.select_version", return_value=versions[0]), patch(
        "mega_snake.config_environment.maven_set.update_workspace"
    ) as update_workspace_mock, patch(
        "mega_snake.config_environment.maven_set.set_version_local_config"
    ) as set_local:
        _maven_set(
            workspace_file="src/tests/test.code-workspace",
            working_path="/tmp/work",
            local_file="/tmp/local.sh",
            shell="bash",
            maven_home=None,
        )
        assert versions[0].default is True
        update_workspace_mock.assert_called_once()
        updated_workspace = update_workspace_mock.call_args.args[0]
        assert updated_workspace["settings"][ENV_VARIABLE]["M2_HOME"] == "/opt/maven-3.9.9"
        assert updated_workspace["settings"]["maven.executable.path"] == "/opt/maven-3.9.9/bin/mvn"
        set_local.assert_called_once_with(versions[0], "/tmp/local.sh", "bash", "M2_HOME")


def test_maven_set_warns_when_no_versions_found() -> None:
    """_maven_set should warn and exit when no Maven installations are discovered."""
    with patch("mega_snake.config_environment.maven_set._get_versions", return_value=[]), patch(
        "mega_snake.config_environment.maven_set.ws_warning"
    ) as ws_warn, patch("mega_snake.config_environment.maven_set.load_json_with_comments") as load_workspace:
        _maven_set(
            workspace_file="src/tests/test.code-workspace",
            working_path="/tmp/work",
            local_file="/tmp/local.sh",
            shell="bash",
            maven_home=None,
        )
        ws_warn.assert_called_once()
        load_workspace.assert_not_called()


def test_maven_set_with_existing_version_in_workspace() -> None:
    """_maven_set should detect existing version from workspace settings and local config."""
    wk_content = load_json_with_comments(DARWIN_FILES["wk_file"])
    versions = [
        MavenVersion(version="3.9.6", _path="/opt/apache-maven-3.9.6", default=False),
        MavenVersion(version="3.9.8", _path="/opt/apache-maven-3.9.8", default=False),
    ]

    with patch("mega_snake.config_environment.maven_set._get_versions", return_value=versions), patch(
        "mega_snake.config_environment.maven_set.load_json_with_comments", return_value=wk_content
    ), patch(
        "mega_snake.config_environment.maven_set.find_local_tool_home", return_value="/opt/apache-maven-3.9.6"
    ), patch("mega_snake.config_environment.maven_set.ws_success") as ws_suc:
        _maven_set(
            workspace_file="src/tests/maven/darwin.code-workspace",
            working_path="/tmp/work",
            local_file="src/tests/maven/bash_local_file.sh",
            shell="bash",
            maven_home=None,
        )
        # All three lookups find the same version -> VersionSetException -> ws_success
        ws_suc.assert_called_once()


# --- _detect_maven_home tests ---


def test_detect_maven_home_prefers_mvn_output() -> None:
    """Maven home should be parsed from mvn -v output when available."""
    with patch("mega_snake.config_environment.maven_set.shutil.which", return_value="/usr/bin/mvn"), patch(
        "mega_snake.config_environment.maven_set.run_operation",
        return_value=SimpleNamespace(stdout="Apache Maven 3.9.8\nMaven home: /opt/apache-maven-3.9.8\n"),
    ):
        assert _detect_maven_home() == "/opt/apache-maven-3.9.8"


def test_detect_maven_home_falls_back_to_binary_path() -> None:
    """Maven home should fall back to the binary path when mvn output lacks Maven home."""
    with patch("mega_snake.config_environment.maven_set.shutil.which", return_value="/usr/local/bin/mvn"), patch(
        "mega_snake.config_environment.maven_set.run_operation", return_value=SimpleNamespace(stdout="")
    ):
        assert _detect_maven_home() == "/usr/local"


def test_detect_maven_home_returns_none_when_mvn_not_found() -> None:
    """Maven home should return None when mvn is not on PATH."""
    with patch("mega_snake.config_environment.maven_set.shutil.which", return_value=None):
        assert _detect_maven_home() is None


def test_detect_maven_home_handles_windows_path() -> None:
    """Maven home should handle Windows-style paths and normalize to forward slashes."""
    with patch("mega_snake.config_environment.maven_set.shutil.which", return_value="C:\\maven\\bin\\mvn"), patch(
        "mega_snake.config_environment.maven_set.run_operation",
        return_value=SimpleNamespace(stdout="Apache Maven 3.9.8\nMaven home: C:\\Program Files\\maven-3.9.8\n"),
    ):
        result = _detect_maven_home()
        assert result == "C:/Program Files/maven-3.9.8"
