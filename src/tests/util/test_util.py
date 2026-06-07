"""Test cases for util.py"""

import subprocess
from unittest.mock import MagicMock, patch, mock_open
from typing import Generator, Callable
from types import SimpleNamespace
import pytest
import click
from click.testing import CliRunner
from mega_snake.util.util import (
    load_json_with_comments,
    run_operation,
    get_command_return_code,
    get_input_or_default,
    get_validated_input,
    get_remote,
    get_remote_url,
    get_main_branch,
    get_current_commit,
    cli_metadata,
    wrapper_decorator,
)


@pytest.fixture(name="mk_ws_advice")
def fixture_mk_ws_advice() -> Generator[MagicMock]:
    """Fixture for ws_advice."""
    with patch("mega_snake.util.util.ws_advice") as mock:
        yield mock


@pytest.fixture(name="mk_ws_warning")
def fixture_mk_ws_warning() -> Generator[MagicMock]:
    """Fixture for ws_warning."""
    with patch("mega_snake.util.util.ws_warning") as mock:
        yield mock


@pytest.fixture(name="mk_subprocess_run")
def fixture_mk_subprocess_run() -> Generator[MagicMock]:
    """Fixture for subprocess.run."""
    with patch("mega_snake.util.util.subprocess.run") as mock:
        yield mock


@pytest.fixture(name="mk_input")
def fixture_mk_input() -> Generator[MagicMock]:
    """Fixture for builtins.input."""
    with patch("builtins.input") as mock:
        yield mock


@pytest.fixture(name="mk_run_operation")
def fixture_mk_run_operation() -> Generator[MagicMock]:
    """Fixture for run_operation."""
    with patch("mega_snake.util.util.run_operation") as mock:
        yield mock


@pytest.fixture(name="mk_get_validated_input")
def fixture_mk_get_validated_input() -> Generator[Callable]:
    """Fixture for get_validated_input."""
    with patch("mega_snake.util.util.get_validated_input") as mock:
        yield mock


@pytest.fixture(name="mk_get_remote")
def fixture_mk_get_remote() -> Generator[Callable]:
    """Fixture for get_remote."""
    with patch("mega_snake.util.util.get_remote") as mock:
        yield mock


def test_load_json_with_comments() -> None:
    """Test load_json_with_comments function."""
    m_open: MagicMock = mock_open()
    file_mock: MagicMock = m_open.return_value
    read_mock: MagicMock = file_mock.read
    read_mock.return_value = '{"key": "value"}'
    expected_result = {"key": "value"}

    with patch("builtins.open", m_open):
        result = load_json_with_comments("dummy_path")

    assert result == expected_result

    # Test empty file
    read_mock.return_value = ""
    expected_result = {}
    with patch("builtins.open", m_open):
        result = load_json_with_comments("dummy_path")
    assert result == expected_result


def test_run_operation(mk_ws_warning: MagicMock, mk_subprocess_run: MagicMock) -> None:
    """Test run_operation function."""
    command = "echo 'Hello, World!'"
    description = "Test command"

    valid_value: SimpleNamespace = SimpleNamespace(stdout="Hello, World!", stderr="", returncode=0)
    error_value = subprocess.CalledProcessError(returncode=-1, cmd="echo 'Hello, World!'", stderr="Command failed")

    # Test when command runs successfully
    mk_subprocess_run.return_value = valid_value
    with patch("mega_snake.util.util.get_property", return_value="bash"):
        result = run_operation(command, description)
    mk_ws_warning.assert_not_called()
    mk_subprocess_run.assert_called_once_with(["bash", "-c", command], shell=False, check=True, capture_output=True, text=True)
    assert result.stdout == "Hello, World!"
    mk_subprocess_run.reset_mock()
    mk_ws_warning.reset_mock()

    # Test when command fails once and succeeds on retry
    mk_subprocess_run.side_effect = [error_value, valid_value]
    with patch("mega_snake.util.util.get_property", return_value="bash"):
        result = run_operation(command, description)
    assert mk_ws_warning.call_count == 3
    assert mk_subprocess_run.call_count == 2
    assert result.stdout == "Hello, World!"
    mk_subprocess_run.reset_mock()
    mk_ws_warning.reset_mock()

    # Test when command fails all retries
    mk_subprocess_run.side_effect = [error_value] * 3
    with pytest.raises(subprocess.SubprocessError):
        with patch("mega_snake.util.util.get_property", return_value="bash"):
            run_operation(command, description)
    assert mk_ws_warning.call_count == 8
    assert mk_subprocess_run.call_count == 3


