"""Command that generates the Markdown command reference from the CLI metadata."""

from pathlib import Path

import click

from mega_snake.constants import DOCS_OUTPUT_FILE
from mega_snake.docs_gen.introspect import iter_introspected_commands
from mega_snake.docs_gen.markdown_writer import render_markdown, write_or_check_document
from mega_snake.util.util import cli_metadata


def render_command_reference() -> str:
    """Build the Markdown command reference from the live CLI metadata.

    This is the single composition of "walk the CLI" and "render it", shared by every command that
    publishes the reference (``generate-docs``, ``generate-skill``). It is public precisely because
    it crosses module boundaries: two documents rendered by two different pipelines would drift, and
    the whole point of the generated reference is that it cannot.

    The root group is imported lazily: it is the object being documented, and it imports this
    module to register the command, so a module-level import would be circular.

    Parameters:
        None

    Raises:
        None

    Returns:
        str: The fully rendered Markdown command reference.
    """
    from mega_snake.__main__ import cli

    return render_markdown(iter_introspected_commands(cli))


@click.command(
    name="generate-docs",
    short_help="Generate the Markdown command reference from CLI metadata and fragments.",
    help="Generates the Markdown command reference by introspecting the registered CLI commands,"
    " rendering their help and options, and appending the command-specific fragment bodies.",
)
@cli_metadata(flags={"no_init"})
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path(DOCS_OUTPUT_FILE),
    show_default=True,
    help="Write the generated command reference to this file.",
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Render in memory, compare with the output file, and exit with an error when it is stale.",
)
def generate_docs(output: Path, check: bool) -> None:
    """Generate or validate the Markdown command reference.

    Parameters:
        output: The target Markdown file path.
        check: Whether to validate the file instead of writing it.

    Raises:
        ValidationError: If --check finds that the output file is stale.

    Returns:
        None
    """
    markdown: str = render_command_reference()
    write_or_check_document(output, markdown, check)
    if not check:
        click.echo(f"Generated {output}")
