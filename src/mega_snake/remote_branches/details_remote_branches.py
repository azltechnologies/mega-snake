"""Creates a detailed list of remote branches filtered by type"""

import re
import os
from typing import Optional
import click
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.remote_branches.remote_branch import RemoteBranch
from mega_snake.util.util import run_operation, get_main_branch, get_remote
from mega_snake.util.props import get_property
from mega_snake.constants import REMOTE_BRANCHES_OPT


def get_output_file() -> str:
    """Returns the path to the output file"""
    return f"{get_property('working_path')}/remote_branches.txt"


@click.command(
    name="remote-branches-details",
    short_help="Gets details of remote branches",
    help="Creates a detailed list of remote branches filtered by type",
    epilog="""The branch details are created within $WS_TEMP path.\n
    usage: mgsnake remote-branches-details [OPTIONS]\n
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
    Calls the execute function to create a detailed list of remote branches filtered by type

    Args:
        filter_by: str | "A"
    """
    execute(filter_by)


def execute(filter_by: str, remote: Optional[str] = None) -> None:
    """
    Creates a detailed list of remote branches filtered by type

    Args:
        filter_by: str | "A"
    """
    if filter_by not in REMOTE_BRANCHES_OPT:
        raise ValueError(
            f"Invalid filter: {filter_by}; filter value must be one of:\n {' | '.join(REMOTE_BRANCHES_OPT)}"
        )
    if not remote:
        remote = get_remote()
    if not remote:
        raise LookupError("No remote repository found. Please add a remote repository to the current repository.")
    run_operation("git fetch --all --prune", "Fetching all remotes and pruning deleted branches")
    main_branch: str = get_main_branch(remote)
    list_output: str = get_output_file()
    # check if list_output directory exists. if so, delete it
    if os.path.exists(list_output):
        os.remove(list_output)

    opt_remote_branches: list[Optional[RemoteBranch]] = []
    branches: str = run_operation("git branch -a", "Getting remote branches").stdout.strip()
    if not branches:
        raise ValueError("No remote branches found in the current repository")
    branches = f"{branches}\n remotes/origin/HEAD master"
    matches = re.findall(rf"^\s*(remotes/(?!{remote}/HEAD){remote}/.+)$", branches, re.MULTILINE)
    total_branches = len(matches)
    ws_info(f"Main branch: {main_branch}; Found {total_branches} remote branches to process")
    for match in matches:
        branch = str(match)
        # if branch include single or double quotes, wrap it in the opposite quotes
        if '"' in branch:
            branch = f"'{branch}'"
        elif "'" in branch:
            branch = f'"{branch}"'
        ws_info(f"Processing branch: {branch} filtered by: '{filter_by}'")
        if remote:
            opt_remote_branches.append(RemoteBranch.from_branch(branch, filter_by, main_branch, remote))
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
    ws_success(f"Successfully created remote branches details file at: {list_output}")
