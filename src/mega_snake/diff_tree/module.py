"""diff tree module for the cli"""

import click
from mega_snake.diff_tree.diff_tree import diff_tree
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.props import complete_app_properties
from mega_snake.util.util import cli_metadata, ensure_working_path, wrapper_decorator


@click.group(cls=CliGroup)
def main() -> None:
    """diff tree related commands"""


@cli_metadata(flags={"skip"})
def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    """Pre-flight check for the diff_tree commands.

    diff-tree only needs a git repository and a scratch folder (``working_path``, e.g.
    ``workspace_temp``) to write its output to; it doesn't require a full VS Code workspace, hence
    the "skip" flag. That flag defers the working-path validation done during CLI initialization,
    so this check runs instead: it offers to create the folder and, if the user declines, fails
    with a clean error rather than letting the command crash while writing its output files.

    Unlike the remote_branches commands, no remote is required here: when the repository has none,
    ``get_main_branch`` falls back to the current local branch.

    Once the working path is secured, ``complete_app_properties`` finishes the initialization that
    light-weight mode deferred, so the rest of the command logs to file and honours --log-level.

    Parameters:
        _ctx: The click context (unused).

    Raises:
        click.ClickException: If the working path folder is missing and the user declines to
            create it.

    Returns:
        None
    """
    ensure_working_path()
    complete_app_properties()


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


main.add_command_with_alias(diff_tree, ["dt", "tree"])
