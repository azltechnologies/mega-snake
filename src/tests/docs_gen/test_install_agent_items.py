"""Tests for the install-agent-items command."""

from pathlib import Path, PureWindowsPath
from typing import Generator
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from mega_snake.docs_gen.install_agent_items import (
    STATE_ABSENT,
    STATE_CURRENT,
    STATE_STALE,
    TARGET_OPT,
    TRACKING_KEYS,
    _apply_tracking,
    _check_existing_files,
    _report_dependencies,
    _resolve_compatibility,
    _selection_prompt,
    _tracking_entries,
    _write_items,
    install_agent_items,
    item_state,
)
from mega_snake.docs_gen.item_registry import (
    ALL_RUNTIMES,
    KIND_AGENT,
    REFERENCE_FILE,
    RUNTIME_CLAUDE,
    RUNTIME_COPILOT,
    SKILL_FILE,
    Item,
)
from mega_snake.docs_gen.item_catalog import CLI_SKILL_NAME, ITEMS, ITEMS
from mega_snake.util.formatting import VALIDATION_ERROR_CODE, ValidationError

# Rendered content, distinct per file so a test can tell which one landed where. Neither string is a
# substring of the other.
SKILL_BODY = '---\nname: mgsnake\ndescription: "x"\n---\n\nINDEX BODY\n'
REFERENCE_BODY = "# Available Commands\n\nFULL REFERENCE\n"
CLI_FILES: dict[str, str] = {SKILL_FILE: SKILL_BODY, REFERENCE_FILE: REFERENCE_BODY}
RENDERED: dict[str, dict[str, str]] = {CLI_SKILL_NAME: CLI_FILES}

# Literal patterns the tracking helpers must receive. Written out instead of derived from the
# registry so the expectation cannot restate the expression under test.
COPILOT_SKILL_ENTRY = f".github/skills/{CLI_SKILL_NAME}/"
CLAUDE_SKILL_ENTRY = f".claude/skills/{CLI_SKILL_NAME}/"


def cli_item() -> Item:
    """Build a stand-in for the CLI skill, carrying only what the helpers read.

    Parameters:
        None

    Raises:
        None

    Returns:
        Item: A skill-kind item named after the CLI skill.
    """
    return Item(
        name=CLI_SKILL_NAME,
        summary="The command reference.",
        description="x",
        render=lambda item: CLI_FILES,
    )


@pytest.fixture(name="mk_render")
def fixture_mk_render() -> Generator[MagicMock, None, None]:
    """Patch item rendering so tests do not need a full CLI build."""
    with (
        patch("mega_snake.docs_gen.install_agent_items.item_names", return_value=[CLI_SKILL_NAME]),
        patch("mega_snake.docs_gen.install_agent_items.selectable_names", return_value=[CLI_SKILL_NAME]),
        patch("mega_snake.docs_gen.install_agent_items.expand_items", return_value=[CLI_SKILL_NAME]),
        patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=cli_item()) as mock,
    ):
        yield mock


@pytest.fixture(name="mk_get_validated_input")
def fixture_mk_get_validated_input() -> Generator[MagicMock, None, None]:
    """Patch get_validated_input in the generate_skill module."""
    with patch("mega_snake.docs_gen.install_agent_items.get_validated_input") as mock:
        yield mock


@pytest.fixture(name="mk_exclude_from_git")
def fixture_mk_exclude_from_git() -> Generator[MagicMock, None, None]:
    """Patch exclude_from_git in the generate_skill module."""
    with patch("mega_snake.docs_gen.install_agent_items.exclude_from_git") as mock:
        yield mock


@pytest.fixture(name="mk_add_to_gitignore")
def fixture_mk_add_to_gitignore() -> Generator[MagicMock, None, None]:
    """Patch add_to_gitignore in the generate_skill module."""
    with patch("mega_snake.docs_gen.install_agent_items.add_to_gitignore") as mock:
        yield mock


@pytest.fixture(name="mk_ws_success")
def fixture_mk_ws_success() -> Generator[MagicMock, None, None]:
    """Patch ws_success in the generate_skill module."""
    with patch("mega_snake.docs_gen.install_agent_items.ws_success") as mock:
        yield mock


@pytest.fixture(name="mk_ws_warning")
def fixture_mk_ws_warning() -> Generator[MagicMock, None, None]:
    """Patch ws_warning in the install_agent_items module."""
    with patch("mega_snake.docs_gen.install_agent_items.ws_warning") as mock:
        yield mock


@pytest.fixture(name="mk_ws_info")
def fixture_mk_ws_info() -> Generator[MagicMock, None, None]:
    """Patch ws_info in the generate_skill module."""
    with patch("mega_snake.docs_gen.install_agent_items.ws_info") as mock:
        yield mock


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------


