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
    get_typed_validated_input,
    cli_metadata,
    wrapper_decorator,
    GIT_EXCLUDE_FILE,
)
from mega_snake.util.formatting import (
    USER_DECLINED_ERROR_CODE,
    InternalStateError,
    UserDeclinedError,
    resolve_error_code,
)
from mega_snake.util.cli_group import ATTR_METADATA


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
        ["bash", "-c", command], shell=False, check=True, capture_output=True, text=True, errors="replace", timeout=None
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


def test_run_operation_retries_a_timeout_like_any_other_failure(
    mk_ws_warning: MagicMock, mk_subprocess_run: MagicMock
) -> None:
    """A timeout is a transient failure and must go through the same retries as a bad exit code.

    ``subprocess.TimeoutExpired`` is a ``SubprocessError`` but **not** a ``CalledProcessError``, so
    the retry clause never saw it: one slow network call — a cold fetch, a VPN, a credential prompt
    — aborted the whole command on the first attempt with a raw traceback, and the retries that
    exist precisely for this never ran.
    """
    timed_out = subprocess.TimeoutExpired(cmd="git fetch", timeout=60, output=b"partial", stderr=b"slow")
    valid_value = SimpleNamespace(stdout="fetched", stderr="", returncode=0)

    mk_subprocess_run.side_effect = [timed_out, valid_value]
    with patch("mega_snake.util.util.get_property", return_value="bash"):
        result = run_operation("git fetch", "Fetching", timeout=60)

    assert mk_subprocess_run.call_count == 2, "the timeout was not retried"
    assert result.stdout == "fetched"
    warnings = [issued.args[0] for issued in mk_ws_warning.call_args_list]
    assert warnings[0] == "Fetching timed out after 60 seconds on attempt 1."


def test_run_operation_reports_a_persistent_timeout_as_a_subprocess_error(
    mk_ws_warning: MagicMock, mk_subprocess_run: MagicMock
) -> None:
    """Once the retries are spent the timeout must surface as the same ``SubprocessError`` every
    caller already handles — and it must say it timed out, not that it failed, since there is no
    exit code to show. Leaking the raw ``TimeoutExpired`` is what produced exit 111 and a traceback.
    """
    timed_out = subprocess.TimeoutExpired(cmd="git fetch", timeout=60, output=b"partial", stderr=b"slow")
    mk_subprocess_run.side_effect = [timed_out] * 3

    with patch("mega_snake.util.util.get_property", return_value="bash"):
        with pytest.raises(subprocess.SubprocessError, match="timed out after 3 attempts") as raised:
            run_operation("git fetch", "Fetching", timeout=60)

    assert not isinstance(raised.value, subprocess.TimeoutExpired), "the raw timeout escaped unwrapped"
    assert mk_subprocess_run.call_count == 3
    # TimeoutExpired carries bytes, not the decoded text CalledProcessError has
    assert "slow" in str(raised.value), "the captured stderr was lost decoding it"


def test_run_operation_renders_a_missing_captured_stream_as_empty(
    mk_ws_warning: MagicMock, mk_subprocess_run: MagicMock
) -> None:
    """A timeout that fired before anything was read carries ``None`` on both streams. The warning
    must still render — formatting ``None`` into the message is what a bare ``error.stderr`` did."""
    timed_out = subprocess.TimeoutExpired(cmd="git fetch", timeout=3)
    mk_subprocess_run.side_effect = [timed_out] * 3

    with patch("mega_snake.util.util.get_property", return_value="bash"):
        with pytest.raises(subprocess.SubprocessError) as raised:
            run_operation("git fetch", "Fetching", timeout=3)

    assert "None" not in str(raised.value), "an absent stream leaked as the literal 'None'"
    assert "Error: \n" in str(raised.value)


def test_get_command_return_code() -> None:
    """Test get_command_return_code function."""

    # Test with a valid command
    command = "echo 'Hello, World!'"
    expected_return_code = 0
    result = get_command_return_code(command, "Running a valid command")
    assert result == expected_return_code

    # Test with an invalid command
    command = "invalid_command"
    expected_return_code = 127  # Typically, this is the return code for command not found
    result = get_command_return_code(command, "Running an invalid command")
    assert result == expected_return_code


def test_get_typed_validated_input_accepts_a_listed_value(mk_input: MagicMock, mk_ws_warning: MagicMock) -> None:
    """A value present in the allowed list is returned as-is, with no warning shown."""
    mk_input.return_value = "master"
    assert get_typed_validated_input("Main branch?", "not a branch", ["master", "develop"]) == "master"
    mk_ws_warning.assert_not_called()


