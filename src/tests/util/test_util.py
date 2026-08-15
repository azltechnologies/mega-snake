"""Test cases for util.py"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from typing import Generator, Callable
from types import SimpleNamespace
import pytest
import click
from click.testing import CliRunner
from mega_snake.util.util import (
    load_json_with_comments,
    run_operation,
    ensure_working_path,
    exclude_from_git,
    get_command_return_code,
    get_input_or_default,
    get_validated_input,
    get_remote,
    get_remote_url,
    get_main_branch,
    get_current_commit,
    cli_metadata,
    require_remote,
    reset_remote_cache,
    wrapper_decorator,
    write_json_atomically,
    GIT_EXCLUDE_FILE,
    NO_REMOTE_MESSAGE,
)
from mega_snake.util.formatting import (
    USER_DECLINED_ERROR_CODE,
    InternalStateError,
    UserDeclinedError,
    resolve_error_code,
)
from mega_snake.util.cli_group import ATTR_METADATA


@pytest.fixture(autouse=True)
def fixture_clear_remote_cache() -> Generator[None, None, None]:
    """Keep the memoized remote from leaking between tests."""
    reset_remote_cache()
    yield
    reset_remote_cache()


@pytest.fixture(name="mk_ws_advice")
def fixture_mk_ws_advice() -> Generator[MagicMock, None, None]:
    """Fixture for ws_advice."""
    with patch("mega_snake.util.util.ws_advice") as mock:
        yield mock


@pytest.fixture(name="mk_ws_warning")
def fixture_mk_ws_warning() -> Generator[MagicMock, None, None]:
    """Fixture for ws_warning."""
    with patch("mega_snake.util.util.ws_warning") as mock:
        yield mock


@pytest.fixture(name="mk_subprocess_run")
def fixture_mk_subprocess_run() -> Generator[MagicMock, None, None]:
    """Fixture for subprocess.run."""
    with patch("mega_snake.util.util.subprocess.run") as mock:
        yield mock


@pytest.fixture(name="mk_input")
def fixture_mk_input() -> Generator[MagicMock, None, None]:
    """Fixture for builtins.input."""
    with patch("builtins.input") as mock:
        yield mock


@pytest.fixture(name="mk_run_operation")
def fixture_mk_run_operation() -> Generator[MagicMock, None, None]:
    """Fixture for run_operation."""
    with patch("mega_snake.util.util.run_operation") as mock:
        yield mock


@pytest.fixture(name="mk_get_validated_input")
def fixture_mk_get_validated_input() -> Generator[Callable, None, None]:
    """Fixture for get_validated_input."""
    with patch("mega_snake.util.util.get_validated_input") as mock:
        yield mock


@pytest.fixture(name="mk_get_remote")
def fixture_mk_get_remote() -> Generator[Callable, None, None]:
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
    mk_subprocess_run.assert_called_once_with(
        ["bash", "-c", command], shell=False, check=True, capture_output=True, text=True, errors="replace"
    )
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
    reset_remote_cache()

    # Test with a single remote
    mk_run_operation.return_value.stdout = origin
    result = get_remote()
    assert result == origin
    mk_run_operation.assert_called_once_with("git remote", "Getting remotes")
    mk_get_validated_input.assert_not_called()
    mk_run_operation.reset_mock()
    reset_remote_cache()

    # Test with multiple remotes
    mk_run_operation.return_value.stdout = f"{origin}\n{fork}"
    mk_get_validated_input.return_value = 1
    result = get_remote()
    assert result == fork
    mk_run_operation.assert_called_once_with("git remote", "Getting remotes")
    mk_get_validated_input.assert_called_once()


def test_get_remote_is_cached(mk_run_operation: MagicMock, mk_get_validated_input: MagicMock) -> None:
    """The remote is resolved once per process: no extra `git remote`, no extra prompt."""
    origin = "origin"
    fork = "fork"
    mk_run_operation.return_value.stdout = f"{origin}\n{fork}"
    mk_get_validated_input.return_value = 1

    assert get_remote() == fork
    assert get_remote() == fork
    assert get_remote() == fork
    mk_run_operation.assert_called_once_with("git remote", "Getting remotes")
    mk_get_validated_input.assert_called_once()

    # A "no remote" answer is cached too, so it is not re-resolved on every call either
    reset_remote_cache()
    mk_run_operation.reset_mock()
    mk_run_operation.return_value.stdout = ""
    assert get_remote() is None
    assert get_remote() is None
    mk_run_operation.assert_called_once_with("git remote", "Getting remotes")


def test_get_remote_when_command_fails(mk_run_operation: MagicMock, mk_ws_warning: MagicMock) -> None:
    """A failing `git remote` (e.g. not a git repository) is reported with the friendly message."""
    mk_run_operation.side_effect = subprocess.SubprocessError("git remote failed after 3 attempts")

    assert get_remote() is None
    mk_ws_warning.assert_called_once()
    assert NO_REMOTE_MESSAGE in mk_ws_warning.call_args.args[0]

    # The failure is cached as "no remote", so the retries are not repeated
    mk_run_operation.reset_mock()
    assert get_remote() is None
    mk_run_operation.assert_not_called()


def test_require_remote(mk_run_operation: MagicMock) -> None:
    """require_remote returns the remote, or reports a missing one as an environment error.

    A repository without a remote is not a misuse of the CLI, so it must not carry the
    invocation-error status: the negative assertion is what pins that distinction, since a
    ClickException would also make a bare ``pytest.raises(Exception)`` pass.
    """
    mk_run_operation.return_value.stdout = "origin"
    assert require_remote() == "origin"

    reset_remote_cache()
    mk_run_operation.return_value.stdout = ""
    with pytest.raises(EnvironmentError, match="No remote repository found") as excinfo:
        require_remote()
    assert not isinstance(excinfo.value, click.ClickException), (
        "a missing remote must not be reported as an invocation error"
    )
    assert resolve_error_code(excinfo.value) == 112, (
        f"a missing remote resolved to {resolve_error_code(excinfo.value)}, expected 112"
    )


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

    assert hasattr(test_function, ATTR_METADATA)
    assert getattr(test_function, ATTR_METADATA) == {
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


def test_wrapper_decorator_keeps_a_group_a_group() -> None:
    """Wrapping must not turn a `click.Group` into a leaf command.

    The rebuild copies a command through `click.Command.__init__`'s signature, which knows nothing
    about `commands`. Before this was handled, registering the nested `config` group through its
    module wrapper silently produced a command with no subcommands, so `mgsnake config get` stopped
    resolving.
    """

    def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
        """No-op pre-flight."""

    @click.group(name="parent")
    def parent() -> None:
        """Parent group."""

    @parent.command(name="child")
    def child() -> None:
        """Child command."""
        click.echo("child ran")

    wrapped = wrapper_decorator(wrapper)(parent)

    assert isinstance(wrapped, click.Group)
    assert set(wrapped.commands) == {"child"}
    result = CliRunner().invoke(wrapped, ["child"])
    assert result.exit_code == 0
    assert "child ran" in result.output


def test_write_json_atomically_writes_the_payload(tmp_path: Path) -> None:
    """The happy path writes readable JSON and preserves the caller's key order."""
    destination = tmp_path / "nested" / "payload.json"

    write_json_atomically(destination, [{"b": 1, "a": 2}])

    assert destination.read_text(encoding="utf-8").startswith('[\n  {\n    "b": 1')


