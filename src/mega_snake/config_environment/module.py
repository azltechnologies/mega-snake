"""Contains multiple functions to configure the environment for development with vscode."""

import click
from mega_snake.config_environment.graphql_schema import create_graphql_schema
from mega_snake.config_environment.java_set import set_java_version
from mega_snake.config_environment.gradle_set import set_gradle_version
from mega_snake.config_environment.maven_set import maven_project_setup, set_maven_version
from mega_snake.config_environment.local_config import initial_load
from mega_snake.config_environment.create_working_env import create_working_env
from mega_snake.constants import RELOAD_ENVIRONMENT_EXIT_CODE
from mega_snake.util.util import wrapper_decorator
from mega_snake.util.cli_group import ATTR_METADATA, META_RELOADS_ENV, CliGroup


@click.group(cls=CliGroup)
def main() -> None:
    """Configuration related commands"""


def wrapper(ctx: click.Context, *_args, **_kwargs) -> None:
    """Ask the shell to reload its local environment files, for the commands that rewrite them.

    The signal used to be set for every command in this module, which was wrong in both directions:
    `graphql-schema` and `maven-project-setup` never touch the local environment files, and nothing
    guarantees a future command that does will live here. Each command therefore declares it, with
    ``@cli_metadata(reloads_environment=True)``, and this wrapper only relays what it finds.

    The metadata is read off ``ctx.command.callback`` because by this point the command has been
    rebuilt by ``wrapper_decorator``, which merges the original callback's metadata onto the
    wrapping callback.

    Parameters:
        ctx: The click context of the command being invoked.

    Raises:
        None

    Returns:
        None
    """
    metadata: dict = getattr(ctx.command.callback, ATTR_METADATA, {})
    if metadata.get(META_RELOADS_ENV):
        ctx.obj["exit_code"] = RELOAD_ENVIRONMENT_EXIT_CODE


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)

main.add_command_with_alias(set_java_version, ["java", "sj"])
main.add_command_with_alias(set_gradle_version, ["gradle", "sg"])
main.add_command_with_alias(set_maven_version, ["maven", "sm"])
main.add_command_with_alias(maven_project_setup, ["mps"])
main.add_command_with_alias(initial_load, ["iload", "ilc"])
main.add_command_with_alias(create_working_env, ["cwe", "env"])
main.add_command_with_alias(create_graphql_schema, ["graphql", "gql", "cgs"])
