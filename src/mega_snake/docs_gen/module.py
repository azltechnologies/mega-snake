"""Command group for documentation generation utilities."""

import click

from mega_snake.docs_gen.markdown_writer import generate_docs
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
