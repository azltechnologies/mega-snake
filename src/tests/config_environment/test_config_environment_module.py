""" Test the config_environment module """

from types import SimpleNamespace
from click.testing import CliRunner
from codename_snake.config_environment import module


def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main)
    assert result.exit_code == 0
    assert "Configuration related commands" in result.output


def test_wrapper() -> None:
    """Test the wrapper function"""
    ctx = SimpleNamespace(obj={})
    module.wrapper(ctx)
    assert ctx.obj.get("exit_code", 0) == 21
