""" Sets the environment configuration """

import os
import click
from .util.props import LOG_LEVEL
from .util.logger import config_log
from .diff_tree.module import main as diff_tree
from .util.formatting import ws_info

@click.group()
@click.pass_context
def setup(ctx: click.Context=None) -> None:
    """Sets the initial environment configuration"""

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

    config_log(LOG_LEVEL, log_file)
    ctx.obj["WS_TEMP"] = working_path
    ws_info("Working path set to: " + working_path)


@click.command()
@click.option("--commit-hash","--c", type=click.STRING, default=None, help="Commit hash")
@click.pass_context
def create_diff_tree(ctx: click.Context, commit_hash: str) -> None:
    """
        calls the diff_tree module

        Args:
            ctx: click.Context
            commit_hash: str
    """
    ws_temp: str = f"{ctx.obj['WS_TEMP']}/diff_tree"
    diff_tree(ws_temp, commit_hash)

setup.add_command(create_diff_tree)

if __name__ == "__main__":
    setup()