def test_target_opt_maps_the_three_selection_keys() -> None:
    """TARGET_OPT must offer each runtime alone and both together."""
    assert set(TARGET_OPT) == {"c", "l", "b"}
    assert TARGET_OPT["c"] == (RUNTIME_COPILOT,)
    assert TARGET_OPT["l"] == (RUNTIME_CLAUDE,)
    assert TARGET_OPT["b"] == ALL_RUNTIMES


def test_tracking_keys() -> None:
    """TRACKING_KEYS must contain exactly the three expected keys."""
    assert set(TRACKING_KEYS) == {"e", "g", "v"}


# ---------------------------------------------------------------------------
# _tracking_entries
# ---------------------------------------------------------------------------


def test_tracking_entries_keeps_the_trailing_slash_only_for_a_directory() -> None:
    """A folder pattern needs the slash and a file pattern must not have one.

    ``foo.md/`` matches only a directory, so an agent excluded that way stays tracked with no error
    at all — the same silent class of failure as the backslash case below.
    """
    entries = _tracking_entries(
        [
            (Path(".claude") / "skills" / CLI_SKILL_NAME, "skill"),
            (Path(".claude") / "agents" / "an-agent.md", "agent"),
        ]
    )

    assert entries[0][0] == CLAUDE_SKILL_ENTRY
    assert entries[1][0] == ".claude/agents/an-agent.md"
    assert not entries[1][0].endswith("/"), "a file pattern gained a directory-only slash"


def test_tracking_entries_uses_forward_slashes_on_a_windows_style_path() -> None:
    """A Windows-shaped path must still yield a posix pattern git can actually match.

    PureWindowsPath is what makes this test discriminate on any host: on Linux str() and as_posix()
    agree, so only a genuinely Windows-flavoured path can tell a correct implementation from the
    str() one, where git reads the backslashes as escapes and the pattern matches nothing.
    """
    windows_dir = PureWindowsPath(".github") / "skills" / CLI_SKILL_NAME
    assert "\\" in str(windows_dir), "fixture is not exercising a backslash-separated path"

    entries = _tracking_entries([(windows_dir, "GitHub Copilot skill 'mgsnake'")])

    assert entries == [(COPILOT_SKILL_ENTRY, "GitHub Copilot skill 'mgsnake'")], f"got {entries}"
    assert "\\" not in entries[0][0]


@pytest.mark.parametrize("tracking", ["e", "g"])
def test_apply_tracking_forwards_the_entries_to_the_right_helper(
    tracking: str,
    mk_exclude_from_git: MagicMock,
    mk_add_to_gitignore: MagicMock,
) -> None:
    """'e' writes .git/info/exclude and 'g' writes .gitignore, never both."""
    _apply_tracking([(Path(".claude") / "skills" / CLI_SKILL_NAME, "Claude skill 'mgsnake'")], tracking)

    used = mk_exclude_from_git if tracking == "e" else mk_add_to_gitignore
    unused = mk_add_to_gitignore if tracking == "e" else mk_exclude_from_git
    assert used.call_args[0][0] == [(CLAUDE_SKILL_ENTRY, "Claude skill 'mgsnake'")]
    unused.assert_not_called()


def test_apply_tracking_describes_the_item_instead_of_repeating_the_path(
    mk_exclude_from_git: MagicMock,
) -> None:
    """The description names the item for a reader; repeating the path says nothing new."""
    _apply_tracking([(Path(".claude") / "skills" / CLI_SKILL_NAME, "Claude skill 'mgsnake'")], "e")

    entry, description = mk_exclude_from_git.call_args[0][0][0]
    assert description != entry
    assert entry.rstrip("/") not in description, f"description {description!r} embeds the path"


def test_apply_tracking_versioned_emits_success(mk_ws_success: MagicMock) -> None:
    """Choosing 'v' leaves the files versioned and reports success — no git helpers called."""
    with (
        patch("mega_snake.docs_gen.install_agent_items.exclude_from_git") as mk_exc,
        patch("mega_snake.docs_gen.install_agent_items.add_to_gitignore") as mk_ign,
    ):
        _apply_tracking([(Path(".claude") / "skills" / CLI_SKILL_NAME, "Claude skill")], "v")

    mk_ws_success.assert_called_once()
    mk_exc.assert_not_called()
    mk_ign.assert_not_called()


# ---------------------------------------------------------------------------
# item_state
# ---------------------------------------------------------------------------


def _install(root: Path, files: dict[str, str]) -> Path:
    """Write the CLI skill's files under a project root, as a finished install would leave them.

    Parameters:
        root: The project root.
        files: File name to content.

    Raises:
        None

    Returns:
        Path: The directory that was written.
    """
    directory = root / ".claude" / "skills" / CLI_SKILL_NAME
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (directory / name).write_text(content, encoding="utf-8")
    return directory