def test_get_typed_validated_input_retries_until_a_listed_value_arrives(
    mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """A rejected value is warned about and asked again; the caller only ever receives a listed
    one, never the rejected input."""
    mk_input.side_effect = ["nope", "develop"]
    result = get_typed_validated_input("Main branch?", "not a branch", ["master", "develop"])
    assert result == "develop"
    assert result != "nope", "a rejected value must never reach the caller"
    mk_ws_warning.assert_called_once_with("not a branch")


def test_get_typed_validated_input_gives_up_after_too_many_rejections(
    mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """Prompting forever would trap a scripted caller, so the attempts are capped: the failure is
    raised (carrying the guidance message) instead of returning a value nobody validated."""
    mk_input.side_effect = ["a", "b", "c", "d", "e"]
    with pytest.raises(KeyError, match="run git branch"):
        get_typed_validated_input("Main branch?", "not a branch", ["master"], fail_msg="run git branch")
    assert mk_ws_warning.call_count == 4


def test_get_typed_validated_input_matches_branch_names_case_sensitively(
    mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """The answer is compared verbatim, because the values are git branch names and git treats
    `Main` and `main` as two different branches.

    This is the regression: the answer used to be lowercased before the comparison, which made
    every branch carrying an uppercase letter impossible to select — the user typed the name git
    itself reports, and the tool rejected it while warning that names are case-sensitive.
    """
    mk_input.return_value = "Main"
    assert get_typed_validated_input("Main branch?", "not a branch", ["Main", "develop"]) == "Main"
    mk_ws_warning.assert_not_called()

    # The mirror half: matching verbatim must also reject a case that does not exist, rather than
    # quietly resolving to the branch that differs only in case.
    mk_input.side_effect = ["main", "main", "main", "main", "main"]
    with pytest.raises(KeyError):
        get_typed_validated_input("Main branch?", "not a branch", ["Main"])


def test_get_typed_validated_input_returns_the_answer_untouched(mk_input: MagicMock) -> None:
    """Whatever transformation the comparison applied would also reach the caller, and the caller
    builds git references out of this value — so it must come back exactly as it was typed."""
    for branch in ("release/ABC-123", "Feature_X", "MASTER"):
        mk_input.side_effect = None
        mk_input.return_value = branch
        assert get_typed_validated_input("Main branch?", "warn", [branch]) == branch


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


# ---------------------------------------------------------------------------
# add_to_gitignore
# ---------------------------------------------------------------------------

GITIGNORE_ENTRIES: list[tuple[str, str]] = [
    (".github/skills/mgsnake/", ".github/skills/mgsnake/ folder"),
    (".claude/skills/mgsnake/", ".claude/skills/mgsnake/ folder"),
]


def test_add_to_gitignore_creates_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """A missing .gitignore file is created when entries are added for the first time."""
    from mega_snake.util.util import GITIGNORE_FILE, add_to_gitignore

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()

    add_to_gitignore(GITIGNORE_ENTRIES)

    content = (tmp_path / GITIGNORE_FILE).read_text(encoding="utf-8")
    assert ".github/skills/mgsnake/" in content.splitlines()
    assert ".claude/skills/mgsnake/" in content.splitlines()
    assert mk_util_ws_success.call_count == 2
    mk_ws_advice.assert_not_called()


def test_add_to_gitignore_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """Entries already present in .gitignore are not duplicated."""
    from mega_snake.util.util import GITIGNORE_FILE, add_to_gitignore

    monkeypatch.chdir(tmp_path)
    gitignore = tmp_path / GITIGNORE_FILE
    (tmp_path / ".git").mkdir()
    gitignore.write_text(".github/skills/mgsnake/\n", encoding="utf-8")

    add_to_gitignore(GITIGNORE_ENTRIES)

    lines = gitignore.read_text(encoding="utf-8").splitlines()
    assert lines.count(".github/skills/mgsnake/") == 1
    assert ".claude/skills/mgsnake/" in lines
    mk_util_ws_success.assert_called_once()
    mk_ws_advice.assert_called_once()

    # Second full run changes nothing
    mk_util_ws_success.reset_mock()
    add_to_gitignore(GITIGNORE_ENTRIES)
    assert gitignore.read_text(encoding="utf-8").splitlines() == lines
    mk_util_ws_success.assert_not_called()


def test_add_to_gitignore_separates_an_unterminated_last_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """A .gitignore whose last line has no newline keeps that line intact, entry on its own line.

    This is the realistic shape of a hand-edited file, and the only one that distinguishes appending
    from concatenating: with a trailing newline both behave identically.
    """
    from mega_snake.util.util import GITIGNORE_FILE, add_to_gitignore

    monkeypatch.chdir(tmp_path)
    gitignore = tmp_path / GITIGNORE_FILE
    (tmp_path / ".git").mkdir()
    gitignore.write_text("build/", encoding="utf-8")  # No trailing newline, on purpose.

    add_to_gitignore(GITIGNORE_ENTRIES)

    lines = gitignore.read_text(encoding="utf-8").splitlines()
    assert lines == ["build/", ".github/skills/mgsnake/", ".claude/skills/mgsnake/"], (
        f"the pre-existing last line must survive untouched, got {lines}"
    )
    assert "build/.github/skills/mgsnake/" not in lines, "the entry was concatenated onto the last line"
    assert mk_util_ws_success.call_count == 2
    mk_ws_advice.assert_not_called()


def test_add_to_gitignore_outside_a_git_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_ws_warning: MagicMock,
) -> None:
    """Outside a git repository the additions are skipped with a warning, not an error."""
    from mega_snake.util.util import GITIGNORE_FILE, add_to_gitignore

    monkeypatch.chdir(tmp_path)

    add_to_gitignore(GITIGNORE_ENTRIES)

    assert not (tmp_path / GITIGNORE_FILE).exists()
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
