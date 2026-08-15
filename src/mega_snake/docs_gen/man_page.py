"""Command that paginates the command reference in the terminal, like a man page."""

import shutil
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown

from mega_snake.docs_gen.introspect import IntrospectedCommand, iter_introspected_commands
from mega_snake.docs_gen.markdown_writer import CELL_LINE_BREAK, render_markdown
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.util import cli_metadata

# Prose stops being readable well before a wide terminal ends, so the rendering width is capped
# rather than simply following the window.
MAX_PAGE_WIDTH = 100
# Width used when there is no terminal to measure (piped output, CI).
FALLBACK_PAGE_WIDTH = 80


def _page_width() -> int:
    """Resolve the rendering width for the paged document.

    Parameters:
        None

    Raises:
        None

    Returns:
        int: The terminal width, capped so long lines stay readable.
    """
    return min(shutil.get_terminal_size((FALLBACK_PAGE_WIDTH, 0)).columns, MAX_PAGE_WIDTH)


def _resolve_command_name(root: CliGroup, requested: str) -> str:
    """Map a command name or alias to the public command name.

    Aliases are the daily-use form throughout this CLI, so ``mgsnake man dt`` must work exactly like
    ``mgsnake man diff-tree``. The hidden alias commands cannot be used directly: they are separate
    click objects that the documentation iterator deliberately skips, so the alias is resolved back
    to the real command instead.

    Parameters:
        root: The top-level CLI group.
        requested: The command name or alias asked for on the command line.

    Raises:
        click.ClickException: If the name matches no command and no alias.

    Returns:
        str: The public command name.
    """
    known_names: dict[str, str] = {}
    for entry in root.iter_documented_commands():
        known_names[entry.name] = entry.name
        for alias in entry.aliases:
            known_names[alias] = entry.name
    if requested not in known_names:
        available: str = ", ".join(sorted(known_names))
        raise click.ClickException(f"Unknown command '{requested}'. Available commands and aliases: {available}")
    return known_names[requested]


def _render_for_terminal(commands: list[IntrospectedCommand]) -> str:
    """Render introspected commands as ANSI text suitable for a pager.

    The Markdown writer folds multi-line option help into ``<br>`` so it survives a Markdown table
    row. Rich drops HTML tags outright, which would glue the choice lists of ``--type-msg`` and
    ``--filter-by`` into one unreadable run, so they are folded back into spaces before rendering.

    ANSI is emitted unconditionally (``force_terminal``): Click strips it again when the pager
    cannot display color, so producing it here is safe and keeps the styling when it can.

    Parameters:
        commands: The introspected commands to render.

    Raises:
        None

    Returns:
        str: The rendered, ANSI-styled document.
    """
    markdown: str = render_markdown(commands).replace(CELL_LINE_BREAK, " ")
    console = Console(force_terminal=True, width=_page_width())
    with console.capture() as capture:
        console.print(Markdown(markdown))
    return capture.get()


@click.command(
    name="man",
    short_help="Page through the command reference in the terminal.",
    help="Renders the command reference in the terminal and pages it, showing the whole document or"
    " a single command when one is named. The content is built from the live CLI metadata and the"
    " packaged fragments, so it never depends on a generated file being present.",
    epilog="""
Args:\n
    command: Optional[str] - command name or alias to display. Defaults to the full reference.
""",
)
@cli_metadata(flags={"no_init"})
@click.argument("command_name", metavar="[COMMAND]", required=False, type=click.STRING)
def man(command_name: Optional[str]) -> None:
    """Page the command reference, optionally narrowed to a single command.

    The root group is imported lazily: it is the object being documented, and it imports this
    module to register the command, so a module-level import would be circular.

    Parameters:
        command_name: The command name or alias to display, or None for the full reference.

    Raises:
        click.ClickException: If the requested command matches no command and no alias.

    Returns:
        None
    """
    from mega_snake.__main__ import cli  # pylint: disable=C0415

    commands: list[IntrospectedCommand] = list(iter_introspected_commands(cli))
    if command_name:
        resolved: str = _resolve_command_name(cli, command_name)
        commands = [command for command in commands if command.name == resolved]
    click.echo_via_pager(_render_for_terminal(commands))
