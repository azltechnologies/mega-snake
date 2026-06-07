""" Test cases for the util module """

from unittest.mock import patch, MagicMock, call, mock_open
from typing import Generator
import pytest
from mega_snake.config_environment.util import get_local_file, update_workspace, get_version_number


@pytest.fixture(name="get_property")
def fixture_get_property() -> Generator[MagicMock]:
    """Mock get_property"""
    with patch("mega_snake.config_environment.util.get_property") as mock:
        yield mock


@pytest.fixture(name="mk_open")
def fixture_mk_open() -> Generator[MagicMock]:
    """Mock open"""
    m_open = mock_open(read_data="mocked file content")
    with patch("builtins.open", m_open):
        yield m_open


@pytest.fixture(name="json_dump")
def fixture_json_dump() -> Generator[MagicMock]:
    """Mock json.dump"""
    with patch("json.dump") as mock:
        yield mock


@pytest.fixture(name="os_replace")
def fixture_os_replace() -> Generator[MagicMock]:
    """Mock os.replace"""
    with patch("os.replace") as mock:
        yield mock


def test_get_local_file(get_property: MagicMock) -> None:
    """Test get_local_file"""

    def evaluate_shell(shell: str, ends_with: str) -> str:
        get_property.return_value = shell
        result = get_local_file()
        get_property.assert_has_calls([call("shell"), call("local_config_file")])
        assert get_property.call_count == 2
        get_property.reset_mock()
        assert result.endswith(ends_with)
        return result

    evaluate_shell("bash", ".sh")
    evaluate_shell("zsh", ".sh")
    evaluate_shell("powershell", ".ps1")
    get_property.return_value = "fish"
    with pytest.raises(NotImplementedError):
        get_local_file()


def test_update_workspace(mk_open: MagicMock, os_replace: MagicMock, json_dump: MagicMock) -> None:
    """Test update_workspace"""
    # Test when successful
    json_data = {"key": "value"}
    temp_path = "temp_path"
    workspace_file = "workspace_file"
    file_mock = mk_open.return_value
    write_mock = MagicMock()
    file_mock.write = write_mock
    update_workspace(json_data, temp_path, workspace_file)
    json_dump.assert_called_once_with(json_data, file_mock, indent=2)
    os_replace.assert_called_once_with(temp_path, workspace_file)

    # Test when json_data is None
    with pytest.raises(RuntimeError):
        update_workspace(None, temp_path, workspace_file)

    # Test when os.replace fails
    os_replace.side_effect = OSError("os.replace failed")
    with pytest.raises(OSError) as e:
        update_workspace(json_data, temp_path, workspace_file)
    assert "Failed to replace" in str(e)


def test_get_version_number() -> None:
    """Test get_version_number"""
    assert get_version_number("1.2") == 1002000
    assert get_version_number("1") == 1000000
    assert get_version_number("1.2.3") == 1002003
    # Test when version is not a number
    with pytest.raises(ValueError):
        assert get_version_number("test") == 0.0
