"""remote branches module for the cli"""

import click
from py.remote_branches.cleanup_remote_branches import remote_branches_cleanup
from py.remote_branches.details_remote_branches import remote_branches_details


@click.group()
def main() -> None:
    """gcloud related commands"""


def add_wrapper(command: click.Command) -> click.Command:
    """Adds a wrapper to the command."""

    @click.pass_context
    def wrapper(ctx, *args, **kwargs) -> None:
        # Execute the original command
        result = ctx.invoke(command, *args, **kwargs)
        return result

    return click.Command(
        name=command.name,
        callback=wrapper,
        params=command.params,
        help=command.help,
    )


main.add_command(remote_branches_cleanup)
main.add_command(remote_branches_details)
