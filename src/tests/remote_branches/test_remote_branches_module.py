""" Tests for the remote_branches module. """

from types import SimpleNamespace
from unittest.mock import patch
import click
import pytest
from click.testing import CliRunner
from mega_snake.remote_branches import module
from mega_snake.util.util import require_remote, reset_remote_cache

def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main, ["--help"])
    assert result.exit_code == 0
    assert "remote branches related commands" in result.output


def test_wrapper_has_skip_flag() -> None:
    """The wrapper should be flagged for light-weight (skip) initialization, so a missing
    working path folder doesn't crash the CLI before the wrapper's own check can run."""
    assert module.wrapper.flags["flags"] == {"skip"}
    assert module.wrapper.flags["docs_group"] == "Git & Release Management"


def test_wrapper_delegates_to_the_shared_utilities() -> None:
    """The wrapper is only a pre-flight check: it resolves the remote and the working path through
    the shared utilities, so the commands it wraps reuse the cached remote instead of resolving
    (and prompting for) it a second time."""
    with patch("mega_snake.remote_branches.module.require_remote") as require_remote, patch(
        "mega_snake.remote_branches.module.ensure_working_path"
    ) as ensure_working_path, patch(
        "mega_snake.remote_branches.module.complete_app_properties"
    ) as complete_app_properties:
        module.wrapper(None)
    require_remote.assert_called_once_with()
    ensure_working_path.assert_called_once_with()
    # the log file only becomes possible once the working path is secured, never before
    complete_app_properties.assert_called_once_with()
    assert ensure_working_path.call_count == 1


def test_wrapper_fails_when_no_remote() -> None:
    """A repository without a remote fails with the shared friendly error before anything else."""
    with patch(
        "mega_snake.remote_branches.module.require_remote",
        side_effect=click.ClickException("No remote repository found."),
    ), patch("mega_snake.remote_branches.module.ensure_working_path") as ensure_working_path, patch(
        "mega_snake.remote_branches.module.complete_app_properties"
    ) as complete_app_properties:
        with pytest.raises(click.ClickException, match="No remote repository found"):
            module.wrapper(None)
    ensure_working_path.assert_not_called()
    complete_app_properties.assert_not_called()


def test_wrapper_fails_when_working_path_is_declined() -> None:
    """A missing working path the user declines to create surfaces as a clean ClickException."""
    with patch("mega_snake.remote_branches.module.require_remote"), patch(
        "mega_snake.remote_branches.module.ensure_working_path",
        side_effect=click.ClickException("Cannot continue without the 'workspace_temp' folder."),
    ), patch("mega_snake.remote_branches.module.complete_app_properties") as complete_app_properties:
        with pytest.raises(click.ClickException, match="Cannot continue without"):
            module.wrapper(None)
    complete_app_properties.assert_not_called()


def test_remote_is_resolved_once_across_wrapper_and_command() -> None:
    """End to end on the caching: the wrapper and the command it wraps share a single `git remote`
    resolution, so a repository with several remotes prompts the user only once."""
    reset_remote_cache()
    with patch("mega_snake.util.util.run_operation") as run_operation, patch(
        "mega_snake.util.util.get_validated_input", return_value="1"
    ) as get_validated_input:
        run_operation.return_value = SimpleNamespace(stdout="origin\nfork")
        with patch("mega_snake.remote_branches.module.ensure_working_path"), patch(
            "mega_snake.remote_branches.module.complete_app_properties"
        ):
            module.wrapper(None)
        assert require_remote() == "fork"  # what the wrapped command does right after
    run_operation.assert_called_once_with("git remote", "Getting remotes")
    get_validated_input.assert_called_once()
    reset_remote_cache()
