"""Tests for the generate-skill command."""

from pathlib import Path, PureWindowsPath
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mega_snake.docs_gen.generate_skill import (
    ALL_SKILL_DIRS,
    REFERENCE_FILE,
    SKILL_CLAUDE_DIR,
    SKILL_COPILOT_DIR,
    SKILL_DESCRIPTION,
    SKILL_DIR_LABEL,
    SKILL_FILE,
    SKILL_NAME,
    SKILL_PREAMBLE,
    SKILL_TARGET_OPT,
    SKILL_TRACKING_KEYS,
    _apply_tracking,
    _check_all_existing_skill_files,
    _reference_path,
    _skill_document,
    _skill_files,
    _skill_path,
    _tracking_entries,
    _write_skill_files,
    generate_skill,
)
from mega_snake.util.formatting import VALIDATION_ERROR_CODE

SAMPLE_MARKDOWN = "# Available Commands\n\n## Documentation\n\n### generate-skill\n"
SAMPLE_INDEX = "# mgsnake Command Index\n\n## Documentation\n\n| Command | Aliases | Description |\n"

# What the command actually writes into SKILL.md: the frontmatter, the preamble, then the index --
# never the full reference, which now lives in its own file. Spelled out here rather than reusing
# _skill_document() so a change in the composition has to be acknowledged.
SAMPLE_DOCUMENT = f'---\nname: mgsnake\ndescription: "{SKILL_DESCRIPTION}"\n---\n\n{SKILL_PREAMBLE}\n\n{SAMPLE_INDEX}'

# The two files a completed run leaves in every selected directory.
SAMPLE_FILES = {SKILL_FILE: SAMPLE_DOCUMENT, REFERENCE_FILE: SAMPLE_MARKDOWN}

# The literal directory entries the tracking helpers must receive. Written out instead of derived
# from SKILL_*_DIR so the expectation cannot restate the expression under test: on Windows
# str(SKILL_COPILOT_DIR) is ".github\\skills\\mgsnake", which these literals reject.
COPILOT_ENTRY = ".github/skills/mgsnake/"
CLAUDE_ENTRY = ".claude/skills/mgsnake/"


@pytest.fixture(name="mk_render")
def fixture_mk_render() -> Generator[MagicMock, None, None]:
    """Patch the introspection and both renderers so tests don't need a full CLI build."""
    with (
        patch("mega_snake.docs_gen.generate_skill.introspected_commands") as mk_commands,
        patch("mega_snake.docs_gen.generate_skill.render_index", return_value=SAMPLE_INDEX),
        patch("mega_snake.docs_gen.generate_skill.render_markdown", return_value=SAMPLE_MARKDOWN),
    ):
        mk_commands.return_value = []
        yield mk_commands


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


def test_reference_file_constant() -> None:
    """REFERENCE_FILE is a sibling of SKILL.md, never SKILL.md itself."""
    assert REFERENCE_FILE == "reference.md"
    assert REFERENCE_FILE != SKILL_FILE


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


def test_reference_path_returns_reference_md_inside_dir() -> None:
    """_reference_path should append REFERENCE_FILE to the given directory, beside SKILL.md."""
    p = _reference_path(SKILL_COPILOT_DIR)
    assert p == SKILL_COPILOT_DIR / REFERENCE_FILE
    assert p.name == REFERENCE_FILE
    assert p.parent == _skill_path(SKILL_COPILOT_DIR).parent


# ---------------------------------------------------------------------------
# _skill_document
# ---------------------------------------------------------------------------


def test_skill_document_opens_with_yaml_frontmatter() -> None:
    """The document must start with a frontmatter block carrying name and description.

    Neither runtime registers a SKILL.md that opens with anything else, so a file starting with the
    reference's own "# Available Commands" heading is never loaded as a skill at all.
    """
    lines = _skill_document(SAMPLE_MARKDOWN).splitlines()

    assert lines[0] == "---", f"document opens with {lines[0]!r}, not a frontmatter fence"
    assert lines[1] == f"name: {SKILL_NAME}", f"second line is {lines[1]!r}"
    assert lines[2].startswith("description: "), f"third line is {lines[2]!r}"
    assert lines[3] == "---", f"frontmatter is not closed on line 4, got {lines[3]!r}"


