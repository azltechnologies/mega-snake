"""Test for the ToolVersion model"""

import re
from typing import Generator, Tuple
from types import SimpleNamespace, MethodType
import inspect
from unittest.mock import patch, MagicMock, mock_open
import pytest
from codename_snake.config_environment.models.tools_version import (
    ToolVersion,
    select_version,
    set_version_path_for_query,
    find_local_tool_home,
    set_version_local_config,
    determine_tool_version,
    OS_MAP,
    VersionSetException
)
from codename_snake.constants import SHELL_OPT

VERSIONS = ["1.2.3", "1.2.4", "1.2.5"]
PATHS = ["path/to/tool3", "path/to/tool4", "path/to/tool5"]
VERSION_TEST_SETTING = "versions.selected"
VERSION_TEST_QUERY = f'.tools.["{VERSION_TEST_SETTING}"]'
TOOL_TEST_VARIABLE = "TEST_HOME"
BASH_LOCAL_CONFIG_FILE = f"""export {TOOL_TEST_VARIABLE}='/opt/homebrew/Cellar/gradle/8.11/libexec'
export PATH="${TOOL_TEST_VARIABLE}/bin:$PATH"
export JAVA_HOME='/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home'
export PATH="$JAVA_HOME/bin:$PATH\""""
POWERSHELL_LOCAL_CONFIG_FILE = f"""$env:JAVA_HOME = "/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home"
$env:PATH = "$env:JAVA_HOME/bin:$env:PATH
$env:{TOOL_TEST_VARIABLE} = "/opt/homebrew/Cellar/gradle@6/6.9.4/libexec"
$env:PATH = "$env:{TOOL_TEST_VARIABLE}/bin:$env:PATH\""""


def windows_formater(os: str, output: str) -> str:
    """Format the output for windows"""
    if os.lower() == "windows":
        return re.sub(r"(?<!\$env):", ";", output.replace("/", "\\"))
    return output


def get_os_list() -> list[Tuple[str, str, str]]:
    """Return a list of os and their output"""
    result: list[Tuple[str, str, str]] = []
    for os_s in OS_MAP:
        for shell in SHELL_OPT:
            if shell.lower() == "powershell":
                result.append((os_s, shell, windows_formater(os_s, POWERSHELL_LOCAL_CONFIG_FILE)))
            else:
                result.append((os_s, shell, windows_formater(os_s, BASH_LOCAL_CONFIG_FILE)))

    return result


def get_tool_list() -> list[ToolVersion]:
    """Return a list of ToolVersion"""
    return list(ToolVersion(v, p) for v, p in zip(VERSIONS, PATHS))


def get_data() -> dict[str, str]:
    """Return a copy of the data"""
    dict_tools: list[dict[str, str]] = [{"version": t.version, "path": t.path} for t in get_tool_list()]
    return {"tools": {"versions.available": dict_tools}}


@pytest.fixture(name="ws_advice")
def fixture_ws_advice() -> Generator[MagicMock]:
    """Mock ws_advice"""
    with patch("codename_snake.config_environment.models.tools_version.ws_advice") as mock:
        yield mock


@pytest.fixture(name="ws_info")
def fixture_ws_info() -> Generator[MagicMock]:
    """Mock ws_info"""
    with patch("codename_snake.config_environment.models.tools_version.ws_info") as mock:
        yield mock

@pytest.fixture(name="ws_warning")
def fixture_ws_warning() -> Generator[MagicMock]:
    """Mock ws_warning"""
    with patch("codename_snake.config_environment.models.tools_version.ws_warning") as mock:
        yield mock


@pytest.fixture(name="platform")
def fixture_platform() -> Generator[MagicMock]:
    """Mock platform"""
    with patch("codename_snake.config_environment.models.tools_version.OS") as mock:
        yield mock


@pytest.fixture(name="mk_open")
def fixture_mk_open() -> Generator[MagicMock]:
    """Mock open"""
    m_open = mock_open(read_data="mocked file content")
    with patch("builtins.open", m_open):
        yield m_open


@pytest.fixture(name="get_validated_input")
def fixture_get_validated_input() -> Generator[MagicMock]:
    """Mock get_validated_input"""
    with patch(
        "codename_snake.config_environment.models.tools_version.get_validated_input",
        side_effect=lambda pronmpt, list: list[1],
    ) as mock:
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock]:
    """Mock os"""
    with patch("codename_snake.config_environment.models.tools_version.os") as mock:
        mock.path.exists.return_value = True
        yield mock


