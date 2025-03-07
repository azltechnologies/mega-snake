"""Test cases for props module"""

import builtins
import os
from unittest.mock import MagicMock, patch, mock_open, call
from typing import Generator, Callable, Any
from types import SimpleNamespace
import pytest
from tests.test_util.util_test import param_injector
from tests.test_util.side_effect_wrapper import SideEffectWrapper
from codename_snake.util.props import (
    init_app_properties,
    get_property,
    AppProperties,
    _read_properties as read_properties,
)

ROOT = "src/tests"
RESOURCE_FOLDER = "/resources"
RESOURCE_PATH = f"{ROOT}{RESOURCE_FOLDER}"
PROP_FILE = f"{RESOURCE_PATH}/config.properties"


real_open = builtins.open
real_os_path_exists = os.path.exists


@pytest.fixture(name="get_validated_input")
def fixture_get_validated_input() -> Generator[MagicMock]:
    """Mock get_validated_input"""
    with patch("codename_snake.util.props.get_validated_input") as mock:
        yield mock


@pytest.fixture(name="_constant_source_folder")
def fixture_constant_source_folder() -> Generator[MagicMock]:
    """Mock SOURCE_FOLDER constant"""
    with patch("codename_snake.util.props.SOURCE_FOLDER", RESOURCE_FOLDER) as mock:
        yield mock


@pytest.fixture(name="mk_os_getenv")
def fixture_mk_os_getenv() -> Generator[MagicMock]:
    """Mock os.getenv"""
    with patch("codename_snake.util.props.os.getenv", return_value=ROOT) as mock:
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock]:
    """Mock os.path.exists"""
    with patch("codename_snake.util.props.os", wraps=os) as mock:
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
    _constant_source_folder: MagicMock,
    mk_read_properties: MagicMock,
    formatting: MagicMock,
    mk_os_getenv: MagicMock,
    mk_os: MagicMock,
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
        mk_read_properties,
        m_open,
        file_mock,
        read_mock,
        write_mock,
        formatting,
        ws_advice,
        config_log,
        mk_os_getenv,
        mk_os,
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
        mk_os_getenv.assert_called_once()
        mk_read_properties.assert_called_once_with(PROP_FILE)
        mock_class.assert_called_once_with(log_level, shell, output_read_props)
        formatting.assert_not_called()
        config_log.assert_called_once_with(retrieve_property.call_args_list[0].args[0], val_log_level)
        assert ws_advice.call_count == 5
        reset_mocks(*mocks)

        # Test when AppProperties throws a FileNotFoundError and light_weight is True
        mock_class.side_effect = FileNotFoundError("File not found")
        init_app_properties(log_level, shell, True)
        mk_os_getenv.assert_called_once()
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
        mk_os_getenv.assert_called_once()
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
        mk_os_getenv.assert_called_once()
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
            mk_os_getenv.assert_called_once()
            mk_read_properties.assert_called_once_with(PROP_FILE)
            mock_class.assert_not_called()
            formatting.assert_not_called()
            ws_advice.assert_not_called()
            config_log.assert_not_called()
            retrieve_property.assert_not_called()
            reset_mocks(*mocks)

            # Test when the properties file doesn't exist2
            mk_os.wraps = None
            mk_os = mk_os.path.exists
            mk_os.return_value = False
            with pytest.raises(FileNotFoundError):
                init_app_properties(log_level, shell, light_weight)
            mk_os_getenv.assert_called_once()
            mk_os.assert_called_once_with(PROP_FILE)
            mk_read_properties.assert_not_called()
            mock_class.assert_not_called()
            formatting.assert_not_called()
            ws_advice.assert_not_called()
            config_log.assert_not_called()
            retrieve_property.assert_not_called()
            reset_mocks(*mocks)

        # Test when PYTHONPATH is not set
        mk_os_getenv.return_value = None
        with pytest.raises(EnvironmentError):
            init_app_properties(log_level, shell, light_weight)
        mk_os_getenv.assert_called_once()
        mk_read_properties.assert_not_called()
        mock_class.assert_not_called()
        formatting.assert_not_called()
        config_log.assert_not_called()
        reset_mocks(*mocks)


