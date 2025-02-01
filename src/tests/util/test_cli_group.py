"""Test the CliGroup class"""

from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock
from click.testing import CliRunner
import click
import pytest
from codename_snake.util.cli_group import CliGroup

ATTR_ALIAS = "aliases"
TEST_PARAMS = [MagicMock(name="param1"), MagicMock(name="param2")]
TEST_HELP = "help fot cmd1"
TEST_SHORT_HELP = "short_help for cmd1"
TEST_EPILOG = "epilog for cmd1"


@click.group(context_settings=dict(help_option_names=["-h", "--help"]), cls=CliGroup)
def cli() -> None:
    """My Excellent CLI"""


@cli.command()
def hello() -> None:
    """Says hello"""
    click.echo("Hello, World!")


@cli.command(name="do", aliases=["stuff", "things"], help=TEST_HELP, short_help=TEST_SHORT_HELP, epilog=TEST_EPILOG)
@click.argument("name")
@click.option("--times", "-t", default=1, help="Number of times to do the thing")
def my_command(name, times) -> None:
    """This is my command"""
    click.echo(f"Doing {name} {times} times.")


def test_command() -> None:
    """Test the command"""

    def my_other_command() -> None:
        """This is my other command"""
        click.echo("Doing other stuff.")

    my_other_command = click.argument("name")(my_other_command)
    my_other_command = click.option("--times", "-t", default=1, help="Number of times to do the thing")(my_other_command)
    cli.command(name="other", aliases=["otherstuff", "otherthings"], help=TEST_HELP, short_help=TEST_SHORT_HELP, epilog=TEST_EPILOG)(my_other_command)

    def my_wrong_command() -> None:
        """This is my wrong command"""
        click.echo("Doing wrong stuff.")

    assert len(cli.commands) == 7
    assert len(cli.commands["do"].params) == 2
    do_params = [cli.commands["do"].params[0], cli.commands["do"].params[1]]
    do_callback = cli.commands["do"].callback
    assert_add_command(cli, "do", "stuff", do_params, do_callback)
    assert_add_command(cli, "do", "things", do_params, do_callback)
    assert len(cli.commands["other"].params) == 2
    other_params = [cli.commands["other"].params[0], cli.commands["other"].params[1]]
    other_callback = cli.commands["other"].callback
    assert_add_command(cli, "other", "otherstuff", other_params, other_callback)
    assert_add_command(cli, "other", "otherthings", other_params, other_callback)
    with pytest.raises(click.UsageError):
        my_wrong_command = click.argument("name")(my_wrong_command)
        my_wrong_command = click.option("--times", "-t", default=1, help="Number of times to do the thing")(my_wrong_command)
        cli.command(aliases=["wrongstuff", "wrongthings"], help=TEST_HELP, short_help=TEST_SHORT_HELP, epilog=TEST_EPILOG)(my_wrong_command)


def call_back() -> int:
    """ " Test callback function"""
    return 1 + 1


def assert_add_command(group: CliGroup, name: str, alias: str, params: Any, callback: Callable) -> None:
    """Assert that the command was added"""
    assert name in group.commands
    assert alias in group.commands
    assert f"Alias for '{name}'." in group.commands[alias].help
    assert f"Alias for '{name}'." in group.commands[alias].short_help
    assert group.commands[name].help == TEST_HELP
    assert group.commands[name].short_help == TEST_SHORT_HELP
    assert group.commands[name].epilog == TEST_EPILOG
    assert group.commands[name].params == params
    assert group.commands[name].callback == callback  # pylint: disable=w0143
    assert group.commands[alias].hidden is True
    assert group.commands[alias].params == params
    assert group.commands[alias].epilog == TEST_EPILOG
    assert group.commands[alias].callback == callback  # pylint: disable=w0143
    assert group.commands[alias].name == alias
    assert group.commands[alias].params == group.commands[name].params
    assert group.commands[alias].epilog == group.commands[name].epilog
    assert group.commands[alias].callback == group.commands[name].callback


def test_add_command_with_alias() -> None:
    """Test the add_command_with_alias method"""
    name: str = "TEST_CMD_NAME"
    cmd = SimpleNamespace(name=name, callback=call_back, params=TEST_PARAMS, help=TEST_HELP, short_help=TEST_SHORT_HELP, epilog=TEST_EPILOG)
    group = CliGroup(cmd)
    group.add_command_with_alias(cmd, ["TEST_ALIAS"])
    assert_add_command(group, name, "TEST_ALIAS", TEST_PARAMS, call_back)


def test_add_command_with_alias_no_aliases() -> None:
    """Test the add_command_with_alias method with no aliases"""
    alias: str = "TEST_ALIAS"
    name: str = "TEST_CMD_NAME"
    cmd = SimpleNamespace(name=name, callback=call_back, params=TEST_PARAMS, help=TEST_HELP, short_help=TEST_SHORT_HELP, epilog=TEST_EPILOG)
    group = CliGroup(cmd)
    group.add_command_with_alias(cmd)
    assert name in group.commands
    assert len(group.commands) == 1
    group2 = CliGroup(cmd)
    group2.add_command_with_alias(cmd, alias)
    assert name in group2.commands
    assert alias not in group2.commands
    assert len(group2.commands) == 1


def test_format_commands() -> None:
    """Test format_commands"""

    @click.group(context_settings=dict(help_option_names=["-h", "--help"]), cls=CliGroup)
    def clo() -> None:
        """My Excellent CLO"""

    for cmd in cli.commands.values():
        clo.add_command_with_alias(cmd)

    @click.command(name="moreCommands", help="More commands")
    def more_commands() -> None:
        """More commands"""
        click.echo("More commands")

    clo.add_command_with_alias(more_commands, ["mc", "mC"])
    runner = CliRunner()
    result = runner.invoke(clo, ["--help"])
    assert result.exit_code == 0
    assert "My Excellent CLO" in result.output
    assert "More commands" in result.output