def test_write_json_atomically_leaves_the_previous_file_intact_on_failure(tmp_path: Path) -> None:
    """A failed serialization must neither corrupt the target nor leak the temporary file."""
    destination = tmp_path / "payload.json"
    destination.write_text("[]\n", encoding="utf-8")
    original_bytes = destination.read_bytes()

    with patch("json.dump", side_effect=RuntimeError("interrupted")):
        with pytest.raises(RuntimeError):
            write_json_atomically(destination, [{"a": 1}])

    assert destination.read_bytes() == original_bytes
    assert [entry.name for entry in tmp_path.iterdir()] == ["payload.json"]


@pytest.fixture(name="mk_util_ws_success")
def fixture_mk_util_ws_success() -> Generator[MagicMock, None, None]:
    """Fixture for ws_success."""
    with patch("mega_snake.util.util.ws_success") as mock:
        yield mock


@pytest.fixture(name="mk_util_ws_info")
def fixture_mk_util_ws_info() -> Generator[MagicMock, None, None]:
    """Fixture for ws_info."""
    with patch("mega_snake.util.util.ws_info") as mock:
        yield mock


@pytest.fixture(name="mk_get_property")
def fixture_mk_get_property() -> Generator[MagicMock, None, None]:
    """Fixture for get_property."""
    with patch("mega_snake.util.util.get_property") as mock:
        yield mock


ENTRIES: list[tuple[str, str]] = [("workspace_temp/", "workspace_temp folder"), (".vscode/", ".vscode folder")]


