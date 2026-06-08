"""This module contains the functions for setting the workspace for the project."""

import os
import click
from mega_snake.util.props import get_property
from mega_snake.util.formatting import ws_success
from mega_snake.config_environment.util import get_local_file


@click.command(
    name="init_local_config",
    short_help="Creates a local configuration file",
    help="Creates or updates the local configuration file used for developer-specific shell settings.",
    epilog="""usage: mgsnake init_local_config [OPTIONS]\n
    OPTIONS:\n
        -o | --override: Optional[bool] - Override the current local configuration file with a new one\n
    """,
)
@click.option("--override", "-o", is_flag=True, help="Override the current local configuration file with a new one")
def initial_load(override: bool) -> None:  # previously initialLoad
    """
    Calls the execute function to initialize the configuration system.
    """
    execute(override)


def execute(override: bool) -> None:  # previously initialLoad
    """
    Initializes the configuration system by creating a local config file if it doesn't exist,
    then loads its contents into the environment.

    Args:
        override (bool): A boolean value to override the current gradle version.
    """
    local_file = get_local_file()
    if not os.path.exists(local_file) or override:
        shell = get_property("shell")
        contents: str = "# This file is used to store local configurations for the project.\n"
        contents += "# You can add custom functions and configurations here.\n"
        match shell:
            case "bash" | "zsh":
                contents += (
                    "example() {\n    mgsnake msg 'Hello, World!'\n}\nexport "
                    "ORG_GRADLE_PROJECT_example_password='some value'\n"
                )
            case "powershell" | "pwsh":
                contents = (
                    "function example {\n    mgsnake msg 'Hello, World!'\n}\n"
                    "$env:ORG_GRADLE_PROJECT_example_password = 'some value'\n"
                )
            case _:
                return
        with open(local_file, "w", encoding="utf-8") as file:
            file.write(contents)
        ws_success(f"Local configuration file created: {local_file}")
