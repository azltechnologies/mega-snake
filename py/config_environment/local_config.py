""" This module contains the functions for setting the workspace for the project. """

import os
import click
from py.util.props import AppProperties
from py.util.formatting import ws_success
from py.config_environment.util import get_local_file


@click.command(
    name="initLocalConfig",
    short_help="Creates a local configuration file",
    help="Creates a local configuration file",
    epilog="""usage: set_env createLocalConfig [OPTIONS]\n
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
    props_inst: AppProperties = AppProperties.get_instance()
    local_file = get_local_file()
    if not os.path.exists(local_file) or override:
        shell = props_inst.retrieve_property("shell")
        contents: str = "# This file is used to store local configurations for the project.\n"
        contents += "# You can add custom functions and configurations here.\n"
        match shell:
            case "bash" | "zsh":
                contents += "example() {\n    set_env msg 'Hello, World!'\n}\nexport ORG_GRADLE_PROJECT_example_password='some value'\n"
            case "powershell":
                contents = "function example {\n    set_env msg 'Hello, World!'\n}\n$env:ORG_GRADLE_PROJECT_example_password = 'some value'\n"
            case _:
                return
        with open(local_file, "w", encoding="utf-8") as file:
            file.write(contents)
        ws_success(f"Local configuration file created: {local_file}")
