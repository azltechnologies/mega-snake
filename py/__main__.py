""" Sets the environment configuration """

import os
from typing import Optional
import click
from .branch_cleanup.module import main as branch_cleanup
from .config_environment.module import echo as msg
from .util.logger import get_traceback
from .util.props import init_app_properties
from .diff_tree.module import main as diff_tree
from .remote_branches.module import main as remote_branches
from .util.formatting import WorkspaceError, ws_advice


@click.group(
    help="Python CLI tool to prepare the environment for a vscode workspace and ",
    epilog="requires ...",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--log-level", "-l", type=click.STRING, default="INFO", help="log level")
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:  # mypy: ignore-assignement
    """cli entry point"""
    try:
        working_path: Optional[str] = os.getenv("WS_TEMP")  # my
        init_app_properties(log_level, working_path)
        if ctx.invoked_subcommand:
            ws_advice(f"Invoking subcommand: {ctx.invoked_subcommand}")
    except Exception as e:
        print(f"Error during initialization: {e}")
        print(get_traceback(e))
        raise SystemExit(e) from e


@cli.result_callback()
@click.pass_context
def post_command(ctx, result, **kwargs):  # pylint: disable=W0613
    """Post-command execution logic"""
    if ctx.invoked_subcommand:
        ws_advice(f"Command '{ctx.invoked_subcommand}' completed successfully")


@cli.command(
    name="createDiffTree",
    short_help="Creates diff tree and commit list of current changes",
    help="Creates a diff tree of changes and a commit list of the current branch against master or a specified commit hash",
    epilog="the directory tree and commit list are created within $WS_TEMP path.",
)
@click.option("--commit-hash", "-c", type=click.STRING, default=None, help="Commit hash to compare against instead of master")
def create_diff_tree(commit_hash: str) -> None:
    """
    calls the diff_tree module:

    Args:
        commit_hash: str | None
    """
    diff_tree(commit_hash)


@cli.command(
    name="remoteBranchesDetails",
    short_help="Gets details of remote branches",
    help="Creates a detailed list of remote branches filtered by type",
    epilog="the branch details are created within $WS_TEMP path.",
)
@click.option(
    "--filter_by",
    "-f",
    type=click.Choice(["M", "U", "A"], False),
    help="""filter branches by merge status against main branch:\n
    'M' - merged branches\n
    'U' - unmerged branches\n
    'A' - all branches (default)\n""",
    default="A",
)
def remote_branches_details(filter_by: str) -> None:
    """
    calls the remote_branches module:

    Args:
        filter_by: str | "A"
    """
    remote_branches(filter_by)


@cli.command(
    name="remoteBranchesCleanUp",
    short_help="Helper function for deleting branches merged branches from the remote repository.",
    help="Iterates over the remote branches asking the user which merged branches to delete",
    epilog="Requires user input to delete branches",
)
def remote_branches_clean_up() -> None:
    """
    calls the branch_cleanup module
    """
    branch_cleanup()


@cli.command(
    name="msg",
    short_help="Prints message to the console and logs it.",
    help="Prints a message to the console in a custom format and logs it into the workspace configuration log file.",
    epilog="""
    usage: set_env msg <message> [-t | --type]  <type>\n
    OPTIONS:\n
        type: message type value must be one of:\n
            S | I | W | E | A | T
    """,
)
@click.argument("message", type=click.STRING)
@click.option(
    "--type",
    "-t",
    type=click.Choice(["S", "I", "W", "E", "A", "T"], False),
    help="""The type of message to be printed:\n
        'S' - Success\n
        'I' - Information -- default\n
        'W' - Warning\n
        'E' - Error\n
        'A' - Advice -- use for Debugging\n
        'T' - Tip\n
     """,
    default="I",
)
def echo(message: str, type: str) -> None:
    """
    Calls the echo function from the config_environment module

    Args:
        message: str
        type: str
    """
    msg(message, type)


if __name__ == "__main__":
    try:
        cli(prog_name="set_env")
    except Exception as e:
        raise WorkspaceError("Error during initialization", e) from e
