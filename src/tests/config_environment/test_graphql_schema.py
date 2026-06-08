""" Tests for the GraphQL schema creation. """

import builtins
from unittest.mock import MagicMock, patch, mock_open
from typing import Generator, Any
from graphql import build_schema
from click.testing import CliRunner
import pytest
from mega_snake.config_environment.graphql_schema import create_graphql_schema


# Save the real open function
real_open = builtins.open

# A dictionary to store mocks keyed by filename, if needed
write_mocks = {}


def custom_open(file, mode="r", *args, **kwargs) -> Any:  # pylint: disable=W1113
    """Custom open function that returns a mock for write mode and the real open function for read mode."""
    if "w" in mode:
        # Create a new mock for write mode and store it (if you need later access)
        m = mock_open()
        write_mocks[file] = m
        # Return the mock file handle (i.e., m() is what open returns)
        return m()
    else:
        # For read (or other modes), use the real open function
        return real_open(file, mode, *args, **kwargs)


@pytest.fixture(name="mk_open")
def fixture_mk_open() -> Generator[MagicMock, None, None]:
    """Mock open"""
    m_open: MagicMock = mock_open()
    m_open.side_effect = custom_open
    with patch("builtins.open", m_open):
        yield m_open


# Mocking build_schema, GraphQLSchema, print_schema, introspection_from_schema
@pytest.fixture(name="mk_build_schema")
def fixture_mk_build_schema() -> Generator[MagicMock, None, None]:
    """Mock mk_build_schema"""
    with patch("mega_snake.config_environment.graphql_schema.build_schema", wraps=build_schema) as mock:
        yield mock


@pytest.fixture(name="graphql_schema")
def fixture_graphql_schema() -> Generator[MagicMock, None, None]:
    """Mock GraphQLSchema"""
    with patch("mega_snake.config_environment.graphql_schema.GraphQLSchema") as mock:
        yield mock


@pytest.fixture(name="print_schema")
def fixture_print_schema() -> Generator[MagicMock, None, None]:
    """Mock print_schema"""
    with patch("mega_snake.config_environment.graphql_schema.print_schema") as mock:
        yield mock


@pytest.fixture(name="introspection_from_schema")
def fixture_introspection_from_schema() -> Generator[MagicMock, None, None]:
    """Mock introspection_from_schema"""
    with patch("mega_snake.config_environment.graphql_schema.introspection_from_schema") as mock:
        yield mock


@pytest.fixture(name="ws_success")
def fixture_ws_success() -> Generator[MagicMock, None, None]:
    """Mock ws_success"""
    with patch("mega_snake.config_environment.graphql_schema.ws_success") as mock:
        yield mock


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock, None, None]:
    """Mock run_operation"""
    with patch("mega_snake.config_environment.graphql_schema.run_operation") as mock:
        yield mock


@pytest.fixture(name="get_property")
def fixture_get_property() -> Generator[MagicMock, None, None]:
    """Mock get_property"""
    with patch("mega_snake.config_environment.graphql_schema.get_property") as mock:
        yield mock


@pytest.fixture(name="mk_os")
def fixture_mk_os() -> Generator[MagicMock, None, None]:
    """Mock os"""
    with patch("mega_snake.config_environment.graphql_schema.os") as mock:
        yield mock


@pytest.fixture(name="_create_schema")
def fixture_create_schema() -> Generator[MagicMock, None, None]:
    """Mock _create_schema"""
    with patch("mega_snake.config_environment.graphql_schema._create_schema") as mock:
        yield mock


def reset_mocks(*mocks: MagicMock) -> None:
    """Reset all mocks"""
    for mock in mocks:
        mock.reset_mock()


