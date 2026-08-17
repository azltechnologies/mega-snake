"""Test the CliGroup class"""

from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock
from click.testing import CliRunner
import click
import pytest
from mega_snake.util.cli_group import ATTR_GROUP, CliGroup

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
    assert group.commands[name].callback == callback
    assert group.commands[alias].hidden is True
    assert group.commands[alias].params == params
    assert group.commands[alias].epilog == TEST_EPILOG
    assert group.commands[alias].callback == callback
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


def test_help_lists_commands_with_their_aliases() -> None:
    """Rendering help should list every public command together with its aliases.

    rich-click renders that alias column natively from the ``aliases`` attribute, which is why
    CliGroup no longer overrides ``format_commands``.
    """

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
    assert "moreCommands" in result.output
    assert "mc" in result.output
    assert set(clo.commands) == {*(cmd.name for cmd in cli.commands.values()), "moreCommands", "mc", "mC"}


def test_add_command_keeps_an_explicit_group_title_verbatim() -> None:
    """An explicitly declared docs group must never be reformatted, unlike a derived one."""

    @click.command(name="explicit", help="Explicit group")
    def explicit_command() -> None:
        """Command carrying an explicit group title."""

    @click.command(name="derived", help="Derived group")
    def derived_command() -> None:
        """Command without any group metadata."""

    setattr(explicit_command, ATTR_GROUP, "GraphQL & gRPC")
    group = CliGroup(name="root")
    group.add_command(explicit_command)
    group.add_command(derived_command)

    assert getattr(group.commands["explicit"], ATTR_GROUP) == "GraphQL & gRPC"
    # The derived title comes from the module path, so it is turned into a display title.
    derived_key: str = derived_command.callback.__module__.split(".")[-1]
    assert getattr(group.commands["derived"], ATTR_GROUP) == derived_key.replace("_", " ").title()


def make_command(name: str, docs_group: str) -> click.Command:
    """Build a command carrying an explicit documentation group.

    Parameters:
        name: The command name to register.
        docs_group: The documentation group reported as the command's origin.

    Raises:
        None

    Returns:
        click.Command: A command ready to be registered on a CliGroup.
    """

    @click.command(name=name, help=f"Command {name}")
    def command() -> None:
        """Command used to exercise duplicate registration."""

    setattr(command, ATTR_GROUP, docs_group)
    return command


def test_add_command_rejects_a_name_already_registered_by_another_group() -> None:
    """Registering a second command under a taken name must fail instead of shadowing the first.

    This is the exact failure that let a duplicated `scan-dependencies` implementation reach the
    repository: click's registry is a plain dict, so the later registration silently replaced the
    earlier one and the shadowed command became unreachable while its own tests kept passing.
    """
    group = CliGroup(name="root")
    first: click.Command = make_command("scan-dependencies", "Dependency Audit")
    second: click.Command = make_command("scan-dependencies", "Light Weight")
    group.add_command(first)

    with pytest.raises(click.UsageError) as excinfo:
        group.add_command(second)

    assert str(excinfo.value) == (
        "Command 'scan-dependencies' is already registered by 'Dependency Audit' "
        "and cannot be reused by 'Light Weight'. "
        "Rename one of them or drop the duplicate registration."
    )
    # The rejection must leave the registry untouched: the first command stays reachable...
    assert group.commands["scan-dependencies"] is first
    # ...and the second one is not registered under any name at all.
    assert second not in group.commands.values()


def test_add_command_rejects_a_duplicate_explicit_name_override() -> None:
    """The collision is detected on the resolved name, not on the command's own attribute.

    ``add_command(cmd, name)`` registers under ``name``, so a command whose own ``name`` differs
    must still be rejected when the override collides.
    """
    group = CliGroup(name="root")
    group.add_command(make_command("taken", "First Group"))

    with pytest.raises(click.UsageError) as excinfo:
        group.add_command(make_command("its-own-name", "Second Group"), "taken")

    assert str(excinfo.value) == (
        "Command 'taken' is already registered by 'First Group' and cannot be reused by 'Second Group'. "
        "Rename one of them or drop the duplicate registration."
    )
    assert "its-own-name" not in group.commands


@pytest.mark.parametrize(
    "existing_name, existing_aliases, colliding_alias",
    [
        pytest.param("alpha", None, "alpha", id="alias-shadows-a-command-name"),
        pytest.param("alpha", ["a"], "a", id="alias-shadows-another-alias"),
    ],
)
def test_add_command_with_alias_rejects_a_taken_alias(
    existing_name: str, existing_aliases: Any, colliding_alias: str
) -> None:
    """An alias must never shadow an existing command name or an alias already registered.

    Aliases are registered as separate hidden commands, so without this check they overwrite
    whatever occupies the name and silently reroute an existing command to a different callback.

    Parameters:
        existing_name: The name of the command registered first.
        existing_aliases: The aliases registered for that first command.
        colliding_alias: The alias the second command tries to claim.

    Raises:
        None

    Returns:
        None
    """
    group = CliGroup(name="root")
    group.add_command_with_alias(make_command(existing_name, "First Group"), existing_aliases)
    shadowed_callback: Callable = group.commands[colliding_alias].callback

    with pytest.raises(click.UsageError) as excinfo:
        group.add_command_with_alias(make_command("beta", "Second Group"), [colliding_alias])

    assert str(excinfo.value) == (
        f"Alias '{colliding_alias}' is already registered by 'First Group' "
        "and cannot be reused by 'Second Group'. "
        "Rename one of them or drop the duplicate registration."
    )
    # The occupied name must still resolve to the command that owned it.
    assert group.commands[colliding_alias].callback is shadowed_callback


def test_duplicate_registration_reports_the_module_when_no_group_is_declared() -> None:
    """Without an explicit docs group the message must still locate both commands, by module."""

    @click.command(name="clash", help="First clash")
    def first() -> None:
        """First command."""

    @click.command(name="clash", help="Second clash")
    def second() -> None:
        """Second command."""

    group = CliGroup(name="root")
    group.add_command(first)

    with pytest.raises(click.UsageError) as excinfo:
        group.add_command(second)

    derived: str = CliGroup._derive_group_name_from_callback(first.callback)  # pylint: disable=protected-access
    assert str(excinfo.value) == (
        f"Command 'clash' is already registered by '{derived}' and cannot be reused by '{derived}'. "
        "Rename one of them or drop the duplicate registration."
    )


def test_real_cli_registers_every_command_and_alias_exactly_once() -> None:
    """The shipped CLI must expose no shadowed command, across every registered module.

    Importing the entry point performs the whole registration, so a duplicate name introduced by any
    module now raises during import. This asserts the resulting registry matches the commands the
    modules actually declare, so a shadowed command cannot hide behind a passing import.
    """
    from mega_snake.__main__ import MODULES, cli as root_cli  # pylint: disable=import-outside-toplevel

    declared: list[str] = [name for group, _ in MODULES for name in group.commands]

    assert sorted(declared) == sorted(set(declared)), "a module declares the same name twice"
    assert sorted(root_cli.commands) == sorted(declared)
