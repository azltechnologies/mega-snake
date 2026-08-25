"""Test cases for formatting.py"""

import logging
from unittest.mock import MagicMock, patch
from typing import Generator, Callable
from types import SimpleNamespace
import pytest
from mega_snake.util.formatting import (
    logger as formatting_logger,
    ErrorFilter,
    DefaultFilter,
    config_log,
    get_traceback,
    ws_success,
    ws_info,
    ws_warning,
    ws_advice,
    ws_tip,
    ws_error,
    WorkspaceError,
    Color,
    _on_crash as on_crash,
    ERROR_CODES,
)


@pytest.fixture(name="mk_file_handler")
def fixture_mk_file_handler() -> Generator[Callable, None, None]:
    """Mock FileHandler"""
    with patch("logging.FileHandler") as mock_file_handler:
        yield mock_file_handler


@pytest.fixture(name="mk_logger")
def fixture_mk_logger() -> Generator[Callable, None, None]:
    """Mock logger"""
    with patch("mega_snake.util.formatting.logger") as mk_logger:
        yield mk_logger


@pytest.fixture(name="mk_error")
def fixture_mk_error() -> Generator[Callable, None, None]:
    """Mock logger"""
    with patch("mega_snake.util.formatting.logger.error") as mk_error:
        yield mk_error


@pytest.fixture(name="mk_old_hook")
def fixture_mk_old_hook() -> Generator[Callable, None, None]:
    """Mock old exception hook"""
    with patch("mega_snake.util.formatting.old_hook") as old_hook:
        yield old_hook


@pytest.fixture(name="mk_sys_exit")
def fixture_mk_sys_exit() -> Generator[Callable, None, None]:
    """Mock sys.exit"""
    with patch("mega_snake.util.formatting.sys.exit") as mock_exit:
        yield mock_exit


def test_on_crash(mk_old_hook: MagicMock, mk_sys_exit: MagicMock) -> None:
    """Test _on_crash function"""

    # Simulate an exception
    try:
        raise ValueError("Test crash")
    except ValueError as e:
        on_crash(type(e), e, e.__traceback__)
        mk_old_hook.assert_called_once()
        mk_sys_exit.assert_not_called()
        mk_old_hook.reset_mock()

    # Test with WorkspaceError
    try:
        raise ValueError("Test crash")
    except ValueError as e:
        try:
            raise WorkspaceError("Workspace error", e) from e
        except WorkspaceError as ws_err:
            mk_sys_exit.side_effect = IOError("Simulated sys.exit crash")
            expected_error_code = ERROR_CODES[ValueError]
            with pytest.raises(IOError, match="Simulated sys.exit crash"):
                on_crash(type(ws_err), ws_err, ws_err.__traceback__)
            mk_old_hook.assert_not_called()
            mk_sys_exit.assert_called_once_with(expected_error_code)
            assert ws_err.error_code == expected_error_code


def test_error_filter() -> None:
    """Test ErrorFilter class"""
    error_filter = ErrorFilter()
    record = SimpleNamespace(levelno=40, msg="Test error message", name="test_logger")
    assert error_filter.filter(record) is True  # Should pass through since levelno is ERROR

    record.levelno = 30  # Change to WARNING
    assert error_filter.filter(record) is False  # Should not pass through since levelno is not ERROR


def test_default_filter() -> None:
    """Test DefaultFilter class"""
    default_filter = DefaultFilter()
    record = SimpleNamespace(levelno=20, msg="Test info message", name="test_logger")
    assert default_filter.filter(record) is True  # Should pass through since levelno is INFO

    record.levelno = 50  # Change to CRITICAL
    assert default_filter.filter(record) is False  # Should not pass through since levelno is not < ERROR


def test_config_log(mk_file_handler: MagicMock) -> None:
    """Test config_log function"""
    log_path = "test.log"
    log_level = "DEBUG"
    default_handler = MagicMock()
    error_handler = MagicMock()
    mk_file_handler.side_effect = [default_handler, error_handler]

    config_log(log_path, log_level)
    mk_file_handler.assert_called_with(log_path, encoding="utf-8", delay=True)
    assert mk_file_handler.call_count == 2  # Two handlers should be created
    default_handler.setLevel.assert_called_with(logging.DEBUG)
    error_handler.setLevel.assert_called_with(logging.ERROR)
    default_handler.setFormatter.assert_called_once()
    error_handler.setFormatter.assert_called_once()
    default_handler.addFilter.assert_called_once()
    error_handler.addFilter.assert_called_once()


