"""Tests for the generate-skill command."""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mega_snake.docs_gen.generate_skill import (
    ALL_SKILL_DIRS,
    SKILL_CLAUDE_DIR,
    SKILL_COPILOT_DIR,
    SKILL_FILE,
    SKILL_TARGET_OPT,
    SKILL_TRACKING_KEYS,
    _apply_tracking,
    _check_all_existing_skill_files,
    _skill_path,
    _write_skill_files,
    generate_skill,
)
from mega_snake.util.formatting import VALIDATION_ERROR_CODE

SAMPLE_MARKDOWN = "# Available Commands\n\n## Documentation\n\n### generate-skill\n"


@pytest.fixture(name="mk_render")
def fixture_mk_render() -> Generator[MagicMock, None, None]:
    """Patch _render_command_reference so tests don't need a full CLI build."""
    with patch("mega_snake.docs_gen.generate_skill._render_command_reference") as mock:
        mock.return_value = SAMPLE_MARKDOWN
        yield mock


@pytest.fixture(name="mk_get_validated_input")
def fixture_mk_get_validated_input() -> Generator[MagicMock, None, None]:
    """Patch get_validated_input in the generate_skill module."""
    with patch("mega_snake.docs_gen.generate_skill.get_validated_input") as mock:
        yield mock


@pytest.fixture(name="mk_exclude_from_git")
def fixture_mk_exclude_from_git() -> Generator[MagicMock, None, None]:
    """Patch exclude_from_git in the generate_skill module."""
    with patch("mega_snake.docs_gen.generate_skill.exclude_from_git") as mock:
        yield mock


@pytest.fixture(name="mk_add_to_gitignore")
def fixture_mk_add_to_gitignore() -> Generator[MagicMock, None, None]:
    """Patch add_to_gitignore in the generate_skill module."""
    with patch("mega_snake.docs_gen.generate_skill.add_to_gitignore") as mock:
        yield mock


@pytest.fixture(name="mk_ws_success_skill")
def fixture_mk_ws_success_skill() -> Generator[MagicMock, None, None]:
    """Patch ws_success in the generate_skill module."""
    with patch("mega_snake.docs_gen.generate_skill.ws_success") as mock:
        yield mock


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


def test_skill_file_constant() -> None:
    """SKILL_FILE should be the canonical file name."""
    assert SKILL_FILE == "SKILL.md"


def test_all_skill_dirs_contains_both_targets() -> None:
    """ALL_SKILL_DIRS must contain the Copilot and Claude directories in a deterministic order."""
    assert SKILL_COPILOT_DIR in ALL_SKILL_DIRS
    assert SKILL_CLAUDE_DIR in ALL_SKILL_DIRS
    assert len(ALL_SKILL_DIRS) == 2
    # Deterministic order is required for reproducible --check output.
    assert ALL_SKILL_DIRS[0] == SKILL_COPILOT_DIR
    assert ALL_SKILL_DIRS[1] == SKILL_CLAUDE_DIR


def test_skill_target_opt_keys() -> None:
    """SKILL_TARGET_OPT must map exactly the three expected selection keys."""
    assert set(SKILL_TARGET_OPT.keys()) == {"c", "l", "b"}
    assert SKILL_TARGET_OPT["c"] == (SKILL_COPILOT_DIR,)
    assert SKILL_TARGET_OPT["l"] == (SKILL_CLAUDE_DIR,)
    assert SKILL_TARGET_OPT["b"] == (SKILL_COPILOT_DIR, SKILL_CLAUDE_DIR)


def test_skill_tracking_keys() -> None:
    """SKILL_TRACKING_KEYS must contain exactly the three expected keys."""
    assert set(SKILL_TRACKING_KEYS) == {"e", "g", "v"}


# ---------------------------------------------------------------------------
# _skill_path
# ---------------------------------------------------------------------------


def test_skill_path_returns_skill_md_inside_dir() -> None:
    """_skill_path should append SKILL_FILE to the given directory."""
    p = _skill_path(SKILL_COPILOT_DIR)
    assert p == SKILL_COPILOT_DIR / SKILL_FILE
    assert p.name == SKILL_FILE


# ---------------------------------------------------------------------------
# _apply_tracking
# ---------------------------------------------------------------------------


def test_apply_tracking_versioned_emits_success(mk_ws_success_skill: MagicMock) -> None:
    """Choosing 'v' leaves the files versioned and reports success — no git helpers called."""
    with (
        patch("mega_snake.docs_gen.generate_skill.exclude_from_git") as mk_exc,
        patch("mega_snake.docs_gen.generate_skill.add_to_gitignore") as mk_ign,
    ):
        _apply_tracking((SKILL_COPILOT_DIR,), "v")

    mk_ws_success_skill.assert_called_once()
    mk_exc.assert_not_called()
    mk_ign.assert_not_called()


