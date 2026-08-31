"""Creates a detailed markdown report of the repository's branches filtered by merge status."""

from datetime import datetime, timezone
import click
from mega_snake.constants import REMOTE_BRANCHES_OPT
from mega_snake.remote_branches.remote_branch import BranchLoader, GitBranch
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.util.props import get_property
from mega_snake.util.repo import Repo
from mega_snake.util.util import run_operation

FILTER_LABELS: dict[str, str] = {
    "A": "all branches",
    "M": "fully merged branches",
    "U": "not fully merged branches",
}


def get_output_file() -> str:
    """Return the path to the markdown report file.

    Parameters:
        None

    Raises:
        None

    Returns:
        str: The report path under the working path.
    """
    return f"{get_property('working_path')}/remote_branches.md"


@click.command(
    name="remote-branches-details",
    short_help="Gets details of the repository branches",
    help="Creates a detailed markdown report of the repository's branches — local, remote and paired — "
    "filtered by merge status against the main branch",
    epilog="usage: mgsnake remote-branches-details [OPTIONS]",
)
@click.option(
    "--filter-by",
    "-f",
    type=click.Choice(REMOTE_BRANCHES_OPT, False),
    help="""filter branches by merge status against main branch:\n
    'M' - fully merged branches (every existing side is merged)\n
    'U' - not fully merged branches\n
    'A' - all branches (default)\n""",
    default="A",
)
def remote_branches_details(filter_by: str) -> None:
    """
    Calls the execute function to create a detailed markdown report of the repository branches.

    Args:
        filter_by: str - (A)ll [default], fully (M)erged or (U)nmerged against the main branch
    """
    execute(filter_by)


def execute(filter_by: str) -> None:
    """
    Creates the branches report: builds the branch inventory (which offers to fetch/prune first),
    applies the requested filter, and writes the markdown report to workspace_temp/remote_branches.md.

    Args:
        filter_by: str - (A)ll [default], fully (M)erged or (U)nmerged against the main branch

    Raises:
        ValueError: If the filter is not one of the allowed values.
        LookupError: If the repository has no branches to describe.
    """
    if filter_by not in REMOTE_BRANCHES_OPT:
        raise ValueError(
            f"Invalid filter: {filter_by}; filter value must be one of:\n {' | '.join(REMOTE_BRANCHES_OPT)}"
        )
    branches: list[GitBranch] = BranchLoader.from_repository()
    if not branches:
        # Not an invalid value: nothing was passed in. The enumeration simply found nothing, which is
        # the same kind of answer the main-branch lookups in Repo report, and it gets the same status
        # so a script can tell "your repository is empty" apart from "you passed a bad filter".
        raise LookupError("No branches found in the current repository")
    ws_info(f"Main branch: {Repo.MAIN_BRANCH}; Found {len(branches)} branches to describe")
    if filter_by == "M":
        branches = [branch for branch in branches if branch.fully_merged]
    elif filter_by == "U":
        branches = [branch for branch in branches if not branch.fully_merged]
    branches = sorted(branches, reverse=True)
    output_file: str = get_output_file()
    with open(output_file, "w", encoding="utf-8") as file:
        file.write(render_markdown_report(branches, filter_by))
    run_operation(f"code {output_file}", "opening remote branches file")
    ws_success(f"Successfully created remote branches details file at: {output_file}")


def render_markdown_report(branches: list[GitBranch], filter_by: str) -> str:
    """Render the full markdown report: title, repository context and the branches table.

    Parameters:
        branches: The branches to report, already filtered and sorted.
        filter_by: The filter the report was built with, echoed in the header.

    Raises:
        None

    Returns:
        str: The markdown document.
    """
    # TODO (copilot-instructions §8.4): add a --format option, alongside GitBranch.MD_HEADER.
    generated: str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header: str = (
        "# Branches Report\n\n"
        f"- **Remote:** {Repo.REMOTE or GitBranch.SHORT_NA}\n"
        f"- **Main branch:** {Repo.MAIN_BRANCH}"
        f" (local: {GitBranch.hash_cell(Repo.MAIN_LOCAL_HASH)},"
        f" remote: {GitBranch.hash_cell(Repo.MAIN_REMOTE_HASH)})\n"
        f"- **Filter:** {filter_by} ({FILTER_LABELS[filter_by]})\n"
        f"- **Generated:** {generated}\n\n"
        f"## Branches ({len(branches)})\n\n"
    )
    rows: str = "\n".join(branch.to_markdown_row() for branch in branches)
    return f"{header}{GitBranch.MD_HEADER}\n{rows}\n" if rows else f"{header}No branches match the filter.\n"
