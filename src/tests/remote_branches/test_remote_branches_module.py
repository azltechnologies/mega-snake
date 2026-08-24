""" Tests for the remote_branches module. """

from unittest.mock import patch
import click
import pytest
from click.testing import CliRunner
from mega_snake.remote_branches import module
from mega_snake.util.repo import Repo
from mega_snake.util.cli_group import ATTR_METADATA

def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main, ["--help"])
    assert result.exit_code == 0
    assert "remote branches related commands" in result.output


def test_wrapper_has_skip_flag() -> None:
    """The wrapper should be flagged for light-weight (skip) initialization, so a missing
    working path folder doesn't crash the CLI before the wrapper's own check can run."""
    assert getattr(module.wrapper, ATTR_METADATA)["flags"] == {"skip"}
    assert getattr(module.wrapper, ATTR_METADATA)["docs_group"] == "Git & Release Management"


def test_wrapper_delegates_to_the_shared_utilities() -> None:
    """The wrapper is only a pre-flight check: it secures the working path and then finishes the
    initialization light-weight mode deferred, in that order."""
    with patch("mega_snake.remote_branches.module.ensure_working_path") as ensure_working_path, patch(
        "mega_snake.remote_branches.module.complete_app_properties"
    ) as complete_app_properties:
        module.wrapper(None)
    ensure_working_path.assert_called_once_with()
    # the log file only becomes possible once the working path is secured, never before
    complete_app_properties.assert_called_once_with()


def test_wrapper_does_not_require_a_remote() -> None:
    """A repository without a remote is now supported: the Repo snapshot asks for the main branch
    instead. The wrapper must therefore neither resolve nor demand a remote, which would reject the
    repository before the command ever runs."""
    Repo.reset()
    with patch("mega_snake.util.repo.run_operation") as run_operation, patch(
        "mega_snake.remote_branches.module.ensure_working_path"
    ), patch("mega_snake.remote_branches.module.complete_app_properties"):
        module.wrapper(None)
    run_operation.assert_not_called()
    Repo.reset()


def test_wrapper_fails_when_working_path_is_declined() -> None:
    """A missing working path the user declines to create surfaces as a clean ClickException, and
    the deferred initialization is never completed on top of a folder that does not exist."""
    with patch(
        "mega_snake.remote_branches.module.ensure_working_path",
        side_effect=click.ClickException("Cannot continue without the 'workspace_temp' folder."),
    ), patch("mega_snake.remote_branches.module.complete_app_properties") as complete_app_properties:
        with pytest.raises(click.ClickException, match="Cannot continue without"):
            module.wrapper(None)
    complete_app_properties.assert_not_called()
