"""Render CLI metadata and command fragments into a Markdown reference."""

from collections import defaultdict
from difflib import unified_diff
from pathlib import Path
import re
from typing import Iterable

from mega_snake.docs_gen.introspect import IntrospectedCommand
from mega_snake.util.formatting import ValidationError

GROUP_HEADING = "# Available Commands"
INDEX_HEADING = "# mgsnake Command Index"
CELL_LINE_BREAK = "<br>"
BACKTICK = "`"


def _to_single_cell_line(text: str) -> str:
    """Fold a multi-line value into one Markdown table row.

    A table row ends at the first newline, so any help text with manual line breaks (the choice
    lists of ``--filter-by`` and ``--type-msg``) would tear the table apart. Paragraph breaks
    survive as two ``<br>`` because ``normalize_help`` separates paragraphs with a blank line.

    Parameters:
        text: The raw cell text, possibly spanning several lines.

    Raises:
        None

    Returns:
        str: The folded single-line cell text.
    """
    return CELL_LINE_BREAK.join(text.splitlines())


def _escape_markdown_cell(text: str) -> str:
    """Escape prose so it can be safely rendered inside a Markdown table.

    Parameters:
        text: The raw text to escape.

    Raises:
        None

    Returns:
        str: The escaped table cell text.
    """
    return _to_single_cell_line(text.replace("\\", "\\\\").replace("|", "\\|"))


def _render_code_cell(text: str) -> str:
    """Render text as an inline code span that survives a Markdown table.

    Backslashes are left untouched: a code span renders them literally, so escaping them here
    would print a doubled backslash. Pipes still need escaping, since a table row is split on them
    before any inline parsing happens. The fence grows past the longest backtick run in the text,
    which is the standard way to embed backticks in a code span.

    Parameters:
        text: The raw text to render as code.

    Raises:
        None

    Returns:
        str: The fenced, table-safe code span.
    """
    longest_run: int = max((len(run) for run in re.findall(rf"{BACKTICK}+", text)), default=0)
    fence: str = BACKTICK * (longest_run + 1)
    padding: str = " " if text.startswith(BACKTICK) or text.endswith(BACKTICK) else ""
    content: str = _to_single_cell_line(text.replace("|", "\\|"))
    return f"{fence}{padding}{content}{padding}{fence}"


def _render_epilog(epilog: str) -> str:
    """Render the surviving epilog prose as Markdown.

    What is left after ``normalize_epilog`` is mostly per-argument documentation, since Click
    tabulates options but never positional arguments. Those entries read as ``name: type - text``,
    so they become a bullet list; anything else stays a plain paragraph.

    Parameters:
        epilog: The normalized epilog text.

    Raises:
        None

    Returns:
        str: The rendered Markdown block.
    """
    rendered: list[str] = []
    for paragraph in epilog.split("\n\n"):
        if re.match(r"^[\w-]+:\s", paragraph):
            name, _, description = paragraph.partition(":")
            # Drop the leading type annotation ("str - ", "char - "): the synopsis already shows
            # which arguments exist, and the prose is what the reader needs here.
            text: str = re.sub(r"^\s*\w+(\[[\w\s,\[\]]+\])?\s+-\s+", "", description).strip()
            rendered.append(f"- `{name.strip()}` — {text}")
        else:
            rendered.append(f"\n{paragraph}\n" if rendered else paragraph)
    return "\n".join(rendered).strip()


def _render_fragment(fragment_body: str) -> str:
    """Promote fragment headings to the command-section depth used by the writer.

    Parameters:
        fragment_body: The raw fragment body.

    Raises:
        None

    Returns:
        str: The rewritten fragment body.
    """
    return re.sub(r"^##\s+", "#### ", fragment_body, flags=re.MULTILINE)


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
            lines.extend([f"### {command.name}", ""])
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
                    lines.append(f"| {_render_code_cell(option.name)} | {_escape_markdown_cell(option.description)} |")
                lines.append("")
            if command.epilog:
                lines.extend([_render_epilog(command.epilog), ""])
            if command.fragment_body:
                lines.extend([_render_fragment(command.fragment_body), ""])
    return "\n".join(lines).rstrip() + "\n"


def render_index(commands: Iterable[IntrospectedCommand]) -> str:
    """Render the compact command index: one table row per command, no options and no fragments.

    This is a **second projection of the same ``IntrospectedCommand`` list**, never a second walk of
    the CLI. Both agent runtimes load a skill body eagerly, so a skill that inlines the full
    reference spends the reader's context on ~900 lines before it knows which command it needs; the
    index is what the body carries instead, and the reference is read on demand. Rendering it from a
    separate introspection pass would let the two documents disagree about which commands exist,
    which is the one failure a generated document must not have.

    Parameters:
        commands: The introspected command entries to render.

    Raises:
        None

    Returns:
        str: The rendered Markdown index.
    """
    grouped_commands: dict[str, list[IntrospectedCommand]] = defaultdict(list)
    for command in commands:
        grouped_commands[command.group].append(command)

    lines: list[str] = [INDEX_HEADING, ""]
    for group_name in sorted(grouped_commands, key=str.casefold):
        lines.extend([f"## {group_name}", "", "| Command | Aliases | Description |", "| --- | --- | --- |"])
        for command in grouped_commands[group_name]:
            aliases: str = ", ".join(f"`{alias}`" for alias in command.aliases) if command.aliases else "—"
            lines.append(
                f"| `{command.name}` | {aliases} | {_escape_markdown_cell(_to_single_cell_line(command.short_help))} |"
            )
        lines.append("")
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
        ValidationError: If --check finds that the output is stale.

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
            # Stale content is a validation result, not a misuse of the command: its own status
            # lets a CI step tell "the committed file drifted" apart from "the check itself was
            # invoked wrong", which are two very different things to act on.
            raise ValidationError(f"{output_path} is out of date.\n{diff}")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown)
