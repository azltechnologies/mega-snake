"""
parse_remote_branches script, which allows the user to delete old branches
that was already been merged into main branch.
"""

import subprocess
from typing import Optional
from mega_snake.util.formatting import ws_success
from mega_snake.remote_branches.remote_branch import RemoteBranch
from mega_snake.util.util import run_operation, get_main_branch, get_validated_input, require_remote


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
    Deletes the branches in the garbage list

    Args:
        garbage: list[str]
    """
    for branch in garbage:
        try:
            # Delete from remote
            result = run_operation(
                f'git push -d "{require_remote()}" "{branch}" --no-verify 2>&1', f"Deleting remote branch {branch}"
            )
            ws_success(result.stdout.strip())

            # Delete local branch, only if it exists: remote branches from other authors are
            # commonly never checked out locally, and `git branch -D` fails when the ref is absent.
            local_ref_check = run_operation(
                f'git rev-parse --verify --quiet "refs/heads/{branch}"',
                f"Checking if local branch {branch} exists",
                check=False,
            )
            if local_ref_check.returncode == 0:
                run_operation(f'git branch -D "{branch}"', f"Deleting local branch {branch}")
                ws_success(f"Local branch '{branch}' deleted successfully")
            continue  # Continue to the next branch
        except subprocess.SubprocessError:
            continue
