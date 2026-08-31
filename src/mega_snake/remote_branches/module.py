"""remote branches module for the cli"""

import click
from mega_snake.remote_branches.cleanup_remote_branches import remote_branches_cleanup
from mega_snake.remote_branches.details_remote_branches import remote_branches_details
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.props import complete_app_properties
from mega_snake.util.util import cli_metadata, ensure_working_path, wrapper_decorator


@click.group(cls=CliGroup)
def main() -> None:
    """remote branches related commands"""


@cli_metadata(flags={"skip"}, docs_group="Git & Release Management")
def wrapper(_ctx, *_args, **_kwargs) -> None:
    """Pre-flight check for the remote_branches commands.

    These commands only need a git repository and a scratch folder (``working_path``, e.g.
    ``workspace_temp``) to write their output and logs to; they don't require a full VS Code
    workspace. A remote is **not** required up front: the ``Repo`` snapshot resolves one when it
    exists and otherwise asks the user for the main branch, so a repository without remotes still
    gets its local branches reported and cleaned. Requiring one here would refuse a workflow that
    works perfectly well; the remote is demanded only where a remote reference is about to be
    touched (§4.4). The "skip" flag defers the usual
    working-path validation done during CLI initialization, so this check runs instead and can
    offer to create the folder rather than letting the command crash with a raw FileNotFoundError.

    Once the working path is secured, ``complete_app_properties`` finishes the initialization that
    light-weight mode deferred, so the rest of the command logs to file and honours --log-level.

    Parameters:
        _ctx: The click context (unused).

    Raises:
        UserDeclinedError: If the working path folder is missing and the user declines to create it.
        InternalStateError: If the AppProperties instance has not been initialized yet.

    Returns:
        None
    """
    ensure_working_path()
    complete_app_properties()


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


main.add_command_with_alias(remote_branches_cleanup, ["rbc"])
main.add_command_with_alias(remote_branches_details, ["rbd"])
