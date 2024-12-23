"""remote branches module for the cli"""

import click
from py.remote_branches.cleanup_remote_branches import remote_branches_cleanup
from py.remote_branches.details_remote_branches import remote_branches_details
from py.util.util import wrapper_decorator


@click.group()
def main() -> None:
    """remote branches related commands"""


def wrapper(_ctx, *_args, **_kwargs) -> None:
    """Wrapper for the light_weight command."""

# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


main.add_command(remote_branches_cleanup)
main.add_command(remote_branches_details)
