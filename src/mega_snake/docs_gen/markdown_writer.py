"""Render CLI metadata and command fragments into a Markdown reference."""

from collections import defaultdict
from difflib import unified_diff
from pathlib import Path
import re
from typing import Iterable

import click

from mega_snake.docs_gen.introspect import IntrospectedCommand, iter_introspected_commands
from mega_snake.util.util import cli_metadata

GROUP_HEADING = "# Available Commands"


def _escape_markdown_cell(text: str) -> str:
    """Escape text so it can be safely rendered inside a Markdown table.

    Parameters:
        text: The raw text to escape.

    Raises:
        None

    Returns:
        str: The escaped table cell text.
    """
    return text.replace("\\", "\\\\").replace("|", "\\|")


def _render_fragment(fragment_body: str) -> str:
    """Promote fragment headings to the command-section depth used by the writer.

    Parameters:
        fragment_body: The raw fragment body.

    Raises:
        None

    Returns:
        str: The rewritten fragment body.
    """
    return re.sub(r"^##\s+", "### ", fragment_body, flags=re.MULTILINE)


def render_markdown(commands: Iterable[IntrospectedCommand]) -> str:
    """Render the full Markdown command reference.

    Parameters:
        commands: The introspected command entries to render.

    Raises:
        None

    Returns:
        str: The rendered Markdown document.
    """
    grouped_commands: dict[str, list[IntrospectedCommand]] = defaultdict(list)
    for command in commands:
        grouped_commands[command.group].append(command)

    lines: list[str] = [GROUP_HEADING, ""]
    for group_name in sorted(grouped_commands, key=str.casefold):
        lines.extend([f"## {group_name}", ""])
        for command in grouped_commands[group_name]:
            lines.extend([f"### `{command.name}`", ""])
            if command.summary:
                lines.extend([command.summary, ""])
            lines.extend([f"**Synopsis:** `{command.synopsis}`", ""])
            if command.aliases:
                alias_list: str = ", ".join(f"`{alias}`" for alias in command.aliases)
                lines.extend([f"**Aliases:** {alias_list}", ""])
            if command.options:
                lines.extend(
                    [
                        "| Option | Description |",
                        "| --- | --- |",
                    ]
                )
                for option in command.options:
                    lines.append(
                        f"| `{_escape_markdown_cell(option.name)}` | {_escape_markdown_cell(option.description)} |"
                    )
                lines.append("")
            if command.fragment_body:
                lines.extend([_render_fragment(command.fragment_body), ""])
    return "\n".join(lines).rstrip() + "\n"


def _normalize_lines(text: str) -> list[str]:
    """Normalize line endings for portable text comparisons.

    Parameters:
        text: The text to normalize.

    Raises:
        None

    Returns:
        list[str]: The normalized lines.
    """
    return text.splitlines()


def write_or_check_document(output_path: Path, markdown: str, check: bool) -> None:
    """Either write the Markdown file or fail when it is out of date.

    Parameters:
        output_path: The target Markdown file path.
        markdown: The newly rendered Markdown text.
        check: When True, validate instead of writing.

    Raises:
        click.ClickException: If --check finds that the output is stale.

    Returns:
        None
    """
    if check:
        current_content: str = output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
        if _normalize_lines(current_content) != _normalize_lines(markdown):
            diff: str = "\n".join(
                unified_diff(
                    _normalize_lines(current_content),
                    _normalize_lines(markdown),
                    fromfile=str(output_path),
                    tofile="generated",
                    lineterm="",
                )
            )
            raise click.ClickException(f"{output_path} is out of date.\n{diff}")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown)


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
    default=Path("COMMANDS.md"),
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
        click.ClickException: If --check finds that the output file is stale.

    Returns:
        None
    """
    from mega_snake.__main__ import cli

    markdown: str = render_markdown(iter_introspected_commands(cli))
    write_or_check_document(output, markdown, check)
    if not check:
        click.echo(f"Generated {output}")
