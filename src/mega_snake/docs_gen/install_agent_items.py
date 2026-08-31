"""Command that installs the agent skills and agents mgsnake ships."""

from pathlib import Path, PurePath
from typing import Optional, Sequence

import click

from mega_snake.docs_gen.item_registry import (
    ALL_RUNTIMES,
    RUNTIME_LABEL,
    Item,
    bundled_with,
    expand_items,
    get_item,
    item_names,
    item_targets,
    required_by,
    selectable_names,
    tracking_target,
)
from mega_snake.docs_gen.markdown_writer import write_or_check_document
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.util.util import (
    add_to_gitignore,
    cli_metadata,
    exclude_from_git,
    get_validated_input,
    get_validated_selection,
)

# Maps the target-selection keys to their runtimes. c -> GitHub Copilot, l -> Claude, b -> both.
TARGET_OPT: dict[str, tuple[str, ...]] = {
    "c": (ALL_RUNTIMES[0],),
    "l": (ALL_RUNTIMES[1],),
    "b": ALL_RUNTIMES,
}

# Valid keys for the git-tracking selection.
# e -> .git/info/exclude (machine-local), g -> .gitignore (committed), v -> leave versioned
TRACKING_KEYS: tuple[str, ...] = ("e", "g", "v")

# State of one item in one runtime, shown beside its name so the selection is made with the current
# picture rather than from memory.
STATE_ABSENT: str = "not installed"
STATE_CURRENT: str = "installed"
STATE_STALE: str = "STALE"

# What the command renders once and then reuses: item name -> file name -> content.
Rendered = dict[str, dict[str, str]]


def _tracking_entries(targets: Sequence[tuple[PurePath, str]]) -> list[tuple[str, str]]:
    """Build the (entry, description) pairs the git-tracking helpers expect.

    Uses ``as_posix()`` and never ``str()``: on Windows ``str(Path)`` yields backslashes, and git
    reads a backslash inside an ignore pattern as an escape, so the pattern matches nothing and the
    files the user asked to untrack stay tracked with no error at all. The idempotency check in the
    helpers escapes the same string, so a re-run would not recognise its own line either and would
    append a duplicate.

    A directory entry keeps its trailing slash and a file entry must not gain one: ``foo.md/`` is a
    pattern that matches only a directory, so an agent excluded that way stays tracked.

    Parameters:
        targets: Pairs of (path, human label). A path with a suffix is treated as a file.

    Raises:
        None

    Returns:
        list[tuple[str, str]]: One (pattern, label) pair per target, in the order given.
    """
    entries: list[tuple[str, str]] = []
    for target, label in targets:
        pattern: str = target.as_posix()
        entries.append((pattern if target.suffix else f"{pattern}/", label))
    return entries


def _apply_tracking(targets: Sequence[tuple[PurePath, str]], tracking: str) -> None:
    """Apply the chosen git-tracking strategy to everything that was written.

    Parameters:
        targets: Pairs of (path, human label) for every installed item.
        tracking: ``"e"`` for git exclude, ``"g"`` for .gitignore, ``"v"`` to leave them versioned.

    Raises:
        None

    Returns:
        None
    """
    if tracking == "v":
        ws_success("Files left versioned - they will be committed to the repository.")
        return

    entries: list[tuple[str, str]] = _tracking_entries(targets)
    if tracking == "e":
        exclude_from_git(entries)
    elif tracking == "g":
        add_to_gitignore(entries)


def _file_state(path: Path, expected: str) -> str:
    """Classify one file on disk against what would be written there now.

    Parameters:
        path: The file to inspect.
        expected: The content the command would write.

    Raises:
        None

    Returns:
        str: One of ``STATE_ABSENT``, ``STATE_CURRENT`` or ``STATE_STALE``.
    """
    if not path.is_file():
        return STATE_ABSENT
    return STATE_CURRENT if path.read_text(encoding="utf-8").splitlines() == expected.splitlines() else STATE_STALE


def item_state(item: Item, runtime: str, files: dict[str, str]) -> str:
    """Classify a whole item in one runtime: absent, current, or stale.

    An item counts as current only when **every** file it owns is current. The reference half of the
    CLI skill is the larger one and the likelier to be left behind, so treating a fresh ``SKILL.md``
    as proof of a fresh install would hide exactly the case the user needs to see.

    Parameters:
        item: The item being classified.
        runtime: One of ``ALL_RUNTIMES``.
        files: The content that would be written, per file name.

    Raises:
        None

    Returns:
        str: One of ``STATE_ABSENT``, ``STATE_CURRENT`` or ``STATE_STALE``.
    """
    states: set[str] = {_file_state(path, content) for path, content in item_targets(item, runtime, files).items()}
    if states == {STATE_ABSENT}:
        return STATE_ABSENT
    return STATE_CURRENT if states == {STATE_CURRENT} else STATE_STALE


