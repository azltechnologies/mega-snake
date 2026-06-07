"""Tests for the gcloud sign module"""

from typing import Generator
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
import pytest
from mega_snake.gcloud.sign import gcloud_login_env, gcloud_logout

PROJECT = "test-project"


@pytest.fixture(name="formatting_ws_info")
def fixture_formatting_ws_info() -> Generator[MagicMock]:
    """Mock ws_info"""
    with patch("mega_snake.gcloud.sign.ws_info") as mock:
        mock.return_value = None
        yield mock


@pytest.fixture(name="formatting_ws_success")
def fixture_formatting_ws_success() -> Generator[MagicMock]:
    """Mock ws_success"""
    with patch("mega_snake.gcloud.sign.ws_success") as mock:
        mock.return_value = None
        yield mock


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock]:
    """Mock run_operation"""
    with patch("mega_snake.gcloud.sign.run_operation") as mock:
        yield mock


@pytest.fixture(name="os_system")
def fixture_os_system() -> Generator[MagicMock]:
    """Mock os.system to return 0"""
    with patch("os.system") as mock:
        mock.return_value = 0
        yield mock


@pytest.fixture(name="user_login")
def fixture_user_login() -> Generator[MagicMock]:
    """Mock _user_login"""
    with patch("mega_snake.gcloud.sign._user_login") as mock:
        mock.return_value = None
        yield mock


@pytest.fixture(name="app_login")
def fixture_app_login() -> Generator[MagicMock]:
    """Mock _app_login"""
    with patch("mega_snake.gcloud.sign._app_login") as mock:
        mock.return_value = None
        yield mock


@pytest.fixture(name="project_set")
def fixture_project_set() -> Generator[MagicMock]:
    """Mock _project_set"""
    with patch("mega_snake.gcloud.sign._project_set") as mock:
        mock.return_value = None
        yield mock


@pytest.fixture(name="get_command_return_code")
def fixture_get_command_return_code() -> Generator[MagicMock]:
    """Mock get_command_return_code"""
    with patch("mega_snake.gcloud.sign.get_command_return_code") as mock:
        mock.return_value = 0
        yield mock


def test_gcloud_logout_unexpected_argument() -> None:
    """Test gcloud_logout unexpected argument"""
    runner = CliRunner()
    result = runner.invoke(gcloud_logout, ["unexpected"])
    assert result.exit_code != 0
    assert "Got unexpected extra argument" in result.stdout


def test_gcloud_logout(formatting_ws_success: MagicMock, os_system: MagicMock) -> None:
    """Test gcloud_logout success and failure"""
    # Test success
    runner = CliRunner()
    runner.invoke(gcloud_logout)
    assert os_system.call_count == 2
    assert formatting_ws_success.call_count == 2
    # Test failure
    os_system.return_value = 1
    os_system.reset_mock()
    formatting_ws_success.reset_mock()
    runner.invoke(gcloud_logout)
    assert os_system.call_count == 2
    assert formatting_ws_success.call_count == 0


def test_gcloud_login_env_invalid_type() -> None:
    """Test gcloud_login_env invalid type"""
    runner = CliRunner()
    project: str = PROJECT
    type_login: str = "invalid"
    result = runner.invoke(gcloud_login_env, [type_login, project])
    assert result.exit_code != 0
    assert f"Invalid value for '[[U|A|B]]': '{type_login}'" in result.stdout
    result = runner.invoke(gcloud_login_env, [type_login])
    assert result.exit_code != 0
    assert f"Invalid value for '[[U|A|B]]': '{type_login}'" in result.stdout
    result = runner.invoke(gcloud_login_env, [project])
    assert result.exit_code != 0
    assert f"Invalid value for '[[U|A|B]]': '{project}'" in result.stdout


