#!/usr/bin/env python3

"""Creates a diff tree of the current branch against master"""

from py.util.formatting import ws_error,ws_info
from py.util.util import run_operation
from py.diff_tree.file_type import FileType


def main(tree_output:str, commit_hash: str = None):
    current_branch: str = run_operation("git rev-parse HEAD", "Getting current branch").stdout.strip()
    main_branch: str
    if commit_hash is None:
        main_branch = run_operation("git remote show origin | sed -n '/HEAD branch/s/.*: //p'", "Getting main branch").stdout.strip()
        ws_info(f"Main branch: {main_branch}")
    else:
        commit_validation: str = run_operation(f"git cat-file -t {commit_hash} 2>/dev/null", "Checking if commit hash is valid").stdout.strip()
        if commit_validation != "commit":
            ws_error(f"Invalid commit hash: {commit_hash}", ValueError(f"Invalid commit hash: {commit_hash}"))
        main_branch = commit_hash
    differences: list[str] = run_operation(f"git diff-tree -r {main_branch} {current_branch}", "getting differences between branches").stdout.strip().split("\n")
    # iterate over the differences and write them to the output file
    for diff in differences:
        columns: list[str] = diff.split("\t")
        symbol = columns[0].split(" ")[4]
        path: str = columns[1]
        FileType.from_symbol(symbol).add(path)
