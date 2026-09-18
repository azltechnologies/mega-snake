"""The `comment-killer` command group, which drives a mission, and the hidden guard its agents' hooks call."""

import json
import sys
from typing import Any, Callable, Optional

import click

from mega_snake.comment_killer import mission as crew
from mega_snake.comment_killer.constants import GUARD_COMMAND, GUARD_OPT, STATUS_ERROR
from mega_snake.comment_killer.guards import evaluate
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.formatting import ValidationError, ws_error
from mega_snake.util.util import cli_metadata


def _emit(action: dict[str, Any]) -> str:
    """Print one action for the agent that asked for it, and return it as the command's result.

    The whole flow is driven by this document, so it is the command's payload and goes to stdout
    alone. It is also what the command returns: the group is a context command, and the module
    ending reads the action's `status` to decide the exit status (§2.3).

    Parameters:
        action: The action to print.

    Raises:
        None

    Returns:
        str: The action, serialized exactly as it was printed.
    """
    document = json.dumps(action, indent=2, ensure_ascii=False)
    click.echo(document)
    return document


def _emit_or_report(produce: Callable[[], dict[str, Any]]) -> str:
    """Print the action a state-machine call produces, or the error it raised, as an action.

    A refusal of the state machine -- a malformed or unknown mission id, an unreadable state, an
    ambiguous verdict -- is something the orchestrator has to relay, not a crash: it arrives as an
    `error` action carrying the whole message on stdout, and the module ending turns it into the
    validation status. Nothing reaches stderr, because nothing is raised.

    Parameters:
        produce: The state-machine call.

    Raises:
        None

    Returns:
        str: The action printed.
    """
    try:
        action = produce()
    except ValidationError as error:
        action = {"status": STATUS_ERROR, "message": error.message}
    return _emit(action)


@click.group(cls=CliGroup)
@cli_metadata(flags={"skip"}, context_command=True)
def comment_killer() -> None:
    """Drives the comment-killer crew: one mission per code review comment."""


@comment_killer.command(
    name="start",
    short_help="Opens a mission for one code review comment.",
    help=(
        "Opens a comment-killer mission and prints the first action for the crew's orchestrator. "
        "Given the code review comment, it files it as the brief and prints the spotter's launch; "
        "without it, the first action is to write the brief."
    ),
)
@click.argument("comment", required=False)
def start(comment: Optional[str]) -> str:
    """Open a mission.

    Parameters:
        comment: The code review comment, when the caller has it at hand.

    Raises:
        UserDeclinedError: If the working path is missing and the user declines to create it.

    Returns:
        str: The action printed.
    """
    return _emit(crew.start(comment))


@comment_killer.command(
    name="next",
    short_help="Validates the finished stage and prints the next action.",
    help=(
        "Validates the file the current stage was supposed to produce and prints the next action: "
        "a file to write, an agent to launch, or the mission's outcome."
    ),
)
@click.option(
    "-m",
    "--mission",
    default=None,
    help=(
        "The id of the mission to act on, exactly as the action's `mission` field names it: the "
        "mission folder's own name, never a path. Every action carries it, so passing it back is "
        "what lets two crews work two code review comments at the same time. Without it, the "
        "newest mission in the working path is used."
    ),
)
def next_action(mission: Optional[str]) -> str:
    """Advance the mission.

    Parameters:
        mission: The mission id, when the caller names one.

    Raises:
        None

    Returns:
        str: The action printed: the next one, or an `error` action when the state machine refused.
    """
    return _emit_or_report(lambda: crew.advance(mission))


@comment_killer.command(
    name="status",
    short_help="Prints the pending action again, without advancing.",
    help="Prints the action the mission is waiting on, so an interrupted run can pick up where it stopped.",
)
@click.option(
    "-m",
    "--mission",
    default=None,
    help="The id of the mission to report on. Without it, the newest mission in the working path is used.",
)
def status(mission: Optional[str]) -> str:
    """Print the pending action.

    Parameters:
        mission: The mission id, when the caller names one.

    Raises:
        None

    Returns:
        str: The action printed: the pending one, or an `error` action when the state machine refused.
    """
    return _emit_or_report(lambda: crew.status(mission))


@click.command(
    name=GUARD_COMMAND,
    hidden=True,
    short_help="Answers a PreToolUse hook for one of the crew's agents.",
    help=(
        "Reads a PreToolUse hook payload on stdin and decides whether the tool call goes through. "
        "It is what the crew's agents declare in their own hooks, so the rules travel with the "
        "installed crew instead of living as scripts in your repository."
    ),
    epilog="""
Args:\n
    guard: str - the rule to apply: 'kingpin' (its own commands only), 'trapper' (test files only)
        or 'git-state' (never rewrite the index, the stash, the branch or the history).
""",
)
@cli_metadata(flags={"no_init"}, context_command=True)
@click.argument("guard", type=click.Choice(GUARD_OPT))
def guard(guard: str) -> bool:
    """Answer one hook call.

    The verdict is returned rather than turned into a status here: commands never touch the click
    context, so the module ending is what makes a refusal the hook's blocking exit code (§2.3).

    Parameters:
        guard: The rule to apply.

    Raises:
        ValidationError: If the payload on stdin is not valid JSON.

    Returns:
        bool: True when the call is refused, with the reason already written to stderr for the agent.
    """
    try:
        payload: dict[str, Any] = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as error:
        raise ValidationError(f"The hook payload is not valid JSON: {error}") from error
    refusal = evaluate(guard, payload)
    if refusal:
        # What a hook writes to stderr is what the agent is told.
        ws_error(refusal)
    return bool(refusal)


__all__ = ["comment_killer", "guard"]