def test_apply_tracking_exclude_calls_exclude_from_git(mk_exclude_from_git: MagicMock) -> None:
    """Choosing 'e' delegates to exclude_from_git with the right entries."""
    dirs = (SKILL_COPILOT_DIR, SKILL_CLAUDE_DIR)
    _apply_tracking(dirs, "e")

    mk_exclude_from_git.assert_called_once()
    entries = mk_exclude_from_git.call_args[0][0]
    paths = [entry[0] for entry in entries]
    assert str(SKILL_COPILOT_DIR) + "/" in paths
    assert str(SKILL_CLAUDE_DIR) + "/" in paths


def test_apply_tracking_gitignore_calls_add_to_gitignore(mk_add_to_gitignore: MagicMock) -> None:
    """Choosing 'g' delegates to add_to_gitignore with the right entries."""
    dirs = (SKILL_CLAUDE_DIR,)
    _apply_tracking(dirs, "g")

    mk_add_to_gitignore.assert_called_once()
    entries = mk_add_to_gitignore.call_args[0][0]
    paths = [entry[0] for entry in entries]
    assert str(SKILL_CLAUDE_DIR) + "/" in paths


# ---------------------------------------------------------------------------
# _write_skill_files
# ---------------------------------------------------------------------------


def test_write_skill_files_creates_files(tmp_path: Path, mk_ws_success_skill: MagicMock) -> None:
    """_write_skill_files should write SKILL.md into each chosen directory."""
    dirs = (tmp_path / ".github" / "skills" / "mgsnake", tmp_path / ".claude" / "skills" / "mgsnake")

    written = _write_skill_files(dirs, SAMPLE_MARKDOWN)

    for skill_dir in dirs:
        skill_file = skill_dir / SKILL_FILE
        assert skill_file.is_file(), f"Expected {skill_file} to be written"
        assert skill_file.read_text(encoding="utf-8") == SAMPLE_MARKDOWN

    assert len(written) == 2
    assert mk_ws_success_skill.call_count == 2


def test_write_skill_files_returns_paths(tmp_path: Path, mk_ws_success_skill: MagicMock) -> None:
    """_write_skill_files should return the list of Path objects that were written."""
    dirs = (tmp_path / ".github" / "skills" / "mgsnake",)

    written = _write_skill_files(dirs, SAMPLE_MARKDOWN)

    assert written == [dirs[0] / SKILL_FILE]


# ---------------------------------------------------------------------------
# _check_all_existing_skill_files
# ---------------------------------------------------------------------------


def test_check_all_existing_skill_files_skips_missing(tmp_path: Path) -> None:
    """_check_all_existing_skill_files should silently pass when no skill files exist."""
    with patch(
        "mega_snake.docs_gen.generate_skill.ALL_SKILL_DIRS",
        (tmp_path / ".github" / "skills" / "mgsnake", tmp_path / ".claude" / "skills" / "mgsnake"),
    ):
        _check_all_existing_skill_files(SAMPLE_MARKDOWN)  # Must not raise


def test_check_all_existing_skill_files_passes_when_up_to_date(tmp_path: Path) -> None:
    """_check_all_existing_skill_files should pass when existing skill files match the rendered output."""
    skill_dir = tmp_path / ".github" / "skills" / "mgsnake"
    skill_file = skill_dir / SKILL_FILE
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

    with patch(
        "mega_snake.docs_gen.generate_skill.ALL_SKILL_DIRS",
        (skill_dir, tmp_path / ".claude" / "skills" / "mgsnake"),
    ):
        _check_all_existing_skill_files(SAMPLE_MARKDOWN)  # Must not raise


def test_check_all_existing_skill_files_fails_when_stale(tmp_path: Path) -> None:
    """_check_all_existing_skill_files should raise ValidationError when a skill file is stale."""
    from mega_snake.util.formatting import ValidationError

    skill_dir = tmp_path / ".github" / "skills" / "mgsnake"
    skill_file = skill_dir / SKILL_FILE
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("stale content", encoding="utf-8")

    with (
        patch(
            "mega_snake.docs_gen.generate_skill.ALL_SKILL_DIRS",
            (skill_dir,),
        ),
        pytest.raises(ValidationError),
    ):
        _check_all_existing_skill_files(SAMPLE_MARKDOWN)


# ---------------------------------------------------------------------------
# generate_skill command — --check flag
# ---------------------------------------------------------------------------


