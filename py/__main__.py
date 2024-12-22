""" Sets the environment configuration """

from typing import Optional
import sys
import click
from .diff_tree.module import main as diff_tree
from .create_release.module import main as create_release
from .remote_branches.module import main as remote_branches, add_wrapper as remote_branches_result_callback
from .gcloud.module import main as gcloud, add_wrapper as gcloud_result_callback
from .config_environment.module import main as config_environment, add_wrapper as config_env_result_callback
from .constants import LOGGING_OPT, SHELL_OPT
from .util.formatting import get_traceback
from .util.props import init_app_properties
from .util.formatting import WorkspaceError, ws_advice, ws_info, ws_warning


@click.group(
    help="Python CLI tool to prepare the environment for a vscode workspace and ",
    epilog="requires ...",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--log-level", "-l", type=click.Choice(list(LOGGING_OPT), False), default="INFO", help="log level")
@click.option("--shell", type=click.Choice(SHELL_OPT, False), required=True, hidden=True)
@click.option("--skip-initilization", "-s", is_flag=True, help="Skip initialization in those commands that support it")
@click.pass_context
def cli(ctx: click.Context, log_level: str, shell: str, skip_initilization: bool) -> None:
    """cli entry point"""
    ctx.ensure_object(dict)  # Ensures ctx.obj is a dictionary
    try:
        cmd_name = ctx.invoked_subcommand
        if cmd_name:
            ws_advice(f"Invoking subcommand: {cmd_name}")
            if skip_initilization:
                # Access params
                cmd = cli.get_command(ctx, cmd_name)
                if not cmd:
                    raise click.ClickException(f"Command '{cmd_name}' not found")
                # check if the command has cli_metadata
                metadata = getattr(cmd.callback, "flags", {})
                flags: Optional[set[str]] = metadata.get("flags")
                if flags and "skip" in flags:
                    ws_info("'skip' flag detected. Skipping initialization.")
                    return
                ws_warning("'skip' flag detected but not supported by the invoked command. \n Proceeding with initialization.")
        init_app_properties(log_level, shell)
    except Exception as e:
        print(f"Error during initialization: {e}")
        print(get_traceback(e))
        raise SystemExit(e) from e


@cli.result_callback()
@click.pass_context
def post_command(ctx, result, **kwargs) -> None:
    """Post-command execution logic"""
    if ctx.invoked_subcommand:
        ws_advice(f"Command '{ctx.invoked_subcommand}' completed successfully with result: {result} and kwargs: { kwargs}")
    exit_code: int = ctx.obj.get("exit_code", 0)
    if exit_code:
        sys.exit(exit_code)


cli.add_command(diff_tree)
cli.add_command(create_release)
for command in config_environment.commands.values():
    cli.add_command(config_env_result_callback(command))
for command in gcloud.commands.values():
    cli.add_command(gcloud_result_callback(command))
for command in remote_branches.commands.values():
    cli.add_command(remote_branches_result_callback(command))

if __name__ == "__main__":
    try:
        cli.main(prog_name="set_env")
    except Exception as e:
        raise WorkspaceError("Error during cli execution", e) from e
