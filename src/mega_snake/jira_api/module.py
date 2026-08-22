"""Contains the Jira command group: board, sprint and issue extraction for Jira Cloud."""

import click

from mega_snake.jira_api.board import jira_board
from mega_snake.jira_api.issues import jira_issues
from mega_snake.jira_api.sprint import jira_sprint
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.util import cli_metadata, wrapper_decorator


@click.group(cls=CliGroup)
def main() -> None:
    """jira related commands"""


@cli_metadata(docs_group="Jira")
def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    """Pre-flight check for the jira commands.

    Deliberately empty. This module mixes initialization levels: ``jira-board`` and ``jira-sprint``
    are ``no_init`` (their stdout is a machine contract read with ``$(...)``, so they must answer
    before the environment exists and must never print anything else), while ``jira-issues`` is
    ``skip`` because it writes to the working path. A module wrapper runs for every command in the
    module, so any pre-flight here would run for the two commands that must not have one --
    ``jira-issues`` secures the working path in its own body instead.

    What the wrapper still does is carry ``docs_group`` onto every command, and let each command
    declare its own initialization flags through ``@cli_metadata``: ``wrapper_decorator`` merges the
    module's metadata first and the command callback's second, so the per-command flags win.

    Parameters:
        _ctx: The click context (unused).

    Raises:
        None

    Returns:
        None
    """


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


main.add_command_with_alias(jira_board, ["jb"])
main.add_command_with_alias(jira_sprint, ["js"])
main.add_command_with_alias(jira_issues, ["ji"])