def test_gcloud_login_env_success(user_login: MagicMock, app_login: MagicMock, project_set: MagicMock) -> None:
    """Test gcloud_login_env success"""

    def reset_mocks() -> None:
        """Reset mocks"""
        user_login.reset_mock()
        app_login.reset_mock()
        project_set.reset_mock()

    def assert_mocks(user_count: int, app_count: int, project_count: int) -> None:
        """Assert mocks"""
        assert user_login.call_count == user_count
        assert app_login.call_count == app_count
        assert project_set.call_count == project_count

    runner = CliRunner()
    runner.invoke(gcloud_login_env, [])
    assert_mocks(1, 1, 0)
    reset_mocks()
    runner.invoke(gcloud_login_env, ["B"])
    assert_mocks(1, 1, 0)
    reset_mocks()
    runner.invoke(gcloud_login_env, ["U"])
    assert_mocks(1, 0, 0)
    reset_mocks()
    runner.invoke(gcloud_login_env, ["A"])
    assert_mocks(0, 1, 0)
    reset_mocks()
    project: str = PROJECT
    runner.invoke(gcloud_login_env, ["U", project])
    assert_mocks(1, 0, 1)
    reset_mocks()
    runner.invoke(gcloud_login_env, ["A", project])
    assert_mocks(0, 1, 1)
    reset_mocks()
    runner.invoke(gcloud_login_env, ["B", project])
    assert_mocks(1, 1, 1)


def test_project_set_success(
    user_login: MagicMock,
    app_login: MagicMock,
    os_system: MagicMock,
    formatting_ws_success: MagicMock,
    formatting_ws_info: MagicMock,
    run_operation: MagicMock,
) -> None:
    """Test _project_set success"""

    runner = CliRunner()
    other_project: str = "other-project"

    def reset_mocks() -> None:
        """Reset mocks"""
        user_login.reset_mock()
        app_login.reset_mock()
        os_system.reset_mock()
        formatting_ws_success.reset_mock()
        formatting_ws_info.reset_mock()
        run_operation.reset_mock()

    # Test changing project
    run_operation.side_effect = [MagicMock(stdout=PROJECT), MagicMock(stdout=other_project)]
    result = runner.invoke(gcloud_login_env, ["B", other_project])
    assert result.exit_code == 0
    assert result.exception is None
    formatting_ws_info.assert_not_called()
    user_login.assert_called_once()
    app_login.assert_called_once()
    os_system.assert_called_once()
    formatting_ws_success.assert_called_once()
    assert run_operation.call_count == 2

    # Test same project
    reset_mocks()
    run_operation.side_effect = [MagicMock(stdout=PROJECT), MagicMock(stdout=other_project)]
    result = runner.invoke(gcloud_login_env, ["B", PROJECT])
    assert result.exit_code == 0
    assert result.exception is None
    user_login.assert_called_once()
    app_login.assert_called_once()
    formatting_ws_info.assert_called_once()
    os_system.assert_not_called()
    formatting_ws_success.assert_not_called()
    run_operation.assert_called_once()


def test_project_set_failure(
    user_login: MagicMock,
    app_login: MagicMock,
    os_system: MagicMock,
    formatting_ws_success: MagicMock,
    formatting_ws_info: MagicMock,
    run_operation: MagicMock,
) -> None:
    """Test _project_set failure"""

    runner = CliRunner()
    other_project: str = "other-project"

    def reset_mocks() -> None:
        """Reset mocks"""
        user_login.reset_mock()
        app_login.reset_mock()
        os_system.reset_mock()
        formatting_ws_success.reset_mock()
        formatting_ws_info.reset_mock()
        run_operation.reset_mock()

    # Test Failure on setting project
    reset_mocks()
    run_operation.side_effect = [MagicMock(stdout=PROJECT), MagicMock(stdout=other_project)]
    os_system.return_value = 1
    result = runner.invoke(gcloud_login_env, ["B", other_project])
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    user_login.assert_called_once()
    app_login.assert_called_once()
    formatting_ws_info.assert_not_called()
    os_system.assert_called_once()
    formatting_ws_success.assert_not_called()
    run_operation.assert_called_once()

    # Test Failure on project not changed
    reset_mocks()
    run_operation.side_effect = [MagicMock(stdout=PROJECT), MagicMock(stdout=PROJECT)]
    os_system.return_value = 0
    result = runner.invoke(gcloud_login_env, ["B", other_project])
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    user_login.assert_called_once()
    app_login.assert_called_once()
    formatting_ws_info.assert_not_called()
    os_system.assert_called_once()
    formatting_ws_success.assert_not_called()
    assert run_operation.call_count == 2


