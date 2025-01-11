""" Contains multiple functions to configure the environment for development with vscode. """

import click
from py.config_environment.graphql_schema import create_graphql_schema
from py.config_environment.java_set import set_java_version
from py.config_environment.gradle_set import set_gradle_version
from py.config_environment.local_config import initial_load
from py.config_environment.create_working_env import create_working_env
from py.util.util import wrapper_decorator
from py.util.cli_group import CliGroup


@click.group(cls=CliGroup)
def main() -> None:
    """Configuration related commands"""


def wrapper(ctx: click.Context, *_args, **_kwargs) -> None:
    """Wrapper for the config_environment command."""
    ctx.obj["exit_code"] = 21


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)

main.add_command_with_alias(create_graphql_schema,["graphql","gql"])
main.add_command_with_alias(set_java_version,["java"])
main.add_command_with_alias(set_gradle_version,["gradle"])
main.add_command_with_alias(initial_load,["iload"])
main.add_command_with_alias(create_working_env,["cwe", "env"])
