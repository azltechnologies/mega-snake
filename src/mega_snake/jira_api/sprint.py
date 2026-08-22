"""Report the active sprints of a board, replacing `getSprintInfo.sh`.

The shell version piped ``.values[]`` through ``jq`` without wrapping it in an array, so a board with
two active sprints emitted two concatenated JSON objects -- which is not a JSON document, and blows
up in ``json.load``. The output here is always an array, even for a single sprint, and a board with
no active sprint (a kanban board, or a sprint that was never started) is an empty array and a
successful exit, not an error.
"""

import json
from typing import Optional

import click

from mega_snake.jira_api.board import resolve_board
from mega_snake.jira_api.client import JiraClient
from mega_snake.jira_api.models import Board, Sprint
from mega_snake.util.util import cli_metadata

SPRINT_PATH_TEMPLATE: str = "/rest/agile/1.0/board/{board_id}/sprint"
ACTIVE_STATE: str = "active"


def get_active_sprints(board_id: int, cloud_domain: str, client: Optional[JiraClient] = None) -> list[Sprint]:
    """Return every active sprint of the given board.

    Parameters:
        board_id: The Agile board to query.
        cloud_domain: The Jira Cloud domain, echoed back in the output contract.
        client: An existing client to reuse. One is created on demand when omitted.

    Raises:
        click.ClickException: If the request fails.

    Returns:
        list[Sprint]: The active sprints, empty when the board has none.
    """
    api: JiraClient = client or JiraClient()
    payload: dict = api.get(SPRINT_PATH_TEMPLATE.format(board_id=board_id), {"state": ACTIVE_STATE})
    return [Sprint.from_payload(entry, cloud_domain, board_id) for entry in payload.get("values") or []]


@click.command(
    name="jira-sprint",
    short_help="Prints the active sprints of a project's board as a JSON array.",
    help="""Prints the active sprints of a Jira project's Agile board to stdout as a JSON array, and
    nothing else, so the output can be captured with command substitution. The array is always an
    array: one active sprint yields a one-element list, and a board with none (kanban, or a sprint
    that was never started) yields an empty list and a successful exit.""",
    epilog="""
    Args:\n
        project_key: str - Jira project key. Defaults to the stored jira.project_key.
    """,
)
@cli_metadata(flags={"no_init"})
@click.argument("project_key", required=False)
def jira_sprint(project_key: Optional[str]) -> None:
    """Print the active sprints of a project's board as a JSON array.

    Parameters:
        project_key: The Jira project key, or None to use the stored one.

    Raises:
        click.ClickException: If the settings are missing, or the board cannot be resolved.

    Returns:
        None
    """
    client: JiraClient = JiraClient()
    board: Board = resolve_board(project_key, client=client)
    sprints: list[Sprint] = get_active_sprints(board.id, board.cloud_domain, client)
    click.echo(json.dumps([sprint.to_dict() for sprint in sprints]))