def test_item_state_reports_absent_when_nothing_is_installed(tmp_path: Path) -> None:
    """Nothing on disk is 'not installed', never 'stale'."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        assert item_state(cli_item(), RUNTIME_CLAUDE, CLI_FILES) == STATE_ABSENT


def test_item_state_reports_current_when_every_file_matches(tmp_path: Path) -> None:
    """All files present and matching is the only way to be current."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        _install(Path(iso), CLI_FILES)
        assert item_state(cli_item(), RUNTIME_CLAUDE, CLI_FILES) == STATE_CURRENT


def test_item_state_reports_stale_when_only_the_reference_drifted(tmp_path: Path) -> None:
    """A fresh SKILL.md with a stale reference beside it is stale, not current.

    The discriminating case: a state derived from SKILL.md alone would report a current install while
    the document it points at described commands that no longer exist.
    """
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        directory = _install(Path(iso), CLI_FILES)
        (directory / REFERENCE_FILE).write_text("outdated", encoding="utf-8")
        assert item_state(cli_item(), RUNTIME_CLAUDE, CLI_FILES) == STATE_STALE


def test_item_state_reports_stale_when_a_file_is_missing(tmp_path: Path) -> None:
    """A half-written install is stale, never absent: something is there and it is wrong."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        _install(Path(iso), {SKILL_FILE: SKILL_BODY})
        assert item_state(cli_item(), RUNTIME_CLAUDE, CLI_FILES) == STATE_STALE


# ---------------------------------------------------------------------------
# The selection prompt
# ---------------------------------------------------------------------------

DEPENDENT = "jira-continue"


def _two_item_registry() -> MagicMock:
    """Build a get_item double for a catalogue of two, the second bundling the first.

    Parameters:
        None

    Raises:
        None

    Returns:
        MagicMock: A get_item stand-in resolving both names.
    """
    dependent = Item(
        name=DEPENDENT,
        summary="Resume a Jira story.",
        description="d",
        render=lambda item: {SKILL_FILE: "body"},
        requires=(CLI_SKILL_NAME,),
    )
    return MagicMock(side_effect=lambda name: {CLI_SKILL_NAME: cli_item(), DEPENDENT: dependent}[name])


def test_selection_prompt_lists_every_offered_item_with_its_kind_and_state(tmp_path: Path) -> None:
    """Installed items stay on the list, annotated, so they can be refreshed."""
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", _two_item_registry()),
        patch(
            "mega_snake.docs_gen.install_agent_items.selectable_names",
            return_value=[CLI_SKILL_NAME, DEPENDENT],
        ),
        patch("mega_snake.docs_gen.install_agent_items.bundled_with", return_value=[]),
        runner.isolated_filesystem(temp_dir=tmp_path),
    ):
        prompt = _selection_prompt({CLI_SKILL_NAME: CLI_FILES, DEPENDENT: {SKILL_FILE: "body"}})

    assert CLI_SKILL_NAME in prompt
    assert DEPENDENT in prompt
    assert "[skill]" in prompt, "the item kind is not shown"
    assert STATE_ABSENT in prompt, "the state annotation is missing"


def test_selection_prompt_announces_what_comes_bundled(tmp_path: Path) -> None:
    """What an item drags along is shown before the choice, while it can still change it."""
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", _two_item_registry()),
        patch("mega_snake.docs_gen.install_agent_items.selectable_names", return_value=[DEPENDENT]),
        patch("mega_snake.docs_gen.install_agent_items.bundled_with", return_value=[CLI_SKILL_NAME]),
        runner.isolated_filesystem(temp_dir=tmp_path),
    ):
        prompt = _selection_prompt({DEPENDENT: {SKILL_FILE: "body"}})

    assert f"installs with it: {CLI_SKILL_NAME}" in prompt, f"bundle not disclosed: {prompt!r}"


def test_selection_prompt_reports_a_state_per_runtime(tmp_path: Path) -> None:
    """An item installed for one assistant and not the other must say which is which."""
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", _two_item_registry()),
        patch("mega_snake.docs_gen.install_agent_items.selectable_names", return_value=[CLI_SKILL_NAME]),
        patch("mega_snake.docs_gen.install_agent_items.bundled_with", return_value=[]),
        runner.isolated_filesystem(temp_dir=tmp_path) as iso,
    ):
        _install(Path(iso), CLI_FILES)
        prompt = _selection_prompt({CLI_SKILL_NAME: CLI_FILES})

    assert f"{STATE_CURRENT}: Claude" in prompt, f"the installed runtime is not named: {prompt!r}"
    assert f"{STATE_ABSENT}: GitHub Copilot" in prompt, f"the missing runtime is not named: {prompt!r}"


def test_prompt_items_does_not_ask_when_only_one_is_offered(mk_ws_info: MagicMock) -> None:
    """A single-option multiple choice is a question with one answer; it is reported, not asked."""
    from mega_snake.docs_gen.install_agent_items import _prompt_items

    with (
        patch("mega_snake.docs_gen.install_agent_items.selectable_names", return_value=[CLI_SKILL_NAME]),
        patch("mega_snake.docs_gen.install_agent_items.get_validated_selection") as mk_selection,
    ):
        chosen = _prompt_items(RENDERED)

    assert chosen == [CLI_SKILL_NAME]
    mk_selection.assert_not_called()
    mk_ws_info.assert_called_once()


def test_prompt_items_asks_when_there_is_a_real_choice(tmp_path: Path) -> None:
    """With more than one item offered, the multi-select prompt is used."""
    from mega_snake.docs_gen.install_agent_items import _prompt_items

    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", _two_item_registry()),
        patch(
            "mega_snake.docs_gen.install_agent_items.selectable_names",
            return_value=[CLI_SKILL_NAME, DEPENDENT],
        ),
        patch("mega_snake.docs_gen.install_agent_items.bundled_with", return_value=[]),
        patch(
            "mega_snake.docs_gen.install_agent_items.get_validated_selection",
            return_value=[DEPENDENT],
        ) as mk_selection,
        runner.isolated_filesystem(temp_dir=tmp_path),
    ):
        chosen = _prompt_items({CLI_SKILL_NAME: CLI_FILES, DEPENDENT: {SKILL_FILE: "body"}})

    assert chosen == [DEPENDENT]
    assert mk_selection.call_args[0][1] == [CLI_SKILL_NAME, DEPENDENT], "the offered names are wrong"


# ---------------------------------------------------------------------------
# _report_dependencies
# ---------------------------------------------------------------------------


def test_report_dependencies_says_nothing_when_nothing_was_added(mk_ws_info: MagicMock) -> None:
    """A selection that needs nothing extra must not print a dependency line."""
    with patch("mega_snake.docs_gen.install_agent_items.required_by", return_value={}):
        _report_dependencies([CLI_SKILL_NAME])

    mk_ws_info.assert_not_called()


def test_report_dependencies_names_both_the_addition_and_its_reason(mk_ws_info: MagicMock) -> None:
    """The message must name what is being installed and what asked for it."""
    with patch(
        "mega_snake.docs_gen.install_agent_items.required_by",
        return_value={CLI_SKILL_NAME: [DEPENDENT]},
    ):
        _report_dependencies([DEPENDENT])

    message = mk_ws_info.call_args[0][0]
    assert CLI_SKILL_NAME in message, f"the added item is not named: {message!r}"
    assert DEPENDENT in message, f"the reason is not named: {message!r}"


# ---------------------------------------------------------------------------
# Writing and checking
# ---------------------------------------------------------------------------


def test_write_items_creates_every_file_for_every_runtime(
    mk_render: MagicMock, mk_ws_success: MagicMock, tmp_path: Path
) -> None:
    """Both files land under both runtimes, each with its own content."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        written = _write_items(ALL_RUNTIMES, RENDERED)
        for root in (".github", ".claude"):
            for file_name, expected in CLI_FILES.items():
                target = Path(iso) / root / "skills" / CLI_SKILL_NAME / file_name
                assert target.read_text(encoding="utf-8") == expected, f"{target} holds the wrong document"

    assert len(written) == 4, f"expected two files per runtime, got {written}"