def test_id() -> None:
    """Test id"""
    count = 0
    for version, path in zip(VERSIONS, PATHS):
        inst: ToolVersion = ToolVersion(version, path)
        count += 1
        assert inst.id == count


def test_select_version(get_validated_input: MagicMock) -> None:
    """Test select_version"""
    # Test when list is empty
    list_tools: list[ToolVersion] = []
    with pytest.raises(RuntimeError):
        select_version(list_tools)
    get_validated_input.assert_not_called()

    # Test when list selection happens
    list_tools: list[ToolVersion] = list(ToolVersion(v, p) for v, p in zip(VERSIONS, PATHS))
    list_tools[1].default = True
    result = select_version(list_tools)
    assert result == list_tools[1]
    get_validated_input.reset_mock()

    # Test when list selection fails with None
    get_validated_input.side_effect = None
    get_validated_input.return_value = None
    with pytest.raises(TypeError):
        select_version(list_tools)
    get_validated_input.assert_called_once()
    get_validated_input.reset_mock()

    # Test when list selection fails with a non existent version
    get_validated_input.side_effect = None
    get_validated_input.return_value = 10
    with pytest.raises(RuntimeError):
        select_version(list_tools)
    get_validated_input.assert_called_once()
    get_validated_input.reset_mock()


def test_set_version_path_for_query() -> None:
    """Test set_version_path_for_query"""
    # Test when list is empty
    list_tools: list[ToolVersion] = []
    with pytest.raises(RuntimeError):
        set_version_path_for_query(list_tools, get_data(), VERSION_TEST_QUERY)

    # Test when no default version is found
    list_tools: list[ToolVersion] = list(ToolVersion(v, p) for v, p in zip(VERSIONS, PATHS))
    with pytest.raises(RuntimeError):
        set_version_path_for_query(list_tools, get_data(), VERSION_TEST_QUERY)

    # Test when default version is found
    list_tools[1].default = True
    result = set_version_path_for_query(list_tools, get_data(), VERSION_TEST_QUERY)
    assert result["tools"][VERSION_TEST_SETTING] == list_tools[1].path

    # Test when default version is found jq fails
    with pytest.raises(ValueError):
        set_version_path_for_query(list_tools, get_data(), "VERSION_TEST_QUERY")

    # Test when default version is found but has multiple entries
    list_tools[2].default = True
    with pytest.raises(RuntimeError):
        set_version_path_for_query(list_tools, get_data(), VERSION_TEST_QUERY)


def test_find_local_tool_home(mk_os: MagicMock, mk_open: MagicMock) -> None:
    """Test find_local_tool_home"""
    path = "/path/to/tool"
    file_mock = mk_open.return_value
    read_mock = MagicMock(return_value=None)
    file_mock.read = read_mock
    # Test when path is found
    for osys, shell, output in get_os_list():
        read_mock.return_value = output
        result = find_local_tool_home(path, shell, TOOL_TEST_VARIABLE)
        assert windows_formater(osys, "/opt/homebrew/Cellar") in result
        mk_open.assert_called_once()
        mk_os.path.exists.assert_called_once()
        mk_open.reset_mock()
        mk_os.path.exists.reset_mock()

        # Test when file is empty
    for osys, shell, output in get_os_list():
        read_mock.return_value = None
        result = find_local_tool_home(path, shell, TOOL_TEST_VARIABLE)
        assert result is None
        mk_open.assert_called_once()
        mk_os.path.exists.assert_called_once()
        mk_open.reset_mock()
        mk_os.path.exists.reset_mock()

        # Test when path is not found
    for osys, shell, output in get_os_list():
        mk_os.path.exists.return_value = False
        read_mock.return_value = output
        result = find_local_tool_home(path, shell, TOOL_TEST_VARIABLE)
        assert result is None
        mk_open.assert_not_called()
        mk_os.path.exists.assert_called_once()
        mk_open.reset_mock()
        mk_os.path.exists.reset_mock()


