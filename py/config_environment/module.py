""" Contains multiple functions to configure the environment for development with vscode. """

import click
from py.config_environment.graphql_schema import create_graphql_schema
from py.config_environment.java_set import set_java_version
from py.config_environment.gradle_set import set_gradle_version
from py.config_environment.local_config import initial_load
from py.util.util import wrapper_decorator


@click.group()
def main() -> None:
    """Configuration related commands"""


def wrapper(ctx: click.Context, *_args, **_kwargs) -> None:
    """Wrapper for the config_environment command."""
    ctx.obj["exit_code"] = 21


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)

main.add_command(create_graphql_schema)
main.add_command(set_java_version)
main.add_command(set_gradle_version)
main.add_command(initial_load)