def test_write_items_puts_an_agent_in_a_single_runtime_specific_file(
    mk_ws_success: MagicMock, tmp_path: Path
) -> None:
    """An agent is one file, and its name differs per runtime."""
    an_agent = Item(
        name="an-agent",
        summary="s",
        description="d",
        render=lambda item: {"ignored": "AGENT BODY"},
        kind=KIND_AGENT,
    )
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=an_agent),
        runner.isolated_filesystem(temp_dir=tmp_path) as iso,
    ):
        _write_items(ALL_RUNTIMES, {"an-agent": {"ignored": "AGENT BODY"}})
        copilot = Path(iso) / ".github" / "agents" / "an-agent.agent.md"
        claude = Path(iso) / ".claude" / "agents" / "an-agent.md"

    assert copilot.read_text(encoding="utf-8") == "AGENT BODY"
    assert claude.read_text(encoding="utf-8") == "AGENT BODY"
    assert not (Path(iso) / ".claude" / "agents" / "an-agent.agent.md").exists(), "wrong suffix for Claude"


@pytest.mark.parametrize("stale_file", [SKILL_FILE, REFERENCE_FILE])
def test_check_reports_a_stale_file_whichever_one_it_is(
    stale_file: str, mk_render: MagicMock, tmp_path: Path
) -> None:
    """A --check that only looked at SKILL.md would pass on a stale reference."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        directory = _install(Path(iso), CLI_FILES)
        (directory / stale_file).write_text("stale content", encoding="utf-8")
        with pytest.raises(ValidationError, match=stale_file):
            _check_existing_files(RENDERED)


def test_check_skips_files_that_do_not_exist(mk_render: MagicMock, tmp_path: Path) -> None:
    """--check validates what is kept; it does not mandate that anything is installed."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _check_existing_files(RENDERED)  # Must not raise


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def test_install_agent_items_check_passes_when_nothing_is_installed(mk_render: MagicMock, tmp_path: Path) -> None:
    """--check exits 0 when nothing exists on disk."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(install_agent_items, ["--check"])

    assert result.exit_code == 0, result.output


def test_install_agent_items_check_fails_when_stale(mk_render: MagicMock, tmp_path: Path) -> None:
    """--check exits with VALIDATION_ERROR_CODE when any installed file is stale."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        directory = Path(iso) / ".claude" / "skills" / CLI_SKILL_NAME
        directory.mkdir(parents=True)
        (directory / SKILL_FILE).write_text("outdated", encoding="utf-8")
        result = runner.invoke(install_agent_items, ["--check"])

    assert result.exit_code == VALIDATION_ERROR_CODE
    assert result.exit_code != 1


