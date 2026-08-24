"""Creates a diff tree of the current branch against master"""

import os
import shutil
import subprocess
from typing import Optional
import click
from directory_tree import DisplayTree
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.util.repo import Repo
from mega_snake.util.util import run_operation, get_current_commit
from mega_snake.util.props import get_property
from mega_snake.diff_tree.file_type import FileType


@click.command(
    name="diff-tree",
    short_help="Creates diff tree and commit list of current changes",
    help="Creates a diff tree of changes and a commit list between two points in history. The comparison"
    " runs from master (or the commit given with --origin-hash) up to the current HEAD (or the commit"
    " given with --target-hash), which makes it possible to inspect a past range instead of only the current work.",
    epilog="usage: mgsnake diff-tree [OPTIONS]",
)
@click.option(
    "--origin-hash", "-o", type=click.STRING, default=None, help="Commit hash to compare against instead of master"
)
@click.option(
    "--target-hash",
    "-t",
    type=click.STRING,
    default=None,
    help="Commit hash to compare up to, instead of the current HEAD. Requires --scope c (the default),"
    " since the index and the working tree only exist for HEAD; any other scope is rejected.",
)
@click.option(
    "--delete-original-files",
    "-d",
    is_flag=True,
    help="Delete the generated copy of the original files in the diff tree",
)
@click.option(
    "--scope",
    "-s",
    type=click.Choice(["c", "s", "u"], case_sensitive=False),
    default="c",
    show_default=True,
    help="Changes to include: (c)ommitted only [default], committed and (s)taged, or also (u)nstaged and untracked."
    " Only 'c' is compatible with --target-hash: the other two read the index and the working tree, which"
    " exist only for HEAD, so passing them together is rejected instead of silently ignoring one of them.",
)
def diff_tree(origin_hash: Optional[str], target_hash: Optional[str], delete_original_files: bool, scope: str) -> None:
    """
    Creates a diff tree between two points in history.

    Args:
        origin_hash: str | None - Commit hash to compare against instead of master
        target_hash: str | None - Commit hash to compare up to, instead of the current HEAD
        delete_original_files: bool - Delete the generated copy of the original files in the diff tree
        scope: str - Changes to include: (c)ommitted only [default], committed and (s)taged, or also (u)nstaged
                                            and untracked

    Raises:
        click.ClickException: If --target-hash is combined with a scope that reaches the index or the working tree.
        ValueError: If a given commit hash does not resolve to a commit.
    """
    # Validated before anything is written, so a rejected invocation never wipes the previous output.
    if target_hash is not None and scope != "c":
        raise click.ClickException(
            f"BAD REQUEST: --target-hash and --scope {scope} are mutually exclusive. "
            "--target-hash compares two commits, but that scope also reads the index or the working tree, "
            "which only exist for HEAD. Use one or the other: drop --target-hash, or use --scope c."
        )
    # Both ends are resolved and validated before anything is written: a mistyped hash is the most
    # likely rejection there is, and destroying the previous run's output to then abort would leave
    # the user with an empty folder and nothing to fall back on.
    main_branch: str
    if origin_hash is None:
        main_branch = Repo().MAIN_BRANCH
        ws_info(f"Main branch: {main_branch}")
    else:
        main_branch = _validate_commit(origin_hash)
    current_branch: str = _validate_commit(target_hash) if target_hash is not None else get_current_commit()

    tree_output: str = f"{get_property('working_path')}/diff_tree"
    diff_commit_file: str = f"{tree_output}/diff_commit.txt"
    diff_changes_file: str = f"{tree_output}/diff_changes.txt"
    diff_tree_dummy_repo: str = f"{tree_output}/diff_tree_dummy_repo"

    # every run starts from a clean output directory, which is always (re)created so the files
    # written further down never depend on a directory a previous run happened to leave behind
    if os.path.exists(tree_output):
        shutil.rmtree(tree_output)
    os.makedirs(diff_tree_dummy_repo, exist_ok=True)

    diff_target: str = _get_diff_target(scope, main_branch, current_branch)
    untracked_files: list[str] = _get_untracked_files(scope)
    # rename detection is disabled so every scope reports the same raw format, with one entry
    # per path, which is what the tree reconstruction below expects
    diff_str: str = run_operation(
        f"git diff --raw --no-renames {diff_target}",
        f"getting differences for '{diff_target}'",
    ).stdout.strip()
    # check if there are no differences
    if not diff_str and not untracked_files:
        ws_success("No differences found between the current branch and the main branch")
        return

    # iterate over the differences and write them to the output file
    for diff in diff_str.split("\n") if diff_str else []:
        columns: list[str] = diff.split("\t")
        symbol = columns[0].split(" ")[4]
        path: str = columns[1]
        FileType.from_symbol(symbol).add(path)
    # untracked files have no counterpart in the diff, so they are reported as added
    for untracked_file in untracked_files:
        FileType.ADDED.add(untracked_file)
    binary_files: set[str] = _get_binary_files(diff_target)
    _create_files(diff_tree_dummy_repo, main_branch, not delete_original_files, binary_files)
    _display_inner_tree(diff_tree_dummy_repo, f"{tree_output}/diff_tree.txt", not delete_original_files)
    ws_success(f"Diff tree created at {tree_output}/diff_tree.txt")
    # write the commit list to the file
    commits: str = run_operation(
        f" git log --pretty=format:'%ad %H%n%B' --date=short {current_branch}...{main_branch}",
        "Writing commit list to file",
    ).stdout.strip()
    # the pending work goes above the most recent commit, so the file reads newest first
    pending_changes: str = _get_pending_changes_report(scope, untracked_files)
    with open(diff_commit_file, "w", encoding="utf-8") as diff_commit:
        diff_commit.write(f"{pending_changes}{commits}")
    run_operation(f"code {diff_commit_file}", "opening diff commit file")
    ws_success(f"Commit list created at {diff_commit_file}")
    # write all the changes to a file
    changes: str = run_operation(f"git diff {diff_target}", "getting all git changes").stdout.strip()
    with open(diff_changes_file, "w", encoding="utf-8") as diff_changes:
        diff_changes.write(changes)
    run_operation(f"code {diff_changes_file}", "opening diff changes file")
    ws_success(f"Changes list created at {diff_changes_file}")
    if delete_original_files:
        shutil.rmtree(diff_tree_dummy_repo)
        ws_success("Deleted the generated copy of the original files in the diff tree")