def test_user_login_success(
    os_system: MagicMock,
    formatting_ws_info: MagicMock,
    formatting_ws_success: MagicMock,
    get_command_return_code: MagicMock,
    app_login: MagicMock,
    project_set: MagicMock,
) -> None:
    """Test _user_login success cases"""

    runner = CliRunner()

    # Test when credentials are already set
    get_command_return_code.return_value = 0
    result = runner.invoke(gcloud_login_env, ["U"])
    assert result.exit_code == 0
    assert result.exception is None
    app_login.assert_not_called()
    project_set.assert_not_called()
    formatting_ws_info.assert_called_once()
    os_system.assert_not_called()
    formatting_ws_success.assert_not_called()
    get_command_return_code.assert_called_once()

    # Test when credentials need to be set
    os_system.reset_mock()
    formatting_ws_info.reset_mock()
    formatting_ws_success.reset_mock()
    get_command_return_code.reset_mock()
    app_login.reset_mock()
    project_set.reset_mock()
    get_command_return_code.return_value = 1
    os_system.return_value = 0
    result = runner.invoke(gcloud_login_env, ["U"])
    assert result.exit_code == 0
    assert result.exception is None
    app_login.assert_not_called()
    project_set.assert_not_called()
    formatting_ws_info.assert_not_called()
    os_system.assert_called_once()
    formatting_ws_success.assert_called_once()
    get_command_return_code.assert_called_once()


def test_user_login_failure(
    os_system: MagicMock,
    formatting_ws_info: MagicMock,
    formatting_ws_success: MagicMock,
    get_command_return_code: MagicMock,
    app_login: MagicMock,
    project_set: MagicMock,
) -> None:
    """Test _user_login failure case"""
    runner = CliRunner()

    get_command_return_code.return_value = 1
    os_system.return_value = 1

    result = runner.invoke(gcloud_login_env, ["U"])
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    app_login.assert_not_called()
    project_set.assert_not_called()
    formatting_ws_info.assert_not_called()
    os_system.assert_called_once()
    formatting_ws_success.assert_not_called()
    get_command_return_code.assert_called_once()


def test_app_login_success(
    os_system: MagicMock,
    formatting_ws_info: MagicMock,
    formatting_ws_success: MagicMock,
    get_command_return_code: MagicMock,
    user_login: MagicMock,
    project_set: MagicMock,
) -> None:
    """Test _app_login success cases"""
    runner = CliRunner()

    # Test when account is already set
    get_command_return_code.return_value = 0
    result = runner.invoke(gcloud_login_env, ["A"])
    assert result.exit_code == 0
    assert result.exception is None
    user_login.assert_not_called()
    project_set.assert_not_called()
    formatting_ws_info.assert_called_once()
    os_system.assert_not_called()
    formatting_ws_success.assert_not_called()
    get_command_return_code.assert_called_once()

    # Test when account needs to be set
    os_system.reset_mock()
    formatting_ws_info.reset_mock()
    formatting_ws_success.reset_mock()
    get_command_return_code.reset_mock()
    user_login.reset_mock()
    project_set.reset_mock()
    get_command_return_code.return_value = 1
    os_system.return_value = 0
    result = runner.invoke(gcloud_login_env, ["A"])
    assert result.exit_code == 0
    assert result.exception is None
    user_login.assert_not_called()
    project_set.assert_not_called()
    formatting_ws_info.assert_not_called()
    os_system.assert_called_once()
    formatting_ws_success.assert_called_once()
    get_command_return_code.assert_called_once()


def test_app_login_failure(
    os_system: MagicMock,
    formatting_ws_info: MagicMock,
    formatting_ws_success: MagicMock,
    get_command_return_code: MagicMock,
    user_login: MagicMock,
    project_set: MagicMock,
) -> None:
    """Test _app_login failure case"""
    runner = CliRunner()

    get_command_return_code.return_value = 1
    os_system.return_value = 1

    result = runner.invoke(gcloud_login_env, ["A"])
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    user_login.assert_not_called()
    project_set.assert_not_called()
    formatting_ws_info.assert_not_called()
    os_system.assert_called_once()
    formatting_ws_success.assert_not_called()
    get_command_return_code.assert_called_once()