def test_install_agent_items_check_never_prompts(mk_render: MagicMock, tmp_path: Path) -> None:
    """--check is the mode a CI step runs, so it must not reach an interactive prompt."""
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_validated_input") as mk_input,
        patch("mega_snake.docs_gen.install_agent_items.get_validated_selection") as mk_selection,
        runner.isolated_filesystem(temp_dir=tmp_path),
    ):
        result = runner.invoke(install_agent_items, ["--check"])

    assert result.exit_code == 0, result.output
    mk_input.assert_not_called()
    mk_selection.assert_not_called()


def test_install_agent_items_flags_make_the_run_non_interactive(
    mk_render: MagicMock,
    mk_exclude_from_git: MagicMock,
    tmp_path: Path,
) -> None:
    """With --skill, --target and --tracking nothing is asked, so a hook or CI step can run it."""
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_validated_input") as mk_input,
        patch("mega_snake.docs_gen.install_agent_items.get_validated_selection") as mk_selection,
        runner.isolated_filesystem(temp_dir=tmp_path) as iso,
    ):
        result = runner.invoke(
            install_agent_items,
            ["--item", CLI_SKILL_NAME, "--target", "l", "--tracking", "e"],
        )
        written = (Path(iso) / ".claude" / "skills" / CLI_SKILL_NAME / SKILL_FILE).read_text(encoding="utf-8")

    assert result.exit_code == 0, result.output
    mk_input.assert_not_called()
    mk_selection.assert_not_called()
    assert written == SKILL_BODY
    mk_exclude_from_git.assert_called_once()


