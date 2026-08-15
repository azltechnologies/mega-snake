"""Tests for the terminal man page command."""

import os
from pathlib import Path
import re

import click
from click.testing import CliRunner
import pytest

from mega_snake import __main__ as app_main
from mega_snake.docs_gen import man_page
from mega_snake.docs_gen.markdown_writer import CELL_LINE_BREAK

# Every command emits exactly one of these lines, which makes it the reliable way to tell which
# commands a rendered page actually contains.
SYNOPSIS_PREFIX = "Synopsis: mgsnake"


def _flatten(text: str) -> str:
    """Reduce rendered terminal output to a form that can be searched for phrases.

    Rich styles the document with ANSI sequences and wraps it to the page width, so a phrase from
    the source Markdown is never a literal substring of the output. Removing the styling and
    collapsing every run of whitespace puts both back on comparable ground.

    Parameters:
        text: The rendered terminal output.

    Raises:
        None

    Returns:
        str: The unstyled, whitespace-collapsed text.
    """
    return re.sub(r"\s+", " ", click.unstyle(text))


def _page(mocker, args: list[str]) -> str:
    """Invoke the man command and capture what it sent to the pager.

    Parameters:
        mocker: The pytest-mock fixture.
        args: The command line arguments passed to the CLI.

    Raises:
        AssertionError: If the command failed instead of paging a document.

    Returns:
        str: The flattened text handed to the pager.
    """
    pager = mocker.patch("click.echo_via_pager")
    result = CliRunner().invoke(app_main.cli, args)

    assert result.exit_code == 0, result.output
    pager.assert_called_once()
    return _flatten(pager.call_args.args[0])


def _commands_in(text: str) -> set[str]:
    """Collect the commands a rendered page documents.

    Parameters:
        text: The flattened page text.

    Raises:
        None

    Returns:
        set[str]: The names of every command whose synopsis appears on the page.
    """
    all_names = {entry.name for entry in app_main.cli.iter_documented_commands()}
    return {name for name in all_names if f"{SYNOPSIS_PREFIX} {name}" in text}


def test_man_pages_every_documented_command(mocker) -> None:
    """With no argument the whole reference is paged, not a sample of it."""
    expected = {entry.name for entry in app_main.cli.iter_documented_commands()}

    assert _commands_in(_page(mocker, ["man"])) == expected


def test_man_pages_only_the_requested_command(mocker) -> None:
    """Naming a command must narrow the page to it and exclude every other command."""
    assert _commands_in(_page(mocker, ["man", "diff-tree"])) == {"diff-tree"}


@pytest.mark.parametrize("alias", ["dt", "tree"])
def test_man_resolves_aliases_to_the_same_page(mocker, alias: str) -> None:
    """An alias must produce the identical page, since aliases are the daily-use form."""
    assert _page(mocker, ["man", alias]) == _page(mocker, ["man", "diff-tree"])


def test_man_rejects_an_unknown_command() -> None:
    """An unknown name must fail loudly and tell the user what is available."""
    result = CliRunner().invoke(app_main.cli, ["man", "not-a-command"])

    assert result.exit_code == 1
    output = _flatten(result.output)
    assert "Unknown command 'not-a-command'" in output
    assert "diff-tree" in output, "the error should list the real command names"
    assert "dt" in output, "the error should list aliases too, since they are accepted input"


def test_man_renders_the_document_and_not_its_markdown_source(mocker) -> None:
    """The page must be rendered prose, never the raw Markdown the writer produces."""
    text = _page(mocker, ["man", "diff-tree"])

    assert "Synopsis: mgsnake diff-tree [OPTIONS]" in text
    assert "### diff-tree" not in text, "heading markers must be rendered away"
    assert "| --- |" not in text, "the option table must be rendered, not printed as pipes"
    assert "**Synopsis:**" not in text


def test_man_folds_table_line_breaks_back_into_readable_text(mocker) -> None:
    """The <br> the Markdown table needs must not survive, nor collapse the choice list.

    Rich drops HTML tags outright. Left alone, the multi-line choice list of --type-msg renders as
    one glued run ("Success'I' - Information"), which is why they are folded into spaces first.
    """
    text = _page(mocker, ["man", "msg"])

    assert CELL_LINE_BREAK not in text
    assert "'S' - Success 'I' - Information" in text
    assert "Success'I'" not in text, "the choice entries were glued together"


def test_man_does_not_depend_on_the_generated_reference_file(mocker, tmp_path: Path) -> None:
    """The page is built in memory, so it must work where COMMANDS.md does not exist.

    COMMANDS.md lives in the repository and is not shipped in the wheel: reading it would give
    installed users a command that only works inside a source checkout.
    """
    with CliRunner().isolated_filesystem(temp_dir=tmp_path) as sandbox:
        assert not (Path(sandbox) / "COMMANDS.md").exists()
        text = _page(mocker, ["man", "shell-path"])

    assert _commands_in(text) == {"shell-path"}


def test_man_runs_without_any_initialization(mocker) -> None:
    """man is a no_init command: it must not require MEGA_SNAKE_SHELL to be set."""
    mocker.patch.dict("os.environ", {}, clear=True)
    pager = mocker.patch("click.echo_via_pager")

    result = CliRunner().invoke(app_main.cli, ["man", "man"])

    assert result.exit_code == 0, result.output
    pager.assert_called_once()


@pytest.mark.parametrize(
    ("terminal_columns", "expected"),
    [
        (40, 40),
        (100, 100),
        (240, man_page.MAX_PAGE_WIDTH),
    ],
)
def test_page_width_follows_the_terminal_but_stays_capped(mocker, terminal_columns: int, expected: int) -> None:
    """A narrow terminal is honoured; a very wide one is capped so prose stays readable."""
    # The real call returns os.terminal_size, not a plain tuple: the code reads '.columns'.
    mocker.patch("shutil.get_terminal_size", return_value=os.terminal_size((terminal_columns, 24)))

    assert man_page._page_width() == expected
