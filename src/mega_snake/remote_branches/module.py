"""remote branches module for the cli"""

import click
from mega_snake.remote_branches.cleanup_remote_branches import remote_branches_cleanup
from mega_snake.remote_branches.details_remote_branches import remote_branches_details
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.props import complete_app_properties
from mega_snake.util.util import cli_metadata, ensure_working_path, require_remote, wrapper_decorator


@click.group(cls=CliGroup)
def main() -> None:
    """remote branches related commands"""


@cli_metadata(flags={"skip"}, docs_group="Git & Release Management")
def wrapper(_ctx, *_args, **_kwargs) -> None:
    """Pre-flight check for the remote_branches commands.

    These commands only need a git repository with a configured remote and a scratch folder
    (``working_path``, e.g. ``workspace_temp``) to write their output to; they don't require a
    full VS Code workspace. The "skip" flag defers the usual working-path validation done during
    CLI initialization, so this check runs instead and can offer to create the folder rather than
    letting the command crash with a raw FileNotFoundError.

    The remote is resolved through ``require_remote``, which caches it, so the commands invoked
    right after this check reuse the same answer instead of resolving (and prompting for) it again.

    Once the working path is secured, ``complete_app_properties`` finishes the initialization that
    light-weight mode deferred, so the rest of the command logs to file and honours --log-level.

    Parameters:
        _ctx: The click context (unused).

    Raises:
        EnvironmentError: If no remote repository is found.
        UserDeclinedError: If the working path folder is missing and the user declines to create it.
        RuntimeError: If the AppProperties instance has not been initialized yet.

    Returns:
        None
    """
    require_remote()
    ensure_working_path()
    complete_app_properties()


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


main.add_command_with_alias(remote_branches_cleanup, ["rbc"])
main.add_command_with_alias(remote_branches_details, ["rbd"])
