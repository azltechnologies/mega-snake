"""Command group for documentation generation utilities."""

import click

from mega_snake.docs_gen.generate_docs import generate_docs
from mega_snake.docs_gen.install_agent_items import install_agent_items
from mega_snake.docs_gen.man_page import man
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.util import cli_metadata, wrapper_decorator


@click.group(cls=CliGroup)
def main() -> None:
    """Documentation generation related commands."""


@cli_metadata(docs_group="Documentation")
def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    """Wrapper for the docs_gen command group.

    Parameters:
        _ctx: The click context (unused).

    Raises:
        None

    Returns:
        None
    """


add_wrapper = wrapper_decorator(wrapper)

main.add_command(generate_docs)
main.add_command_with_alias(install_agent_items, ["generate-skill", "iai"])
main.add_command(man)
