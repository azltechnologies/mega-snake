"""remote branches module for the cli"""

import os
import click
from mega_snake.remote_branches.cleanup_remote_branches import remote_branches_cleanup
from mega_snake.remote_branches.details_remote_branches import remote_branches_details
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.formatting import ws_success
from mega_snake.util.props import get_property
from mega_snake.util.util import cli_metadata, get_remote, get_validated_input, wrapper_decorator


@click.group(cls=CliGroup)
def main() -> None:
    """remote branches related commands"""


@cli_metadata(flags={"skip"})
def wrapper(_ctx, *_args, **_kwargs) -> None:
    """Pre-flight check for the remote_branches commands.

    These commands only need a git repository with a configured remote and a scratch folder
    (``working_path``, e.g. ``workspace_temp``) to write their output to; they don't require a
    full VS Code workspace. The "skip" flag defers the usual working-path validation done during
    CLI initialization, so this check runs instead and can offer to create the folder rather than
    letting the command crash with a raw FileNotFoundError.

    Parameters:
        _ctx: The click context (unused).

    Raises:
        LookupError: If no remote repository is found for the current git repository.
        click.ClickException: If the working path folder is missing and the user declines to
            create it.

    Returns:
        None
    """
    if not get_remote():
        raise LookupError("No remote repository found. Please add a remote repository to the current repository.")
    working_path: str = get_property("working_path")
    if os.path.exists(working_path):
        return
    prompt: str = f"The working path folder '{working_path}' does not exist. Would you like to create it?"
    if get_validated_input(prompt, ["y", "n"]) != "y":
        raise click.ClickException(
            f"Cannot run this command without the '{working_path}' folder. Please create it and try again."
        )
    os.makedirs(working_path)
    ws_success(f"Created working path folder at '{working_path}'")


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


main.add_command_with_alias(remote_branches_cleanup, ["rbc"])
main.add_command_with_alias(remote_branches_details, ["rbd"])
