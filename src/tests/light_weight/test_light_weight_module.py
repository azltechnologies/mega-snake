""" Test the module.py file in the light_weight directory """

from click.testing import CliRunner
from mega_snake.light_weight import module

def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main)
    assert result.exit_code == 0
    assert "light weight related commands" in result.output
