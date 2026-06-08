"""Sets the environment configuration"""

import os
from typing import Optional
import sys
import click
from .diff_tree.module import main as diff_tree
from .light_weight.module import main as create_release, add_wrapper as create_release_result_callback
from .remote_branches.module import main as remote_branches, add_wrapper as remote_branches_result_callback
from .config_environment.module import main as config_environment, add_wrapper as config_env_result_callback
from .constants import LOGGING_OPT, SHELL_OPT, APP_NAME
from .util.formatting import get_traceback
from .util.props import init_app_properties
from .util.formatting import WorkspaceError, ws_advice
from .util.cli_group import CliGroup


@click.group(
    help="""A CLI tool focused on simplifying Java development with VSCode by automating workspace configuration.

Main features:
- Automated workspace setup for Java/Gradle projects
- Java and Gradle version management
- VSCode extensions and settings configuration
- Debug configurations and launch settings
- Local development environment setup
- Git integration and workspace organization""",
    epilog="""Examples:\n
    # Set up a complete workspace environment\n
    mgsnake working-env\n
    \n
    # Configure Java version\n
    mgsnake set-java\n
    \n
    # Configure Gradle version\n
    mgsnake set-gradle\n
    \n
    # Initialize local configurations\n
    mgsnake init-local-config\n
    \n
    # Run with debug logging\n
    mgsnake --log-level DEBUG <command>\n
    \n
For more details on specific commands, use: mgsnake <command> --help""",
    context_settings={"help_option_names": ["-h", "--help"]},
    cls=CliGroup,
    no_args_is_help=True,
)
@click.option("--log-level", "-l", type=click.Choice(list(LOGGING_OPT), False), default="INFO", help="log level")
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """cli entry point"""
    ctx.ensure_object(dict)  # Ensures ctx.obj is a dictionary
    try:
        light_weight: bool = False
        cmd_name = ctx.invoked_subcommand
        if cmd_name:
            cmd = cli.get_command(ctx, cmd_name)
            if not cmd:
                raise click.ClickException(f"Command '{cmd_name}' not found")
            # check if the command has cli_metadata
            metadata = getattr(cmd.callback, "flags", {})
            flags: Optional[set[str]] = metadata.get("flags")
            if flags and "no_init" in flags:
                return
            ws_advice(f"Invoking subcommand: {cmd_name}")
            if flags and "skip" in flags:
                ws_advice("'skip' flag detected. Running in light-weight mode if local working directory is not found.")
                light_weight = True
        shell = os.environ.get("MEGA_SNAKE_SHELL")
        if not shell:
            raise EnvironmentError("Environment variable 'MEGA_SNAKE_SHELL' is not set")
        if shell not in SHELL_OPT:
            raise ValueError(f"Unsupported shell: {shell}. Supported shells are: {', '.join(SHELL_OPT)}")
        init_app_properties(log_level, shell, light_weight)
    except Exception as e:
        click.echo(f"Error during initialization: {e}", err=True)
        click.echo(get_traceback(e), err=True)
        raise SystemExit(e) from e


@cli.result_callback()
@click.pass_context
def post_command(ctx, result, **kwargs) -> None:
    """Post-command execution logic"""
    if ctx.invoked_subcommand:
        ws_advice(
            f"Command '{ctx.invoked_subcommand}' completed successfully with result: {result} and kwargs: {kwargs}"
        )
    exit_code: int = ctx.obj.get("exit_code", 0)
    if exit_code:
        sys.exit(exit_code)


cli.add_command_with_alias(diff_tree, ["dt", "tree"])
for command in create_release.commands.values():
    cli.add_command(create_release_result_callback(command))
for command in config_environment.commands.values():
    cli.add_command(config_env_result_callback(command))
for command in remote_branches.commands.values():
    cli.add_command(remote_branches_result_callback(command))

if __name__ == "__main__":
    try:
        cli.main(prog_name=APP_NAME)
    except Exception as e:
        raise WorkspaceError("Error during cli execution", e) from e
