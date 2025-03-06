"""Test cases for props module"""

import builtins
import os
from unittest.mock import MagicMock, patch, mock_open, call
from typing import Generator, Callable
from types import SimpleNamespace
import pytest
from codename_snake.util.props import (
    init_app_properties,
    get_property,
    AppProperties,
    _read_properties as read_properties,
)

ROOT = "src/tests/resources"
DUMMY_RESOURCE_FILE = f"{ROOT}/test_resources"
PROP_FILE = f"{ROOT}/config.properties"

NON_EXISTENT_RESOURCE_FOLDER = "src/tests/resources/non_existent"
RESOURCE_FOLDER = "src/tests/resources/test_resources"

real_open = builtins.open


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock]:
    """Mock os"""

    def os_multiple_side_effect(path: str,cal: Callable) -> bool:
        """Side effect for os.path.exists"""
        if path == "src/tests/resources/test_resources":
            return True
        return cal(path)

    with patch("codename_snake.util.props.os") as mock:
        mock.path.exists.side_effect = lambda x:os_multiple_side_effect(x,os.path.exists)
        mock.path.isdir.side_effect = lambda x: os_multiple_side_effect(x,os.path.isdir)
        yield mock


@pytest.fixture(name="formatting")
def fixture_formatting() -> Generator[MagicMock]:
    """Mock formatting"""
    with patch("codename_snake.util.props.formatting") as mock:
        yield mock


@pytest.fixture(name="get_package_root")
def fixture_get_package_root() -> Generator[MagicMock]:
    """Mock get_package_root"""
    with patch("codename_snake.util.props._get_package_root", return_value=ROOT) as mock:
        yield mock


@pytest.fixture(name="mk_read_properties")
def fixture_mk_read_properties() -> Generator[MagicMock]:
    """Mock read_properties"""
    with patch("codename_snake.util.props._read_properties", wraps=read_properties) as mock:
        yield mock


def reset_mocks(*mocks: MagicMock) -> None:
    """Reset mocks"""
    AppProperties._instance = None  # pylint: disable=W0212
    for mock in mocks:
        mock.reset_mock()


def test_get_property() -> None:
    """Test get_property method"""
    return_val = "value_1"
    mock_instance = SimpleNamespace(_retrieve_property=lambda x: return_val)
    with patch.object(AppProperties, "get_instance", return_value=mock_instance):
        result = get_property("key")
        assert result == return_val


