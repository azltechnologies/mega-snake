"""Contains multiple functions to configure the environment for development with vscode."""

import click
from mega_snake.config_environment.graphql_schema import create_graphql_schema
from mega_snake.config_environment.java_set import set_java_version
from mega_snake.config_environment.gradle_set import set_gradle_version
from mega_snake.config_environment.local_config import initial_load
from mega_snake.config_environment.create_working_env import create_working_env
from mega_snake.util.util import wrapper_decorator
from mega_snake.util.cli_group import CliGroup


@click.group(cls=CliGroup)
def main() -> None:
    """Configuration related commands"""


def wrapper(ctx: click.Context, *_args, **_kwargs) -> None:
    """Wrapper for the config_environment command."""
    ctx.obj["exit_code"] = 21


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)

main.add_command_with_alias(create_graphql_schema, ["graphql", "gql"])
main.add_command_with_alias(set_java_version, ["java"])
main.add_command_with_alias(set_gradle_version, ["gradle"])
main.add_command_with_alias(initial_load, ["iload"])
main.add_command_with_alias(create_working_env, ["cwe", "env"])
