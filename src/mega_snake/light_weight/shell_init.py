"""
Light-weight commands for shell initialization.

Provides commands to print the packaged shell init script path and the resolved local config file path.
"""

from importlib.resources import files
import click
from mega_snake.constants import SHELL_OPT, MODULE_NAME
from mega_snake.config_environment.util import get_local_file

CONFIG_SCRIPT = "config_setup"
WIN_SHELLS: list[str] = ["powershell", "pwsh"]
SH_SHELLS: list[str] = ["bash", "zsh"]


@click.command(
    name="shell-path",
    short_help="Prints the current location of the script file to be sourced.",
    help="Prints a message to stdout with the current location where this cli was installed "
    "followed by the script file to be sourced.",
    epilog=f"""
    usage: mgsnake shell-path <shell>\n
    OPTIONS:\n
        shell:\n
            usage: mgsnake shell-path <shell>\n
            allowed values:\n
                {" | ".join(SHELL_OPT)}
    """,
)
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
    help="Prints a message to stdout with the current location of the local configuration file.",
    epilog="""
    usage: mgsnake get-local-config-path\n
    OPTIONS:\n
            usage: mgsnake get-local-config-path
    """,
)
def get_local_config_path() -> None:
    """
    Prints the current location of the local configuration file.

    Returns:
        None
    """
    click.echo(get_local_file())
