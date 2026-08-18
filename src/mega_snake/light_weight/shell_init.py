"""
Light-weight commands for shell initialization.

Provides commands to print the packaged shell init script path and the resolved local config file
path, plus the two commands whose real work is carried out by the shell itself (`reload-config` and
`load-env`).
"""

import sys
from importlib.resources import files
from typing import Optional
import click
from mega_snake.constants import (
    LOAD_ENV_COMMAND,
    LOAD_ENV_EXIT_CODE,
    MODULE_NAME,
    RELOAD_CONFIG_COMMAND,
    RELOAD_ENVIRONMENT_EXIT_CODE,
    SHELL_OPT,
)
from mega_snake.config_environment.util import get_local_file, get_local_env
from mega_snake.util.util import cli_metadata

CONFIG_SCRIPT = "config_setup"
WIN_SHELLS: list[str] = ["powershell", "pwsh"]
SH_SHELLS: list[str] = ["bash", "zsh"]


@click.command(
    name="shell-path",
    short_help="Prints the current location of the script file to be sourced.",
    help="Prints to stdout the path of the packaged shell initialization script"
    " (config_setup.sh or config_setup.ps1) to be sourced from the shell profile.",
    epilog="""
    usage: mgsnake shell-path <shell>\n
    Args:\n
        shell: str - The shell to be initialized.
    """,
)
@cli_metadata(flags={"no_init"})
@click.argument("shell", type=click.Choice(SHELL_OPT, False))
def shell_path(shell: str) -> None:
    """
    Prints the current location where this cli was installed followed by the script file to be sourced.

    Args:
        shell (str): The shell to be initialized.

    Returns:
        None
    """
    ext: str
    if shell in WIN_SHELLS:
        ext = "ps1"
    elif shell in SH_SHELLS:
        ext = "sh"
    else:
        raise ValueError(f"Unsupported shell: {shell}")
    script_path = files(MODULE_NAME).joinpath(f"{CONFIG_SCRIPT}.{ext}")

    # validate it exists
    if not script_path.is_file():
        raise FileNotFoundError(f"Configuration script not found at {script_path}")
    click.echo(str(script_path))


@click.command(
    name="local-config-path",
    short_help="Prints the current location of the local configuration file.",
    help="Prints to stdout the path of the local configuration file (.sh or .ps1 depending on the active shell).",
    epilog="usage: mgsnake local-config-path",
)
def get_local_config_path() -> None:
    """
    Prints the current location of the local configuration file (.sh or .ps1 depending on
    the active shell). Only the path is written to stdout so the output stays parseable.

    Returns:
        None
    """
    click.echo(get_local_file())


@click.command(
    name="local-env-path",
    short_help="Prints the current location of the local environment file.",
    help="Prints to stdout the path of the local environment file.",
    epilog="usage: mgsnake local-env-path",
)
def get_local_env_path() -> None:
    """
    Prints the current location of the local environment file.
    Only the path is written to stdout so the output stays parseable.

    Returns:
        None
    """
    click.echo(get_local_env())


@click.command(
    name=RELOAD_CONFIG_COMMAND,
    short_help="Reloads the local configuration file in the current shell session.",
    help="Re-sources the local configuration file (and the environment file it loads) into the"
    " current shell session, so edits to it take effect without opening a new terminal.",
    epilog=f"usage: mgsnake {RELOAD_CONFIG_COMMAND}",
)
@cli_metadata(flags={"no_init"})
def reload_config() -> None:
    """Ask the shell to re-source the local configuration file.

    The work cannot happen here: a child process cannot mutate its parent's environment, so this
    command only reports the request through its exit status and the `mgsnake` shell function
    installed by config_setup performs the sourcing in the session that asked for it.

    Raises:
        SystemExit: Always, carrying RELOAD_ENVIRONMENT_EXIT_CODE.

    Returns:
        None
    """
    sys.exit(RELOAD_ENVIRONMENT_EXIT_CODE)


@click.command(
    name=LOAD_ENV_COMMAND,
    short_help="Loads an environment file into the current shell session.",
    help="Exports the variables declared in an environment file into the current shell session."
    " The file is a plain list of KEY=value lines: no `export` keyword, one pair per line, `#`"
    " starts a comment, and surrounding single or double quotes around a value are stripped.",
    epilog=f"""
    usage: mgsnake {LOAD_ENV_COMMAND} [env_file]\n
    Args:\n
        env_file: Optional[str] - Path to the environment file to load. When omitted, the local
        environment file (see `local-env-path`, e.g. `.mgsnake.env` under workspace_temp) is loaded
        if it exists; otherwise `.env` in the current directory is loaded instead.
    """,
)
@cli_metadata(flags={"no_init"})
@click.argument("env_file", required=False, type=click.Path())
def load_env(env_file: Optional[str]) -> None:  # pylint: disable=unused-argument
    """Ask the shell to export the variables declared in an environment file.

    Like `reload-config`, the exporting itself has to happen in the caller's own session, so this
    command only reports the request through its exit status. The shell function recovers
    ``env_file`` by re-reading the arguments it was given, which is why nothing needs to travel
    through stdout and this command can log freely.

    ``env_file`` is deliberately declared but unused here: the declaration is what puts the argument
    in `--help` and in the generated reference, and what makes click reject a second positional
    argument. The value itself is only ever consumed by the shell.

    Parameters:
        env_file: Path to the environment file, or None to let the shell fall back first to the
            local environment file (if it exists) and then to `.env` in the current directory.

    Raises:
        SystemExit: Always, carrying LOAD_ENV_EXIT_CODE.

    Returns:
        None
    """
    sys.exit(LOAD_ENV_EXIT_CODE)
