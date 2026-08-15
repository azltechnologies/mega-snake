"""
Light-weight commands for shell initialization.

Provides commands to print the packaged shell init script path and the resolved local config file path.
"""

from importlib.resources import files
import click
from mega_snake.constants import SHELL_OPT, MODULE_NAME
from mega_snake.config_environment.util import get_local_file
from mega_snake.util.util import cli_metadata

CONFIG_SCRIPT = "config_setup"
WIN_SHELLS: list[str] = ["powershell", "pwsh"]
SH_SHELLS: list[str] = ["bash", "zsh"]


@click.command(
    name="shell-path",
    short_help="Prints the current location of the script file to be sourced.",
    help="Prints to stdout the path of the packaged shell initialization script"
    " (config_setup.sh or config_setup.ps1) to be sourced from the shell profile.",
    epilog=f"""
    usage: mgsnake shell-path <shell>\n
    Args:\n
        shell: str - The shell to be initialized\n
            allowed values:\n
                {" | ".join(SHELL_OPT)}
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
    name="get-local-config-path",
    short_help="Prints the current location of the local configuration file.",
    help="Prints to stdout the path of the local configuration file"
    " (.sh or .ps1 depending on the active shell).",
    epilog="""
    usage: mgsnake get-local-config-path\n
    Prints only the path, so its stdout can be consumed via command substitution
    (as config_setup does).
    """,
)
def get_local_config_path() -> None:
    """
    Prints the current location of the local configuration file (.sh or .ps1 depending on
    the active shell). Only the path is written to stdout so the output stays parseable.

    Returns:
        None
    """
    click.echo(get_local_file())
