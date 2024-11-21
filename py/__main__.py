""" Sets the environment configuration """

import os
import click
from .util.logger import get_traceback
from .util.props import init_app_properties
from .diff_tree.module import main as diff_tree
from .util.formatting import ws_info, ws_error, ws_success, ws_tip


@click.group(
    help="Python CLI tool to prepare the environment for a vscode workspace and ",
    epilog="requires ...",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--log-level", "-l", type=click.STRING, default="INFO", help="log level")
@click.pass_context
def cli(ctx: click.Context = None, log_level: str = None) -> None:
    """cli entry point"""
    try:
        working_path: str = os.getenv("WS_TEMP")
        init_app_properties(log_level, working_path)
        if ctx.invoked_subcommand:
            ws_tip("Invoking subcommand:", ctx.invoked_subcommand)
    except Exception as e:
        print(f"Error during initialization: {e}")
        print(get_traceback(e))
        raise SystemExit(e) from e

@cli.result_callback()
@click.pass_context
def post_command(ctx, result, **kwargs): # pylint: disable=W0613
    """Post-command execution logic"""
    if ctx.invoked_subcommand:
        ws_success(f"Command '{ctx.invoked_subcommand}' completed successfully")

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
    short_help="Creates a workspace configuration",
    help="Creates a workspace configuration for vscode",
    epilog="the workspace configuration is created within $WS_TEMP path.",
)
@click.option(
    "--filert", "-f", 
    type=click.Choice(['m','u','a'],True), help="filter the branches to a specific type where:")
def dum() -> None:
    pass



if __name__ == "__main__":
    try:
        cli(prog_name="set_env")
    except Exception as e: # pylint: disable=W0703
        ws_error("Error during initialization", e)
