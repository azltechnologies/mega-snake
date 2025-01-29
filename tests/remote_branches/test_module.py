""" Tests for the remote_branches module. """

from click.testing import CliRunner
import codename_snake.remote_branches.module as module


def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main)
    assert result.exit_code == 0
    assert "remote branches related commands" in result.output
