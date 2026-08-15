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
# Size used when there is no terminal to measure (piped output, CI). Only the width is read; the
# height is shutil's own documented default.
FALLBACK_TERMINAL_SIZE = (80, 24)
# A Markdown table row is the only place the writer emits CELL_LINE_BREAK, and it always starts here.
TABLE_ROW_PREFIX = "|"


def _page_width() -> int:
    """Resolve the rendering width for the paged document.

    Parameters:
        None

    Raises:
        None

    Returns:
        int: The terminal width, capped so long lines stay readable.
    """
    return min(shutil.get_terminal_size(FALLBACK_TERMINAL_SIZE).columns, MAX_PAGE_WIDTH)


def _fold_table_line_breaks(markdown: str) -> str:
    """Turn the table-only ``<br>`` markers back into spaces.

    The Markdown writer folds multi-line option help into ``CELL_LINE_BREAK`` so it survives a table
    row. Rich drops HTML tags outright, which would glue the choice lists of ``--type-msg`` and
    ``--filter-by`` into one unreadable run, so they are folded into spaces before rendering.

    Only table rows are rewritten. A document-wide replacement would also rewrite a literal ``<br>``
    written by a human in fragment prose or inside a fenced code block, where it is content rather
    than a table artifact.

    Parameters:
        markdown: The rendered Markdown document.

    Raises:
        None

    Returns:
        str: The document with table cell breaks folded into spaces.
    """
    return "\n".join(
        line.replace(CELL_LINE_BREAK, " ") if line.startswith(TABLE_ROW_PREFIX) else line
        for line in markdown.splitlines()
    )


def _resolve_command_name(root: CliGroup, requested: str) -> str:
    """Map a command name or alias to the public command name.

    Aliases are the daily-use form throughout this CLI, so ``mgsnake man dt`` must work exactly like
    ``mgsnake man diff-tree``. The hidden alias commands cannot be used directly: they are separate
    click objects that the documentation iterator deliberately skips, so the alias is resolved back
    to the real command instead.

    Real names are seeded first and aliases only fill the gaps, so a command is always reachable by
    its own name. Sharing one lookup without that precedence would let an alias registered by a
    later command shadow an earlier command's real name -- and several current aliases (``audit``,
    ``release``, ``env``, ``tree``) are plausible names for a future command, which would silently
    page the wrong entry.

    Parameters:
        root: The top-level CLI group.
        requested: The command name or alias asked for on the command line.

    Raises:
        click.ClickException: If the name matches no command and no alias.

    Returns:
        str: The public command name.
    """
    entries = list(root.iter_documented_commands())
    known_names: dict[str, str] = {entry.name: entry.name for entry in entries}
    for entry in entries:
        for alias in entry.aliases:
            known_names.setdefault(alias, entry.name)
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
    console = Console(force_terminal=True, width=_page_width())
    with console.capture() as capture:
        console.print(Markdown(_fold_table_line_breaks(render_markdown(commands))))
    return capture.get()


def _page_or_echo(text: str) -> None:
    """Page the document, falling back to plain output when the pager cannot accept it.

    ``click.echo_via_pager`` is broken on the interactive Windows path of click 8.4.x, which is
    exactly the PowerShell case this command exists to serve. ``_pager_contextmanager`` selects
    ``_tempfilepager`` there, which yields a binary ``NamedTemporaryFile``; ``get_pager_file`` only
    wraps a stream when it exposes a ``.buffer``, so the raw binary handle reaches
    ``echo_via_pager``, which writes ``str`` to it and raises ``TypeError``. There is no fixed click
    release to upgrade to (8.4.2 is the latest), and pinning backwards would drop below what
    rich-click resolves.

    ``UnicodeEncodeError`` is caught for the same platform: that path encodes with the console
    encoding, and the box-drawing characters rich uses for tables are not representable in legacy
    code pages such as ``cp1252``.

    Only these two are caught. Any other failure is a real error and must surface.

    Parameters:
        text: The rendered document to display.

    Raises:
        None

    Returns:
        None
    """
    try:
        click.echo_via_pager(text)
    except (TypeError, UnicodeEncodeError):
        click.echo(text)


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
    _page_or_echo(_render_for_terminal(commands))
