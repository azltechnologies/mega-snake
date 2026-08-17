"""Tests for CLI documentation introspection and generation."""

import inspect
from pathlib import Path
import re

from click.testing import CliRunner
import pytest

from mega_snake import __main__ as app_main
from mega_snake.docs_gen.introspect import iter_introspected_commands, normalize_help
from mega_snake.docs_gen.markdown_writer import _render_code_cell, _render_epilog, render_markdown

# Shorter strings are too generic to prove a real duplication between an epilog and a fragment.
MIN_DUPLICATE_SENTENCE_LEN = 30
# Document hierarchy: # document > ## group > ### command > #### fragment section.
COMMAND_HEADING_LEVEL = 3


def test_iter_documented_commands_skips_hidden_alias_duplicates() -> None:
    """The documented command iterator should yield one entry per public command only."""
    entries = list(app_main.cli.iter_documented_commands())
    command_names = [entry.name for entry in entries]

    assert "diff-tree" in command_names
    assert "dt" not in command_names
    assert "tree" not in command_names
    assert len(command_names) == len(set(command_names))


def test_iter_documented_commands_applies_the_group_override() -> None:
    """Module-level docs_group metadata should survive wrapping and reach the iterator."""
    entries = {entry.name: entry for entry in app_main.cli.iter_documented_commands()}

    assert entries["remote-branches-cleanup"].group == "Git & Release Management"
    assert entries["remote-branches-details"].group == "Git & Release Management"


@pytest.mark.parametrize("entry", list(app_main.cli.iter_documented_commands()), ids=lambda entry: entry.name)
def test_every_command_has_a_fragment(entry) -> None:
    """Each public command should have a matching docs fragment."""
    assert entry.fragment_path.is_file(), f"{entry.name} has no docs fragment at {entry.fragment_path}"


def test_no_orphan_fragments() -> None:
    """A renamed command should not leave a stale fragment behind."""
    documented_fragments = {f"{entry.fragment_name}.md" for entry in app_main.cli.iter_documented_commands()}
    docs_dir = Path(next(iter(app_main.cli.iter_documented_commands())).fragment_path).parent
    fragment_files = {path.name for path in docs_dir.glob("*.md")}

    assert fragment_files == documented_fragments


@pytest.mark.parametrize("entry", list(app_main.cli.iter_documented_commands()), ids=lambda entry: entry.name)
def test_every_documented_command_uses_explicit_help(entry) -> None:
    """The generator should only consume explicit help strings, never callback docstrings.

    Click falls back to the callback docstring when ``help=`` is omitted, and this codebase writes
    docstrings in the mandated API format, so that fallback would publish "Parameters: ..." blocks
    into the reference. Comparing against the docstring is what makes the difference visible.
    """
    assert entry.command.help is not None
    assert entry.command.help != inspect.getdoc(entry.command.callback), (
        f"{entry.name} inherits its help from the callback docstring; declare help= explicitly."
    )


@pytest.mark.parametrize("entry", list(iter_introspected_commands(app_main.cli)), ids=lambda entry: entry.name)
def test_epilog_never_repeats_generated_content(entry) -> None:
    """The rendered epilog must not restate the synopsis or the options table.

    Epilogs in this repo predate the generator and used to re-document every flag by hand. Those
    paragraphs are dropped by normalize_epilog; this guards against a new one creeping back in.
    """
    assert "usage:" not in entry.epilog.lower(), f"{entry.name}: the synopsis already states the usage line"
    for option in entry.options:
        flag: str = option.name.split(",")[0].split()[0]
        assert not any(
            paragraph.strip().startswith(flag) for paragraph in entry.epilog.split("\n\n")
        ), f"{entry.name}: the options table already documents {flag}"


@pytest.mark.parametrize("entry", list(iter_introspected_commands(app_main.cli)), ids=lambda entry: entry.name)
def test_fragment_never_repeats_the_epilog(entry) -> None:
    """A fragment must add to the epilog, never restate it (copilot-instructions section 6.3)."""
    fragment_sentences = {
        sentence.strip().casefold().rstrip(".")
        for sentence in re.split(r"[.\n]", entry.fragment_body)
        if len(sentence.strip()) > MIN_DUPLICATE_SENTENCE_LEN
    }
    epilog_sentences = {
        sentence.strip().casefold().rstrip(".")
        for sentence in re.split(r"[.\n]", entry.epilog)
        if len(sentence.strip()) > MIN_DUPLICATE_SENTENCE_LEN
    }

    assert not fragment_sentences & epilog_sentences, (
        f"{entry.name}: these sentences appear in both the epilog and the fragment: "
        f"{fragment_sentences & epilog_sentences}"
    )