def test_generate_skill_check_passes_when_no_skill_files_exist(mk_render: MagicMock, tmp_path: Path) -> None:
    """--check exits 0 when no skill files exist on disk (nothing to validate)."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(generate_skill, ["--check"])

    assert result.exit_code == 0, result.output


def test_generate_skill_check_passes_when_files_match(mk_render: MagicMock, tmp_path: Path) -> None:
    """--check exits 0 when existing skill files are up to date."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        skill_dir = Path(iso) / ".github" / "skills" / "mgsnake"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILE).write_text(SAMPLE_MARKDOWN, encoding="utf-8")
        result = runner.invoke(generate_skill, ["--check"])

    assert result.exit_code == 0, result.output


def test_generate_skill_check_fails_when_stale(mk_render: MagicMock, tmp_path: Path) -> None:
    """--check exits with VALIDATION_ERROR_CODE when any existing skill file is stale."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        skill_dir = Path(iso) / ".github" / "skills" / "mgsnake"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILE).write_text("outdated", encoding="utf-8")
        result = runner.invoke(generate_skill, ["--check"])

    assert result.exit_code == VALIDATION_ERROR_CODE
    assert result.exit_code != 1


# ---------------------------------------------------------------------------
# generate_skill command — interactive write flow
# ---------------------------------------------------------------------------


def test_generate_skill_copilot_only_exclude(
    mk_render: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_exclude_from_git: MagicMock,
    tmp_path: Path,
) -> None:
    """Choosing 'c' + 'e' creates Copilot SKILL.md only and excludes it from git."""
    mk_get_validated_input.side_effect = ["c", "e"]
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        result = runner.invoke(generate_skill, [])
        copilot_file = Path(iso) / ".github" / "skills" / "mgsnake" / SKILL_FILE
        assert copilot_file.is_file(), "Copilot SKILL.md should have been created"
        assert copilot_file.read_text(encoding="utf-8") == SAMPLE_MARKDOWN
        claude_file = Path(iso) / ".claude" / "skills" / "mgsnake" / SKILL_FILE
        assert not claude_file.exists(), "Claude SKILL.md should NOT have been created"

    assert result.exit_code == 0, result.output
    mk_exclude_from_git.assert_called_once()


def test_generate_skill_claude_only_gitignore(
    mk_render: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_add_to_gitignore: MagicMock,
    tmp_path: Path,
) -> None:
    """Choosing 'l' + 'g' creates Claude SKILL.md only and adds it to .gitignore."""
    mk_get_validated_input.side_effect = ["l", "g"]
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        result = runner.invoke(generate_skill, [])
        claude_file = Path(iso) / ".claude" / "skills" / "mgsnake" / SKILL_FILE
        assert claude_file.is_file(), "Claude SKILL.md should have been created"
        copilot_file = Path(iso) / ".github" / "skills" / "mgsnake" / SKILL_FILE
        assert not copilot_file.exists(), "Copilot SKILL.md should NOT have been created"

    assert result.exit_code == 0, result.output
    mk_add_to_gitignore.assert_called_once()


def test_generate_skill_both_versioned(
    mk_render: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_exclude_from_git: MagicMock,
    mk_add_to_gitignore: MagicMock,
    tmp_path: Path,
) -> None:
    """Choosing 'b' + 'v' creates both SKILL.md files and leaves them versioned."""
    mk_get_validated_input.side_effect = ["b", "v"]
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        result = runner.invoke(generate_skill, [])
        for sub in [".github/skills/mgsnake", ".claude/skills/mgsnake"]:
            f = Path(iso) / sub / SKILL_FILE
            assert f.is_file(), f"{sub}/SKILL.md should have been created"

    assert result.exit_code == 0, result.output
    mk_exclude_from_git.assert_not_called()
    mk_add_to_gitignore.assert_not_called()


def test_generate_skill_target_prompt_shows_directories(mk_render: MagicMock) -> None:
    """The target prompt text should include both skill directory paths for context."""
    runner = CliRunner()
    # Provide valid answers so the command completes; assert only on the prompt text.
    with (
        patch("mega_snake.docs_gen.generate_skill.get_validated_input", side_effect=["c", "v"]) as mk_input,
        runner.isolated_filesystem(),
    ):
        runner.invoke(generate_skill, [])
        first_call_prompt = mk_input.call_args_list[0][0][0]

    assert str(SKILL_COPILOT_DIR / SKILL_FILE) in first_call_prompt
    assert str(SKILL_CLAUDE_DIR / SKILL_FILE) in first_call_prompt
