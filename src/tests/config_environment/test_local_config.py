""" Tests for local_config.py """

from unittest.mock import patch, MagicMock, mock_open
from typing import Generator
from click.testing import CliRunner
import pytest
from mega_snake.config_environment.local_config import execute, initial_load


@pytest.fixture(name="ws_success")
def fixture_ws_success() -> Generator[MagicMock, None, None]:
    """Mock ws_success"""
    with patch("mega_snake.config_environment.local_config.ws_success") as mock:
        yield mock


@pytest.fixture(name="m_execute")
def fixture_m_execute() -> Generator[MagicMock, None, None]:
    """Mock execute"""
    with patch("mega_snake.config_environment.local_config.execute") as mock:
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock, None, None]:
    """Mock os"""
    with patch("mega_snake.config_environment.local_config.os") as mock:
        yield mock


@pytest.fixture(name="get_local_file")
def fixture_get_local_file() -> Generator[MagicMock, None, None]:
    """Mock get_local_file"""
    with patch("mega_snake.config_environment.local_config.get_local_file") as mock:
        yield mock


@pytest.fixture(name="get_property")
def fixture_get_property() -> Generator[MagicMock, None, None]:
    """Mock get_property"""
    with patch("mega_snake.config_environment.local_config.get_property") as mock:
        yield mock


@pytest.fixture(name="mk_open")
def fixture_mk_open() -> Generator[MagicMock, None, None]:
    """Mock open"""
    m_open = mock_open(read_data="mocked file content")
    with patch("builtins.open", m_open):
        yield m_open


def test_initial_load(m_execute: MagicMock) -> None:
    """Test initial_load"""
    # Test when no parameters are passed
    runner = CliRunner()
    result = runner.invoke(initial_load)
    assert result.exit_code == 0
    m_execute.assert_called_once_with(False)
    m_execute.reset_mock()

    # Test when parameter is passed
    result = runner.invoke(initial_load, ["-o"])
    assert result.exit_code == 0
    m_execute.assert_called_once_with(True)
    m_execute.reset_mock()


def test_execute(
    mk_os: MagicMock, get_local_file: MagicMock, mk_open: MagicMock, get_property: MagicMock, ws_success: MagicMock
) -> None:
    """Test execute"""

    os_path_exists: MagicMock = mk_os.path.exists
    os_path_basename: MagicMock = mk_os.path.basename
    os_path_basename.return_value = ".test.env"
    file_mock = mk_open.return_value
    write_mock = MagicMock()
    file_mock.write = write_mock

    def reset_mocks() -> None:
        """Reset mocks"""
        os_path_exists.reset_mock()
        os_path_exists.side_effect = None
        get_local_file.reset_mock()
        mk_open.reset_mock()
        get_property.reset_mock()
        file_mock.reset_mock()
        write_mock.reset_mock()
        ws_success.reset_mock()
        os_path_basename.reset_mock()

    def valid_execution(shell: str) -> None:
        """Test valid execution"""
        if shell == "no-exist":
            get_local_file.assert_called_once()
            os_path_exists.assert_called_once()
            get_property.assert_called_once()
            mk_open.assert_not_called()
            write_mock.assert_not_called()
            ws_success.assert_not_called()
        else:
            
            result = write_mock.call_args_list[0][0][0]
            assert "local environment variables" in result
            result = write_mock.call_args_list[1][0][0]
            assert result
            if shell in ["bash", "zsh"]:
                assert "example() {" in result
                assert "export ORG_GRADLE_PROJECT_example_password='some value'" in result
                if shell == "bash":
                    assert 'mgsnake_load_env "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"/.test.env' in result
                else:
                    assert 'mgsnake_load_env "$(cd "$(dirname "${(%):-%N}")" && pwd)"/.test.env' in result
            elif shell == "powershell":
                assert "function example {" in result
                assert "$env:ORG_GRADLE_PROJECT_example_password = 'some value'" in result
                assert 'mgsnake_load_env "$(Split-Path -Parent $MyInvocation.MyCommand.Definition)/.test.env"' in result
            get_local_file.assert_called_once()
            assert os_path_exists.call_count == 2
            os_path_basename.assert_called_once()
            assert get_property.call_count == 2
            assert mk_open.call_count == 2
            assert write_mock.call_count == 2
            assert ws_success.call_count == 2
        reset_mocks()

    shells = ["bash", "zsh", "powershell", "no-exist"]
    for shell in shells:

                

        get_property.return_value = shell
        # Test when files exists and False
        os_path_exists.return_value = True
        execute(False)
        get_local_file.assert_called_once()
        assert os_path_exists.call_count == 2
        get_property.assert_called_once()
        mk_open.assert_not_called()
        write_mock.assert_not_called()
        ws_success.assert_not_called()
        reset_mocks()
        
        if shell == "no-exist":
            os_path_exists.side_effect = [True, True]
            with pytest.raises(NotImplementedError):
                execute(True)
            reset_mocks()
            os_path_exists.side_effect = [True, False]
            with pytest.raises(NotImplementedError):
                execute(False)
            reset_mocks()
            continue

        # Test when file exists and True
        os_path_exists.side_effect = [True, True]
        execute(True)
        valid_execution(shell)

        # Test when file doesn't exist and False
        os_path_exists.side_effect = [False, False]
        execute(False)
        valid_execution(shell)

        # Test when file doesn't exist and True
        os_path_exists.side_effect = [True, False]
        execute(True)
        valid_execution(shell)
