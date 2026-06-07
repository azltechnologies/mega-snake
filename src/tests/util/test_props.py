"""Test cases for props module"""

import builtins
import os
from unittest.mock import MagicMock, patch, mock_open
from typing import Generator, Callable
from types import SimpleNamespace
import pytest
from tests.test_util.util_test import param_injector, get_mock
from tests.test_util.side_effect_wrapper import SideEffectWrapper
from mega_snake.util.props import (
    init_app_properties,
    get_property,
    AppProperties,
    _read_properties as read_properties,
    _check_property as check_property,
    _check_forbidden_execution as check_forbidden_execution,
)
from mega_snake.constants import LOGGING_NAME_TO_LEVEL

ROOT = "src/tests"
RESOURCE_FOLDER = "/resources"
RESOURCE_PATH = f"{ROOT}{RESOURCE_FOLDER}"
PROP_FILE = f"{ROOT}/config.properties"


real_open = builtins.open
real_os_path_exists = os.path.exists


@pytest.fixture(name="get_validated_input")
def fixture_get_validated_input() -> Generator[MagicMock]:
    """Mock get_validated_input"""
    with patch("mega_snake.util.props.get_validated_input") as mock:
        yield mock



@pytest.fixture(name="mk_importlib_resources_files")
def fixture_mk_importlib_resources_files() -> Generator[MagicMock]:
    """Mock importlib.resources.files"""
    with patch("mega_snake.util.props.files", return_value=ROOT) as mock:
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock]:
    """Mock os.path.exists"""
    with patch("mega_snake.util.props.os", wraps=os) as mock:
        yield mock


@pytest.fixture(name="formatting")
def fixture_formatting() -> Generator[MagicMock]:
    """Mock formatting"""
    with patch("mega_snake.util.props.formatting") as mock:
        yield mock


@pytest.fixture(name="get_package_root")
def fixture_get_package_root() -> Generator[MagicMock]:
    """Mock get_package_root"""
    with patch("mega_snake.util.props._get_package_root", return_value=ROOT) as mock:
        yield mock


@pytest.fixture(name="mk_read_properties")
def fixture_mk_read_properties() -> Generator[MagicMock]:
    """Mock read_properties"""
    with patch("mega_snake.util.props._read_properties", wraps=read_properties) as mock:
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


def test_get_instance_when_instance_is_none() -> None:
    """Test get_instance method when instance is None"""
    with pytest.raises(RuntimeError):
        AppProperties.get_instance()