def test_set_version_local_config(mk_os: MagicMock, mk_open: MagicMock, ws_advice: MagicMock) -> None:
    """Test set_version_local_config"""
    path = "/path/to/tool"
    file_mock = mk_open.return_value
    read_mock = MagicMock(return_value=None)
    write_mock = MagicMock(return_value=None)
    file_mock.read = read_mock
    file_mock.write = write_mock
    # Test when path and pattern is found
    for version in get_tool_list():
        for osys, shell, output in get_os_list():
            with patch("codename_snake.config_environment.models.tools_version.OS", osys):
                read_mock.return_value = output
                set_version_local_config(version, path, shell, TOOL_TEST_VARIABLE)
                result = write_mock.call_args_list[0][0][0]
                eq_str = r"\s=\s" if shell.lower() == "powershell" else "="
                quo_str = '"' if shell.lower() == "powershell" else "'"
                pattern = rf"{TOOL_TEST_VARIABLE}{eq_str}{quo_str}{version.path}{quo_str}"
                matches = re.findall(pattern, result)
                assert len(matches) == 1
                env_str = r"env\:" if shell.lower() == "powershell" else ""
                pattern = rf'PATH{eq_str}"\${env_str}{TOOL_TEST_VARIABLE}'
                matches = re.findall(pattern, result)
                assert len(matches) == 1
                read_mock.assert_called_once()
                write_mock.assert_called_once()
                mk_os.path.exists.assert_called_once()
                read_mock.reset_mock()
                write_mock.reset_mock()
                mk_os.path.exists.reset_mock()

    # Test when shell is not found
    for version in get_tool_list():
        for osys, shell, output in get_os_list():
            shell = "dummy"
            with patch("codename_snake.config_environment.models.tools_version.OS", osys):
                read_mock.return_value = output
                with pytest.raises(NotImplementedError):
                    set_version_local_config(version, path, shell, TOOL_TEST_VARIABLE)
                read_mock.assert_called_once()
                write_mock.assert_not_called()
                mk_os.path.exists.assert_called_once()
                read_mock.reset_mock()
                write_mock.reset_mock()
                mk_os.path.exists.reset_mock()
                ws_advice.assert_not_called()
                ws_advice.reset_mock()

    # Test when path is not found
    mk_os.path.exists.return_value = False
    for version in get_tool_list():
        for osys, shell, output in get_os_list():
            with patch("codename_snake.config_environment.models.tools_version.OS", osys):
                read_mock.return_value = output
                set_version_local_config(version, path, shell, TOOL_TEST_VARIABLE)
                read_mock.assert_not_called()
                write_mock.assert_not_called()
                mk_os.path.exists.assert_called_once()
                read_mock.reset_mock()
                write_mock.reset_mock()
                mk_os.path.exists.reset_mock()
                ws_advice.assert_called_once()
                ws_advice.reset_mock()


def test_determine_tool_version(mk_os: MagicMock, mk_open: MagicMock, ws_info: MagicMock,ws_warning : MagicMock) -> None:
    """Test determine_tool_version"""
    path = "/path/to/tool"
    file_mock = mk_open.return_value
    read_mock = MagicMock(return_value=None)
    write_mock = MagicMock(return_value=None)
    file_mock.read = read_mock
    file_mock.write = write_mock

    dummy_version = ToolVersion("v", "p")
    another_version = ToolVersion("w", "q")

    # Test when list is empty
    result = determine_tool_version([])
    assert result is None
    ws_info.assert_called_once()
    ws_info.reset_mock()

    # Test when all the versions are None
    result = determine_tool_version([None, None, None])
    assert result is None
    ws_info.assert_called_once()
    ws_info.reset_mock()
    ws_warning.assert_not_called()

    # Test when all the versions are the same
    with pytest.raises(VersionSetException):
        determine_tool_version([dummy_version, dummy_version, dummy_version])
    ws_info.assert_not_called()
    ws_warning.assert_not_called()

    # Test when only one version is found
    with pytest.raises(VersionSetException):
        determine_tool_version([dummy_version])
    ws_info.assert_not_called()
    ws_warning.assert_not_called()

    # Test when different versions are found
    result:ToolVersion = determine_tool_version(get_tool_list())
    assert not result
    ws_warning.assert_called_once()
    ws_warning.reset_mock()
    ws_info.assert_not_called()

    # Test when different versions are found and one is None
    result:ToolVersion = determine_tool_version([dummy_version, None, another_version])
    assert not result
    ws_warning.assert_called_once()
    ws_warning.reset_mock()
    ws_info.assert_not_called()

    # Test when same versions are found but also None
    result:ToolVersion = determine_tool_version([dummy_version, None, dummy_version])
    assert result
    assert result.default
    ws_info.assert_called_once()
    ws_info.reset_mock()
    ws_warning.assert_not_called()