def _describe_states(item: Item, files: dict[str, str]) -> str:
    """Summarise where an item currently stands, across every runtime.

    Parameters:
        item: The item being described.
        files: The content that would be written, per file name.

    Raises:
        None

    Returns:
        str: A short annotation such as ``"installed: Claude | not installed: GitHub Copilot"``.
    """
    by_state: dict[str, list[str]] = {}
    for runtime in ALL_RUNTIMES:
        by_state.setdefault(item_state(item, runtime, files), []).append(RUNTIME_LABEL[runtime])
    return " | ".join(f"{state}: {', '.join(labels)}" for state, labels in by_state.items())


def _selection_prompt(rendered: Rendered) -> str:
    """Build the multi-select prompt: one entry per offered item, with its state and its bundle.

    Every selectable item is listed, installed ones included. Hiding what is already on disk would
    remove the only way to refresh an item whose content this version of mgsnake improved: the run
    would report "everything is installed" and leave the user with a stale file and a zero exit.

    What an item drags along is shown **before** the choice, not after the write, because that is
    when it can still change the user's mind.

    Parameters:
        rendered: Every registered item's content, keyed by name.

    Raises:
        KeyError: If a selectable name is not registered.

    Returns:
        str: The prompt text.
    """
    lines: list[str] = ["Which items do you want to install or refresh?"]
    for name in selectable_names():
        item: Item = get_item(name)
        bundle: list[str] = bundled_with(name)
        extra: str = f"  (installs with it: {', '.join(bundle)})" if bundle else ""
        lines.append(f"  {name} [{item.kind}] - {item.summary}{extra}")
        lines.append(f"      [{_describe_states(item, rendered[name])}]")
    return "\n".join(lines)


def _prompt_items(rendered: Rendered) -> list[str]:
    """Ask which items to install, defaulting to the only one when just one is offered.

    Parameters:
        rendered: Every registered item's content, keyed by name.

    Raises:
        KeyError: If the user exhausts the retry limit.

    Returns:
        list[str]: The selected names, before dependency expansion.
    """
    offered: list[str] = selectable_names()
    if len(offered) == 1:
        # A single-option multiple choice is a question with one possible answer. Reporting it keeps
        # the run self-explanatory without asking the user to type the only thing they could type.
        ws_info(f"Only one item is available; installing '{offered[0]}'.")
        return offered
    return get_validated_selection(_selection_prompt(rendered), offered)


def _prompt_target() -> tuple[str, ...]:
    """Ask which agent runtime to install for.

    Parameters:
        None

    Raises:
        KeyError: If the user exhausts the retry limit.

    Returns:
        tuple[str, ...]: The selected runtimes.
    """
    answer: str = get_validated_input(
        "For which AI agent assistant do you want to install?\n"
        f"  c - {RUNTIME_LABEL[ALL_RUNTIMES[0]]}  (.github/skills/, .github/agents/)\n"
        f"  l - {RUNTIME_LABEL[ALL_RUNTIMES[1]]}          (.claude/skills/, .claude/agents/)\n"
        "  b - both",
        list(TARGET_OPT),
    )
    return TARGET_OPT[answer]


def _prompt_tracking() -> str:
    """Ask how the generated files should be tracked in git.

    Parameters:
        None

    Raises:
        KeyError: If the user exhausts the retry limit.

    Returns:
        str: The chosen tracking key.
    """
    return get_validated_input(
        "How do you want to track the generated files?\n"
        "  e - exclude from git (.git/info/exclude, machine-local, not committed)\n"
        "  g - add to .gitignore (committed exclusion, applies to the whole team)\n"
        "  v - leave versioned (commit the files to the repository)",
        list(TRACKING_KEYS),
    )


def _report_dependencies(selected: Sequence[str]) -> None:
    """Tell the user which items were added because something they picked requires them.

    Installing an unselected item is correct - a task skill is useless to an assistant that does not
    know the commands it drives, and an agent's components are meaningless on their own - but it must
    never be a surprise: files appear in the working tree, and without this line the user cannot tell
    an intended install from a defect.

    Parameters:
        selected: The names the user actually chose.

    Raises:
        KeyError: If a selected or required name is not registered.

    Returns:
        None
    """
    for name, reasons in required_by(selected).items():
        ws_info(f"Also installing '{name}': required by {', '.join(repr(reason) for reason in reasons)}.")