def test_init_app_properties(
    mk_read_properties: MagicMock,
    formatting: MagicMock,
    mk_importlib_resources_files: MagicMock,
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
        mk_importlib_resources_files,
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
    with patch("mega_snake.util.props.AppProperties", return_value=mock_instance) as mock_class:
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
        mk_importlib_resources_files.assert_called_once()
        mk_read_properties.assert_called_once_with(PROP_FILE)
        mock_class.assert_called_once_with(log_level, shell, output_read_props)
        formatting.assert_not_called()
        config_log.assert_called_once_with(retrieve_property.call_args_list[0].args[0], val_log_level)
        assert ws_advice.call_count == 5
        reset_mocks(*mocks)

        # Test when AppProperties throws a FileNotFoundError and light_weight is True
        mock_class.side_effect = FileNotFoundError("File not found")
        init_app_properties(log_level, shell, True)
        mk_importlib_resources_files.assert_called_once()
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
        mk_importlib_resources_files.assert_called_once()
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
        mk_importlib_resources_files.assert_called_once()
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
            mk_importlib_resources_files.assert_called_once()
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
            mk_importlib_resources_files.assert_called_once()
            mk_os.assert_called_once_with(PROP_FILE)
            mk_read_properties.assert_not_called()
            mock_class.assert_not_called()
            formatting.assert_not_called()
            ws_advice.assert_not_called()
            config_log.assert_not_called()
            retrieve_property.assert_not_called()
            reset_mocks(*mocks)

        # Test when PYTHONPATH is not set
        mk_importlib_resources_files.return_value = None
        with pytest.raises(EnvironmentError):
            init_app_properties(log_level, shell, light_weight)
        mk_importlib_resources_files.assert_called_once()
        mk_read_properties.assert_not_called()
        mock_class.assert_not_called()
        formatting.assert_not_called()
        config_log.assert_not_called()
        reset_mocks(*mocks)


def resources_path_validator_injector(request: pytest.FixtureRequest) -> Callable:
    """Specialized decorator for resources_path_validator tests with predefined parameters."""
    mk_os: MagicMock = get_mock(request, "mk_os")
    mk_os_path_exists: MagicMock = mk_os.path.exists
    os_path_exists_wrapper = SideEffectWrapper(os.path.exists)
    mk_os_path_exists.side_effect = os_path_exists_wrapper
    more_mocks = {
        "mk_os": mk_os,
        "mk_os_path_exists": mk_os_path_exists,
    }
    return param_injector(
        request, "get_package_root", log_level="DEBUG", shell="bash", light_weight=False, more_mocks=more_mocks
    )


def test_resources_path_validator(request) -> None:
    """Test resources_path_validator method"""

    @resources_path_validator_injector(request)
    def my_function(log_level: str, shell: str, light_weight: bool, mocks: dict[str, MagicMock]) -> None:
        """Test function"""
        non_existent_resource_folder = "src/tests/non_existent"
        path_to_test_a_file = f"{ROOT}/test_resources"
        get_package_root = mocks["get_package_root"]

        # Test when the resources location exists and is a directory but has no access
        get_package_root.return_value = ROOT
        with patch("mega_snake.util.props.os.access", return_value=False):
            with pytest.raises(PermissionError):
                init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

        # Test when the resources location exists but is a file
        get_package_root.return_value = None
        get_package_root.side_effect = [ROOT, path_to_test_a_file]
        with pytest.raises(NotADirectoryError):
            init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

        # Test when the resources location doesn't exist
        get_package_root.side_effect = [ROOT, non_existent_resource_folder]
        with pytest.raises(AssertionError):
            init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

    my_function()  # pylint: disable=E1120


def _find_code_workspace_files__after_failure_injector(request: pytest.FixtureRequest) -> Callable:
    """Specialized decorator for _find_code_workspace_files__after_failure tests with predefined parameters."""
    mk_os: MagicMock = get_mock(request, "mk_os")
    get_validated_input: MagicMock = get_mock(request, "get_validated_input")
    get_validated_input.return_value = 1
    mk_os_path_abspath: MagicMock = mk_os.path.abspath
    os_path_abspath_wrapper = SideEffectWrapper(os.path.abspath)
    mk_os_path_abspath.side_effect = os_path_abspath_wrapper
    more_mocks = {
        "mk_os_path_abspath": mk_os_path_abspath,
    }
    parent = resources_path_validator_injector(request)
    return parent(param_injector)(request, "get_validated_input", more_mocks=more_mocks)


def _find_code_workspace_files__on_success_injector(request: pytest.FixtureRequest) -> Callable:
    """Specialized decorator for _find_code_workspace_files__after_failure tests with predefined parameters."""
    get_package_root: MagicMock = get_mock(request, "get_package_root")
    get_package_root.return_value = ROOT
    parent = _find_code_workspace_files__after_failure_injector(request)
    return parent(param_injector)(request, "formatting")


def test__find_code_workspace_files(request) -> None:
    """Test _find_code_workspace_files method"""

    @_find_code_workspace_files__after_failure_injector(request)
    def on_failure(log_level: str, shell: str, light_weight: bool, mocks: dict[str, MagicMock]) -> None:
        """Test function on failure"""
        get_package_root: MagicMock = mocks["get_package_root"]
        mk_os_path_abspath: MagicMock = mocks["mk_os_path_abspath"]
        non_existent_working_dir: MagicMock = "src/tests/non_existent"

        # Test when parent of working exists with one unique file
        result = "test.code-workspace"
        get_package_root.return_value = ROOT
        mk_os_path_abspath.side_effect.set_values([non_existent_working_dir, f"{ROOT}/"])
        init_app_properties(log_level, shell, True)
        assert get_property("workspace_file").endswith(result)
        reset_mocks(*mocks.values())

        # Test when parent of working exists with multiple files
        result = ".code-workspace"
        mk_os_path_abspath.side_effect.set_values([non_existent_working_dir, f"{ROOT}/gradle"])
        init_app_properties(log_level, shell, True)
        assert get_property("workspace_file").endswith(result)

        # Test create an AppProperties instance twice
        with pytest.raises(RuntimeError):
            init_app_properties(log_level, shell, True)
        reset_mocks(*mocks.values())

        # Test when parent of working directory doesn't exist
        mk_os_path_abspath.side_effect = None
        mk_os_path_abspath.return_value = non_existent_working_dir
        with pytest.raises(FileNotFoundError):
            init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

    on_failure()  # pylint: disable=E1120

    @_find_code_workspace_files__on_success_injector(request)
    def on_succes(log_level: str, shell: str, light_weight: bool, mocks: dict[str, MagicMock]) -> None:
        """Test function on success"""
        mk_os_path_abspath: MagicMock = mocks["mk_os_path_abspath"]
        get_package_root: MagicMock = mocks["get_package_root"]
        get_package_root.return_value = ROOT

        # Test when workspace file is not found
        mk_os_path_abspath.side_effect.set_values([f"{ROOT}/"])
        init_app_properties(log_level, shell, True)
        assert get_property("workspace_file") == ""
        reset_mocks(*mocks.values())

        # Test when workspace file is found
        result = "test.code-workspace"
        mk_os_path_abspath.side_effect.set_values(
            [f"{ROOT}/test_resources/", f"{ROOT}/"]
        )
        init_app_properties(log_level, shell, light_weight)
        assert get_property("workspace_file").endswith(result)
        reset_mocks(*mocks.values())

    on_succes()  # pylint: disable=E1120


def __log_level_from_str_injector(request: pytest.FixtureRequest) -> Callable:
    """Specialized decorator for _find_code_workspace_files__after_failure tests with predefined parameters."""
    parent = _find_code_workspace_files__on_success_injector(request)
    mk_os_path_abspath: MagicMock = get_mock(request, "mk_os_path_abspath")
    rm = mk_os_path_abspath.reset_mock
    mk_os_path_abspath.reset_mock = lambda *args, **kwargs: mk_os_path_abspath.side_effect.reset(rm, *args, **kwargs)
    mk_os_path_abspath.side_effect.set_values([f"{ROOT}/", f"{ROOT}/"])
    return parent(param_injector)(request)


def test__log_level_from_str(request) -> None:
    """Test _log_level_from_str method"""

    @__log_level_from_str_injector(request)
    def my_function(log_level: str, shell: str, light_weight: bool, mocks: dict[str, MagicMock]) -> None:
        """Test function on failure"""
        mk_os_path_exists = mocks["mk_os_path_exists"]
        mk_os_makedirs: MagicMock = MagicMock()
        mocks["mk_os"].makedirs = mk_os_makedirs

        # changing debug to info
        init_app_properties(log_level, shell, light_weight)
        AppProperties.get_instance().log_level = LOGGING_NAME_TO_LEVEL["INFO"]
        reset_mocks(*mocks.values())

        # Test when log level is not found
        with pytest.raises(KeyError):
            init_app_properties("GREAT", shell, light_weight)
        reset_mocks(*mocks.values())

        # Test when log level is found and log file parent folder doesn't exist
        mk_os_path_exists.side_effect.set_values([True, True, True, False])
        init_app_properties(log_level, shell, light_weight)
        assert AppProperties.get_instance().log_level == LOGGING_NAME_TO_LEVEL[log_level]
        mk_os_makedirs.assert_called_once()
        result = get_property("log_file")
        assert result.endswith(".log") and "/logs" in result
        reset_mocks(*mocks.values())

    my_function()  # pylint: disable=E1120


def test__shell_validator(request) -> None:
    """Test _shell_validator method"""

    @__log_level_from_str_injector(request)
    def my_function(log_level: str, shell: str, light_weight: bool, mocks: dict[str, MagicMock]) -> None:
        """Test function on failure"""
        # Test when shell is not found
        with pytest.raises(ValueError):
            init_app_properties(log_level, "GREAT", light_weight)
        reset_mocks(*mocks.values())

        # Test when shell is found
        init_app_properties(log_level, shell, light_weight)
        assert get_property("shell") == shell
        reset_mocks(*mocks.values())

    my_function()  # pylint: disable=E1120


def test_fail_scenarios(request) -> None:
    """Test when a property with no value is passed"""

    @__log_level_from_str_injector(request)
    def my_function(log_level: str, shell: str, light_weight: bool, mocks: dict[str, MagicMock]) -> None:
        """Test function on failure"""
        mk_os = mocks["mk_os"]
        mk_os_path_isdir = mk_os.path.isdir
        mk_os_path_isdir.side_effect = SideEffectWrapper(os.path.isdir)
        mk_os_path_isdir.side_effect.set_values([True, False])
        mocks["mk_os_path_isdir"] = mk_os_path_isdir

        # Test when working_path is not a directory
        with pytest.raises(NotADirectoryError):
            init_app_properties(log_level, shell, light_weight)
        mk_os_path_isdir.side_effect.set_values([])
        reset_mocks(*mocks.values())

        mk_os_access = mk_os.access
        mk_os_access.side_effect = SideEffectWrapper(os.access)
        mk_os_access.side_effect.set_values([True, False])
        mocks["mk_os_access"] = mk_os_access

        # Test when working_path is not accessible
        with pytest.raises(PermissionError):
            init_app_properties(log_level, shell, light_weight)
        mk_os_access.side_effect.set_values([])
        reset_mocks(*mocks.values())

        # Test when log level string is none
        with patch("mega_snake.util.props.LOGGING_NAME_TO_LEVEL", {"DEBUG": None}):
            with pytest.raises(ValueError):
                init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

        # Test when log level is none
        with patch("mega_snake.util.props.LOGGING_LEVEL_TO_NANE", {10: None}):
            with pytest.raises(ValueError):
                init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

        # Test when log level is not found
        with patch("mega_snake.util.props.LOGGING_LEVEL_TO_NANE", {}):
            with pytest.raises(KeyError):
                init_app_properties(log_level, shell, light_weight)
        reset_mocks(*mocks.values())

        # Test when retrieving unknown property
        init_app_properties(log_level, shell, light_weight)
        with pytest.raises(KeyError):
            AppProperties.get_instance()._retrieve_property("unknown") # pylint: disable=W0212
        reset_mocks(*mocks.values())

        # Test when getting props directly
        init_app_properties(log_level, shell, light_weight)
        with pytest.raises(PermissionError):
            _ = AppProperties.get_instance().props
        reset_mocks(*mocks.values())

        # Test when empty props are passed
        init_app_properties(log_level, shell, light_weight)
        with patch(
            "mega_snake.util.props._check_forbidden_execution",
            side_effect=lambda method, message, reload, props: check_forbidden_execution(
                method, message, reload, None
            ),
        ):
            with pytest.raises(ValueError):
                AppProperties.get_instance().log_level = LOGGING_NAME_TO_LEVEL["INFO"]
        reset_mocks(*mocks.values())

        def check_property_side_effect(prop: str, dic: dict[str, str]) -> None:
            """Side effect for check_property"""
            if prop == "local_config_file_name":
                prop = None
            result: str = check_property(prop, dic)
            return result

        # Test when property is not found at check_property
        with patch("mega_snake.util.props._check_property", side_effect=check_property_side_effect):
            with pytest.raises(KeyError):
                init_app_properties(log_level, shell, light_weight)
            reset_mocks(*mocks.values())

        original_method = AppProperties._AppProperties__adding_prop_validator  # pylint: disable=W0212

        def adding_prop_validator_side_effect(key: str, value: str) -> None:
            """Side effect for adding_prop_validator"""
            instance = AppProperties.get_instance()
            if key == "local_config_file":
                value = None
            result: str = original_method(instance, key, value)  # pylint: disable=E1121
            return result

        # Test when property is not found at adding_prop_validator
        with patch(
            "mega_snake.util.props.AppProperties._AppProperties__adding_prop_validator",
            side_effect=adding_prop_validator_side_effect,
        ):
            with pytest.raises(ValueError):
                init_app_properties(log_level, shell, light_weight)
            reset_mocks(*mocks.values())

        original_method = AppProperties.__post_init__  # pylint: disable=W0212

        def post_init_side_effect() -> None:
            """Side effect for __post_init__"""
            instance = AppProperties.get_instance()
            instance._log_level = None  # pylint: disable=W0212
            original_method(instance)

        # Test when property is not found at __post_init__
        with patch(
            "mega_snake.util.props.AppProperties.__post_init__",
            side_effect=post_init_side_effect,
        ):
            with pytest.raises(ValueError):
                init_app_properties(log_level, shell, light_weight)
            reset_mocks(*mocks.values())

        # Test when creating instance outside of module
        with pytest.raises(PermissionError):
            AppProperties(log_level, shell, {})
        reset_mocks(*mocks.values())

    my_function()  # pylint: disable=E1120
