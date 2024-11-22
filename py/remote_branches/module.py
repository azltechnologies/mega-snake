"""Creates a detailed list of remote branches filtered by type"""

import re
import os
from py.util.formatting import WorkspaceError, ws_info
from py.util.remote_branch import RemoteBranch
from py.util.util import run_operation, get_main_branch
from py.util import props


def main(filter_by: str):
    """
    Creates a detailed list of remote branches filtered by type

    Args:
        filter: str
    """
    main_branch: str = get_main_branch()
    list_output: str = f"{props.APP_PROPERTIES.working_path}/remote_branches.txt"
    # check if list_output directory exists. if so, delete it
    if os.path.exists(list_output):
        os.remove(list_output)

    remote_branches: list[RemoteBranch] = []
    branches: str = run_operation("git branch -a", "Getting remote branches").stdout.strip()
    if not branches:
        e = ValueError("No remote branches found in the current repository")
        raise WorkspaceError("No remote branches found", e) from e
    branches = f"{branches}\n remotes/origin/HEAD master"
    pattern = r"^\s*(remotes/(?!origin/HEAD).+)$"
    matches = re.findall(pattern,branches,re.MULTILINE)
    total_branches = len(matches)
    ws_info(f"Main branch: {main_branch}; Found {total_branches} remote branches to process")
    for match in matches:
        branch = str(match)
        ws_info(f"Processing branch: {branch}")
        remote_branches.append(RemoteBranch.from_branch(branch, filter_by, main_branch))
        remote_branches = [x for x in remote_branches if x is not None]
        total_branches -= 1
        ws_info(f"Remaining branches to process: {total_branches}")

    # sort the remote branches by 
    remote_branches = sorted(remote_branches, key=lambda r: r.commit.dt, reverse=True)
    output:str = ""
    for remote_branch in remote_branches:
        output += remote_branch.printing_remote_branches_details()
    with open(list_output, "a", encoding="utf-8") as file:
        file.write(output)
    run_operation(f"code {list_output}", "opening remote branches file")