def test_install_agent_items_target_flag_writes_only_that_runtime(
    mk_render: MagicMock,
    mk_exclude_from_git: MagicMock,
    tmp_path: Path,
) -> None:
    """--target l installs for Claude and leaves the Copilot tree alone."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        result = runner.invoke(
            install_agent_items,
            ["--item", CLI_SKILL_NAME, "--target", "l", "--tracking", "v"],
        )

    assert result.exit_code == 0, result.output
    assert (Path(iso) / ".claude" / "skills" / CLI_SKILL_NAME / SKILL_FILE).is_file()
    assert not (Path(iso) / ".github").exists(), "the unselected runtime's tree was created"


def test_install_agent_items_asks_everything_before_writing(
    mk_render: MagicMock,
    mk_exclude_from_git: MagicMock,
    tmp_path: Path,
) -> None:
    """Nothing exists on disk at the moment any prompt is answered.

    Writing first would strand files that are neither excluded nor gitignored for a user who only
    fumbled a later answer.
    """
    runner = CliRunner()
    seen: list[list[str]] = []

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:

        def record(prompt: str, valid: list[str]) -> str:
            """Answer a prompt while recording what was on disk when it was asked."""
            seen.append(sorted(str(path) for path in Path(iso).rglob("*.md")))
            return "b" if "assistant" in prompt else "e"

        with patch("mega_snake.docs_gen.install_agent_items.get_validated_input", side_effect=record):
            result = runner.invoke(install_agent_items, [])
        written = sorted(str(path) for path in Path(iso).rglob("*.md"))

    assert result.exit_code == 0, result.output
    assert seen == [[], []], f"a file already existed when a prompt was asked: {seen}"
    assert len(written) == 4, f"both files should exist for both runtimes, got {written}"


def test_install_agent_items_writes_nothing_when_a_prompt_is_abandoned(
    mk_render: MagicMock,
    mk_get_validated_input: MagicMock,
    mk_exclude_from_git: MagicMock,
    mk_add_to_gitignore: MagicMock,
    tmp_path: Path,
) -> None:
    """Exhausting the retries on the tracking prompt leaves the working tree untouched."""
    mk_get_validated_input.side_effect = ["b", KeyError("too many invalid inputs")]
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path) as iso:
        result = runner.invoke(install_agent_items, [])
        leftovers = sorted(str(path) for path in Path(iso).rglob("*.md"))

    assert isinstance(result.exception, KeyError), f"expected the KeyError to propagate, got {result.exception!r}"
    assert leftovers == [], f"the failed run left files behind: {leftovers}"
    mk_exclude_from_git.assert_not_called()
    mk_add_to_gitignore.assert_not_called()


def test_install_agent_items_installs_a_required_item_and_reports_it(
    mk_ws_info: MagicMock,
    mk_exclude_from_git: MagicMock,
    tmp_path: Path,
) -> None:
    """Naming only a dependent item still installs what it requires, and says so."""
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.item_names", return_value=[CLI_SKILL_NAME]),
        patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=cli_item()),
        patch("mega_snake.docs_gen.install_agent_items.expand_items", return_value=[CLI_SKILL_NAME]),
        patch(
            "mega_snake.docs_gen.install_agent_items.required_by",
            return_value={CLI_SKILL_NAME: [DEPENDENT]},
        ),
        runner.isolated_filesystem(temp_dir=tmp_path) as iso,
    ):
        result = runner.invoke(
            install_agent_items,
            ["--item", CLI_SKILL_NAME, "--target", "l", "--tracking", "e"],
        )
        installed = (Path(iso) / ".claude" / "skills" / CLI_SKILL_NAME / SKILL_FILE).is_file()

    assert result.exit_code == 0, result.output
    assert installed, "the required item was not installed"
    mk_ws_info.assert_called_once()


# ---------------------------------------------------------------------------
# The shipped catalogue, documented
# ---------------------------------------------------------------------------
#
# This block is the human-readable list of everything `install-agent-items` can install. It is a test
# and not a comment on purpose: a comment describing a catalogue goes stale the first time somebody
# adds an item and forgets it, whereas this fails, names the item, and cannot be merged around.
#
# Adding an item means adding a row here. Keep the summary short -- it is the one-line description a
# user reads in the selection list.

EXPECTED_CATALOGUE: dict[str, dict[str, object]] = {
    # The command reference itself. Generated from the live CLI, never hand-written, and required by
    # every task skill: an assistant told to run mgsnake commands needs to know what they accept.
    "mgsnake": {
        "kind": "skill",
        "hidden": False,
        "requires": (),
        "about": "Index of every mgsnake command plus reference.md beside it, read on demand.",
    },
    # Resume work on a Jira story: one board download, then jq. Its prose lives in
    # resources/skills/jira-continue.md.
    "jira-continue": {
        "kind": "skill",
        "hidden": False,
        "requires": ("mgsnake",),
        "about": "Rebuilds a story's context from its comment history and records the agreed plan.",
    },
    # Report a day's progress on a story: one `diff-tree` run, then judgement. Its prose lives in
    # resources/skills/jira-progress-comment.md.
    "jira-progress-comment": {
        "kind": "skill",
        "hidden": False,
        "requires": ("mgsnake",),
        "about": "Drafts a progress comment from the commit range, and never publishes unapproved.",
    },
    # --- the comment-killer crew: one agent and the five components it bundles ---
    # All six are Claude-only: their headers fork other agents, take arguments and execute blocks,
    # none of which GitHub Copilot understands. The port is catalogued in §8.8.
    #
    # The kingpin is the only one offered. The five below are hidden because each is handed its
    # inputs by the kingpin and does nothing on its own.
    "comment-killer-kingpin": {
        "kind": "agent",
        "hidden": False,
        "requires": (
            "create-progress-folder",
            "create-progress-file",
            "comment-killer-spotter",
            "comment-killer-playermaker",
            "comment-killer-hitman",
        ),
        "about": "Orchestrates a review-comment run: investigate, plan, implement, verify, report.",
    },
    # Shells out to `mgsnake local-config-path`, which is what carries the whole crew to the CLI
    # skill transitively.
    "create-progress-folder": {
        "kind": "skill",
        "hidden": True,
        "requires": ("mgsnake",),
        "about": "Creates the mission folder every report of a run is written into.",
    },
    # Takes the folder the skill above returns as its only argument.
    "create-progress-file": {
        "kind": "skill",
        "hidden": True,
        "requires": ("create-progress-folder",),
        "about": "Creates one timestamped report file inside a mission folder.",
    },
    # A read-only fork of the Explore agent: decides whether the comment is still valid.
    "comment-killer-spotter": {
        "kind": "skill",
        "hidden": True,
        "requires": (),
        "about": "Investigates whether a review comment still applies, and gathers the code context.",
    },
    # A read-only fork of the Plan agent: turns the spotter's findings into a plan.
    "comment-killer-playermaker": {
        "kind": "skill",
        "hidden": True,
        "requires": (),
        "about": "Writes the implementation plan the hitman executes.",
    },
    # The only henchman that may write: applies the plan, verifies it, files its own report.
    "comment-killer-hitman": {
        "kind": "skill",
        "hidden": True,
        "requires": (),
        "about": "Carries out the plan, runs the verification, and documents the outcome.",
    },
}

# Items that cannot be installed for every runtime, and the runtimes each one supports. Kept beside
# the catalogue so a new restriction has to be acknowledged here rather than discovered by a user
# whose install came out half empty.
EXPECTED_RUNTIME_LIMITS: dict[str, tuple[str, ...]] = {
    "comment-killer-kingpin": (RUNTIME_CLAUDE,),
    "create-progress-folder": (RUNTIME_CLAUDE,),
    "create-progress-file": (RUNTIME_CLAUDE,),
    "comment-killer-spotter": (RUNTIME_CLAUDE,),
    "comment-killer-playermaker": (RUNTIME_CLAUDE,),
    "comment-killer-hitman": (RUNTIME_CLAUDE,),
}


def test_the_catalogue_is_exactly_what_is_documented_here() -> None:
    """Every shipped item appears in EXPECTED_CATALOGUE, and nothing else does.

    Compared as whole sets rather than by containment, so both directions fail loudly: an item added
    to the registry without a row here, and a row left behind by an item that was removed.
    """
    assert {item.name for item in ITEMS} == set(EXPECTED_CATALOGUE), (
        "the shipped catalogue and the documented one disagree; update EXPECTED_CATALOGUE"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED_CATALOGUE))
def test_each_item_matches_its_documented_shape(name: str) -> None:
    """Kind, visibility and dependencies are pinned per item.

    Parametrized over the documented names so a failure names the item, and derived from the
    production catalogue for the actual values so the assertion cannot restate itself.
    """
    expected = EXPECTED_CATALOGUE[name]
    item = next(candidate for candidate in ITEMS if candidate.name == name)

    assert item.kind == expected["kind"], f"{name} is a {item.kind}, documented as {expected['kind']}"
    assert item.hidden == expected["hidden"], f"{name} visibility differs from the documented one"
    assert item.requires == expected["requires"], f"{name} requires {item.requires}, documented {expected['requires']}"


@pytest.mark.parametrize("name", sorted(EXPECTED_CATALOGUE))
def test_each_item_carries_a_usable_summary_and_description(name: str) -> None:
    """The summary is what the selection list shows and the description is what triggers the item.

    An empty either one ships an entry a user cannot choose between, or an item an assistant never
    activates -- both of which install cleanly and fail silently.
    """
    item = next(candidate for candidate in ITEMS if candidate.name == name)

    assert item.summary.strip(), f"{name} has no summary for the selection list"
    assert item.description.strip(), f"{name} has no frontmatter description"
    assert '"' not in item.description, f"{name} would break its quoted YAML scalar"


# ---------------------------------------------------------------------------
# Runtime compatibility, at the command level
# ---------------------------------------------------------------------------

CLAUDE_ONLY = "claude-only-item"


def claude_only_item() -> Item:
    """Build an item that only one runtime can read.

    Parameters:
        None

    Raises:
        None

    Returns:
        Item: A Claude-only skill.
    """
    return Item(
        name=CLAUDE_ONLY,
        summary="Uses vocabulary only Claude understands.",
        description="d",
        render=lambda item: {SKILL_FILE: "CLAUDE ONLY BODY"},
        runtimes=(RUNTIME_CLAUDE,),
    )


def test_write_items_skips_a_runtime_the_item_cannot_run_on(mk_ws_success: MagicMock, tmp_path: Path) -> None:
    """Writing a Claude-only item for both runtimes must leave the Copilot tree untouched.

    A file written where the runtime cannot read it installs cleanly and then behaves nothing like
    what was authored — worse than not installing it, because it looks installed.
    """
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=claude_only_item()),
        runner.isolated_filesystem(temp_dir=tmp_path) as iso,
    ):
        written = _write_items(ALL_RUNTIMES, {CLAUDE_ONLY: {SKILL_FILE: "CLAUDE ONLY BODY"}})

    assert len(written) == 1, f"expected one file, got {written}"
    assert (Path(iso) / ".claude" / "skills" / CLAUDE_ONLY / SKILL_FILE).is_file()
    assert not (Path(iso) / ".github").exists(), "a file was written for the unsupported runtime"


def test_describe_states_never_mentions_an_unsupported_runtime(tmp_path: Path) -> None:
    """"not installed: GitHub Copilot" would be a lie for an item that never goes there."""
    from mega_snake.docs_gen.install_agent_items import _describe_states

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        described = _describe_states(claude_only_item(), {SKILL_FILE: "CLAUDE ONLY BODY"})

    assert "Claude" in described
    assert "GitHub Copilot" not in described, f"an unsupported runtime was reported: {described!r}"


def test_selection_prompt_marks_an_item_that_only_one_runtime_can_read(tmp_path: Path) -> None:
    """Compatibility is disclosed before the choice, not after the write."""
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=claude_only_item()),
        patch("mega_snake.docs_gen.install_agent_items.selectable_names", return_value=[CLAUDE_ONLY]),
        patch("mega_snake.docs_gen.install_agent_items.bundled_with", return_value=[]),
        runner.isolated_filesystem(temp_dir=tmp_path),
    ):
        prompt = _selection_prompt({CLAUDE_ONLY: {SKILL_FILE: "CLAUDE ONLY BODY"}})

    assert "Claude only" in prompt, f"the restriction is not disclosed: {prompt!r}"


def test_a_partial_install_warns_but_succeeds(mk_ws_warning: MagicMock) -> None:
    """'both' means 'wherever it fits', so dropping one runtime is reported, never an error."""
    with patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=claude_only_item()):
        _resolve_compatibility({CLAUDE_ONLY: {}}, ALL_RUNTIMES, [CLAUDE_ONLY])

    message = mk_ws_warning.call_args[0][0]
    assert CLAUDE_ONLY in message
    assert "GitHub Copilot" in message, f"the skipped runtime is not named: {message!r}"


def test_an_explicitly_selected_item_that_fits_nowhere_is_an_invocation_error(
    mk_ws_warning: MagicMock,
) -> None:
    """Asking for something impossible must fail, not install nothing and exit 0.

    The discriminating pair with the test above: same item, same code path, and the only difference
    is whether any chosen runtime can take it. Installing zero files while reporting success is the
    outcome this refuses.
    """
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=claude_only_item()),
        pytest.raises(click.ClickException, match=CLAUDE_ONLY),
    ):
        _resolve_compatibility({CLAUDE_ONLY: {}}, (RUNTIME_COPILOT,), [CLAUDE_ONLY])


def test_an_incompatible_dependency_warns_instead_of_failing(mk_ws_warning: MagicMock) -> None:
    """The user asked for the parent, not for this — so it is reported, not raised.

    Told apart from the error above by whether the name is in the selection, never by how much was
    dropped: failing here would refuse an install the user did ask for because of a component they
    never named.
    """
    with patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=claude_only_item()):
        _resolve_compatibility({CLAUDE_ONLY: {}}, (RUNTIME_COPILOT,), ["some-other-item"])

    message = mk_ws_warning.call_args[0][0]
    assert CLAUDE_ONLY in message
    assert "dependency" in message, f"the message does not say why it arrived: {message!r}"


def test_a_portable_item_produces_no_compatibility_message(mk_ws_warning: MagicMock) -> None:
    """The common case must stay silent; a warning on every run trains the user to ignore them."""
    with patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=cli_item()):
        _resolve_compatibility({CLI_SKILL_NAME: {}}, ALL_RUNTIMES, [CLI_SKILL_NAME])

    mk_ws_warning.assert_not_called()


def test_check_ignores_a_file_sitting_where_the_item_cannot_run(tmp_path: Path) -> None:
    """A leftover under an unsupported runtime is not this item's file, so --check must not judge it.

    Without the skip, a directory left behind by an earlier version — or by a hand copy — would be
    compared against content that is never written there, and `--check` would fail forever with no
    way to make it pass short of deleting a file the command does not manage.
    """
    runner = CliRunner()
    with (
        patch("mega_snake.docs_gen.install_agent_items.get_item", return_value=claude_only_item()),
        runner.isolated_filesystem(temp_dir=tmp_path) as iso,
    ):
        stray = Path(iso) / ".github" / "skills" / CLAUDE_ONLY
        stray.mkdir(parents=True)
        (stray / SKILL_FILE).write_text("whatever was left here", encoding="utf-8")

        _check_existing_files({CLAUDE_ONLY: {SKILL_FILE: "CLAUDE ONLY BODY"}})  # Must not raise


@pytest.mark.parametrize("name", sorted(EXPECTED_CATALOGUE))
def test_each_item_supports_exactly_the_documented_runtimes(name: str) -> None:
    """A narrowed item is documented as narrowed, and a portable one is not narrowed by accident.

    Both directions matter. An undocumented restriction means a user's install silently comes out
    half empty; a restriction that quietly disappears means a file is written where the runtime
    cannot read it, which installs cleanly and behaves nothing like what was authored.
    """
    item = next(candidate for candidate in ITEMS if candidate.name == name)
    expected = EXPECTED_RUNTIME_LIMITS.get(name, ALL_RUNTIMES)

    assert item.runtimes == expected, f"{name} supports {item.runtimes}, documented as {expected}"


def test_every_documented_runtime_limit_names_a_real_item() -> None:
    """A leftover row would document a restriction on something that no longer exists."""
    assert set(EXPECTED_RUNTIME_LIMITS) <= set(EXPECTED_CATALOGUE), (
        f"unknown items in EXPECTED_RUNTIME_LIMITS: {set(EXPECTED_RUNTIME_LIMITS) - set(EXPECTED_CATALOGUE)}"
    )
