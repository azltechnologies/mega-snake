"""Contains the persistent-state command group: everything under `mgsnake config`."""

import click

from mega_snake.state.config_cmd import config
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.util import cli_metadata, wrapper_decorator


@click.group(cls=CliGroup)
def main() -> None:
    """persistent state related commands"""


@cli_metadata(docs_group="Configuration")
def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    """Pre-flight check for the state commands.

    There is nothing to check. The store resolves its own paths lazily and depends on neither
    ``AppProperties`` nor a workspace, which is exactly what lets the whole group run with
    ``no_init`` and answer before the environment it configures exists. The wrapper is kept so the
    module registers like every other one and so ``docs_group`` reaches the command.

    Parameters:
        _ctx: The click context (unused).

    Raises:
        None

    Returns:
        None
    """


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


main.add_command(config)
