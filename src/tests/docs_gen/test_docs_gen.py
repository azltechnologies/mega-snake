"""Tests for CLI documentation introspection and generation."""

from pathlib import Path

from click.testing import CliRunner
import pytest

from mega_snake import __main__ as app_main
from mega_snake.docs_gen.introspect import iter_introspected_commands
from mega_snake.docs_gen.markdown_writer import render_markdown


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
    """The generator should only consume explicit help strings, never callback docstrings."""
    assert entry.command.help is not None


def test_generate_docs_renders_fragment_sections_at_command_depth() -> None:
    """Fragment headings should be rendered below the command heading level."""
    commands = list(iter_introspected_commands(app_main.cli))
    markdown = render_markdown(commands)

    assert "### `generate-docs`" in markdown
    assert "### Output" in markdown
    assert "\n## Output\n" not in markdown


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
    assert "is out of date" in result.output


def test_generate_docs_check_accepts_matching_output(tmp_path: Path) -> None:
    """--check should succeed once the target file matches the rendered output."""
    output_path = tmp_path / "COMMANDS.md"
    markdown = render_markdown(list(iter_introspected_commands(app_main.cli)))
    output_path.write_text(markdown.replace("\n", "\r\n"), encoding="utf-8")

    result = CliRunner().invoke(app_main.cli, ["generate-docs", "--output", str(output_path), "--check"])

    assert result.exit_code == 0


def test_help_render_keeps_the_real_command_registry_intact() -> None:
    """Rendering help must not replace command keys with display strings."""
    original_keys = set(app_main.cli.commands)

    result = CliRunner().invoke(app_main.cli, ["--help"])

    assert result.exit_code == 0
    assert "generate-docs" in app_main.cli.commands
    assert "generate-docs |" not in app_main.cli.commands
    assert set(app_main.cli.commands) == original_keys
