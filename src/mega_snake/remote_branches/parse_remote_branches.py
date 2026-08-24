"""
parse_remote_branches script, which allows the user to delete old branches
that was already been merged into main branch.
"""

import subprocess
from typing import NamedTuple
from mega_snake.util.formatting import ws_success, ws_advice
from mega_snake.remote_branches.remote_branch import GitBranch
from mega_snake.util.util import (
    LOCAL_PREFIX,
    REMOTE_PREFIX,
    get_validated_input,
    ref_exists,
    require_remote,
    run_operation,
)


class Garbage(NamedTuple):
    """Garbage class to hold the branches that are selected for deletion."""

    branch: str
    local: bool
    remote: bool


def parsing_branches(branches: list[GitBranch], remote: str) -> list[Garbage]:
    """
    Parses the branches and returns the branches that require deletion

    Args:
        branches: list[GitBranch]

    Returns:
        list[Garbage]
    """
    if len(branches) == 0:
        return []
    main_branch = branches[0].get_any_branch().MAIN_BRANCH
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
    reference is actually there, since ``git push -d`` and ``git branch -D`` both fail on a missing
    reference and would report a deletion that never had anything to delete as an error.

    A failure deleting a branch from the remote leaves the local copy alone and moves on to the next
    branch, so a single unreachable or protected branch does not abort the whole cleanup.

    Parameters:
        garbage: The branches selected for deletion.

    Raises:
        EnvironmentError: If no remote repository is configured and there is something to delete.

    Returns:
        None
    """
    # Remover comentarios una vez aclarados por el agente
    if not garbage:
        return
    remote: str = require_remote()
    for garbage_item in garbage:
        branch = garbage_item.branch
        try:
            # ¿Hace falta todavía corroborar con ref_exists() usando el nuevo metodo? ¿Acaso ya sobra y es overkill?
            if garbage_item.remote and ref_exists(f"{REMOTE_PREFIX}/{remote}/{branch}"):
                result = run_operation(
                    f'git push -d "{remote}" "{branch}" --no-verify 2>&1', f"Deleting remote branch {branch}"
                )
                ws_success(result.stdout.strip())
            else:
                ws_advice(f"Branch '{branch}' has no counterpart on '{remote}'; skipping the remote deletion")
            # Misma duda que arriba: ¿Hace falta todavía corroborar con ref_exists() usando el nuevo metodo?
            # ¿Acaso ya sobra y es overkill?
            if garbage_item.local and ref_exists(f"{LOCAL_PREFIX}/{branch}"):
                run_operation(f'git branch -D "{branch}"', f"Deleting local branch {branch}")
                ws_success(f"Local branch '{branch}' deleted successfully")
            else:
                ws_advice(f"Branch '{branch}' has no local counterpart; skipping the local deletion")
            continue  # Hace falta este continue? ¿O es redundante y sobra?
        except subprocess.SubprocessError:
            continue