def resources_path_validator_injector(request: pytest.FixtureRequest) -> Callable:
    """Specialized decorator for resources_path_validator tests with predefined parameters."""
    return param_injector(request, "get_package_root", log_level="DEBUG", shell="bash", light_weight=False)


def test_resources_path_validator(request) -> None:
    """Test resources_path_validator method"""

    @resources_path_validator_injector(request)
    def my_function(log_level: str, shell: str, light_weight: bool, mocks: dict[str, MagicMock]) -> None:
        """Test function"""
        non_existent_resource_folder = "src/tests/non_existent"
        path_to_test_a_file = f"{ROOT}{RESOURCE_FOLDER}/test_resources"
        get_package_root = mocks["get_package_root"]

        # Test when the resources location exists and is a directory but has no access
        get_package_root.return_value = RESOURCE_PATH
        with patch("codename_snake.util.props.os.access", return_value=False):
            with pytest.raises(PermissionError):
                init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

        # Test when the resources location exists but is a file
        get_package_root.return_value = None
        get_package_root.side_effect = [RESOURCE_PATH, path_to_test_a_file]
        with pytest.raises(NotADirectoryError):
            init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

        # Test when the resources location doesn't exist
        get_package_root.side_effect = [RESOURCE_PATH, non_existent_resource_folder]
        with pytest.raises(AssertionError):
            init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

    my_function()  # pylint: disable=E1120


def _find_code_workspace_files__after_failure_injector(request: pytest.FixtureRequest) -> Callable:
    """Specialized decorator for _find_code_workspace_files__after_failure tests with predefined parameters."""
    mk_os:MagicMock = request.getfixturevalue("mk_os")
    mk_os_path_abspath:MagicMock = mk_os.path.abspath
    os_path_abspath_wrapper = SideEffectWrapper(os.path.abspath)
    mk_os_path_abspath.side_effect = os_path_abspath_wrapper
    more_mocks = {
        "mk_os_path_abspath": mk_os_path_abspath,
        "mk_os": mk_os,
    }
    return param_injector(request, "get_validated_input", more_mocks=more_mocks)


def test__find_code_workspace_files__after_failure(request) -> None:
    """Test _find_code_workspace_files__after_failure method"""

    @resources_path_validator_injector(request)
    @_find_code_workspace_files__after_failure_injector(request)
    def my_function(log_level: str, shell: str, light_weight: bool, mocks: dict[str, MagicMock]) -> None:
        """Test function"""
        get_package_root: MagicMock = mocks["get_package_root"]
        mk_os: MagicMock = mocks["mk_os"]
        mk_os_path_abspath: MagicMock = mocks["mk_os_path_abspath"]
        non_existent_working_dir: MagicMock = "src/tests/non_existent"
        get_validated_input: MagicMock = mocks["get_validated_input"]
        get_validated_input.return_value = 1



        #src/tests/resources
        # Test when parent of working exists with one unique file
        result = "test.code-workspace"
        get_package_root.return_value = RESOURCE_PATH
        mk_os_path_abspath.side_effect.set_values([non_existent_working_dir, f"{RESOURCE_PATH}/test_resources/"])
        init_app_properties(log_level, shell, True)
        assert get_property("workspace_file").endswith(result)
        reset_mocks(*mocks.values())


        # Test when parent of working exists with multiple files
        result = ".code-workspace"
        mk_os_path_abspath.side_effect.set_values([non_existent_working_dir,f"{RESOURCE_PATH}/gradle"])
        init_app_properties(log_level, shell, True)
        assert get_property("workspace_file").endswith(result)
        reset_mocks(*mocks.values())

        # Test when parent of working directory doesn't exist
        mk_os_path_abspath.side_effect = None
        mk_os_path_abspath.return_value = non_existent_working_dir
        with pytest.raises(FileNotFoundError):
            init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

    my_function()  # pylint: disable=E1120