def test_config_log_replaces_handlers_instead_of_stacking_them(mk_file_handler: MagicMock) -> None:
    """Reconfiguring logging must not leave the previous handlers attached.

    A properties reload calls config_log again; if the old handlers stayed, every record would be
    written twice to the same file from that point on.
    """
    original_handlers = list(formatting_logger.handlers)
    original_level = formatting_logger.level
    try:
        formatting_logger.handlers.clear()
        mk_file_handler.side_effect = [MagicMock() for _ in range(4)]

        config_log("first.log", logging.INFO)
        first_handlers = list(formatting_logger.handlers)
        assert len(first_handlers) == 2

        config_log("second.log", logging.DEBUG)
        assert len(formatting_logger.handlers) == 2
        assert all(handler not in first_handlers for handler in formatting_logger.handlers)
        # the replaced handlers are closed, so their file descriptors are not leaked
        for handler in first_handlers:
            handler.close.assert_called_once()
        assert formatting_logger.level == logging.DEBUG
    finally:
        formatting_logger.handlers.clear()
        formatting_logger.handlers.extend(original_handlers)
        formatting_logger.setLevel(original_level)


def test_get_traceback() -> None:
    """Test get_traceback function"""
    exception = Exception("Test exception")
    with patch("traceback.format_exception") as mock_format_exception:
        mock_format_exception.return_value = [
            '"Dummy.py", line 29. Traceback (most recent call last):\n',
            "Exception: Test exception\n",
        ]
        result = get_traceback(exception)
        assert result == '"Dummy.py:29". Traceback (most recent call last):\nException: Test exception\n'
        mock_format_exception.assert_called_once_with(type(exception), exception, exception.__traceback__)


def test_ws_success(mk_logger: MagicMock) -> None:
    """Test ws_success function"""
    ws_success("Test success message")
    mk_logger.info.assert_called_once_with("Test success message", stacklevel=2)


def test_ws_info(mk_logger: MagicMock) -> None:
    """Test ws_info function"""
    ws_info("Test info message")
    mk_logger.info.assert_called_once_with("Test info message", stacklevel=2)


def test_ws_warning(mk_logger: MagicMock) -> None:
    """Test ws_warning function"""
    ws_warning("Test warning message")
    mk_logger.warning.assert_called_once_with("Test warning message", stacklevel=2)


def test_ws_advice(mk_logger: MagicMock) -> None:
    """Test ws_advice function"""
    mk_logger.level = logging.DEBUG
    ws_advice("Test advice message")
    mk_logger.debug.assert_called_once_with("Test advice message", stacklevel=2)


def test_ws_advice_writes_to_stderr_only(mk_logger: MagicMock, capsys: pytest.CaptureFixture) -> None:
    """ws_advice must keep stdout clean so captured command output stays parseable."""
    mk_logger.level = logging.DEBUG

    ws_advice("Test advice message")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Test advice message" in captured.err


def test_ws_advice_forced_writes_to_stderr_only(mk_logger: MagicMock, capsys: pytest.CaptureFixture) -> None:
    """The `force` path must respect the same stdout/stderr split."""
    mk_logger.level = logging.INFO

    ws_advice("Forced advice message", force=True)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Forced advice message" in captured.err


@pytest.mark.parametrize(
    "force, expected_level, dropped_level",
    [
        pytest.param(True, "info", "debug", id="forced"),
        pytest.param(False, "debug", "info", id="not_forced"),
    ],
)
def test_ws_advice_logs_a_forced_message_above_the_default_threshold(
    force: bool, expected_level: str, dropped_level: str, mk_logger: MagicMock
) -> None:
    """A forced advice must reach the log file at the default level, an ordinary one must not.

    `force` gates the console print only. Logging a forced message at DEBUG left it invisible in the
    log file unless the whole run was at `--log-level DEBUG`, so the on-screen line and the
    persistent record disagreed. The negative half is what pins the pair: asserting only that INFO
    was called would also pass if the helper logged at both levels.
    """
    mk_logger.level = logging.DEBUG if not force else logging.INFO

    ws_advice("Advice message", force=force)

    getattr(mk_logger, expected_level).assert_called_once_with("Advice message", stacklevel=2)
    getattr(mk_logger, dropped_level).assert_not_called()