def test_init_app_properties(
    get_package_root: MagicMock,
    mk_read_properties: MagicMock,
    formatting: MagicMock,
) -> None:
    """Test init_app_properties method"""
    output_read_props = None
    ws_advice: MagicMock = formatting.ws_advice
    config_log: MagicMock = formatting.config_log
    m_open: MagicMock = mock_open()
    file_mock: MagicMock = m_open.return_value
    read_mock: MagicMock = file_mock.read
    write_mock: MagicMock = file_mock.write
    mocks = [
        get_package_root,
        mk_read_properties,
        m_open,
        file_mock,
        read_mock,
        write_mock,
        formatting,
        ws_advice,
        config_log,
    ]

    def read_props_side_effect(*args, **kwargs) -> dict:
        """Side effect for read_properties"""
        nonlocal output_read_props
        output_read_props = read_properties(*args, **kwargs)
        return output_read_props

    mk_read_properties.wraps = None
    mk_read_properties.side_effect = read_props_side_effect
    mock_instance = MagicMock()
    with patch("codename_snake.util.props.AppProperties", return_value=mock_instance) as mock_class:
        mock_class.get_instance.return_value = mock_instance
        mocks.append(mock_class)
        log_level = "DEBUG"
        shell = "bash"
        light_weight = False
        val_log_level: int = 1000
        retrieve_property: MagicMock = mock_instance._retrieve_property  # pylint: disable=W0212
        retrieve_property.side_effect = lambda x: x  # pylint: disable=W0212
        mocks.append(retrieve_property)
        mock_instance.log_level = val_log_level

        # Test when AppProperties is successfully initialized
        init_app_properties(log_level, shell, True)
        get_package_root.assert_called_once()
        mk_read_properties.assert_called_once_with(PROP_FILE)
        mock_class.assert_called_once_with(log_level, shell, output_read_props)
        formatting.assert_not_called()
        config_log.assert_called_once_with(retrieve_property.call_args_list[0].args[0], val_log_level)
        assert ws_advice.call_count == 5
        reset_mocks(*mocks)

        # Test when AppProperties throws a FileNotFoundError and light_weight is True
        mock_class.side_effect = FileNotFoundError("File not found")
        init_app_properties(log_level, shell, True)
        get_package_root.assert_called_once()
        mk_read_properties.assert_called_once_with(PROP_FILE)
        mock_class.assert_called_once_with(log_level, shell, output_read_props)
        formatting.assert_not_called()
        ws_advice.assert_not_called()
        config_log.assert_not_called()
        retrieve_property.assert_not_called()
        reset_mocks(*mocks)

        # Test when AppProperties throws a FileNotFoundError and light_weight is False
        mock_class.side_effect = FileNotFoundError("File not found")
        with pytest.raises(FileNotFoundError):
            init_app_properties(log_level, shell, light_weight)
        get_package_root.assert_called_once()
        mk_read_properties.assert_called_once_with(PROP_FILE)
        mock_class.assert_called_once_with(log_level, shell, output_read_props)
        formatting.assert_not_called()
        ws_advice.assert_not_called()
        config_log.assert_not_called()
        retrieve_property.assert_not_called()
        reset_mocks(*mocks)

        # Test when shell parameter is not provided
        with pytest.raises(EnvironmentError):
            init_app_properties(log_level, None, light_weight)
        get_package_root.assert_called_once()
        mk_read_properties.assert_called_once_with(PROP_FILE)
        mock_class.assert_not_called()
        formatting.assert_not_called()
        ws_advice.assert_not_called()
        config_log.assert_not_called()
        retrieve_property.assert_not_called()
        reset_mocks(*mocks)

        # Test when the properties file exists but empty
        with patch("builtins.open", m_open):
            read_mock.return_value = ""
            with pytest.raises(ValueError):
                init_app_properties(log_level, shell, light_weight)
            get_package_root.assert_called_once()
            mk_read_properties.assert_called_once_with(PROP_FILE)
            mock_class.assert_not_called()
            formatting.assert_not_called()
            ws_advice.assert_not_called()
            config_log.assert_not_called()
            retrieve_property.assert_not_called()
            reset_mocks(*mocks)

        # Test when the properties file doesn't exist
        with patch("codename_snake.util.props.os") as mk_os:
            os_path_exists: MagicMock = mk_os.path.exists
            os_path_exists.return_value = False
            mocks.append(mk_os)
            mocks.append(os_path_exists)
            with pytest.raises(FileNotFoundError):
                init_app_properties(log_level, shell, light_weight)
            get_package_root.assert_called_once()
            os_path_exists.assert_called_once_with(PROP_FILE)
            mk_read_properties.assert_not_called()
            mock_class.assert_not_called()
            formatting.assert_not_called()
            ws_advice.assert_not_called()
            config_log.assert_not_called()
            retrieve_property.assert_not_called()
            reset_mocks(*mocks)


def test_of_functionality(
    get_package_root: MagicMock,
    #mk_os: MagicMock,
) -> None:
    """Functional test for the props module"""
    log_level = "DEBUG"
    shell = "bash"
    light_weight = False
    mocks: dict[MagicMock] = [
        get_package_root,
        #mk_os,
    ]

    # Test when 
    get_package_root.side_effect = None
    #init_app_properties(log_level, shell, light_weight)

    # Test when the resources location exists and is a directory but has no access
    with patch("codename_snake.util.props.os.access", return_value=False):
        with pytest.raises(PermissionError):
            init_app_properties(log_level, shell, light_weight)
    reset_mocks(*mocks)

    # Test when the resources location exists but is a file
    get_package_root.side_effect = [ROOT, DUMMY_RESOURCE_FILE]
    with pytest.raises(NotADirectoryError):
        init_app_properties(log_level, shell, light_weight)
    reset_mocks(*mocks)

    # Test when the resources location doesn't exist
    get_package_root.side_effect = [ROOT, NON_EXISTENT_RESOURCE_FOLDER]
    with pytest.raises(AssertionError):
        init_app_properties(log_level, shell, light_weight)
    reset_mocks(*mocks)

