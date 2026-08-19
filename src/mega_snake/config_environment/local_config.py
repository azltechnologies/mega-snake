"""This module contains the functions for setting the workspace for the project."""

import os
import click
from mega_snake.constants import APP_NAME, LOAD_ENV_HELPER, RELOAD_CONFIG_COMMAND
from mega_snake.util.props import get_property
from mega_snake.util.formatting import ws_success
from mega_snake.util.util import cli_metadata
from mega_snake.config_environment.util import get_local_file


@click.command(
    name="init-local-config",
    short_help="Creates a local configuration file",
    help="Creates or updates the local configuration file used for developer-specific shell settings.",
    epilog="""usage: mgsnake init-local-config [OPTIONS]\n
    OPTIONS:\n
        -o | --override: Optional[bool] - Override the current local configuration file with a new one\n
    """,
)
@cli_metadata(reloads_environment=True)
@click.option("--override", "-o", is_flag=True, help="Override the current local configuration file with a new one")
def initial_load(override: bool) -> None:
    """
    Calls the execute function to initialize the configuration system.
    """
    execute(override)


def execute(override: bool) -> None:
    """
    Initializes the configuration system by creating the local environment file and the
    shell-specific local config file when they don't exist (or when override is set).

    Args:
        override (bool): A boolean value to overwrite the current local configuration files.
    """
    env_file = get_property("local_env_file")
    contents: str
    if not os.path.exists(env_file) or override:
        with open(env_file, "w", encoding="utf-8") as file:
            contents = "# This file is used to store local environment variables for the project.\n"
            contents += "# You can add custom environment variables here.\n"
            file.write(contents)
        ws_success(f"Local environment file created: {env_file}")
    local_file = get_local_file()
    if not os.path.exists(local_file) or override:
        shell = get_property("shell")
        env_name = os.path.basename(env_file)
        # The shell init script no longer announces its helpers on every new terminal, so this
        # header is where a user finds out how to reload the file they are looking at.
        contents = "# This file is used to store local configurations for the project.\n"
        contents += f"# Reload it in your current terminal with: {APP_NAME} {RELOAD_CONFIG_COMMAND}\n"
        contents += f"# See every available command with: {APP_NAME} --help\n"
        # Calls the private helper rather than `mgsnake load-env`: this file is sourced *by* the
        # shell, so the exports already land in the right session.
        match shell:
            case "bash":
                contents += f'{LOAD_ENV_HELPER} "$(cd "$(dirname "${{BASH_SOURCE[0]:-$0}}")" && pwd)"/{env_name}\n'
            case "zsh":
                contents += f'{LOAD_ENV_HELPER} "$(cd "$(dirname "${{(%):-%N}}")" && pwd)"/{env_name}\n'
            case "powershell" | "pwsh":
                contents += f'{LOAD_ENV_HELPER} "$(Split-Path -Parent $MyInvocation.MyCommand.Definition)/{env_name}"\n'
            case _:
                raise NotImplementedError(f"Shell type not supported: {shell}")
        contents += "\n# ----\n# You can add custom functions and configurations here.\n"
        contents += "# The codeblock below loads the local environment variables\n"
        match shell:
            case "bash" | "zsh":
                contents += (
                    "example() {\n    mgsnake msg 'Hello, World!'\n}\nexport "
                    "ORG_GRADLE_PROJECT_example_password='some value'\n"
                )
            case "powershell" | "pwsh":
                contents += (
                    "function example {\n    mgsnake msg 'Hello, World!'\n}\n"
                    "$env:ORG_GRADLE_PROJECT_example_password = 'some value'\n"
                )
        with open(local_file, "w", encoding="utf-8") as file:
            file.write(contents)
        ws_success(f"Local configuration file created: {local_file}")