@pytest.mark.parametrize(
    "helper",
    [
        pytest.param(ws_success, id="ws_success"),
        pytest.param(ws_info, id="ws_info"),
        pytest.param(ws_warning, id="ws_warning"),
        pytest.param(ws_error, id="ws_error"),
        pytest.param(lambda message: ws_tip({Color.GREEN: message}), id="ws_tip"),
    ],
)
def test_every_ws_helper_writes_to_stderr_only(
    helper: Callable[[str], None], mk_logger: MagicMock, capsys: pytest.CaptureFixture
) -> None:
    """No ws_* helper may write to stdout, so a command can emit a value there safely.

    Checked over the whole family rather than one example: the rule is what makes stdout usable as
    a data channel, and a single helper leaking is enough to break every caller that captures it
    with `$(...)`. Asserting stdout is exactly empty (not merely "the message is in stderr") is the
    half that fails when a helper prints to both streams.
    """
    mk_logger.level = logging.DEBUG

    helper("A message on the wrong stream")

    captured = capsys.readouterr()
    assert captured.out == "", f"{captured.out!r} reached stdout; ws_* helpers must use stderr only"
    assert "A message on the wrong stream" in captured.err


def test_ws_tip(mk_logger: MagicMock) -> None:
    """Test ws_tip function"""
    msg_blue = "Test tip message"
    msg_yellow = "with a color"
    message = {Color.BLUE: msg_blue, Color.YELLOW: msg_yellow}
    ws_tip(message)
    mk_logger.info.assert_called_once()
    logged_message = mk_logger.info.call_args[0][0]
    assert msg_blue in logged_message
    assert msg_yellow in logged_message


def test_ws_error(mk_logger: MagicMock) -> None:
    """Test ws_error function"""
    err_msg = "Test error message"
    mk_error = mk_logger.error

    # Test with no error message
    ws_error("")
    mk_error.assert_called_once()
    args, kwargs = mk_error.call_args
    assert "unknown error" in args[0]
    extra = kwargs.get("extra", {})
    assert extra.get("func") == "unknown function"
    assert extra.get("line") == 0
    assert extra.get("namefile") == "unknown file"
    mk_error.reset_mock()

    # Test with a simple error message
    ws_error(err_msg)
    mk_error.assert_called_once()
    args, kwargs = mk_error.call_args
    assert err_msg in args[0]
    extra = kwargs.get("extra", {})
    assert extra.get("func") == "unknown function"
    assert extra.get("line") == 0
    assert extra.get("namefile") == "unknown file"
    mk_error.reset_mock()

    # Test with an exception
    try:
        raise ValueError("Dummy exception")
    except ValueError as e:
        ws_error(err_msg, e)
        mk_error.assert_called_once()
        args, kwargs = mk_error.call_args
        assert err_msg in args[0]
        extra = kwargs.get("extra", {})
        assert extra.get("func") == "unknown function"
        assert extra.get("line") == 0
        assert extra.get("namefile") == "unknown file"


def test_workspace_error(mk_error: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
    """Test WorkspaceError class"""
    value_error_message = "This is a value error"
    workspace_error_message = "This is a workspace error"

    # Test WorkspaceError with no message
    try:
        raise ValueError(value_error_message)
    except ValueError as val_err:
        try:
            raise WorkspaceError(workspace_error_message, val_err) from val_err
        except WorkspaceError:
            mk_error.assert_called_once()
            args, kwargs = mk_error.call_args
            assert value_error_message in args[0]
            extra = kwargs.get("extra", {})
            assert extra.get("func") == "unknown function"
            assert extra.get("line") == 0
            assert extra.get("namefile") == "unknown file"
    mk_error.reset_mock()

    # Test WorkspaceError with a simple message
    try:
        raise ValueError(value_error_message)
    except ValueError as val_err:
        try:
            raise WorkspaceError(workspace_error_message, val_err) from val_err
        except WorkspaceError:
            mk_error.assert_called_once()
            args, kwargs = mk_error.call_args
            assert value_error_message in args[0]
            extra = kwargs.get("extra", {})
            assert extra.get("func") == "unknown function"
            assert extra.get("line") == 0
            assert extra.get("namefile") == "unknown file"
    mk_error.reset_mock()

    # Test when logs are set up
    # with patch("mega_snake.util.formatting.logging") as mock_file_handler:
    # An absolute path under tmp_path: `config_log` resolves a relative name against the current
    # working directory, which during a test run is the repository root -- so the previous
    # relative name wrote an untracked `workspace_error_file.log` there on every `pytest`.
    config_log(str(tmp_path / "workspace_error_file.log"), logging.INFO)
    try:
        raise ValueError(value_error_message)
    except ValueError as val_err:
        try:
            raise WorkspaceError(workspace_error_message, val_err) from val_err
        except WorkspaceError:
            mk_error.assert_called_once()
            args, kwargs = mk_error.call_args
            assert value_error_message in args[0]
            extra = kwargs.get("extra", {})
            assert extra.get("func") == "test_workspace_error"
            assert extra.get("line") > 0
            assert extra.get("namefile") == "test_formatting.py"