@pytest.mark.parametrize(
    ("command_name", "argument_name"),
    [
        ("create-release", "release_type"),
        ("create-release", "notes"),
        ("create-release", "branch"),
        ("expired-certs-jks", "jks_path"),
        ("msg", "message"),
        ("shell-path", "shell"),
        ("graphql-schema", "schema_path"),
        ("man", "command"),
    ],
)
def test_positional_arguments_are_documented_from_the_epilog(command_name: str, argument_name: str) -> None:
    """Click tabulates options but never positional arguments, so the epilog is their only source.

    Dropping the epilog entirely (as the generator first did) silently lost every argument
    description in the reference.
    """
    commands = {command.name: command for command in iter_introspected_commands(app_main.cli)}

    assert f"{argument_name}:" in commands[command_name].epilog


def test_epilog_argument_entries_render_as_a_list_without_type_noise() -> None:
    """Argument entries become bullets, and the Python type annotation is dropped."""
    markdown = render_markdown(list(iter_introspected_commands(app_main.cli)))

    assert "- `branch` — branch to create the release from." in markdown
    assert "Optional[str] -" not in markdown
    assert "char -" not in markdown


@pytest.mark.parametrize(
    ("epilog", "expected"),
    [
        ("name: str - does a thing", "- `name` — does a thing"),
        ("Just prose.", "Just prose."),
        ("name: str - a thing\n\nTrailing prose.", "- `name` — a thing\n\nTrailing prose."),
        ("Leading prose.\n\nname: str - a thing", "Leading prose.\n- `name` — a thing"),
    ],
)
def test_render_epilog_mixes_arguments_and_prose(epilog: str, expected: str) -> None:
    """Argument entries become bullets while surrounding prose stays as paragraphs."""
    assert _render_epilog(epilog) == expected


def test_generate_docs_renders_fragment_sections_below_the_command_heading() -> None:
    """A fragment's ## section must land one level *under* its command heading.

    The document nests as: # document > ## group > ### command > #### fragment section. Assertions
    are anchored to the start of a line, since a bare substring check would pass at any deeper
    level too ("### Output" is contained in "#### Output").
    """
    markdown = render_markdown(list(iter_introspected_commands(app_main.cli)))
    headings = markdown.splitlines()

    assert "### generate-docs" in headings
    assert "#### Output" in headings
    assert "### Output" not in headings
    assert "## Output" not in headings


def test_fragment_sections_never_outrank_their_command() -> None:
    """Every fragment section heading must be deeper than the command heading it belongs to.

    Guards the whole document instead of one sample: walking it in order, no heading between two
    command headings may sit at ### or above.
    """
    command_names = {command.name for command in iter_introspected_commands(app_main.cli)}
    markdown = render_markdown(list(iter_introspected_commands(app_main.cli)))
    inside_command = False

    for line in markdown.splitlines():
        if not line.startswith("#"):
            continue
        level = len(line) - len(line.lstrip("#"))
        title = line.lstrip("#").strip()
        if level < COMMAND_HEADING_LEVEL:
            # A new group heading legitimately closes the previous command's section.
            inside_command = False
            continue
        if level == COMMAND_HEADING_LEVEL:
            assert title in command_names, f"'{title}' sits at command level but is not a command"
            inside_command = True
            continue
        if inside_command:
            assert level > COMMAND_HEADING_LEVEL, f"'{title}' sits at level {level}, not nested under its command"


def test_command_headings_are_plain_names() -> None:
    """Command headings must not be wrapped in backticks, so they read as titles, not as code."""
    markdown = render_markdown(list(iter_introspected_commands(app_main.cli)))
    headings = [line for line in markdown.splitlines() if line.startswith("### ")]

    assert headings
    assert not any(line.startswith("### `") for line in headings)


