"""remote branches module for the cli"""

import click
from mega_snake.remote_branches.cleanup_remote_branches import remote_branches_cleanup
from mega_snake.remote_branches.details_remote_branches import remote_branches_details
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.util import wrapper_decorator


@click.group(cls=CliGroup)
def main() -> None:
    """remote branches related commands"""


def wrapper(_ctx, *_args, **_kwargs) -> None:
    """Wrapper for the light_weight command."""


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


main.add_command_with_alias(remote_branches_cleanup, ["rbc", "remoteBranchesCleanUp"])
main.add_command_with_alias(remote_branches_details, ["rbd", "remoteBranchesDetails"])