def test_skill_document_carries_the_index_and_not_the_reference() -> None:
    """The body is the preamble plus the index; the full reference must not be inlined.

    This is the whole point of the split: both runtimes load SKILL.md eagerly, so a body carrying the
    reference spends the reader's context before it knows which command it needs. Asserting the index
    is present is not enough -- the defect being guarded against is the reference being present *too*.
    """
    document = _skill_document(SAMPLE_INDEX)

    _, _, body = document.partition("\n---\n")
    assert body.lstrip("\n") == f"{SKILL_PREAMBLE}\n\n{SAMPLE_INDEX}"
    assert document.endswith(SAMPLE_INDEX)
    assert SAMPLE_MARKDOWN not in document, "the full reference was inlined into the eagerly loaded body"


def test_skill_document_points_at_a_way_to_read_the_full_entry() -> None:
    """The body must name both routes to the detail the index deliberately omits.

    Without the pointer the index reads as the complete documentation, and an agent answers about
    options and defaults from a table that carries none.
    """
    document = _skill_document(SAMPLE_INDEX)

    assert REFERENCE_FILE in document, "the body never names the reference file"
    assert f"{SKILL_NAME} man <command>" in document, "the body never names the man command"


def test_skill_files_pairs_each_file_with_its_own_content() -> None:
    """The write path and --check share one mapping, so both cover exactly the same files."""
    files = _skill_files(SAMPLE_INDEX, SAMPLE_MARKDOWN)

    assert set(files) == {SKILL_FILE, REFERENCE_FILE}, f"unexpected file set: {sorted(files)}"
    assert files[REFERENCE_FILE] == SAMPLE_MARKDOWN
    assert files[SKILL_FILE] != SAMPLE_MARKDOWN, "SKILL.md must not hold the reference"
    assert files[SKILL_FILE].startswith("---\n"), "SKILL.md lost its frontmatter"


def test_skill_document_quotes_the_description_scalar() -> None:
    """The description is a quoted YAML scalar, and the wording stays quotable.

    A plain scalar may not contain a colon followed by a space, which the description's prose can
    easily reintroduce; quoting removes the trap, and a raw double quote inside would reopen it.
    """
    description_line = _skill_document(SAMPLE_MARKDOWN).splitlines()[2]

    assert description_line == f'description: "{SKILL_DESCRIPTION}"'
    assert '"' not in SKILL_DESCRIPTION, "an unescaped double quote would break the quoted scalar"
    assert "\n" not in SKILL_DESCRIPTION, "a newline would break the single-line scalar"


def test_skill_name_is_a_valid_skill_identifier() -> None:
    """Both runtimes key a skill by its name, which must be a lowercase, hyphen-safe slug."""
    assert SKILL_NAME == SKILL_NAME.lower()
    assert SKILL_NAME.replace("-", "").isalnum(), f"{SKILL_NAME!r} is not a slug"
    assert SKILL_NAME == "mgsnake"


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
    assert paths == [COPILOT_ENTRY, CLAUDE_ENTRY], f"unexpected exclude entries: {paths}"


def test_apply_tracking_gitignore_calls_add_to_gitignore(mk_add_to_gitignore: MagicMock) -> None:
    """Choosing 'g' delegates to add_to_gitignore with the right entries."""
    dirs = (SKILL_CLAUDE_DIR,)
    _apply_tracking(dirs, "g")

    mk_add_to_gitignore.assert_called_once()
    entries = mk_add_to_gitignore.call_args[0][0]
    paths = [entry[0] for entry in entries]
    assert paths == [CLAUDE_ENTRY], f"unexpected .gitignore entries: {paths}"


def test_tracking_entries_uses_forward_slashes_on_a_windows_style_path() -> None:
    """A Windows-shaped path must still yield a posix pattern git can actually match.

    PureWindowsPath is what makes this test discriminate on any host: on Linux str() and as_posix()
    agree, so only a genuinely Windows-flavoured path can tell a correct implementation from the
    str() one, where git reads the backslashes as escapes and the pattern matches nothing.
    """
    windows_dir = PureWindowsPath(".github") / "skills" / "mgsnake"
    assert "\\" in str(windows_dir), "fixture is not exercising a backslash-separated path"

    with patch("mega_snake.docs_gen.generate_skill.SKILL_DIR_LABEL", {windows_dir: "GitHub Copilot skill folder"}):
        entries = _tracking_entries([windows_dir])

    assert entries == [(COPILOT_ENTRY, "GitHub Copilot skill folder")], f"got {entries}"
    assert "\\" not in entries[0][0]


