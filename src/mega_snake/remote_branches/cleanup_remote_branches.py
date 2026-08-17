"""Helper function for deleting branches merged branches from the remote repository."""

import os
from typing import Optional
import click
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.util.util import get_validated_input, require_remote, run_operation
from mega_snake.remote_branches.parse_remote_branches import (
    define_branches,
    RemoteBranch,
    parsing_branches,
    delete_branches,
)
from mega_snake.remote_branches.details_remote_branches import execute as remote_branches_details, get_output_file


@click.command(
    name="remote-branches-cleanup",
    short_help="Deletes merged branches from the remote repository.",
    help="Iterates over the remote branches asking the user which merged branches to delete",
    epilog="usage: mgsnake remote-branches-cleanup",
)
def remote_branches_cleanup() -> None:
    """
    Deletes branches that have been merged into the main branch from the remote repository.

    Offers to re-run remote-branches-details first to refresh the data, reads the report from
    workspace_temp/remote_branches.txt, asks which branches to delete, deletes them from the
    remote, and prunes the local references.
    """
    remote: str = require_remote()
    prompt: str = "Do you want to rerun the remote-branches-details function?"
    yes_no_options: list[str] = ["y", "n"]
    if get_validated_input(prompt, yes_no_options) == "y":
        filter_options: list[str] = ["a", "m"]
        prompt = "Filter branches by (a)ll or (m)erged?"
        user_input: str = get_validated_input(prompt, filter_options).upper()
        ws_info(f"Filtering branches by: {user_input}")
        remote_branches_details(user_input, remote)
        ws_success(f"Successfully ran `remote-branches-details -f {user_input}` function")
    input_file: str = get_output_file()
    # check if input_file exists
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"No file found at {input_file}; File listing the remote branches not found")
    # read the file
    with open(input_file, "r", encoding="utf-8") as file:
        branches: str = file.read().strip()
    # check if branches is empty
    if not branches:
        # Not a bug: the "pipeline via files" design lets the user skip the refresh and hand-edit
        # the report, so an empty file is user-supplied input. IOError is an alias of OSError, whose
        # slot in ERROR_CODES is already taken by EnvironmentError, so it would resolve to 112 and
        # read as an environment failure; ValueError says what this actually is.
        raise ValueError(
            f"No branches found in the file {input_file}. No records in {input_file}, "
            "verify that the file is being written correctly"
        )
    lines: list[str] = branches.split("\n")
    # creating branches list
    opt_branches_list: list[Optional[RemoteBranch]] = list(map(define_branches, lines))
    branches_list: list[RemoteBranch] = [x for x in opt_branches_list if x is not None]
    branches_list = sorted(branches_list, reverse=False)
    # parsing branches
    garbage: list[str] = parsing_branches(branches_list, remote)
    delete_branches(garbage)
    run_operation("git fetch --all --prune", "Fetching all remotes and pruning deleted branches")
    ws_success("Successfully deleted branches that have been merged into the main branch from the remote repository")
