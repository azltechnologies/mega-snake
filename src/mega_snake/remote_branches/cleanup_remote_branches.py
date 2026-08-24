"""Interactively deletes branches already merged into the main branch, locally and on the remote."""

import click
from mega_snake.util.formatting import ws_info, ws_success, ws_warning
from mega_snake.util.util import run_operation
from mega_snake.remote_branches.remote_branch import BranchLoader, GitBranch
from mega_snake.remote_branches.parse_remote_branches import (
    DeletionOutcome,
    Garbage,
    parsing_branches,
    delete_branches,
)


@click.command(
    name="remote-branches-cleanup",
    short_help="Deletes merged branches from the remote and the local repository.",
    help="Builds the branch inventory (local, remote and paired branches) and iterates over the fully "
    "merged ones asking which to delete, removing each selected branch from the sides where it exists",
    epilog="usage: mgsnake remote-branches-cleanup",
)
def remote_branches_cleanup() -> None:
    """
    Deletes branches that have been merged into the main branch, from the remote and locally.

    Builds the same branch inventory as remote-branches-details — offering to fetch/prune first —
    but instead of writing it to a file, feeds it directly to the interactive selection. Each
    selected branch is deleted from the sides (local / remote) where it exists, and the remote
    references are pruned afterwards when anything was deleted remotely.

    The closing message reports what the run actually achieved. Announcing a blanket success was
    wrong whenever a deletion failed: those failures are swallowed on purpose so one unreachable
    branch cannot abort the cleanup, which left the user with a success line and no way to tell
    that a branch had survived it.
    """
    branches: list[GitBranch] = BranchLoader.from_repository()
    if not branches:
        ws_info("No branches found in the current repository; nothing to clean up")
        return
    garbage: list[Garbage] = parsing_branches(branches)
    if not garbage:
        ws_info("No branches were selected for deletion")
        return
    outcome: DeletionOutcome = delete_branches(garbage)
    # Pruning is driven by what was really deleted, not by what was selected: a run whose pushes all
    # failed has nothing to prune.
    if outcome.remote_deleted:
        run_operation("git fetch --all --prune", "Fetching all remotes and pruning deleted branches")
    deleted: int = len(outcome.remote_deleted) + len(outcome.local_deleted)
    if deleted:
        ws_success(
            f"Deleted {len(outcome.remote_deleted)} remote and {len(outcome.local_deleted)} local "
            "branches that have been merged into the main branch"
        )
    if outcome.failures:
        ws_warning(f"{len(outcome.failures)} branch side(s) could not be deleted:")
        for failure in outcome.failures:
            ws_warning(f"\t{failure}")
