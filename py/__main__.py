""" Sets the environment configuration """

import os
import click
from .util.props import set_log_level
from .util.logger import config_log
from .diff_tree.module import main as diff_tree
from .util.formatting import ws_info


@click.group(
    help="Python CLI tool to prepare the environment for a vscode workspace and ",
    epilog="requires ...",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--log-level", "-l", type=click.STRING, default="INFO", help="log level")
@click.pass_context
def setup(ctx: click.Context = None, log_level: str = None) -> None:
    """Sets the initial environment configuration"""
    set_log_level(log_level)

    ctx.ensure_object(dict)
    working_path: str = os.getenv("WS_TEMP")
    # Check if the environment variable WS_TEMP is set
    if not working_path:
        raise click.ClickException("Environment variable 'WS_TEMP' is not set")
    # Convert the path to an absolute path
    working_path = os.path.abspath(working_path)
    # Check if the path exists
    if not os.path.exists(working_path):
        raise click.ClickException(f"Path {working_path} does not exist")
    # Check if the path is a directory
    if not os.path.isdir(working_path):
        raise click.ClickException(f"Path {working_path} is not a directory")
    # Check if the path is writable
    if not os.access(working_path, os.W_OK):
        raise click.ClickException(f"Path {working_path} is not writable")
    log_file: str = f"{working_path}/setup_environment.log"

    config_log(log_file)
    ctx.obj["WS_TEMP"] = working_path
    ws_info("Working path set to: " + working_path)


@setup.command(
    name="createDiffTree",
    short_help="Creates diff tree and commit list of current changes",
    help="Creates a diff tree of changes and a commit list of the current branch against master or a specified commit hash",
    epilog="the directory tree and commit list are created within $WS_TEMP path.",
)
@click.option("--commit-hash", "-c", type=click.STRING, default=None, help="Commit hash to compare against instead of master")
@click.pass_context
def create_diff_tree(ctx: click.Context, commit_hash: str) -> None:
    """
    calls the diff_tree module:

    Args:
        commit_hash: str | None
    """
    ws_temp: str = f"{ctx.obj['WS_TEMP']}/diff_tree"
    diff_tree(ws_temp, commit_hash)

if __name__ == "__main__":
    setup(prog_name="set_env")