def test_command(
    get_property: MagicMock,
    mk_os: MagicMock,
    _create_schema: MagicMock,
) -> None:
    """Test create_graphql_schema"""

    path_schema = "schema_folder"
    abs_schema = "schema_abs"
    file_schema = "schema_file"

    # Create os mocks
    abs_path: MagicMock = mk_os.path.abspath
    is_dir: MagicMock = mk_os.path.isdir
    listdir: MagicMock = mk_os.listdir
    path_exists: MagicMock = mk_os.path.exists
    remove: MagicMock = mk_os.remove
    abs_path.return_value = abs_schema
    get_property.return_value = file_schema

    def mocks_reset() -> None:
        """Reset the mocks."""
        reset_mocks(abs_path, is_dir, listdir, get_property, path_exists, remove, _create_schema)

    # Test when no parameters are passed
    runner = CliRunner()
    result = runner.invoke(create_graphql_schema)
    assert result.exit_code != 0
    assert "Missing argument" in result.output
    abs_path.assert_not_called()
    is_dir.assert_not_called()
    listdir.assert_not_called()
    get_property.assert_not_called()
    path_exists.assert_not_called()
    remove.assert_not_called()
    _create_schema.assert_not_called()
    mocks_reset()

    # Test when file is not a directory
    is_dir.return_value = False
    result = runner.invoke(create_graphql_schema, [path_schema])
    assert result.exit_code != 0
    assert isinstance(result.exception, NotADirectoryError)
    abs_path.assert_called_once()
    is_dir.assert_called_once_with(abs_schema)
    _create_schema.assert_not_called()
    mocks_reset()

    # Test when directory is empty
    is_dir.return_value = True
    listdir.return_value = []
    result = runner.invoke(create_graphql_schema, [path_schema])
    assert result.exit_code != 0
    assert isinstance(result.exception, FileNotFoundError)
    abs_path.assert_called_once()
    is_dir.assert_called_once_with(abs_schema)
    listdir.assert_called_once_with(abs_schema)
    _create_schema.assert_not_called()
    mocks_reset()

    # Test when schema file already exists
    listdir.return_value = ["file1", "file2"]
    path_exists.return_value = True
    result = runner.invoke(create_graphql_schema, [path_schema])
    assert result.exit_code == 0
    abs_path.assert_called_once()
    is_dir.assert_called_once_with(abs_schema)
    listdir.assert_called_once_with(abs_schema)
    get_property.assert_called_once()
    path_exists.assert_called_once_with(file_schema)
    remove.assert_called_once_with(file_schema)
    _create_schema.assert_called_once_with(abs_schema, file_schema)
    mocks_reset()

    # Test when schema file does not exist
    path_exists.return_value = False
    result = runner.invoke(create_graphql_schema, [path_schema])
    assert result.exit_code == 0
    abs_path.assert_called_once()
    is_dir.assert_called_once_with(abs_schema)
    listdir.assert_called_once_with(abs_schema)
    get_property.assert_called_once()
    path_exists.assert_called_once_with(file_schema)
    remove.assert_not_called()
    _create_schema.assert_called_once_with(abs_schema, file_schema)
    mocks_reset()


def test_create_graphql_schema(
    ws_success: MagicMock,
    run_operation: MagicMock,
    get_property: MagicMock,
    mk_open: MagicMock,
    mk_build_schema: MagicMock,
) -> None:
    """Test create_graphql_schema"""
    schema_path = "src/tests/resources/graphql"
    output_file = "graphql_schema_file"
    get_property.return_value = output_file

    def mocks_reset() -> None:
        """Reset the mocks."""
        reset_mocks(ws_success, run_operation, get_property, mk_open, mk_build_schema)

    runner = CliRunner()
    result = runner.invoke(create_graphql_schema, [schema_path])
    assert not result.exception
    assert result.exit_code == 0

    assert run_operation.call_count == 2
    assert ws_success.call_count == 2
    j = []
    for call in write_mocks[f"{output_file}.json"].mock_calls:
        args = [arg for arg in call.args if arg]
        if args:
            j.append("".join(set(call.args)))

    json_written_data = "".join(j)
    assert "isDeprecated" in json_written_data
    assert "description" in json_written_data
    assert "name" in json_written_data
    assert "Mutation" in json_written_data
    assert "Profile" in json_written_data
    assert "avatar" in json_written_data
    assert "updateProfile" in json_written_data
    assert "sendGroupMessage" in json_written_data
    assert "eventsByLocation" in json_written_data
    assert json_written_data.startswith("{")
    schema_written_data = "".join(write_mocks[f"{output_file}.graphql"].mock_calls[2][1])
    assert "Mutation" in schema_written_data
    assert "Profile" in schema_written_data
    assert "avatar" in schema_written_data
    assert "updateProfile" in schema_written_data
    assert "sendGroupMessage" in schema_written_data
    assert "eventsByLocation" in schema_written_data
    assert schema_written_data.startswith("type ")
    assert run_operation.call_count == 2
    assert ws_success.call_count == 2
    mocks_reset()
