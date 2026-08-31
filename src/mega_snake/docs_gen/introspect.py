"""Normalize CLI metadata into documentation-friendly dataclasses."""

from dataclasses import dataclass
from pathlib import Path
import re
import textwrap
from typing import Iterator, Optional

import click

from mega_snake.constants import APP_NAME
from mega_snake.util.cli_group import CliGroup

# Epilog paragraphs the generator already emits elsewhere: the usage line becomes the synopsis and
# the option entries become the options table, so republishing them would duplicate the reference.
EPILOG_USAGE_PREFIX = "usage:"
EPILOG_SECTION_HEADERS = frozenset({"options", "args", "arguments", "allowed values"})

# Width Click is asked to fit a short help into. Generous on purpose: the value is consumed by a
# Markdown table cell, not by an 80-column terminal, so truncating to the terminal default would
# discard wording the author wrote for the command list.
SHORT_HELP_LIMIT = 120


@dataclass(frozen=True)
class CommandOptionDoc:
    """A normalized command option/argument help row.

    Parameters:
        name: The rendered option or argument signature.
        description: The normalized help description.

    Raises:
        None

    Returns:
        None
    """

    name: str
    description: str


@dataclass(frozen=True)
class IntrospectedCommand:
    """Fully normalized documentation data for one command.

    Parameters:
        name: The public command name.
        group: The documentation group title.
        aliases: The registered hidden aliases.
        short_help: The one-line description shown in the command list.
        summary: The normalized long help text.
        synopsis: The command synopsis.
        options: The normalized option rows.
        epilog: The normalized epilog text, without the paragraphs the generator already emits.
        fragment_path: The resolved docs fragment path.
        fragment_body: The docs fragment body, or an empty string when missing.

    Raises:
        None

    Returns:
        None
    """

    name: str
    group: str
    aliases: tuple[str, ...]
    short_help: str
    summary: str
    synopsis: str
    options: tuple[CommandOptionDoc, ...]
    epilog: str
    fragment_path: Path
    fragment_body: str


def normalize_help(text: Optional[str]) -> str:
    """Collapse Click/Rich help strings into clean Markdown paragraphs.

    Parameters:
        text: The raw help or epilog text.

    Raises:
        None

    Returns:
        str: The normalized text.
    """
    if not text:
        return ""
    cleaned: str = textwrap.dedent(text).replace("\b", "").strip()
    paragraphs: list[str] = []
    for paragraph in cleaned.split("\n\n"):
        stripped_lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if stripped_lines:
            paragraphs.append(" ".join(stripped_lines))
    return "\n\n".join(paragraphs)


def _is_generated_paragraph(paragraph: str, option_signatures: frozenset[str]) -> bool:
    """Tell whether an epilog paragraph merely repeats generated content.

    The epilogs in this codebase predate the generator and re-document by hand what is now emitted
    from the Click metadata: a ``usage:`` line (the synopsis), an ``OPTIONS:``/``Args:`` header, and
    one entry per flag (the options table). Those paragraphs are dropped; anything else is prose
    only a human wrote and must survive.

    Detection is anchored on the command's own parameters rather than on the paragraph's shape, so
    a paragraph counts as an option entry only when it actually opens with one of the flags this
    command declares.

    Parameters:
        paragraph: A single normalized epilog paragraph.
        option_signatures: Every option flag declared by the command (e.g. ``-c``, ``--scope``).

    Raises:
        None

    Returns:
        bool: True when the paragraph duplicates generated content.
    """
    stripped: str = paragraph.strip()
    if not stripped:
        return True
    lowered: str = stripped.lower()
    if lowered.startswith(EPILOG_USAGE_PREFIX) or lowered.rstrip(":") in EPILOG_SECTION_HEADERS:
        return True
    first_token: str = re.split(r"[\s:|,]", stripped, maxsplit=1)[0]
    return first_token in option_signatures


def normalize_epilog(epilog: Optional[str], option_signatures: frozenset[str]) -> str:
    """Normalize an epilog, dropping the paragraphs the generator already emits.

    Parameters:
        epilog: The raw epilog text.
        option_signatures: Every option flag declared by the command.

    Raises:
        None

    Returns:
        str: The remaining hand-written prose, or an empty string.
    """
    paragraphs: list[str] = [
        paragraph
        for paragraph in normalize_help(epilog).split("\n\n")
        if not _is_generated_paragraph(paragraph, option_signatures)
    ]
    return "\n\n".join(paragraphs).strip()


