"""Interactively deletes branches already merged into the main branch, locally and on the remote."""

import click
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.util.util import run_operation
from mega_snake.remote_branches.remote_branch import BranchLoader, GitBranch
from mega_snake.remote_branches.parse_remote_branches import (
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
    """
    branches: list[GitBranch] = BranchLoader.from_repository()
    if not branches:
        ws_info("No branches found in the current repository; nothing to clean up")
        return
    garbage: list[Garbage] = parsing_branches(branches)
    if not garbage:
        ws_info("No branches were selected for deletion")
        return
    delete_branches(garbage)
    if any(item.remote for item in garbage):
        run_operation("git fetch --all --prune", "Fetching all remotes and pruning deleted branches")
    ws_success("Successfully deleted branches that have been merged into the main branch")
