"""Command that generates AI agent skill files from the CLI metadata."""

from pathlib import Path, PurePath
from typing import Sequence

import click

from mega_snake.docs_gen.generate_docs import render_command_reference
from mega_snake.docs_gen.markdown_writer import write_or_check_document
from mega_snake.util.formatting import ws_success
from mega_snake.util.util import add_to_gitignore, cli_metadata, exclude_from_git, get_validated_input

# Output file name written into each skill directory.
SKILL_FILE = "SKILL.md"

# YAML frontmatter identifying the document as a skill. Both runtimes this command targets discover
# a skill by reading these two keys off the top of the file; a SKILL.md that opens with a heading is
# simply not registered, so the frontmatter is what makes the generated file a skill rather than a
# stray Markdown document. The same pair serves both targets, which is why one rendered document is
# still written to every selected directory.
SKILL_NAME = "mgsnake"
SKILL_DESCRIPTION = (
    "Complete command reference for the mgsnake CLI (package mega-snake), covering every command, "
    "alias, option and documented behaviour. Use it when running, choosing or explaining an mgsnake "
    "command - VS Code workspace setup for Java, Gradle and Maven projects, git and release "
    "workflows, dependency vulnerability audits, GraphQL and keystore utilities, or shell "
    "integration."
)

# Canonical skill directories, relative to the project root.
SKILL_COPILOT_DIR: Path = Path(".github") / "skills" / "mgsnake"
SKILL_CLAUDE_DIR: Path = Path(".claude") / "skills" / "mgsnake"

# Human label per directory, used in the git-tracking log lines. The helpers take
# (entry, description) pairs where the description names the thing for a reader, so passing the path
# a second time would produce "Excluded .github/skills/mgsnake/ in .git/info/exclude" and say nothing.
SKILL_DIR_LABEL: dict[PurePath, str] = {
    SKILL_COPILOT_DIR: "GitHub Copilot skill folder",
    SKILL_CLAUDE_DIR: "Claude skill folder",
}

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


def _skill_document(markdown: str) -> str:
    """Prepend the skill frontmatter to the rendered command reference.

    The description is emitted as a double-quoted YAML scalar because a plain one may not contain a
    colon followed by a space, which is easy to reintroduce the next time the wording is edited.

    Parameters:
        markdown: The rendered Markdown command reference.

    Raises:
        None

    Returns:
        str: The complete SKILL.md document, frontmatter first.
    """
    return f'---\nname: {SKILL_NAME}\ndescription: "{SKILL_DESCRIPTION}"\n---\n\n{markdown}'


def _tracking_entries(skill_dirs: Sequence[PurePath]) -> list[tuple[str, str]]:
    """Build the (entry, description) pairs the git-tracking helpers expect.

    Uses ``as_posix()`` and never ``str()``: on Windows ``str(Path)`` yields backslashes, and git
    reads a backslash inside an ignore pattern as an escape — ``.github\\skills\\mgsnake/`` becomes
    the pattern ``.githubskillsmgsnake/``, which matches nothing, so the files the user asked to
    untrack stay tracked with no error at all. The idempotency check in the helpers escapes the same
    string, so a re-run would not recognise its own line either and would append a duplicate.

    Parameters:
        skill_dirs: The skill directories to build entries for.

    Raises:
        KeyError: If a directory has no entry in ``SKILL_DIR_LABEL``, which would mean a new target
            was added without giving it a human label.

    Returns:
        list[tuple[str, str]]: One (pattern, label) pair per directory, in the order given.
    """
    return [(f"{skill_dir.as_posix()}/", SKILL_DIR_LABEL[skill_dir]) for skill_dir in skill_dirs]


def _apply_tracking(skill_dirs: tuple[Path, ...], tracking: str) -> None:
    """Apply the chosen git-tracking strategy to the generated skill directories.

    Parameters:
        skill_dirs: The directories whose SKILL.md files were written.
        tracking: The chosen tracking key — ``"e"`` for git exclude, ``"g"`` for .gitignore,
            ``"v"`` to leave the files versioned (no-op).

    Raises:
        KeyError: Propagated from ``_tracking_entries`` when a directory has no human label.

    Returns:
        None
    """
    if tracking == "v":
        ws_success("Skill files left versioned — they will be committed to the repository.")
        return

    entries: list[tuple[str, str]] = _tracking_entries(skill_dirs)
    if tracking == "e":
        exclude_from_git(entries)
    elif tracking == "g":
        add_to_gitignore(entries)


def _check_all_existing_skill_files(document: str) -> None:
    """Validate every skill file that already exists on disk.

    Only files that are present are checked; missing ones are silently skipped so --check does not
    mandate that skill files exist, only that existing ones are up to date.

    Parameters:
        document: The freshly rendered SKILL.md document, frontmatter included, to compare against.

    Raises:
        ValidationError: If any existing skill file is stale.

    Returns:
        None
    """
    for skill_dir in ALL_SKILL_DIRS:
        skill_file: Path = _skill_path(skill_dir)
        if skill_file.is_file():
            write_or_check_document(skill_file, document, check=True)


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


def _write_skill_files(skill_dirs: tuple[Path, ...], document: str) -> list[Path]:
    """Write the SKILL.md file into every selected skill directory.

    Parameters:
        skill_dirs: The directories to write into.
        document: The rendered SKILL.md content, frontmatter included.

    Raises:
        None

    Returns:
        list[Path]: The paths that were written.
    """
    written: list[Path] = []
    for skill_dir in skill_dirs:
        skill_file: Path = _skill_path(skill_dir)
        write_or_check_document(skill_file, document, check=False)
        ws_success(f"Generated {skill_file}")
        written.append(skill_file)
    return written


@click.command(
    name="generate-skill",
    short_help="Generate AI agent skill files (SKILL.md) from CLI metadata.",
    help="Generates SKILL.md for AI agent skill discovery by introspecting the registered CLI"
    " commands and rendering the same reference as generate-docs, behind the YAML frontmatter the"
    " agent runtimes read. Asks which assistant to target — .github/skills/mgsnake/ for GitHub"
    " Copilot, .claude/skills/mgsnake/ for Claude, or both — and how the files should be tracked in"
    " git, then writes them.",
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
    document: str = _skill_document(render_command_reference())

    if check:
        _check_all_existing_skill_files(document)
        return

    # Both questions are asked before anything is written, so exhausting the retries on either
    # prompt leaves the working tree exactly as it was. Writing first would strand SKILL.md files on
    # disk, untracked and un-excluded, for a user who only fumbled the second answer.
    skill_dirs: tuple[Path, ...] = _prompt_target()
    tracking: str = _prompt_tracking()
    _write_skill_files(skill_dirs, document)
    _apply_tracking(skill_dirs, tracking)