@pytest.mark.parametrize("tracking", ["e", "g"])
def test_apply_tracking_writes_posix_separators_only(
    tracking: str,
    mk_exclude_from_git: MagicMock,
    mk_add_to_gitignore: MagicMock,
) -> None:
    """Every git entry must use forward slashes, whatever separator the host OS uses.

    git reads a backslash inside an ignore pattern as an escape, so a Windows-shaped
    ".github\\skills\\mgsnake/" silently matches nothing and the files stay tracked. Asserting the
    literal posix string is what discriminates; comparing against str(SKILL_COPILOT_DIR) would
    restate the very expression under test and pass on any platform.
    """
    _apply_tracking((SKILL_COPILOT_DIR, SKILL_CLAUDE_DIR), tracking)

    helper = mk_exclude_from_git if tracking == "e" else mk_add_to_gitignore
    entries = helper.call_args[0][0]
    for entry, _ in entries:
        assert "\\" not in entry, f"entry {entry!r} carries a backslash git would read as an escape"
    assert [entry for entry, _ in entries] == [COPILOT_ENTRY, CLAUDE_ENTRY]


@pytest.mark.parametrize("tracking", ["e", "g"])
def test_apply_tracking_describes_the_folder_instead_of_repeating_the_path(
    tracking: str,
    mk_exclude_from_git: MagicMock,
    mk_add_to_gitignore: MagicMock,
) -> None:
    """The description half of each pair is the human label, not a second copy of the path.

    The helpers log "Excluded <description> in <file>", so repeating the path there produces a line
    that names the same thing twice and tells the reader nothing.
    """
    _apply_tracking((SKILL_COPILOT_DIR, SKILL_CLAUDE_DIR), tracking)

    helper = mk_exclude_from_git if tracking == "e" else mk_add_to_gitignore
    entries = helper.call_args[0][0]
    for entry, description in entries:
        assert description != entry, f"description for {entry!r} is just the path again"
        assert entry.rstrip("/") not in description, f"description {description!r} embeds the path"
    assert [description for _, description in entries] == [
        SKILL_DIR_LABEL[SKILL_COPILOT_DIR],
        SKILL_DIR_LABEL[SKILL_CLAUDE_DIR],
    ]


def test_skill_dir_label_covers_every_selectable_directory() -> None:
    """_apply_tracking looks the label up by directory, so every reachable target needs one."""
    reachable = {skill_dir for dirs in SKILL_TARGET_OPT.values() for skill_dir in dirs}
    assert reachable <= set(SKILL_DIR_LABEL), f"unlabelled skill directories: {reachable - set(SKILL_DIR_LABEL)}"


# ---------------------------------------------------------------------------
# _write_skill_files
# ---------------------------------------------------------------------------


def test_write_skill_files_creates_every_file_in_each_chosen_directory(
    tmp_path: Path, mk_ws_success_skill: MagicMock
) -> None:
    """Both files land in every selected directory, each with its own content."""
    dirs = (tmp_path / ".github" / "skills" / "mgsnake", tmp_path / ".claude" / "skills" / "mgsnake")

    written = _write_skill_files(dirs, SAMPLE_FILES)

    for skill_dir in dirs:
        for file_name, expected in SAMPLE_FILES.items():
            target = skill_dir / file_name
            assert target.is_file(), f"Expected {target} to be written"
            assert target.read_text(encoding="utf-8") == expected, f"{target} holds the wrong document"

    assert len(written) == 4, f"expected two files per directory, got {written}"
    assert mk_ws_success_skill.call_count == 4


def test_write_skill_files_returns_paths(tmp_path: Path, mk_ws_success_skill: MagicMock) -> None:
    """_write_skill_files should return the list of Path objects that were written."""
    dirs = (tmp_path / ".github" / "skills" / "mgsnake",)

    written = _write_skill_files(dirs, SAMPLE_FILES)

    assert written == [dirs[0] / SKILL_FILE, dirs[0] / REFERENCE_FILE]


