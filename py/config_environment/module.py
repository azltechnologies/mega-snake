""" Contains multiple functions to configure the environment for development with vscode. """

import click
from py.config_environment.graphql_schema import create_graphql_schema
from py.config_environment.java_set import set_java_version
from py.config_environment.gradle_set import set_gradle_version
from py.config_environment.echo import echo
from py.config_environment.set_workspace import initial_load


@click.group()
def main() -> None:
    """Configuration related commands"""


def add_wrapper(command: click.Command) -> click.Command:
    """Adds a wrapper to the command."""

    @click.pass_context
    def wrapper(ctx, *args, **kwargs) -> None:
        ctx.obj["exit_code"] = 1
        # Execute the original command
        result = ctx.invoke(command, *args, **kwargs)
        return result

    return click.Command(
        name=command.name,
        callback=wrapper,
        params=command.params,
        help=command.help,
    )


main.add_command(echo)
main.add_command(create_graphql_schema)
main.add_command(set_java_version)
main.add_command(set_gradle_version)
main.add_command(initial_load)