def test_generate_docs_writes_the_reference_file(tmp_path: Path) -> None:
    """The no-init docs command should generate the Markdown reference without shell setup."""
    output_path = tmp_path / "COMMANDS.md"

    result = CliRunner().invoke(app_main.cli, ["generate-docs", "--output", str(output_path)])

    assert result.exit_code == 0
    assert output_path.is_file()
    assert output_path.read_text(encoding="utf-8").startswith("# Available Commands")


def test_generate_docs_check_reports_stale_output(tmp_path: Path) -> None:
    """--check should fail when the target file differs from the rendered output."""
    output_path = tmp_path / "COMMANDS.md"
    output_path.write_text("stale\n", encoding="utf-8")

    result = CliRunner().invoke(app_main.cli, ["generate-docs", "--output", str(output_path), "--check"])

    assert result.exit_code == 1
    # rich word-wraps the error panel to the terminal width, so "is out of date" can land split
    # across two lines with a "│" border in between; collapse panel borders and whitespace before
    # matching so the assertion does not depend on the environment's column width.
    normalized_output = re.sub(r"[\s│]+", " ", result.output)
    assert "is out of date" in normalized_output


def test_generate_docs_check_accepts_matching_output(tmp_path: Path) -> None:
    """--check should succeed once the target file matches the rendered output."""
    output_path = tmp_path / "COMMANDS.md"
    markdown = render_markdown(list(iter_introspected_commands(app_main.cli)))
    output_path.write_text(markdown.replace("\n", "\r\n"), encoding="utf-8")

    result = CliRunner().invoke(app_main.cli, ["generate-docs", "--output", str(output_path), "--check"])

    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        ("   \n  \n ", ""),
        ("\b\n  first line\n  second line", "first line second line"),
        ("one\n\ntwo", "one\n\ntwo"),
    ],
)
def test_normalize_help_collapses_click_formatting(raw, expected: str) -> None:
    """Click help strings carry \\b markers and manual wrapping that Markdown must not inherit."""
    assert normalize_help(raw) == expected


def test_introspection_honours_the_group_context_settings() -> None:
    """The synthetic context must mirror the real CLI, which declares -h next to --help.

    click.Context does not read context_settings on its own, so forgetting to pass them documents
    a CLI the user does not have, and makes the output depend on whether Click already cached the
    real help option for that command.
    """
    commands = {command.name: command for command in iter_introspected_commands(app_main.cli)}
    help_rows = {
        name: [option.name for option in command.options if "--help" in option.name]
        for name, command in commands.items()
    }

    assert help_rows["generate-docs"] == ["-h, --help"]
    assert all(rows == ["-h, --help"] for rows in help_rows.values()), help_rows


def test_option_table_rows_stay_on_a_single_line() -> None:
    """Multi-line option help must be folded, or the Markdown table breaks apart."""
    markdown = render_markdown(list(iter_introspected_commands(app_main.cli)))
    table_rows = [line for line in markdown.splitlines() if line.startswith("| `") or line.startswith("| ``")]

    assert table_rows
    assert all(row.endswith(" |") for row in table_rows), "a table row lost its closing pipe"
    # The choice lists of these two options are the multi-line worst case in the repo.
    assert "'M' - merged branches" in markdown
    assert "<br>" in markdown
    assert "\n'M' - merged branches" not in markdown


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("--plain", "`--plain`"),
        (r"--path TEXT [C:\dir]", r"`--path TEXT [C:\dir]`"),
        ("--pipe [a|b]", "`--pipe [a\\|b]`"),
        # CommonMark strips one padding space from each side, so both are needed.
        ("--quote `x`", "`` --quote `x` ``"),
        ("--multi\nline", "`--multi<br>line`"),
    ],
)
def test_render_code_cell_is_table_safe(raw: str, expected: str) -> None:
    """Code cells keep backslashes literal, escape pipes, and grow the fence around backticks."""
    assert _render_code_cell(raw) == expected


def test_help_render_keeps_the_real_command_registry_intact() -> None:
    """Rendering help must not replace command keys with display strings."""
    original_keys = set(app_main.cli.commands)

    result = CliRunner().invoke(app_main.cli, ["--help"])

    assert result.exit_code == 0
    assert "generate-docs" in app_main.cli.commands
    assert "generate-docs |" not in app_main.cli.commands
    assert set(app_main.cli.commands) == original_keys
