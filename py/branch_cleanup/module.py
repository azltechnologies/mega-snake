"""Helper function for deleting branches merged branches from the remote repository."""

import os
from py.util.formatting import WorkspaceError, ws_info, ws_success
from py.util.util import get_validated_input
from py.branch_cleanup.parse_remote_branches import define_branches, RemoteBranch, parsing_branches, delete_branches
from py.remote_branches.module import main as remoteBranchesDetails, get_output_file


def main():
    """
    Deletes branches that have been merged into the main branch from the remote repository
    """
    prompt: str = "Do you want to rerun the remoteBranchesDetails function? (y/n)"
    yes_no_options: list[str] = {"y", "n"}
    if get_validated_input(prompt, yes_no_options) == "y":
        filter_options: set[str] = {"a", "m"}
        prompt = "Filter branches by (a)ll or (m)erged?"
        user_input: str = get_validated_input(prompt, filter_options)
        ws_info(f"Filtering branches by: {user_input}")
        remoteBranchesDetails(user_input)
        ws_success(f"Successfully ran `remoteBranchesDetails -f {user_input}` function")
    input_file:str = get_output_file()
    # check if input_file exists
    if not os.path.exists(input_file):
        e = FileNotFoundError(f"No file found at {input_file}")
        WorkspaceError.ws_error("File listing the remote branches not found", e)
        raise e
    # read the file
    with open(input_file, "r", encoding="utf-8") as file:
        branches: str = file.read().strip()
    # creating branches list
    branches_list: list[RemoteBranch] = map(define_branches,branches.split("\n"))
    branches_list = [x for x in branches_list if x is not None]
    branches_list = sorted(branches_list, reverse=False)
    # parsing branches
    garbage: list[str] = parsing_branches(branches_list)
    delete_branches(garbage)
    ws_success("Successfully deleted branches that have been merged into the main branch from the remote repository")
