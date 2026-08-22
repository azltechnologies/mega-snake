"""Tests for how the Jira module registers its commands and their initialization flags."""

from click.testing import CliRunner
import pytest

from mega_snake import __main__ as app_main
from mega_snake.jira_api import module
from mega_snake.util.cli_group import ATTR_GROUP, ATTR_METADATA, META_FLAGS


def test_main_group() -> None:
    """The module exposes its own command group."""
    result = CliRunner().invoke(module.main, ["--help"])

    assert result.exit_code == 0
    assert "jira related commands" in result.output


@pytest.mark.parametrize(
    ("command_name", "expected_flags"),
    [
        ("jira-board", {"no_init"}),
        ("jira-sprint", {"no_init"}),
        ("jira-issues", {"skip"}),
        ("jb", {"no_init"}),
        ("js", {"no_init"}),
        ("ji", {"skip"}),
    ],
)
def test_each_command_keeps_its_own_initialization_flags(command_name: str, expected_flags: set[str]) -> None:
    """This module mixes `no_init` and `skip`, which only works if per-command flags survive wrapping.

    `wrapper_decorator` merges the module wrapper's metadata first and the command callback's
    second, so the command wins. Aliases are checked too: they are separate click objects built from
    the same callback, and the CLI entry point reads the flags off whichever object it resolved.
    """
    command = app_main.cli.commands[command_name]

    assert getattr(command.callback, ATTR_METADATA, {}).get(META_FLAGS) == expected_flags


@pytest.mark.parametrize("command_name", ["jira-board", "jira-sprint", "jira-issues"])
def test_the_module_group_title_reaches_every_command(command_name: str) -> None:
    """The module wrapper carries docs_group even though it carries no flags."""
    assert getattr(app_main.cli.commands[command_name], ATTR_GROUP) == "Jira"


@pytest.mark.parametrize("command_name", ["jira-board", "jira-sprint", "jira-issues"])
def test_commands_are_registered_on_the_root_cli(command_name: str) -> None:
    """Registration goes through the standard MODULES loop, like every other module."""
    assert command_name in app_main.cli.commands
