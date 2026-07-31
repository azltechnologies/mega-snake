""" Tests for the remote_branches module. """

from unittest.mock import patch
import click
import pytest
from click.testing import CliRunner
from mega_snake.remote_branches import module

def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main, ["--help"])
    assert result.exit_code == 0
    assert "remote branches related commands" in result.output


def test_wrapper_has_skip_flag() -> None:
    """The wrapper should be flagged for light-weight (skip) initialization, so a missing
    working path folder doesn't crash the CLI before the wrapper's own check can run."""
    assert module.wrapper.flags == {"flags": {"skip"}}


def test_wrapper_raises_when_no_remote() -> None:
    """The wrapper should raise a LookupError when there is no configured git remote."""
    with patch("mega_snake.remote_branches.module.get_remote", return_value=None):
        with pytest.raises(LookupError, match="No remote repository found"):
            module.wrapper(None)


def test_wrapper_is_noop_when_working_path_exists() -> None:
    """The wrapper should not prompt or touch the filesystem when the folder already exists."""
    with patch("mega_snake.remote_branches.module.get_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.module.get_property", return_value="/tmp/workspace_temp"
    ), patch("mega_snake.remote_branches.module.os.path.exists", return_value=True) as exists, patch(
        "mega_snake.remote_branches.module.os.makedirs"
    ) as makedirs, patch("mega_snake.remote_branches.module.get_validated_input") as get_validated_input:
        module.wrapper(None)
    exists.assert_called_once_with("/tmp/workspace_temp")
    makedirs.assert_not_called()
    get_validated_input.assert_not_called()


def test_wrapper_creates_working_path_when_user_confirms() -> None:
    """The wrapper should create the missing working path folder when the user agrees to."""
    with patch("mega_snake.remote_branches.module.get_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.module.get_property", return_value="/tmp/workspace_temp"
    ), patch("mega_snake.remote_branches.module.os.path.exists", return_value=False), patch(
        "mega_snake.remote_branches.module.os.makedirs"
    ) as makedirs, patch(
        "mega_snake.remote_branches.module.get_validated_input", return_value="y"
    ) as get_validated_input, patch(
        "mega_snake.remote_branches.module.ws_success"
    ) as ws_success:
        module.wrapper(None)
    get_validated_input.assert_called_once()
    makedirs.assert_called_once_with("/tmp/workspace_temp")
    ws_success.assert_called_once()


def test_wrapper_raises_clean_error_when_user_declines() -> None:
    """The wrapper should raise a friendly ClickException, not a raw FileNotFoundError, when the
    user declines to create the missing working path folder."""
    with patch("mega_snake.remote_branches.module.get_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.module.get_property", return_value="/tmp/workspace_temp"
    ), patch("mega_snake.remote_branches.module.os.path.exists", return_value=False), patch(
        "mega_snake.remote_branches.module.os.makedirs"
    ) as makedirs, patch("mega_snake.remote_branches.module.get_validated_input", return_value="n"):
        with pytest.raises(click.ClickException, match="Cannot run this command"):
            module.wrapper(None)
    makedirs.assert_not_called()