def test_get_command_return_code() -> None:
    """Test get_command_return_code function."""

    # Test with a valid command
    command = "echo 'Hello, World!'"
    expected_return_code = 0
    result = get_command_return_code(command)
    assert result == expected_return_code

    # Test with an invalid command
    command = "invalid_command"
    expected_return_code = 127  # Typically, this is the return code for command not found
    result = get_command_return_code(command)
    assert result == expected_return_code


def test_get_input_or_default(mk_input: MagicMock, mk_ws_warning: MagicMock) -> None:
    """Test get_input_or_default function."""

    # Test with correct input
    default_value = "defi"
    prompt = f"Enter a value (default: '{default_value}'): "
    input_value = "user_input"
    mk_input.return_value = input_value
    result = get_input_or_default(prompt, default_value)
    assert result == input_value
    mk_ws_warning.assert_not_called()

    # Test with empty input, should return default value
    mk_input.return_value = ""
    result = get_input_or_default(prompt, default_value)
    assert result == default_value
    mk_ws_warning.assert_not_called()

    # Test with input of different type
    default_value = 42
    prompt = f"Enter a number (default: {default_value}): "
    input_value = "string_input"
    mk_input.return_value = input_value
    result = get_input_or_default(prompt, default_value)
    assert result == default_value
    mk_ws_warning.assert_called_once()


def test_get_validated_input(mk_input: MagicMock, mk_ws_warning: MagicMock) -> None:
    """Test get_validated_input function."""
    valid_input = "option1"
    invalid_input = "invalid_option"
    valid_values = [valid_input, "option2", "option3"]
    prompt = "Choose an option: "

    # Test with valid input
    mk_input.return_value = valid_input
    result = get_validated_input(prompt, valid_values)
    assert result == valid_input
    mk_ws_warning.assert_not_called()

    # Test with invalid input on first try
    mk_input.side_effect = [invalid_input, valid_input]
    get_validated_input(prompt, valid_values)
    assert result == valid_input
    mk_ws_warning.assert_called_once()
    mk_ws_warning.reset_mock()

    # Test with invalid input on multiple tries
    mk_input.side_effect = [invalid_input, invalid_input, invalid_input, invalid_input]
    with pytest.raises(KeyError):
        get_validated_input(prompt, valid_values)
    assert mk_ws_warning.call_count == 4


def test_get_remote(mk_run_operation: MagicMock, mk_get_validated_input: MagicMock) -> None:
    """Test get_remote function."""

    # Test with no remotes
    origin = "origin"
    fork = "fork"
    mk_run_operation.return_value.stdout = ""
    result = get_remote()
    assert result is None
    mk_run_operation.assert_called_once_with("git remote", "Getting remotes")
    mk_get_validated_input.assert_not_called()
    mk_run_operation.reset_mock()

    # Test with a single remote
    mk_run_operation.return_value.stdout = origin
    result = get_remote()
    assert result == origin
    mk_run_operation.assert_called_once_with("git remote", "Getting remotes")
    mk_get_validated_input.assert_not_called()
    mk_run_operation.reset_mock()

    # Test with multiple remotes
    mk_run_operation.return_value.stdout = f"{origin}\n{fork}"
    mk_get_validated_input.return_value = 1
    result = get_remote()
    assert result == fork
    mk_run_operation.assert_called_once_with("git remote", "Getting remotes")
    mk_get_validated_input.assert_called_once()


def test_get_remote_url(mk_run_operation: MagicMock, mk_get_remote: MagicMock) -> None:
    """Test get_remote_url function."""

    # Test with no remote
    mk_get_remote.return_value = None
    result = get_remote_url()
    assert result is None
    mk_get_remote.assert_called_once()
    mk_run_operation.assert_not_called()
    mk_get_remote.reset_mock()

    # Test with a remote that has a URL
    remote_name = "origin"
    expected_url = "git@test.com"
    mk_get_remote.return_value = remote_name
    mk_run_operation.return_value.stdout = expected_url
    result = get_remote_url()
    assert result == expected_url
    mk_get_remote.assert_called_once()
    mk_run_operation.assert_called_once()