# ---------------------------------------------------------------------------
# _check_all_existing_skill_files
# ---------------------------------------------------------------------------


def test_check_all_existing_skill_files_skips_missing(tmp_path: Path) -> None:
    """_check_all_existing_skill_files should silently pass when no skill files exist."""
    with patch(
        "mega_snake.docs_gen.generate_skill.ALL_SKILL_DIRS",
        (tmp_path / ".github" / "skills" / "mgsnake", tmp_path / ".claude" / "skills" / "mgsnake"),
    ):
        _check_all_existing_skill_files(SAMPLE_FILES)  # Must not raise


def test_check_all_existing_skill_files_passes_when_up_to_date(tmp_path: Path) -> None:
    """_check_all_existing_skill_files should pass when existing skill files match the rendered output."""
    skill_dir = tmp_path / ".github" / "skills" / "mgsnake"
    skill_dir.mkdir(parents=True)
    for file_name, content in SAMPLE_FILES.items():
        (skill_dir / file_name).write_text(content, encoding="utf-8")

    with patch(
        "mega_snake.docs_gen.generate_skill.ALL_SKILL_DIRS",
        (skill_dir, tmp_path / ".claude" / "skills" / "mgsnake"),
    ):
        _check_all_existing_skill_files(SAMPLE_FILES)  # Must not raise


@pytest.mark.parametrize("stale_file", [SKILL_FILE, REFERENCE_FILE])
def test_check_all_existing_skill_files_fails_when_any_file_is_stale(stale_file: str, tmp_path: Path) -> None:
    """A stale file is reported whichever of the two it is.

    Parametrized over both names on purpose: a --check that only looked at SKILL.md would pass on a
    checkout whose reference.md still describes commands that no longer exist, and the index -- the
    half that does get checked -- would look perfectly current while it did.
    """
    from mega_snake.util.formatting import ValidationError

    skill_dir = tmp_path / ".github" / "skills" / "mgsnake"
    skill_dir.mkdir(parents=True)
    for file_name, content in SAMPLE_FILES.items():
        (skill_dir / file_name).write_text(content, encoding="utf-8")
    (skill_dir / stale_file).write_text("stale content", encoding="utf-8")

    with (
        patch("mega_snake.docs_gen.generate_skill.ALL_SKILL_DIRS", (skill_dir,)),
        pytest.raises(ValidationError, match=stale_file),
    ):
        _check_all_existing_skill_files(SAMPLE_FILES)


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
        for file_name, content in SAMPLE_FILES.items():
            (skill_dir / file_name).write_text(content, encoding="utf-8")
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
        copilot_dir = Path(iso) / ".github" / "skills" / "mgsnake"
        assert (copilot_dir / SKILL_FILE).read_text(encoding="utf-8") == SAMPLE_DOCUMENT
        assert (copilot_dir / REFERENCE_FILE).read_text(encoding="utf-8") == SAMPLE_MARKDOWN
        claude_dir = Path(iso) / ".claude" / "skills" / "mgsnake"
        assert not claude_dir.exists(), "the Claude skill folder should NOT have been created"

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
        claude_dir = Path(iso) / ".claude" / "skills" / "mgsnake"
        assert (claude_dir / SKILL_FILE).is_file(), "Claude SKILL.md should have been created"
        assert (claude_dir / REFERENCE_FILE).is_file(), "Claude reference.md should have been created"
        copilot_dir = Path(iso) / ".github" / "skills" / "mgsnake"
        assert not copilot_dir.exists(), "the Copilot skill folder should NOT have been created"

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
            for file_name in SAMPLE_FILES:
                f = Path(iso) / sub / file_name
                assert f.is_file(), f"{sub}/{file_name} should have been created"

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


