"""Test cases for util.py"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
from typing import Any, Callable, Generator, Optional
from types import SimpleNamespace
import pytest
import click
from mega_snake.util.util import (
    load_json_with_comments,
    run_operation,
    ensure_working_path,
    exclude_from_git,
    get_command_return_code,
    get_input_or_default,
    get_validated_input,
    get_validated_selection,
    get_typed_validated_input,
    MAX_PROMPT_TRIES,
    cli_metadata,
    write_json_atomically,
    GIT_EXCLUDE_FILE,
)
from mega_snake.util.formatting import (
    USER_DECLINED_ERROR_CODE,
    InternalStateError,
    UserDeclinedError,
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


# The shell `run_operation` must execute with, for every platform and every configurable shell. This
# table *is* the contract, so it is written out rather than derived from the code under test. The rule
# it encodes: a shell native to the platform is kept; anything else falls back to that platform's
# default -- PowerShell on Windows, zsh on macOS, bash on Linux.
SHELL_RESOLUTION: dict[tuple[str, str], str] = {
    ("Linux", "bash"): "bash",
    ("Linux", "zsh"): "zsh",
    ("Linux", "powershell"): "bash",
    ("Linux", "pwsh"): "bash",
    ("Darwin", "bash"): "bash",
    ("Darwin", "zsh"): "zsh",
    ("Darwin", "powershell"): "zsh",
    ("Darwin", "pwsh"): "zsh",
    ("Windows", "bash"): "powershell",
    ("Windows", "zsh"): "powershell",
    ("Windows", "powershell"): "powershell",
    ("Windows", "pwsh"): "pwsh",
}
SUPPORTED_PLATFORMS: tuple[str, ...] = ("Linux", "Darwin", "Windows")


@pytest.mark.parametrize(("platform_name", "configured", "expected"), [(*key, value) for key, value in SHELL_RESOLUTION.items()])
def test_run_operation_resolves_the_shell_for_every_platform_and_configured_shell(
    platform_name: str, configured: str, expected: str, mk_subprocess_run: MagicMock
) -> None:
    """Each (platform, configured shell) pair executes with exactly the shell the contract names.

    The whole matrix, not a sample: the defect this pins was one wrong comparison (`OS != "Darwin"`)
    that sent Windows with PowerShell -- the configuration `config_setup.ps1` exports for every
    Windows user -- to `zsh`, while every row a Linux or macOS developer ever runs stayed correct.
    Only the rows nobody exercises locally could show it, so all of them are asserted. The flag is
    checked too, since PowerShell takes `-Command` and a POSIX shell takes `-c`.
    """
    mk_subprocess_run.return_value = SimpleNamespace(stdout="", stderr="", returncode=0)

    # Every shell is reported as installed, so the row depends only on the resolution rule and not on
    # which shells happen to exist on the machine running the suite. A missing fallback has its own tests.
    with (
        patch("mega_snake.util.util.OS", platform_name),
        patch("mega_snake.util.util.get_property", return_value=configured),
        patch("mega_snake.util.util.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"),
    ):
        run_operation("git status", "Probing the shell")

    argv = mk_subprocess_run.call_args[0][0]
    expected_flag = "-Command" if expected in ("powershell", "pwsh") else "-c"
    assert argv[0] == expected, f"{platform_name} with {configured} ran through {argv[0]}, not {expected}"
    assert argv[1] == expected_flag, f"{platform_name} with {configured} passed {argv[1]} to {argv[0]}"


SUBSTITUTED_SHELLS: list[tuple[str, str, str]] = [
    (platform_name, configured, resolved)
    for (platform_name, configured), resolved in SHELL_RESOLUTION.items()
    if resolved != configured
]


@pytest.mark.parametrize(("platform_name", "configured", "fallback"), SUBSTITUTED_SHELLS)
def test_run_operation_refuses_a_fallback_shell_that_is_not_installed(
    platform_name: str, configured: str, fallback: str, mk_subprocess_run: MagicMock
) -> None:
    """A missing fallback is reported by name, before any attempt, instead of a bare FileNotFoundError.

    Derived from the contract table, so every substitution the resolution can make is covered. The
    error names the configured shell, the platform and the missing fallback -- the three facts a
    user needs, and the ones `[WinError 2] The system cannot find the file specified` gave none of.
    The extent is asserted as well: no process was started, so nothing was retried.
    """
    with (
        patch("mega_snake.util.util.OS", platform_name),
        patch("mega_snake.util.util.get_property", return_value=configured),
        patch("mega_snake.util.util.shutil.which", return_value=None) as mk_which,
        pytest.raises(EnvironmentError) as raised,
    ):
        run_operation("git status", "Probing the shell")

    assert str(raised.value) == (
        f"MEGA_SNAKE_SHELL is '{configured}', which is not native to {platform_name}, so mgsnake runs its "
        f"commands through '{fallback}' instead -- but '{fallback}' is not installed or not on the PATH. "
        f"Install '{fallback}', or set MEGA_SNAKE_SHELL to a shell that is available on {platform_name}."
    )
    assert type(raised.value) is OSError, "a subclass would resolve to a different exit status"
    mk_which.assert_called_once_with(fallback)
    mk_subprocess_run.assert_not_called()


@pytest.mark.parametrize(
    ("platform_name", "configured"),
    [key for key, resolved in SHELL_RESOLUTION.items() if resolved == key[1]],
)
def test_run_operation_does_not_search_the_path_for_a_shell_it_kept(
    platform_name: str, configured: str, mk_subprocess_run: MagicMock
) -> None:
    """The configured shell is not looked up again: initialization already located it on the PATH.

    The discriminating twin of the test above. Checking every shell would pass that test too, but it
    would search the PATH on every command for a fact established once at startup.
    """
    mk_subprocess_run.return_value = SimpleNamespace(stdout="", stderr="", returncode=0)

    with (
        patch("mega_snake.util.util.OS", platform_name),
        patch("mega_snake.util.util.get_property", return_value=configured),
        patch("mega_snake.util.util.shutil.which", return_value=None) as mk_which,
    ):
        run_operation("git status", "Probing the shell")

    mk_which.assert_not_called()
    assert mk_subprocess_run.call_args[0][0][0] == configured


def test_run_operation_resolves_the_shell_once_across_retries(mk_ws_warning: MagicMock, mk_subprocess_run: MagicMock) -> None:
    """Failing attempts are retried with the same shell, and the PATH is searched once, not per attempt."""
    failure = subprocess.CalledProcessError(returncode=1, cmd="git status", stderr="boom")
    mk_subprocess_run.side_effect = [failure, failure, SimpleNamespace(stdout="", stderr="", returncode=0)]

    with (
        patch("mega_snake.util.util.OS", "Linux"),
        patch("mega_snake.util.util.get_property", return_value="pwsh") as mk_property,
        patch("mega_snake.util.util.shutil.which", return_value="/bin/bash") as mk_which,
    ):
        run_operation("git status", "Probing the shell")

    assert [issued.args[0][0] for issued in mk_subprocess_run.call_args_list] == ["bash", "bash", "bash"]
    mk_which.assert_called_once_with("bash")
    mk_property.assert_called_once_with("shell")


def test_shell_resolution_contract_covers_every_configurable_shell_on_every_platform() -> None:
    """A shell added to SHELL_OPT must be given a row per platform, or the matrix above silently skips it."""
    from mega_snake.constants import SHELL_OPT

    expected_keys = {(platform_name, shell) for platform_name in SUPPORTED_PLATFORMS for shell in SHELL_OPT}
    assert set(SHELL_RESOLUTION) == expected_keys, (
        f"missing: {sorted(expected_keys - set(SHELL_RESOLUTION))}, "
        f"unexpected: {sorted(set(SHELL_RESOLUTION) - expected_keys)}"
    )


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


@pytest.mark.parametrize(
    ("helper_name", "target_name"),
    [("add_to_gitignore", "GITIGNORE_FILE"), ("exclude_from_git", "GIT_EXCLUDE_FILE")],
)
def test_appending_nothing_leaves_the_file_byte_identical(
    helper_name: str,
    target_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """A run where every entry is already listed must not rewrite the file at all.

    The fixture deliberately omits the final newline: with one present, rewriting and not rewriting
    produce identical bytes, so only an unterminated file distinguishes a real no-op from a
    read-modify-write that happens to reproduce the same content plus a normalized ending.
    """
    import mega_snake.util.util as util_module

    helper = getattr(util_module, helper_name)
    target = getattr(util_module, target_name)

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    file_path = tmp_path / target
    file_path.parent.mkdir(parents=True, exist_ok=True)
    before = ".github/skills/mgsnake/\n.claude/skills/mgsnake/"  # No trailing newline, on purpose.
    file_path.write_text(before, encoding="utf-8")

    helper(GITIGNORE_ENTRIES)

    after = file_path.read_text(encoding="utf-8")
    assert after == before, f"{target} was rewritten although every entry was already present"
    mk_util_ws_success.assert_not_called()
    assert mk_ws_advice.call_count == len(GITIGNORE_ENTRIES)


IGNORE_FILE_HELPERS = pytest.mark.parametrize(
    ("helper_name", "target_name"),
    [("add_to_gitignore", "GITIGNORE_FILE"), ("exclude_from_git", "GIT_EXCLUDE_FILE")],
)


def ignore_file_under_test(helper_name: str, target_name: str, root: Path, content: Optional[bytes]) -> tuple[Any, Path]:
    """Prepare a git repository holding the given ignore-file bytes, and return the helper and its file.

    Bytes rather than text on purpose: every assertion in these tests is about line endings, which a
    text-mode read or write would translate before the assertion could see them.

    Parameters:
        helper_name: The public helper to exercise, looked up on the util module.
        target_name: The util constant naming the file that helper writes.
        root: The directory to use as the repository root; the caller has already chdir'ed into it.
        content: The file's initial bytes, or None to leave it absent.

    Raises:
        None

    Returns:
        tuple[Any, Path]: The helper function, and the absolute path of the file it writes.
    """
    import mega_snake.util.util as util_module

    (root / ".git").mkdir(exist_ok=True)
    file_path = root / getattr(util_module, target_name)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        file_path.write_bytes(content)
    return getattr(util_module, helper_name), file_path


@IGNORE_FILE_HELPERS
def test_appending_keeps_every_existing_crlf_line_ending(
    helper_name: str,
    target_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """Adding one entry to a CRLF file changes only the new line, and the new line is CRLF too.

    Compared as exact bytes: a text-mode read-modify-write turns every `\\r\\n` into `\\n`, and a
    text comparison would translate both sides and pass. `.gitignore` is committed, so that rewrite
    is a whole-file diff for a one-line change. The negative half pins that no bare `\\n` slipped in,
    which is what appending with a hard-coded ending would produce -- a file with mixed endings.
    """
    monkeypatch.chdir(tmp_path)
    before = b"build/\r\nnode_modules/\r\n"
    helper, file_path = ignore_file_under_test(helper_name, target_name, tmp_path, before)

    helper([GITIGNORE_ENTRIES[0]])

    after = file_path.read_bytes()
    assert after == before + b".github/skills/mgsnake/\r\n", f"{target_name} came back as {after!r}"
    assert after.startswith(before), f"{target_name}: the pre-existing lines were rewritten"
    assert b"\n" not in after.replace(b"\r\n", b""), f"{target_name} ended up with mixed line endings"


@IGNORE_FILE_HELPERS
def test_appending_to_an_unterminated_crlf_file_separates_with_crlf(
    helper_name: str,
    target_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """The separator added before the first new entry follows the file's convention as well."""
    monkeypatch.chdir(tmp_path)
    helper, file_path = ignore_file_under_test(helper_name, target_name, tmp_path, b"build/\r\nnode_modules/")

    helper([GITIGNORE_ENTRIES[0]])

    assert file_path.read_bytes() == b"build/\r\nnode_modules/\r\n.github/skills/mgsnake/\r\n"