def test_get_main_branch(mk_run_operation: MagicMock, mk_get_remote: MagicMock) -> None:
    """Test get_main_branch function."""

    # Tes when no remote is found
    mk_get_remote.return_value = None
    current_branch = "curent"
    run_operation_result = SimpleNamespace(stdout=current_branch)
    mk_run_operation.return_value = run_operation_result
    result = get_main_branch()
    assert result == current_branch
    mk_get_remote.assert_called_once()
    mk_run_operation.assert_called_once()
    mk_run_operation.reset_mock()
    mk_get_remote.reset_mock()

    # Test when a remote is found
    remote_name = "origin"
    main_branch = "master"
    mk_get_remote.return_value = remote_name
    stdout_srt = (
        f"Fetch URL: https://github.com/dummy/repo.git\n"
        f"Push  URL: https://github.com/dummy/repo.git\n"
        f"HEAD branch: {main_branch}\n"
        f"Remote branches:\n"
    )
    run_operation_result = SimpleNamespace(stdout=stdout_srt)
    mk_run_operation.return_value = run_operation_result
    result = get_main_branch()
    assert result == main_branch
    mk_get_remote.assert_called_once()
    mk_run_operation.assert_called_once()
    mk_run_operation.reset_mock()
    mk_get_remote.reset_mock()

    # Test when a remote is found but no main branch is found
    mk_get_remote.return_value = remote_name
    run_operation_result = SimpleNamespace(stdout="")
    mk_run_operation.return_value = run_operation_result
    with pytest.raises(LookupError):
        get_main_branch()
    mk_get_remote.assert_called_once()
    mk_run_operation.assert_called_once()
    mk_run_operation.reset_mock()
    mk_get_remote.reset_mock()

    # Test when a remote is found but failed to parse the main branch
    mk_get_remote.return_value = remote_name
    stdout_srt = "Fetch URL:"
    run_operation_result = SimpleNamespace(stdout=stdout_srt)
    mk_run_operation.return_value = run_operation_result
    with pytest.raises(LookupError):
        get_main_branch()
    mk_get_remote.assert_called_once()
    mk_run_operation.assert_called_once()


def test_get_current_commit(mk_run_operation: MagicMock) -> None:
    """Test get_current_commit function."""
    expected_commit = "abc123"
    run_operation_result = SimpleNamespace(stdout=expected_commit)
    mk_run_operation.return_value = run_operation_result

    result = get_current_commit()
    assert result == expected_commit
    mk_run_operation.assert_called_once_with("git rev-parse HEAD", "Getting current branch")


def test_cli_metadata() -> None:
    """Test cli_metadata decorator."""

    @cli_metadata(name="test_command", short_help="Test command", help="This is a test command")
    def test_function() -> None:
        pass

    assert hasattr(test_function, "flags")
    assert test_function.flags == {
        "name": "test_command",
        "short_help": "Test command",
        "help": "This is a test command",
    }


def test_wrapper_decorator() -> None:
    """Test wrapper_decorator function."""

    def wrapper(ctx: click.Context, *_args, **_kwargs) -> None:
        """Wrapper for the config_environment command."""
        ctx.obj["exit_code"] = 21

    add_wrapper = wrapper_decorator(wrapper)

    exit_code: int = 0

    @click.command()
    @click.pass_context
    # This command is decorated with cli_metadata
    @cli_metadata(name="test_command", short_help="Test command", help="This is a test command")
    def test_command(ctx) -> None:
        """Test command."""
        nonlocal exit_code
        exit_code = ctx.obj.get("exit_code", 0)

    # Add aliases to the command
    setattr(test_command, "aliases", ["tc", "testcmd"])

    wrapped_command: click.Command = add_wrapper(test_command)
    runner = CliRunner()
    result = runner.invoke(wrapped_command, obj={"foo": "bar"})
    assert result.exit_code == 0
    assert result.exception is None
    assert isinstance(wrapped_command, click.Command)
    assert exit_code == 21
