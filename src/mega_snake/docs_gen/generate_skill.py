"""Command that generates AI agent skill files from the CLI metadata."""

from pathlib import Path

import click

from mega_snake.docs_gen.generate_docs import render_command_reference
from mega_snake.docs_gen.markdown_writer import write_or_check_document
from mega_snake.util.formatting import ws_success
from mega_snake.util.util import add_to_gitignore, cli_metadata, exclude_from_git, get_validated_input

# Output file name written into each skill directory.
SKILL_FILE = "SKILL.md"

# Canonical skill directories, relative to the project root.
SKILL_COPILOT_DIR: Path = Path(".github") / "skills" / "mgsnake"
SKILL_CLAUDE_DIR: Path = Path(".claude") / "skills" / "mgsnake"

# All known skill directories in deterministic order (used for --check iteration).
ALL_SKILL_DIRS: tuple[Path, ...] = (SKILL_COPILOT_DIR, SKILL_CLAUDE_DIR)

# Maps the interactive target-selection keys to their skill directories.
# c → GitHub Copilot, l → Claude, b → both
SKILL_TARGET_OPT: dict[str, tuple[Path, ...]] = {
    "c": (SKILL_COPILOT_DIR,),
    "l": (SKILL_CLAUDE_DIR,),
    "b": (SKILL_COPILOT_DIR, SKILL_CLAUDE_DIR),
}

# Valid keys for the git-tracking selection prompt.
# e → .git/info/exclude (machine-local), g → .gitignore (committed), v → leave versioned
SKILL_TRACKING_KEYS: tuple[str, ...] = ("e", "g", "v")


def _skill_path(skill_dir: Path) -> Path:
    """Return the full path to the SKILL.md file inside a skill directory.

    Parameters:
        skill_dir: The skill directory.

    Raises:
        None

    Returns:
        Path: The full path to SKILL.md.
    """
    return skill_dir / SKILL_FILE


def _apply_tracking(skill_dirs: tuple[Path, ...], tracking: str) -> None:
    """Apply the chosen git-tracking strategy to the generated skill directories.

    Parameters:
        skill_dirs: The directories whose SKILL.md files were written.
        tracking: The chosen tracking key — ``"e"`` for git exclude, ``"g"`` for .gitignore,
            ``"v"`` to leave the files versioned (no-op).

    Raises:
        None

    Returns:
        None
    """
    if tracking == "v":
        ws_success("Skill files left versioned — they will be committed to the repository.")
        return

    # TODO (copilot-instructions §8.2, items 2 and 3): str(Path) yields backslashes on Windows, which
    # git reads as escapes, and the description repeats the path instead of naming it.
    entries: list[tuple[str, str]] = [(str(skill_dir) + "/", f"{skill_dir}/") for skill_dir in skill_dirs]
    if tracking == "e":
        exclude_from_git(entries)
    elif tracking == "g":
        add_to_gitignore(entries)


def _check_all_existing_skill_files(markdown: str) -> None:
    """Validate every skill file that already exists on disk.

    Only files that are present are checked; missing ones are silently skipped so --check does not
    mandate that skill files exist, only that existing ones are up to date.

    Parameters:
        markdown: The freshly rendered Markdown to compare against.

    Raises:
        ValidationError: If any existing skill file is stale.

    Returns:
        None
    """
    for skill_dir in ALL_SKILL_DIRS:
        skill_file: Path = _skill_path(skill_dir)
        if skill_file.is_file():
            write_or_check_document(skill_file, markdown, check=True)


def _prompt_target() -> tuple[Path, ...]:
    """Ask the user which AI agent's skill directory to target.

    Parameters:
        None

    Raises:
        KeyError: If the user exhausts the retry limit for the target prompt.

    Returns:
        tuple[Path, ...]: The selected skill directories.
    """
    answer: str = get_validated_input(
        "For which AI agent assistant do you want to generate the skill?\n"
        f"  c — GitHub Copilot  ({SKILL_COPILOT_DIR / SKILL_FILE})\n"
        f"  l — Claude          ({SKILL_CLAUDE_DIR / SKILL_FILE})\n"
        "  b — both",
        list(SKILL_TARGET_OPT),
    )
    return SKILL_TARGET_OPT[answer]


def _prompt_tracking() -> str:
    """Ask the user how to track the generated skill files in git.

    Parameters:
        None

    Raises:
        KeyError: If the user exhausts the retry limit for the tracking prompt.

    Returns:
        str: The chosen tracking key.
    """
    return get_validated_input(
        "How do you want to track the generated skill files?\n"
        "  e — exclude from git (.git/info/exclude, machine-local, not committed)\n"
        "  g — add to .gitignore (committed exclusion, applies to the whole team)\n"
        "  v — leave versioned (commit the files to the repository)",
        list(SKILL_TRACKING_KEYS),
    )


def _write_skill_files(skill_dirs: tuple[Path, ...], markdown: str) -> list[Path]:
    """Write the SKILL.md file into every selected skill directory.

    Parameters:
        skill_dirs: The directories to write into.
        markdown: The rendered Markdown content.

    Raises:
        None

    Returns:
        list[Path]: The paths that were written.
    """
    written: list[Path] = []
    for skill_dir in skill_dirs:
        skill_file: Path = _skill_path(skill_dir)
        write_or_check_document(skill_file, markdown, check=False)
        ws_success(f"Generated {skill_file}")
        written.append(skill_file)
    return written


@click.command(
    name="generate-skill",
    short_help="Generate AI agent skill files (SKILL.md) from CLI metadata.",
    help="Generates SKILL.md for AI agent skill discovery by introspecting the registered CLI"
    " commands and rendering the same reference as generate-docs. Creates the file under"
    " .github/skills/mgsnake/ for GitHub Copilot, .claude/skills/mgsnake/ for Claude, or both,"
    " then asks how those files should be tracked in git.",
)
@cli_metadata(flags={"no_init"})
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Render in memory, compare with every skill file that already exists on disk,"
    " and exit with an error when any is stale.",
)
def generate_skill(check: bool) -> None:
    """Generate or validate the AI agent skill files.

    Parameters:
        check: When True, validate existing skill files instead of creating them.

    Raises:
        ValidationError: If --check finds that any existing skill file is stale.
        KeyError: If the user provides too many invalid answers to an interactive prompt.

    Returns:
        None
    """
    markdown: str = render_command_reference()

    if check:
        _check_all_existing_skill_files(markdown)
        return

    # TODO (copilot-instructions §8.2, items 1 and 4): the document still lacks the YAML frontmatter
    # an agent runtime needs to register it as a skill, and writing before the second prompt leaves
    # files behind when that prompt fails.
    skill_dirs: tuple[Path, ...] = _prompt_target()
    _write_skill_files(skill_dirs, markdown)
    tracking: str = _prompt_tracking()
    _apply_tracking(skill_dirs, tracking)
