"""Creates a detailed list of remote branches filtered by type"""

import re
import os
from typing import Optional
import click
from py.util.formatting import ws_info
from py.remote_branches.remote_branch import RemoteBranch
from py.util.util import run_operation, get_main_branch
from py.util.props import AppProperties
from py.constants import REMOTE_BRANCHES_OPT


def get_output_file() -> str:
    """Returns the path to the output file"""
    return f"{AppProperties.get_instance().retrieve_property("working_path")}/remote_branches.txt"

@click.command(
    name="remoteBranchesDetails",
    short_help="Gets details of remote branches",
    help="Creates a detailed list of remote branches filtered by type",
    epilog="""The branch details are created within $WS_TEMP path.\n
    usage: set_env remoteBranchesDetails [OPTIONS]\n
    OPTIONS:\n
        -f | --filter-by: Optional[str] - filter branches by merge status against main branch\n
    """,
)
@click.option(
    "--filter-by",
    "-f",
    type=click.Choice(REMOTE_BRANCHES_OPT, False),
    help="""filter branches by merge status against main branch:\n
    'M' - merged branches\n
    'U' - unmerged branches\n
    'A' - all branches (default)\n""",
    default="A",
)
def remote_branches_details(filter_by: str) -> None:
    """
    Creates a detailed list of remote branches filtered by type

    Args:
        filter_by: str | "A"
    """
    if filter_by not in REMOTE_BRANCHES_OPT:
        raise ValueError(f"Invalid filter: {filter_by}; filter value must be one of:\n {' | '.join(REMOTE_BRANCHES_OPT)}")
    main_branch: str = get_main_branch()
    list_output: str = get_output_file()
    # check if list_output directory exists. if so, delete it
    if os.path.exists(list_output):
        os.remove(list_output)

    opt_remote_branches: list[Optional[RemoteBranch]] = []
    branches: str = run_operation("git branch -a", "Getting remote branches").stdout.strip()
    if not branches:
        raise ValueError("No remote branches found in the current repository")
    branches = f"{branches}\n remotes/origin/HEAD master"
    matches = re.findall(r"^\s*(remotes/(?!origin/HEAD).+)$", branches, re.MULTILINE)
    total_branches = len(matches)
    ws_info(f"Main branch: {main_branch}; Found {total_branches} remote branches to process")
    for match in matches:
        branch = str(match)
        ws_info(f"Processing branch: {branch} filtered by: '{filter_by}'")
        opt_remote_branches.append(RemoteBranch.from_branch(branch, filter_by, main_branch))
        total_branches -= 1
        ws_info(f"Remaining branches to process: {total_branches}")

    remote_branches: list[RemoteBranch] = [x for x in opt_remote_branches if x is not None]
    # sort the remote branches by
    remote_branches = sorted(remote_branches, key=lambda r: r.commit.dt, reverse=True)
    output: str = ""
    for remote_branch in remote_branches:
        output += remote_branch.printing_remote_branches_details()
    with open(list_output, "a", encoding="utf-8") as file:
        file.write(output)
    run_operation(f"code {list_output}", "opening remote branches file")
