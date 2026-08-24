"""
Selection and deletion helpers for the branch cleanup: pick the fully merged branches the user
wants gone, then delete each one from the sides (local / remote) where it actually exists.
"""

import subprocess
from typing import NamedTuple, Optional
from mega_snake.util.formatting import ws_success
from mega_snake.remote_branches.remote_branch import GitBranch
from mega_snake.util.repo import Repo
from mega_snake.util.util import get_validated_input, require_remote, run_operation


class Garbage(NamedTuple):
    """A branch selected for deletion, with the sides it exists on.

    The flags come from the same enumeration that built the branch inventory, so they are the
    single source of truth for where the branch lives: no reference re-probing is needed later.
    """

    branch: str
    local: bool
    remote: bool


def parsing_branches(branches: list[GitBranch]) -> list[Garbage]:
    """
    Ask the user which of the fully merged branches to delete.

    Only fully merged branches are offered (every side that exists is merged into the main branch),
    and the main branch itself is never a candidate. The user can stop the review early with the
    'finalize' answer.

    Parameters:
        branches: The branch inventory to pick candidates from.

    Raises:
        None

    Returns:
        list[Garbage]: The branches the user selected, with the sides each one exists on.
    """
    if len(branches) == 0:
        return []
    main_branch: str = Repo.MAIN_BRANCH
    options: list[str] = ["y", "n", "f"]
    del_branches: list[GitBranch] = [
        branch for branch in branches if branch.fully_merged and branch.get_any_branch().short_name != main_branch
    ]

    garbage: list[Garbage] = []
    for parent in del_branches:
        branch = parent.get_any_branch()
        parts = [f"{'local' if parent.local else ''}", f"{'remote' if parent.remote else ''}"]
        result = " and ".join([p for p in parts if p])
        prompt = (
            f"\nDo you want to delete the following branch?\n"
            f"\tBranch: {branch.short_name}\n"
            f"\tDate: {branch.str_time}\n"
            f"\tAuthor: {branch.mail}\n"
            f"\tCommit: {branch.hash}\n"
            f"\tMessage: {branch.message}\n\n"
            f"\tLocation: {result}\n\n"
            f"(y)es | (n)o | (f)inalize\n"
        )
        user_input = get_validated_input(prompt, options)
        if user_input in {"y", "yes"}:
            garbage.append(Garbage(branch=branch.short_name, local=bool(parent.local), remote=bool(parent.remote)))
        elif user_input in {"f", "finalize"}:
            break
    return garbage


def delete_branches(garbage: list[Garbage]) -> None:
    """
    Deletes the branches in the garbage list, from the remote and from the local repository.

    A selected branch does not necessarily exist on both sides: a remote branch from another author
    is commonly never checked out locally, and a branch whose remote counterpart was deleted when its
    pull request was merged only survives locally. Each side is therefore attempted only when its
    ``Garbage`` flag says the side exists — the flags were captured by the same enumeration that
    built the inventory, so re-probing the references here would only repeat that answer.

    A failure deleting a branch from the remote leaves the local copy alone and moves on to the next
    branch, so a single unreachable or protected branch does not abort the whole cleanup. The remote
    is only resolved (and required) when at least one selected branch has a remote side, so a
    local-only cleanup works in a repository without remotes.

    Parameters:
        garbage: The branches selected for deletion.

    Raises:
        EnvironmentError: If a branch must be deleted from the remote and no remote is configured.

    Returns:
        None
    """
    if not garbage:
        return
    remote: Optional[str] = require_remote() if any(item.remote for item in garbage) else None
    for garbage_item in garbage:
        branch = garbage_item.branch
        try:
            if garbage_item.remote:
                result = run_operation(
                    f'git push -d "{remote}" "{branch}" --no-verify 2>&1', f"Deleting remote branch {branch}"
                )
                ws_success(result.stdout.strip())
            if garbage_item.local:
                run_operation(f'git branch -D "{branch}"', f"Deleting local branch {branch}")
                ws_success(f"Local branch '{branch}' deleted successfully")
        except subprocess.SubprocessError:
            continue