@IGNORE_FILE_HELPERS
def test_appending_to_an_lf_file_keeps_lf(
    helper_name: str,
    target_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """The discriminating twin of the CRLF test: an LF file must not be converted to CRLF."""
    monkeypatch.chdir(tmp_path)
    helper, file_path = ignore_file_under_test(helper_name, target_name, tmp_path, b"build/\n")

    helper([GITIGNORE_ENTRIES[0]])

    after = file_path.read_bytes()
    assert after == b"build/\n.github/skills/mgsnake/\n", f"{target_name} came back as {after!r}"
    assert b"\r" not in after, f"{target_name} gained a carriage return"


@IGNORE_FILE_HELPERS
def test_two_entries_naming_the_same_pattern_in_one_batch_are_written_once(
    helper_name: str,
    target_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mk_util_ws_success: MagicMock,
    mk_ws_advice: MagicMock,
) -> None:
    """`foo/` and `foo` in the same call are one pattern: the first is added, the second is present.

    Both are missing from the original file, which is exactly why a presence check run only against
    that file appended both. The descriptions differ so the messages show which one was written.
    """
    monkeypatch.chdir(tmp_path)
    helper, file_path = ignore_file_under_test(helper_name, target_name, tmp_path, None)

    helper([("foo/", "first declaration"), ("foo", "second declaration")])

    assert file_path.read_bytes() == b"foo/\n", f"{target_name} came back as {file_path.read_bytes()!r}"
    assert mk_util_ws_success.call_count == 1, "the duplicate was reported as added"
    assert "first declaration" in mk_util_ws_success.call_args[0][0]
    mk_ws_advice.assert_called_once()
    assert "second declaration" in mk_ws_advice.call_args[0][0], "the duplicate was not reported as present"


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


# ---------------------------------------------------------------------------
# get_validated_selection — the comma-separated multiple choice
# ---------------------------------------------------------------------------

# Deliberately distinguishable fixtures: three values that share no prefix, so a wrong entry can
# never be mistaken for a right one by a substring comparison, and none of them is the all key.
SELECTABLE = ["mgsnake", "jira-continue", "jira-progress"]


def test_get_validated_selection_accepts_a_single_entry(mk_input: MagicMock) -> None:
    """One value is a selection of one, returned as a list."""
    mk_input.return_value = "jira-continue"

    assert get_validated_selection("Pick:", SELECTABLE) == ["jira-continue"]


def test_get_validated_selection_splits_and_trims_a_comma_separated_answer(mk_input: MagicMock) -> None:
    """Entries are separated by commas and surrounding blanks are ignored.

    Order is asserted against the order typed, not against SELECTABLE: returning the declaration
    order would pass a containment check while silently ignoring what the user actually asked for.
    """
    mk_input.return_value = "  jira-progress ,mgsnake  "

    assert get_validated_selection("Pick:", SELECTABLE) == ["jira-progress", "mgsnake"]


def test_get_validated_selection_expands_the_all_key(mk_input: MagicMock) -> None:
    """'all' selects every value, and the result is the full list rather than the key itself."""
    mk_input.return_value = "all"

    result = get_validated_selection("Pick:", SELECTABLE)

    assert result == SELECTABLE
    assert "all" not in result, "the all key leaked into the selection"


def test_get_validated_selection_collapses_duplicates(mk_input: MagicMock) -> None:
    """A value named twice is selected once, so a caller cannot act on it twice."""
    mk_input.return_value = "mgsnake,jira-continue,mgsnake"

    assert get_validated_selection("Pick:", SELECTABLE) == ["mgsnake", "jira-continue"]


def test_get_validated_selection_matches_case_insensitively(mk_input: MagicMock) -> None:
    """Answers are lowercased before matching, and returned lowercased."""
    mk_input.return_value = "MGSNAKE"

    assert get_validated_selection("Pick:", SELECTABLE) == ["mgsnake"]


def test_get_validated_selection_rejects_the_whole_answer_for_one_unknown_entry(
    mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """One unrecognised entry rejects everything, and the retry returns the corrected answer.

    The discriminating case: the answer also carries two perfectly valid entries. An implementation
    that dropped the unknown one and kept the rest would return a selection the user never made,
    and the caller would report success for it.
    """
    mk_input.side_effect = ["mgsnake,typo,jira-continue", "mgsnake,jira-continue"]

    result = get_validated_selection("Pick:", SELECTABLE)

    assert result == ["mgsnake", "jira-continue"]
    assert mk_input.call_count == 2, "the invalid answer was not re-asked"
    mk_ws_warning.assert_called_once()


def test_get_validated_selection_rejects_an_empty_answer(mk_input: MagicMock, mk_ws_warning: MagicMock) -> None:
    """A blank answer is not "select nothing"; it is a missing answer and is re-asked."""
    mk_input.side_effect = ["   ", ",,", "mgsnake"]

    assert get_validated_selection("Pick:", SELECTABLE) == ["mgsnake"]
    assert mk_ws_warning.call_count == 2
    reasons = [issued.args[0].splitlines()[0] for issued in mk_ws_warning.call_args_list]
    assert reasons == ["No entry was given.", "No entry was given."], f"got {reasons}"


def test_get_validated_selection_gives_up_after_the_shared_retry_limit(
    mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """It stops after MAX_PROMPT_TRIES retries, like every other prompt in this module.

    The limit is read from the production constant rather than hard-coded, so raising it there does
    not leave this test asserting the old number.
    """
    mk_input.return_value = "not-a-skill"

    with pytest.raises(KeyError, match="Too many invalid selections"):
        get_validated_selection("Pick:", SELECTABLE)

    assert mk_input.call_count == MAX_PROMPT_TRIES + 1


def test_get_validated_selection_warns_naming_the_unknown_entries(
    mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """The warning's first line names exactly the entries that were not recognised, in typed order.

    The fixture mixes two unknown names around a valid one, so the assertion separates an
    implementation that names the culprits from one that repeats the whole answer (the valid name
    would appear) or names only the first (the second would be missing). Compared by equality over
    the first line, since the lines below it are the generic guidance every rejection repeats.
    """
    typos = ["jira-continu", "comment-kiler"]
    mk_input.side_effect = [f"{typos[0]}, mgsnake, {typos[1]}", "mgsnake"]

    get_validated_selection("Pick:", SELECTABLE)

    reason = mk_ws_warning.call_args[0][0].splitlines()[0]
    assert reason == f"Not recognised: {', '.join(repr(typo) for typo in typos)}.", f"got {reason!r}"
    assert "'mgsnake'" not in reason, "a valid entry was reported as unrecognised"


def test_get_validated_selection_warning_still_says_nothing_was_applied(
    mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """Below the reason, the warning keeps disclaiming a partial effect."""
    mk_input.side_effect = ["typo", "mgsnake"]

    get_validated_selection("Pick:", SELECTABLE)

    guidance = mk_ws_warning.call_args[0][0].splitlines()[1]
    assert guidance.startswith("Invalid selection; nothing has been applied."), f"got {guidance!r}"


@pytest.mark.parametrize("answer", ["all, typo", "typo, all", "ALL, typo"])
def test_get_validated_selection_rejects_an_unknown_entry_even_next_to_the_all_key(
    answer: str, mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """`all` must not short-circuit validation: an unknown entry beside it still rejects the answer.

    Checked in both positions and in upper case, because the defect was an ordering one -- the `all`
    shortcut ran before the unknown-entry check -- and a fix that only reorders for one position or
    one casing would pass a single-case test. Rejection is asserted by its effects: the answer is
    re-asked, the retry's result is what comes back, and the typo is named.
    """
    mk_input.side_effect = [answer, "mgsnake"]

    result = get_validated_selection("Pick:", SELECTABLE)

    assert result == ["mgsnake"], f"{answer!r} was accepted as {result}"
    assert result != SELECTABLE, f"{answer!r} selected the whole catalogue"
    assert mk_input.call_count == 2, f"{answer!r} was not re-asked"
    assert mk_ws_warning.call_args[0][0].splitlines()[0] == "Not recognised: 'typo'."


def test_get_validated_selection_accepts_the_all_key_next_to_valid_entries(mk_input: MagicMock) -> None:
    """Redundant but valid: `all` beside real names still selects everything, without a retry."""
    mk_input.return_value = "mgsnake, all"

    assert get_validated_selection("Pick:", SELECTABLE) == SELECTABLE
    assert mk_input.call_count == 1


def test_get_validated_input_warning_is_unchanged_by_the_rejection_reason(
    mk_input: MagicMock, mk_ws_warning: MagicMock
) -> None:
    """Only a helper that supplies a reason gets one: the single-value prompt keeps its exact warning."""
    mk_input.side_effect = ["nope", "b"]

    get_validated_input("Pick:", ["a", "b"])

    assert mk_ws_warning.call_args[0][0] == "Invalid input. Please enter one of:\n a | b"
