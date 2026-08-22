"""Tests for how the state module registers the nested `config` group."""

import click
from click.testing import CliRunner

from mega_snake import __main__ as app_main
from mega_snake.state import module
from mega_snake.util.cli_group import ATTR_GROUP, ATTR_METADATA, META_FLAGS

EXPECTED_SUBCOMMANDS = {"get", "set", "unset", "list", "export"}


def test_main_group() -> None:
    """The module exposes its own command group."""
    result = CliRunner().invoke(module.main, ["--help"])

    assert result.exit_code == 0
    assert "persistent state related commands" in result.output


def test_config_stays_a_group_after_wrapping() -> None:
    """The registered `config` is still a group and still has every subcommand.

    This is the whole reason `wrapper_decorator` had to learn about groups: a rebuild through
    `click.Command.__init__` drops `commands`, and the failure is invisible until someone runs
    `mgsnake config get`.
    """
    registered = app_main.cli.commands["config"]

    assert isinstance(registered, click.Group)
    assert set(registered.commands) == EXPECTED_SUBCOMMANDS


def test_config_is_registered_as_no_init() -> None:
    """`config get` and `config export` are read with command substitution, so the group is no_init."""
    registered = app_main.cli.commands["config"]

    assert getattr(registered.callback, ATTR_METADATA, {}).get(META_FLAGS) == {"no_init"}


def test_config_lands_in_the_configuration_documentation_group() -> None:
    """The module wrapper's docs_group must survive wrapping."""
    assert getattr(app_main.cli.commands["config"], ATTR_GROUP) == "Configuration"