def _get_option_signatures(command: click.Command) -> frozenset[str]:
    """Collect every flag declared by a command, used to spot duplicated epilog entries.

    Parameters:
        command: The command being inspected.

    Raises:
        None

    Returns:
        frozenset[str]: The command's option flags (both short and long forms).
    """
    return frozenset(
        option
        for parameter in command.params
        if isinstance(parameter, click.Option)
        for option in parameter.opts + parameter.secondary_opts
    )


def _build_command_context(root: CliGroup, command: click.Command, command_name: str) -> click.Context:
    """Create the Click context used for usage/help introspection.

    The group's ``context_settings`` are applied by hand because ``click.Context.__init__`` never
    reads them: only ``Command.make_context`` does, and that is not the path taken here. Without
    them the context falls back to Click's defaults and the generated document would describe a
    different CLI than the one the user runs -- ``--help`` instead of ``-h, --help``, for instance.

    Parameters:
        root: The top-level CLI group.
        command: The command being inspected.
        command_name: The public command name.

    Raises:
        None

    Returns:
        click.Context: The command context chained to the top-level CLI.
    """
    parent_ctx = click.Context(root, info_name=APP_NAME, **root.context_settings)
    return click.Context(command, info_name=command_name, parent=parent_ctx, **command.context_settings)


# Width used only to render the synopsis: wide enough that Click never wraps a usage line, so
# the generated docs do not depend on the terminal that produced them.
SYNOPSIS_WIDTH = 10_000


def _get_synopsis(root: CliGroup, command: click.Command, command_name: str) -> str:
    """Render a normalized one-line synopsis for a command.

    Parameters:
        root: The top-level CLI group.
        command: The command being inspected.
        command_name: The public command name.

    Raises:
        None

    Returns:
        str: The normalized synopsis string.
    """
    ctx = _build_command_context(root, command, command_name)
    # Click wraps the usage line to whatever terminal is attached, so the very same command yields
    # a different committed COMMANDS.md locally than on CI -- and a narrow terminal even splits a
    # metavar mid-word. Widening the context past any realistic usage line stops the wrapping at
    # the source; collapsing whitespace afterwards guarantees the single line promised above.
    ctx.terminal_width = SYNOPSIS_WIDTH
    ctx.max_content_width = SYNOPSIS_WIDTH
    usage = command.get_usage(ctx).removeprefix("Usage: ")
    return " ".join(usage.split())


def _get_option_docs(root: CliGroup, command: click.Command, command_name: str) -> tuple[CommandOptionDoc, ...]:
    """Collect help rows for the public parameters of a command.

    Parameters:
        root: The top-level CLI group.
        command: The command being inspected.
        command_name: The public command name.

    Raises:
        None

    Returns:
        tuple[CommandOptionDoc, ...]: The normalized parameter rows.
    """
    ctx = _build_command_context(root, command, command_name)
    rows: list[CommandOptionDoc] = []
    for parameter in command.get_params(ctx):
        help_record = parameter.get_help_record(ctx)
        if not help_record:
            continue
        rows.append(CommandOptionDoc(name=normalize_help(help_record[0]), description=normalize_help(help_record[1])))
    return tuple(rows)


def iter_introspected_commands(root: CliGroup) -> Iterator[IntrospectedCommand]:
    """Iterate over the documented commands and normalize them for rendering.

    Parameters:
        root: The top-level CLI group.

    Raises:
        None

    Returns:
        Iterator[IntrospectedCommand]: The normalized commands in deterministic order.
    """
    for entry in root.iter_documented_commands():
        fragment_body: str = ""
        if entry.fragment_path.is_file():
            fragment_body = entry.fragment_path.read_text(encoding="utf-8").strip()
        yield IntrospectedCommand(
            name=entry.name,
            group=entry.group,
            aliases=entry.aliases,
            # `get_short_help_str` is what Click itself puts in the command list, so it falls back to
            # the truncated help exactly the way `mgsnake --help` does. Reading `short_help` directly
            # would yield None for every command that never declared one, and the index would render
            # a column of blanks for commands whose description the user does in fact see.
            short_help=normalize_help(entry.command.get_short_help_str(limit=SHORT_HELP_LIMIT)),
            summary=normalize_help(entry.command.help),
            synopsis=_get_synopsis(root, entry.command, entry.name),
            options=_get_option_docs(root, entry.command, entry.name),
            epilog=normalize_epilog(entry.command.epilog, _get_option_signatures(entry.command)),
            fragment_path=entry.fragment_path,
            fragment_body=fragment_body,
        )