def _validate_commit(commit_hash: str) -> str:
    """
    Confirms a reference resolves to a commit before any diff is attempted against it.

    Both ends of the comparison accept an arbitrary reference from the user, so this check is shared
    by them: a typo that resolves to a tree or a blob would otherwise reach git as a valid-looking
    revision and produce a diff nobody asked for.

    Args:
        commit_hash: str

    Raises:
        ValueError: If the reference does not resolve to a commit.

    Returns:
        str: The validated reference, unchanged.
    """
    # check=False because a reference that does not exist is the expected failure here, not an
    # operational one: `git cat-file` exits 128 for it, which under the default check=True would be
    # retried three times with a two-second sleep and reported as a subprocess failure instead of the
    # typo it is. Same pattern as `_tag_exists` in light_weight/release.py.
    result: subprocess.CompletedProcess[str] = run_operation(
        f"git cat-file -t {commit_hash} 2>/dev/null",
        f"Checking if commit hash '{commit_hash}' is valid",
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "commit":
        raise ValueError(f"Invalid commit hash: {commit_hash}")
    return commit_hash


def _get_diff_target(scope: str, main_branch: str, current_branch: str) -> str:
    """
    Builds the git revision arguments that restrict a diff to the requested scope.

    The three scopes are cumulative, and each one maps to the way git itself selects what to
    compare: an explicit commit range only sees committed work, ``--cached`` adds the index on
    top of it, and comparing the working tree directly adds the unstaged changes as well.

    Args:
        scope: str
        main_branch: str
        current_branch: str

    Returns:
        str: The revision arguments to append to a git diff command.
    """
    if scope == "s":
        return f"--cached {main_branch}"
    if scope == "u":
        return f"{main_branch}"
    return f"{main_branch} {current_branch}"


def _get_untracked_files(scope: str) -> list[str]:
    """
    Lists the untracked files that belong to the requested scope.

    Untracked files are invisible to ``git diff``, so without this they would silently be missing
    from a scope that claims to cover the working tree. Only the unstaged scope includes them, and
    the files ignored by git are left out.

    Args:
        scope: str

    Returns:
        list[str]: Paths of the untracked files, empty for any scope other than unstaged.
    """
    if scope != "u":
        return []
    return _get_paths("git ls-files --others --exclude-standard", "getting untracked files")


def _get_paths(command: str, description: str) -> list[str]:
    """
    Runs a git command listing one path per line and returns those paths.

    An empty output means no path at all, which is why it cannot simply be split: doing so would
    yield a single empty path and report a change that does not exist.

    Args:
        command: str
        description: str

    Returns:
        list[str]: The listed paths, empty when the command reported none.
    """
    output: str = run_operation(command, description).stdout.strip()
    return output.split("\n") if output else []


def _get_pending_changes_report(scope: str, untracked_files: list[str]) -> str:
    """
    Builds the report of the changes that are not part of any commit yet.

    The commit list only knows about committed work, so the uncommitted part of the scope would
    otherwise be missing from it entirely. Each section is only reported when the scope covers it
    and when it actually has files, so a clean working tree never adds noise to the file. Sections
    are ordered from the furthest from being committed to the closest, matching the newest-first
    reading order of the commit list that follows them.

    Args:
        scope: str
        untracked_files: list[str]

    Returns:
        str: The report to prepend to the commit list, empty when there is nothing pending.
    """
    sections: list[str] = []
    if scope == "u":
        unstaged: list[str] = _get_paths("git diff --name-only", "getting unstaged files")
        sections.append(_format_pending_section("Unstaged files", unstaged + untracked_files))
    if scope in ("s", "u"):
        staged: list[str] = _get_paths("git diff --cached --name-only", "getting staged files")
        sections.append(_format_pending_section("Staged files", staged))
    return "".join(sections)


def _format_pending_section(title: str, files: list[str]) -> str:
    """
    Formats one section of the pending changes report.

    Args:
        title: str
        files: list[str]

    Returns:
        str: The formatted section, empty when there is no file to report.
    """
    if not files:
        return ""
    listed_files: str = "\n".join(f"- {file}" for file in files)
    return f"{title}:\n{listed_files}\n\n"


def _get_binary_files(diff_target: str) -> set[str]:
    """
    Identifies binary files changed within the given diff target using ``git diff --numstat``.

    Git reports ``-`` in both the added/removed line columns for binary files, which is
    used here to detect them without any extra I/O beyond the diff itself.

    Args:
        diff_target: str

    Returns:
        set[str]: Paths of files detected as binary in the diff.
    """
    numstat: str = run_operation(
        f"git diff --numstat {diff_target}",
        f"getting binary file information for '{diff_target}'",
    ).stdout.strip()
    binary_files: set[str] = set()
    if not numstat:
        return binary_files
    for line in numstat.split("\n"):
        columns: list[str] = line.split("\t")
        if len(columns) == 3 and columns[0] == "-" and columns[1] == "-":
            binary_files.add(columns[2])
    return binary_files


def _create_files(
    location: str, main_branch: str, show_contents: bool, binary_files: Optional[set[str]] = None
) -> None:
    """
    Creates new files for each file type in the specified location.

    Binary files are detected via ``binary_files`` and written with a placeholder instead
    of their raw contents, since dumping binary bytes into a text snapshot has no value and
    previously crashed the command with a UnicodeDecodeError.

    Args:
        location: str
        main_branch: str
        show_contents: bool
        binary_files: Optional[set[str]]
    """
    contents: str
    binary_files = binary_files or set()
    for file_type in FileType:
        for file in file_type.files:
            new_file_path: str = f"{location}/{file} - {file_type.symbol}"
            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
            if not show_contents or file_type.id_type == "A":
                contents = ""
            elif file in binary_files:
                contents = "Binary file (contents not shown)"
            else:
                contents = run_operation(f"git show {main_branch}:{file}", "Getting file contents").stdout
            with open(new_file_path, "w", encoding="utf-8") as new_file:
                new_file.write(contents)


def _display_inner_tree(root_dir: str, output_file: str, show_contents: bool) -> None:
    """
    Display the tree of a directory's contents, hiding the root directory.

    Args:
        root_dir (str): The directory whose contents are to be displayed.
        output_file (str): The file to write the tree to.

    Returns:
        None
    """
    tree: str = DisplayTree(f"{root_dir}", stringRep=True, header=False)
    tree = f"{tree}\n{FileType.get_changes()}"
    lines: list[str] = tree.splitlines()
    lines[0] = "."
    tree = "\n".join(lines)
    with open(output_file, "w", encoding="utf-8") as diff_tree:
        diff_tree.write(tree)
    if show_contents:
        for root, _, files in os.walk(root_dir):
            for filename in files:
                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, filename[:-4])
                try:
                    os.rename(old_path, new_path)
                except OSError as e:
                    raise OSError(f"Failed to rename file {old_path} to {new_path}") from e
    run_operation(f"code {output_file}", "opening diff tree file")