def _write_items(runtimes: Sequence[str], installing: Rendered) -> list[Path]:
    """Write every file of every selected item, for every selected runtime.

    Parameters:
        runtimes: The runtimes to install for.
        installing: The items to write, keyed by name.

    Raises:
        InternalStateError: If a single-file item rendered more than one file.

    Returns:
        list[Path]: The paths that were written.
    """
    written: list[Path] = []
    for runtime in runtimes:
        for name, files in installing.items():
            for path, content in item_targets(get_item(name), runtime, files).items():
                write_or_check_document(path, content, check=False)
                ws_success(f"Generated {path}")
                written.append(path)
    return written


def _check_existing_files(rendered: Rendered) -> None:
    """Validate every installed file on disk, across every item and every runtime.

    Only files that are present are checked; missing ones are skipped, so --check does not mandate
    that anything is installed, only that what is kept is current. Each file is checked
    independently: the reference half of the CLI skill is the larger one and the likelier to go
    stale, and validating only SKILL.md would report a current skill while the document it points at
    described commands long gone.

    Parameters:
        rendered: Every registered item's content, keyed by name.

    Raises:
        ValidationError: If any existing file is stale.

    Returns:
        None
    """
    for runtime in ALL_RUNTIMES:
        for name, files in rendered.items():
            for path, content in item_targets(get_item(name), runtime, files).items():
                if path.is_file():
                    write_or_check_document(path, content, check=True)


@click.command(
    name="install-agent-items",
    short_help="Install the mgsnake agent skills and agents for Copilot or Claude.",
    help="Installs the agent assets mgsnake ships - skills into .github/skills/<name>/ or"
    " .claude/skills/<name>/, agents into .github/agents/<name>.agent.md or"
    " .claude/agents/<name>.md. Every item is offered with its current state, so an installed one"
    " can be refreshed in place; an item that requires others pulls them in and says so. The"
    " selection, the target and the git-tracking strategy are asked interactively unless --item,"
    " --target and --tracking supply them, which is what makes the command usable from a hook or a"
    " CI step.",
    epilog="""
    Notes:\n
        Re-running is idempotent: an item already present is rewritten with the current content,
        which is how an installation is brought up to date after upgrading mgsnake.
    """,
)
@cli_metadata(flags={"no_init"})
@click.option(
    "--item",
    "items",
    multiple=True,
    type=click.Choice(item_names(), case_sensitive=False),
    help="Install this item instead of asking. Repeat the option to install several. Items required"
    " by the ones named are installed too, and reported. Accepts bundled items that the interactive"
    " list does not offer, so one can be refreshed without reinstalling what bundles it.",
)
@click.option(
    "--target",
    type=click.Choice(list(TARGET_OPT), case_sensitive=False),
    default=None,
    help="Where to install, instead of asking: 'c' for GitHub Copilot, 'l' for Claude, 'b' for both.",
)
@click.option(
    "--tracking",
    type=click.Choice(list(TRACKING_KEYS), case_sensitive=False),
    default=None,
    help="How to track the files in git, instead of asking: 'e' excludes them in .git/info/exclude,"
    " 'g' adds them to .gitignore, 'v' leaves them versioned.",
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Render in memory, compare with every installed file on disk, and exit with an error when"
    " any is stale. Never prompts and never writes.",
)
def install_agent_items(items: tuple[str, ...], target: Optional[str], tracking: Optional[str], check: bool) -> None:
    """Install or validate the AI agent skills and agents.

    Parameters:
        items: The items named with --item; empty to select them interactively.
        target: The runtime to install for; None to ask.
        tracking: The git-tracking strategy; None to ask.
        check: When True, validate installed files instead of installing them.

    Raises:
        ValidationError: If --check finds that any installed file is stale.
        KeyError: If the user provides too many invalid answers to an interactive prompt.

    Returns:
        None
    """
    rendered: Rendered = {name: get_item(name).files() for name in item_names()}

    if check:
        _check_existing_files(rendered)
        return

    # Every answer is resolved before the first byte is written, so abandoning any prompt leaves the
    # working tree exactly as it was. Writing first would strand files on disk, neither excluded nor
    # gitignored, for a user who only fumbled a later answer.
    selected: list[str] = [name.lower() for name in items] if items else _prompt_items(rendered)
    runtimes: tuple[str, ...] = TARGET_OPT[target] if target else _prompt_target()
    strategy: str = tracking or _prompt_tracking()

    _report_dependencies(selected)
    installing: Rendered = {name: rendered[name] for name in expand_items(selected)}
    _write_items(runtimes, installing)
    _apply_tracking(
        [
            (
                tracking_target(get_item(name), runtime),
                # The item name belongs in the label: the helpers log "Excluded <description> in
                # <file>", so a label carrying only the runtime and the kind prints the same line
                # once per item and identifies none of them.
                f"{RUNTIME_LABEL[runtime]} {get_item(name).kind} '{name}'",
            )
            for runtime in runtimes
            for name in installing
        ],
        strategy,
    )