def test_exclude_from_git_creates_missing_exclude_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """A missing .git/info/exclude file is created instead of crashing with FileNotFoundError."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()

    exclude_from_git(ENTRIES)

    content = (tmp_path / GIT_EXCLUDE_FILE).read_text(encoding="utf-8")
    assert content.splitlines() == ["workspace_temp/", ".vscode/"]
    assert mk_util_ws_success.call_count == 2
    mk_ws_advice.assert_not_called()


def test_exclude_from_git_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """Entries already excluded are reported but not duplicated, and comments are preserved."""
    monkeypatch.chdir(tmp_path)
    exclude_file = tmp_path / GIT_EXCLUDE_FILE
    exclude_file.parent.mkdir(parents=True)
    exclude_file.write_text("# comments here\nworkspace_temp/", encoding="utf-8")

    exclude_from_git(ENTRIES)

    lines = exclude_file.read_text(encoding="utf-8").splitlines()
    assert lines == ["# comments here", "workspace_temp/", ".vscode/"]
    mk_util_ws_success.assert_called_once()
    mk_ws_advice.assert_called_once()

    # Running it again changes nothing
    mk_util_ws_success.reset_mock()
    exclude_from_git(ENTRIES)
    assert exclude_file.read_text(encoding="utf-8").splitlines() == lines
    mk_util_ws_success.assert_not_called()


def test_exclude_from_git_outside_a_git_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_ws_warning: MagicMock,
) -> None:
    """Outside a git repository the exclusions are skipped with a warning, not an error."""
    monkeypatch.chdir(tmp_path)

    exclude_from_git(ENTRIES)

    assert not (tmp_path / ".git").exists()
    mk_ws_warning.assert_called_once()


def test_ensure_working_path_when_it_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_get_property: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_util_ws_info: MagicMock,
) -> None:
    """An existing working path is returned as-is, without prompting the user."""
    monkeypatch.chdir(tmp_path)
    working_path = tmp_path / "workspace_temp"
    working_path.mkdir()
    mk_get_property.return_value = str(working_path)

    assert ensure_working_path() == str(working_path)
    mk_get_validated_input.assert_not_called()
    mk_util_ws_info.assert_called_once()


def test_ensure_working_path_creates_and_excludes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_get_property: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_util_ws_success: MagicMock,
    mk_ws_warning: MagicMock,
    mk_util_ws_info: MagicMock,
) -> None:
    """A missing working path is created on confirmation and excluded from git right away."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    working_path = tmp_path / "workspace_temp"
    mk_get_property.return_value = str(working_path)
    mk_get_validated_input.return_value = "y"

    assert ensure_working_path() == str(working_path)
    assert working_path.is_dir()
    mk_get_validated_input.assert_called_once()
    assert "workspace_temp/" in (tmp_path / GIT_EXCLUDE_FILE).read_text(encoding="utf-8").splitlines()
    assert mk_util_ws_success.call_count == 2  # one for the exclusion, one for the creation

    # It is safe to run again even if the folder appeared in between (no exist_ok race)
    mk_get_validated_input.reset_mock()
    assert ensure_working_path() == str(working_path)
    mk_get_validated_input.assert_not_called()


def test_ensure_working_path_when_user_declines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_get_property: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_ws_warning: MagicMock,
) -> None:
    """Declining to create the folder fails with UserDeclinedError, carrying its own exit status.

    It stays a ClickException subclass so the output remains clean and traceback-free, but the
    status has to be 114 and not the generic 1: a script that offered the prompt needs to tell
    "the user said no" apart from "the command was called wrong".
    """
    monkeypatch.chdir(tmp_path)
    working_path = tmp_path / "workspace_temp"
    mk_get_property.return_value = str(working_path)
    mk_get_validated_input.return_value = "n"

    with pytest.raises(UserDeclinedError, match="Cannot continue without") as excinfo:
        ensure_working_path()
    assert not working_path.exists()
    assert isinstance(excinfo.value, click.ClickException), "must keep Click's traceback-free output"
    assert excinfo.value.exit_code == USER_DECLINED_ERROR_CODE, (
        f"declining exited {excinfo.value.exit_code}, expected {USER_DECLINED_ERROR_CODE}"
    )
    assert excinfo.value.exit_code != 1, "declining must not be reported as an invocation error"

    # Callers can customize the message shown when the user declines
    with pytest.raises(UserDeclinedError, match="custom message"):
        ensure_working_path("custom message")


def test_ensure_working_path_invalid_property(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_get_property: MagicMock,
) -> None:
    """An empty working path, or one outside the current directory, is a bug: InternalStateError.

    Both conditions were already ruled out when the properties were built, so neither is something
    the user caused or can fix. Asserting the type is what keeps them from being reported as an
    ordinary bad value the user should go correct.
    """
    monkeypatch.chdir(tmp_path)

    mk_get_property.return_value = ""
    with pytest.raises(InternalStateError, match="not found in the properties"):
        ensure_working_path()

    mk_get_property.return_value = str(tmp_path.parent / "somewhere_else")
    with pytest.raises(InternalStateError, match="not in the current directory"):
        ensure_working_path()
