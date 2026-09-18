"""comment-killer module for the cli"""

import json
from typing import Any

import click

from mega_snake.comment_killer.commands import comment_killer, guard
from mega_snake.comment_killer.constants import HOOK_BLOCK_CODE, STATUS_ERROR
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.command_registration import ModuleRegistration, wrapper_context_decorator
from mega_snake.util.formatting import VALIDATION_ERROR_CODE, InternalStateError
from mega_snake.util.util import cli_metadata


@click.group(cls=CliGroup)
def main() -> None:
    """comment-killer related commands"""


@cli_metadata(docs_group="Comment Killer")
def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    """Pre-flight check for the comment-killer commands.

    Deliberately empty, and deliberately without initialization flags. This module mixes levels:
    the `comment-killer` group is light-weight, because `start` secures the working path itself
    through `ensure_working_path`, while `comment-killer-guard` is `no_init`, because it answers the
    agents' hooks and must work in an environment where nothing of mgsnake's has been set up.

    Unlike `jira-issues`, nothing here calls `complete_app_properties()` afterwards, so the
    initialization light-weight mode deferred is never completed: the console output is unaffected
    (§4.1), but `--log-level` has no effect and nothing reaches the log file. The crew talks to
    agents through stdout and to hooks through exit statuses, neither of which reads the log.

    A module wrapper runs for every command in the module, so each
    command declares its own flags through `@cli_metadata`; the command registration merges the module's
    metadata first and the command callback's second, so those per-command flags win.

    Parameters:
        _ctx: The click context (unused).

    Raises:
        None

    Returns:
        None
    """


def ending(ctx: click.Context, result: Any) -> None:
    """Turn a command's result into the exit status its caller reads.

    Both of the module's commands are context commands, and their results never share a type, which
    the registration enforces through their return annotations:

    - the guard returns ``bool``: True means the call is refused, which a hook signals with
      ``HOOK_BLOCK_CODE`` -- any other non-zero status is a hook error the runtime proceeds past;
    - the ``comment-killer`` subcommands return the action they printed, as JSON text: an ``error``
      action leaves with the validation status, like the refusal it reports.

    Parameters:
        ctx: The click context of the command being invoked.
        result: The command's result.

    Raises:
        InternalStateError: If the result is of a type neither command returns.

    Returns:
        None
    """
    if isinstance(result, bool):
        if result:
            ctx.obj["exit_code"] = HOOK_BLOCK_CODE
    elif isinstance(result, str):
        if json.loads(result).get("status") == STATUS_ERROR:
            ctx.obj["exit_code"] = VALIDATION_ERROR_CODE
    else:
        raise InternalStateError(
            f"The comment-killer ending received {type(result).__name__}; it only reads a guard's bool "
            "or an action's JSON text."
        )


main.add_command_with_alias(comment_killer, ["ck"])
main.add_command(guard)

# The module's single export: its group, wrapped command by command by the CLI entry point.
# Every command here is a context command, so there is no plain decorator to export.
registration = ModuleRegistration(main, add_context_wrapper=wrapper_context_decorator(wrapper, ending))