def test_generate_skill_writes_the_frontmatter_to_disk(
    mk_render: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_exclude_from_git: MagicMock,
    tmp_path: Path,
) -> None:
    """The file that lands on disk is the frontmatter document, not the bare reference."""
    mk_get_validated_input.side_effect = ["c", "e"]
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        result = runner.invoke(generate_skill, [])
        written = (Path(iso) / ".github" / "skills" / "mgsnake" / SKILL_FILE).read_text(encoding="utf-8")

    assert result.exit_code == 0, result.output
    assert written.startswith(f"---\nname: {SKILL_NAME}\n"), f"file opens with {written[:40]!r}"
    assert not written.startswith("# Available Commands"), "the bare reference is not a loadable skill"
    assert SAMPLE_MARKDOWN not in written, "the eagerly loaded body must not carry the full reference"


def test_generate_skill_check_rejects_a_file_missing_its_frontmatter(
    mk_render: MagicMock,
    tmp_path: Path,
) -> None:
    """--check compares the frontmatter too, so a body-only file is reported stale.

    This is the file every version of the command before the frontmatter existed produced, and the
    one case that distinguishes a --check covering the whole document from one covering the body.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        skill_dir = Path(iso) / ".claude" / "skills" / "mgsnake"
        skill_dir.mkdir(parents=True)
        (skill_dir / SKILL_FILE).write_text(SAMPLE_INDEX, encoding="utf-8")
        result = runner.invoke(generate_skill, ["--check"])

    assert result.exit_code == VALIDATION_ERROR_CODE, result.output
    assert result.exit_code != 1


def test_generate_skill_writes_nothing_when_the_target_prompt_is_abandoned(
    mk_render: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_exclude_from_git: MagicMock,
    mk_add_to_gitignore: MagicMock,
    tmp_path: Path,
) -> None:
    """Exhausting the retries on the first prompt leaves the working tree untouched."""
    mk_get_validated_input.side_effect = KeyError("too many invalid inputs")
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        result = runner.invoke(generate_skill, [])
        leftovers = sorted(str(path) for path in Path(iso).rglob('*.md'))

    assert isinstance(result.exception, KeyError), f"expected the KeyError to propagate, got {result.exception!r}"
    assert leftovers == [], f"the failed run left files behind: {leftovers}"
    mk_exclude_from_git.assert_not_called()
    mk_add_to_gitignore.assert_not_called()


def test_generate_skill_writes_nothing_when_the_tracking_prompt_is_abandoned(
    mk_render: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_exclude_from_git: MagicMock,
    mk_add_to_gitignore: MagicMock,
    tmp_path: Path,
) -> None:
    """A valid target followed by a fumbled tracking answer must still leave nothing on disk.

    Asking both questions before writing is what makes this true: writing first would strand
    SKILL.md files that are neither excluded nor gitignored, with the command exiting non-zero.
    """
    mk_get_validated_input.side_effect = ["b", KeyError("too many invalid inputs")]
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        result = runner.invoke(generate_skill, [])
        leftovers = sorted(str(path) for path in Path(iso).rglob('*.md'))

    assert isinstance(result.exception, KeyError), f"expected the KeyError to propagate, got {result.exception!r}"
    assert leftovers == [], f"the failed run left files behind: {leftovers}"
    mk_exclude_from_git.assert_not_called()
    mk_add_to_gitignore.assert_not_called()


def test_generate_skill_prompts_for_both_answers_before_writing(
    mk_render: MagicMock,
    mk_exclude_from_git: MagicMock,
    tmp_path: Path,
) -> None:
    """No SKILL.md exists yet at the moment the tracking prompt is answered.

    Ordering is the whole point of the two tests above; this one pins it directly rather than
    inferring it from a failure, so a refactor that reorders the calls fails here with a clear cause.
    """
    runner = CliRunner()
    seen: list[list[str]] = []

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:

        def record(prompt: str, valid: list[str]) -> str:
            """Answer each prompt while recording what was on disk when it was asked."""
            seen.append(sorted(str(path) for path in Path(iso).rglob('*.md')))
            return "b" if "assistant" in prompt else "e"

        with patch("mega_snake.docs_gen.generate_skill.get_validated_input", side_effect=record):
            result = runner.invoke(generate_skill, [])
        written = sorted(str(path) for path in Path(iso).rglob('*.md'))

    assert result.exit_code == 0, result.output
    assert seen == [[], []], f"a skill file already existed when a prompt was asked: {seen}"
    assert len(written) == 4, f"both files should exist in both folders once finished, got {written}"
