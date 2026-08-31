"""Command that generates AI agent skill files from the CLI metadata."""

from pathlib import Path, PurePath
from typing import Sequence

import click

from mega_snake.docs_gen.generate_docs import introspected_commands
from mega_snake.docs_gen.markdown_writer import render_index, render_markdown, write_or_check_document
from mega_snake.util.formatting import ws_success
from mega_snake.util.util import add_to_gitignore, cli_metadata, exclude_from_git, get_validated_input

# Files written into each skill directory.
#
# The split is what keeps the skill cheap to load. Both runtimes read SKILL.md eagerly the moment the
# skill triggers, so whatever sits in it is spent from the reader's context before it knows which
# command it needs; both are also built for progressive disclosure, where a short body points at
# reference files opened on demand. SKILL.md therefore carries the frontmatter and the index — every
# command name, its aliases and its one-line description — and REFERENCE_FILE carries the full
# reference the index points at.
SKILL_FILE = "SKILL.md"
REFERENCE_FILE = "reference.md"

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

# Body of SKILL.md above the index. Written here rather than in a packaged fragment because it
# describes the *generated* pair of files and has to name REFERENCE_FILE, which only this module
# defines: a fragment would restate a file name it cannot see, and §6.3's rule is that generated
# facts are never hand-written twice.
SKILL_PREAMBLE = (
    f"Reference for the `{SKILL_NAME}` CLI (PyPI package `mega-snake`).\n"
    "\n"
    f"The table below lists every command with its aliases and a one-line description. It is an\n"
    f"index, not the documentation: it carries no options, defaults, output files or caveats.\n"
    "\n"
    f"**Before running a command, read its full entry.** Two equivalent ways, cheapest first:\n"
    "\n"
    f"- `{SKILL_NAME} man <command>` — renders that one command's full reference in the terminal.\n"
    f"- `{REFERENCE_FILE}`, next to this file — the same reference for every command, as a file.\n"
    "\n"
    f"Read only the entry you need. `{SKILL_NAME} man <command>` is preferred: it returns a single\n"
    f"command instead of the whole document, and it always reflects the installed version.\n"
    "\n"
    f"Every command also accepts `-h`/`--help`, and `{SKILL_NAME} --help` lists the commands."
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


def _reference_path(skill_dir: Path) -> Path:
    """Return the full path to the reference file inside a skill directory.

    Parameters:
        skill_dir: The skill directory.

    Raises:
        None

    Returns:
        Path: The full path to the reference file.
    """
    return skill_dir / REFERENCE_FILE


def _skill_files(index: str, reference: str) -> dict[str, str]:
    """Pair every file name the command writes with its rendered content.

    Returned as one mapping so the write path and ``--check`` iterate the *same* set: a file added to
    the skill and forgotten in the validation would drift with nothing reporting it, which is the
    failure mode ``--check`` exists to prevent.

    Parameters:
        index: The rendered command index.
        reference: The rendered full command reference.

    Raises:
        None

    Returns:
        dict[str, str]: File name to file content, for every file the skill is made of.
    """
    return {SKILL_FILE: _skill_document(index), REFERENCE_FILE: reference}


def _skill_document(index: str) -> str:
    """Assemble SKILL.md: the frontmatter, the pointer to the reference, and the command index.

    The description is emitted as a double-quoted YAML scalar because a plain one may not contain a
    colon followed by a space, which is easy to reintroduce the next time the wording is edited.

    The pointer is the load-bearing sentence of the whole document: it is what makes the reference a
    file the agent opens when it needs detail rather than ~900 lines it pays for on every trigger.
    Without it the index reads as the complete documentation, and the agent answers from a table that
    deliberately carries no options, defaults or caveats.

    Parameters:
        index: The rendered Markdown command index.

    Raises:
        None

    Returns:
        str: The complete SKILL.md document, frontmatter first.
    """
    return f'---\nname: {SKILL_NAME}\ndescription: "{SKILL_DESCRIPTION}"\n---\n\n{SKILL_PREAMBLE}\n\n{index}'


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


def _check_all_existing_skill_files(files: dict[str, str]) -> None:
    """Validate every skill file that already exists on disk.

    Only files that are present are checked; missing ones are silently skipped so --check does not
    mandate that skill files exist, only that existing ones are up to date.

    Every file of the skill is validated, not just SKILL.md: the reference half is the larger of the
    two and the one a stale checkout is most likely to keep, so checking only the index would report
    a skill as current while the document it points at describes commands that no longer exist.

    Parameters:
        files: File name to rendered content, for every file the skill is made of.

    Raises:
        ValidationError: If any existing skill file is stale.

    Returns:
        None
    """
    for skill_dir in ALL_SKILL_DIRS:
        for file_name, content in files.items():
            skill_file: Path = skill_dir / file_name
            if skill_file.is_file():
                write_or_check_document(skill_file, content, check=True)


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


def _write_skill_files(skill_dirs: tuple[Path, ...], files: dict[str, str]) -> list[Path]:
    """Write every file of the skill into every selected skill directory.

    Parameters:
        skill_dirs: The directories to write into.
        files: File name to rendered content, for every file the skill is made of.

    Raises:
        None

    Returns:
        list[Path]: The paths that were written.
    """
    written: list[Path] = []
    for skill_dir in skill_dirs:
        for file_name, content in files.items():
            skill_file: Path = skill_dir / file_name
            write_or_check_document(skill_file, content, check=False)
            ws_success(f"Generated {skill_file}")
            written.append(skill_file)
    return written


@click.command(
    name="generate-skill",
    short_help="Generate AI agent skill files (SKILL.md) from CLI metadata.",
    help="Generates the agent skill files by introspecting the registered CLI commands: SKILL.md,"
    " carrying the YAML frontmatter the agent runtimes read plus a compact command index, and"
    " reference.md beside it, carrying the same full reference as generate-docs for the agent to"
    " open on demand. Asks which assistant to target — .github/skills/mgsnake/ for GitHub Copilot,"
    " .claude/skills/mgsnake/ for Claude, or both — and how the files should be tracked in git,"
    " then writes them.",
)
@cli_metadata(flags={"no_init"})
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Render in memory, compare with every skill file that already exists on disk — SKILL.md"
    " and reference.md alike — and exit with an error when any is stale.",
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
    # One walk of the CLI, two projections of its result. Introspecting twice would let the index
    # and the reference disagree about which commands exist.
    commands = introspected_commands()
    files: dict[str, str] = _skill_files(render_index(commands), render_markdown(commands))

    if check:
        _check_all_existing_skill_files(files)
        return

    # Both questions are asked before anything is written, so exhausting the retries on either
    # prompt leaves the working tree exactly as it was. Writing first would strand skill files on
    # disk, untracked and un-excluded, for a user who only fumbled the second answer.
    skill_dirs: tuple[Path, ...] = _prompt_target()
    tracking: str = _prompt_tracking()
    _write_skill_files(skill_dirs, files)
    _apply_tracking(skill_dirs, tracking)
