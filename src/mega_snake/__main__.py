"""Sets the environment configuration"""

import os
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as get_package_version
from typing import Optional
import sys
import click
from .diff_tree.module import registration as diff_tree
from .docs_gen.module import registration as docs_gen
from .light_weight.module import registration as create_release
from .remote_branches.module import registration as remote_branches
from .config_environment.module import registration as config_environment
from .dependency_audit.module import registration as dependency_audit
from .state.module import registration as state
from .jira_api.module import registration as jira_api
from .constants import LOGGING_OPT, SHELL_ENV_VARIABLE, SHELL_OPT, APP_NAME, MODULE_NAME
from .util.formatting import get_traceback
from .util.props import init_app_properties
from .util.formatting import WorkspaceError, ws_advice
from .util.command_registration import ModuleRegistration
from .util.cli_group import ATTR_METADATA, META_FLAGS, CliGroup


def get_version() -> str:
    """Return the installed package version, falling back to 'unknown' when not installed.

    Parameters:
        None

    Raises:
        None

    Returns:
        str: The installed distribution version, or "unknown" if the package metadata
            cannot be found (e.g. running from a source checkout without installation).
    """
    try:
        return get_package_version(MODULE_NAME)
    except PackageNotFoundError:
        return "unknown"


def print_version(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    """Print the CLI version and exit, invoked eagerly by the `-v`/`--version` option.

    Parameters:
        ctx: The current click context.
        _param: The click parameter that triggered this callback (unused).
        value: Whether the flag was provided on the command line.

    Raises:
        None

    Returns:
        None
    """
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"{APP_NAME}, version {get_version()}")
    ctx.exit()


@click.option(
    "--version",
    "-v",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=print_version,
    help="Show the version and exit.",
)
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
For more details on specific commands, use: mgsnake <command> --help\n
For the full reference — outputs, examples and caveats — use: mgsnake man [COMMAND]""",
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
            metadata = getattr(cmd.callback, ATTR_METADATA, {})
            flags: Optional[set[str]] = metadata.get(META_FLAGS)
            if flags and "no_init" in flags:
                return
            ws_advice(f"Invoking subcommand: {cmd_name}")
            if flags and "skip" in flags:
                ws_advice("'skip' flag detected. Running in light-weight mode if local working directory is not found.")
                light_weight = True
        shell = os.environ.get(SHELL_ENV_VARIABLE)
        if not shell:
            raise EnvironmentError(f"Environment variable '{SHELL_ENV_VARIABLE}' is not set")
        if shell not in SHELL_OPT:
            raise ValueError(f"Unsupported shell: {shell}. Supported shells are: {', '.join(SHELL_OPT)}")
        init_app_properties(log_level, shell, light_weight)
    except click.ClickException:
        # Click already owns both halves of this: the message it prints and the status it exits
        # with. Echoing it here too would print it twice.
        raise
    except Exception as e:
        click.echo(f"Error during initialization: {e}", err=True)
        click.echo(get_traceback(e), err=True)
        # Deliberately re-raised with its type intact instead of being converted to a SystemExit.
        # `SystemExit(e)` uses its argument as the status only when that argument is an int; given
        # an exception it prints it and exits 1, flattening every initialization failure to the same
        # code. main() turns this into a WorkspaceError, whose registered status is what actually
        # reaches the shell.
        raise


@cli.result_callback()
@click.pass_context
def post_command(ctx, result, **kwargs) -> None:
    """Deliver the exit status a successful command asked for.

    The only status that travels this way today is RELOAD_ENVIRONMENT_EXIT_CODE: the command
    succeeded, and the shell wrapper installed by ``config_setup.sh`` / ``config_setup.ps1`` must
    re-source the local environment files because a child process cannot mutate its parent's
    environment. ``sys.exit`` here is what turns that request into something the shell can branch
    on; without it the process would report a plain success and the signal would die in-process.
    """
    if ctx.invoked_subcommand:
        ws_advice(
            f"Command '{ctx.invoked_subcommand}' completed successfully with result: {result} and kwargs: {kwargs}"
        )
    exit_code: int = ctx.obj.get("exit_code", 0)
    if exit_code:
        sys.exit(exit_code)


# Registration order drives the order shown in the help output.
MODULES: list[ModuleRegistration] = [
    diff_tree,
    docs_gen,
    create_release,
    config_environment,
    remote_branches,
    dependency_audit,
    state,
    jira_api,
]

for module in MODULES:
    for command in module.group.commands.values():
        cli.add_command(module.wrap(command))


def main() -> None:
    """Run the CLI: the single place where an exception becomes an exit code.

    This is what ``[project.scripts]`` must point at, never at ``cli``. Pointing it at the group makes
    the installed executable call click directly, so the translation below — and with it the
    installation of ``_on_crash`` as the except hook — only runs under ``python -m mega_snake``, which
    no user types: every failure then reports the same status.

    ``click.ClickException`` is re-raised untouched because Click already knows its status
    (``exit_code``); wrapping it would relabel a user error as an internal one. Anything else
    becomes a ``WorkspaceError``, which resolves the status from ``ERROR_CODES`` and arms the except
    hook that delivers it. ``SystemExit`` is a ``BaseException``, so the reload signal raised by
    ``post_command`` passes straight through.

    Parameters:
        None

    Raises:
        WorkspaceError: Wrapping any unexpected exception, carrying its resolved exit code.

    Returns:
        None
    """
    try:
        cli.main(prog_name=APP_NAME)
    except click.ClickException:
        raise
    except Exception as e:
        raise WorkspaceError("Error during cli execution", e) from e


if __name__ == "__main__":
    main()
