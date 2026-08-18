"""
parse_remote_branches script, which allows the user to delete old branches
that was already been merged into main branch.
"""

import subprocess
from typing import Optional
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.remote_branches.remote_branch import RemoteBranch
from mega_snake.util.util import (
    get_main_branch,
    get_validated_input,
    ref_exists,
    require_remote,
    run_operation,
)


def define_branches(line: str) -> Optional[RemoteBranch]:
    """
    Converts a string into a remote_branch instance

    Args:
        line: str

    Returns:
        RemoteBranch
    """
    if line is not None and bool(line):
        return RemoteBranch.from_string(line)
    return None


def parsing_branches(branches: list[RemoteBranch], remote: str) -> list[str]:
    """
    Parses the branches and returns the branches that require deletion

    Args:
        branches: list[RemoteBranch]

    Returns:
        list[RemoteBranch]
    """
    options: list[str] = ["y", "n", "f"]
    main_branch: str = get_main_branch(remote)
    garbage: list[str] = []
    for branch in branches:
        if branch.merged_on_main and branch.branch != main_branch:
            prompt = (
                f"\nDo you want to delete the following branch?\n"
                f"\tBranch: {branch.branch}\n"
                f"\tDate: {branch.commit.date_str}\n"
                f"\tAuthor: {branch.mail}\n"
                f"\tCommit: {branch.commit.commit_hash}\n"
                f"\tMessage: {branch.commit.message}\n\n"
                f"(y)es | (n)o | (f)inalize\n"
            )
            user_input = get_validated_input(prompt, options)
            if user_input in {"y", "yes"}:
                garbage.append(branch.branch)
            elif user_input in {"f", "finalize"}:
                break
    return garbage


def delete_branches(garbage: list[str]) -> None:
    """
    Deletes the branches in the garbage list, from the remote and from the local repository.

    A selected branch does not necessarily exist on both sides: a remote branch from another author
    is commonly never checked out locally, and a branch whose remote counterpart was deleted when its
    pull request was merged only survives locally. Each side is therefore attempted only when its
    reference is actually there, since ``git push -d`` and ``git branch -D`` both fail on a missing
    reference and would report a deletion that never had anything to delete as an error.

    A failure deleting a branch from the remote leaves the local copy alone and moves on to the next
    branch, so a single unreachable or protected branch does not abort the whole cleanup.

    Parameters:
        garbage: The branch names selected for deletion.

    Raises:
        EnvironmentError: If no remote repository is configured and there is something to delete.

    Returns:
        None
    """
    if not garbage:
        return
    remote: str = require_remote()
    for branch in garbage:
        try:
            if ref_exists(f"refs/remotes/{remote}/{branch}"):
                result = run_operation(
                    f'git push -d "{remote}" "{branch}" --no-verify 2>&1', f"Deleting remote branch {branch}"
                )
                ws_success(result.stdout.strip())
            else:
                ws_info(f"Branch '{branch}' has no counterpart on '{remote}'; skipping the remote deletion")

            if ref_exists(f"refs/heads/{branch}"):
                run_operation(f'git branch -D "{branch}"', f"Deleting local branch {branch}")
                ws_success(f"Local branch '{branch}' deleted successfully")
            continue  # Continue to the next branch
        except subprocess.SubprocessError:
            continue
