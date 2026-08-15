"""Normalize CLI metadata into documentation-friendly dataclasses."""

from dataclasses import dataclass
from pathlib import Path
import textwrap
from typing import Iterator, Optional

import click

from mega_snake.constants import APP_NAME
from mega_snake.util.cli_group import CliGroup


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
        summary: The normalized long help text.
        synopsis: The command synopsis.
        options: The normalized option rows.
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
    summary: str
    synopsis: str
    options: tuple[CommandOptionDoc, ...]
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


def _build_command_context(root: CliGroup, command: click.Command, command_name: str) -> click.Context:
    """Create the Click context used for usage/help introspection.

    Parameters:
        root: The top-level CLI group.
        command: The command being inspected.
        command_name: The public command name.

    Raises:
        None

    Returns:
        click.Context: The command context chained to the top-level CLI.
    """
    parent_ctx = click.Context(root, info_name=APP_NAME)
    return click.Context(command, info_name=command_name, parent=parent_ctx)


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
    return command.get_usage(ctx).removeprefix("Usage: ").strip()


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
            summary=normalize_help(entry.command.help),
            synopsis=_get_synopsis(root, entry.command, entry.name),
            options=_get_option_docs(root, entry.command, entry.name),
            fragment_path=entry.fragment_path,
            fragment_body=fragment_body,
        )
