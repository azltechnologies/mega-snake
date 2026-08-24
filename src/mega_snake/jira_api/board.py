"""Resolve a Jira project key to its Agile board, replacing `getJiraBoard.sh`.

The shell version had no error handling at all: when the project did not exist, ``jq -r '.id'``
returned the string ``null``, the next call asked for ``?projectKeyOrId=null``, and the script
happily printed ``{"boardId": "null"}``. It also picked ``.values[0]`` without a word when a project
had several boards. Both are addressed here, and the resolved board id is cached in the repository
scope so the two HTTP calls happen once per clone instead of once per invocation.
"""

import json
from typing import Optional

import click

from mega_snake.constants import JIRA_BOARD_ID_KEY, JIRA_DOMAIN_KEY, JIRA_PROJECT_KEY_KEY
from mega_snake.jira_api.client import JiraClient
from mega_snake.jira_api.models import Board
from mega_snake.util.formatting import ws_warning
from mega_snake.util.store import SCOPE_REPO, Store
from mega_snake.util.util import cli_metadata

PROJECT_PATH_TEMPLATE: str = "/rest/api/2/project/{project_key}"
BOARD_PATH: str = "/rest/agile/1.0/board"

UNKNOWN_PROJECT_MESSAGE: str = (
    "Jira returned no id for project '{project_key}'. Check the project key and that your account can see it."
)
NO_BOARD_MESSAGE: str = (
    "Project '{project_key}' has no Agile board. Create one in Jira, or point '{key}' at a project that has one."
)
INVALID_CACHE_MESSAGE: str = "Ignoring the cached board id '{value}': it is not a number. Resolving it again from Jira."


def _cached_board_id(store: Store, project_key: str) -> Optional[int]:
    """Read the cached board id, but only when it belongs to the project being resolved.

    The cache is repository-scoped and so is ``jira.project_key``, so an explicit project key that
    differs from the stored one must not be answered from it -- that would return this clone's board
    for somebody else's project.

    Parameters:
        store: The persistent store.
        project_key: The project key being resolved.

    Raises:
        None

    Returns:
        Optional[int]: The cached board id, or None when there is no usable cache entry.
    """
    if store.get(JIRA_PROJECT_KEY_KEY) != project_key:
        return None
    raw: Optional[str] = store.get(JIRA_BOARD_ID_KEY)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        # `ws_warning` writes to stderr, so it is safe even here, inside a `no_init` command whose
        # stdout is captured with $(...).
        ws_warning(INVALID_CACHE_MESSAGE.format(value=raw))
        return None


def _cache_board_id(store: Store, project_key: str, board_id: int) -> None:
    """Cache the resolved board id when doing so is both possible and correct.

    Parameters:
        store: The persistent store.
        project_key: The project key that was resolved.
        board_id: The resolved board id.

    Raises:
        None

    Returns:
        None
    """
    if not store.has_scope(SCOPE_REPO) or store.get(JIRA_PROJECT_KEY_KEY) != project_key:
        return
    store.set(JIRA_BOARD_ID_KEY, str(board_id), SCOPE_REPO)


def _select_board(boards: list[dict], project_key: str) -> int:
    """Pick a board, asking the user when the project has more than one.

    The prompt is written to stderr rather than through ``get_validated_input``: this runs inside a
    ``no_init`` command whose stdout is captured with ``$(...)``, and that helper prompts through
    ``input()``, which writes to stdout.

    Parameters:
        boards: The ``values`` array returned by the board endpoint.
        project_key: The project key being resolved, used in the messages.

    Raises:
        click.ClickException: If the project has no board at all.

    Returns:
        int: The id of the selected board.
    """
    if not boards:
        raise click.ClickException(NO_BOARD_MESSAGE.format(project_key=project_key, key=JIRA_PROJECT_KEY_KEY))
    if len(boards) == 1:
        return int(boards[0]["id"])
    options: list[str] = [str(index) for index in range(len(boards))]
    lines: list[str] = [f"Project '{project_key}' has several boards. Please select one:"]
    lines.extend(f"\t{index}: {board.get('id')} - {board.get('name', '')}" for index, board in enumerate(boards))
    click.echo("\n".join(lines), err=True)
    selected: str = click.prompt("Board", type=click.Choice(options), show_choices=False, err=True)
    return int(boards[int(selected)]["id"])


def _fetch_board_id(client: JiraClient, project_key: str) -> int:
    """Resolve a project key to a board id through the Jira API.

    Parameters:
        client: The Jira client to use.
        project_key: The project key to resolve.

    Raises:
        click.ClickException: If the project is unknown or has no board.

    Returns:
        int: The resolved board id.
    """
    project: dict = client.get(PROJECT_PATH_TEMPLATE.format(project_key=project_key))
    project_id: Optional[str] = project.get("id")
    if not project_id:
        raise click.ClickException(UNKNOWN_PROJECT_MESSAGE.format(project_key=project_key))
    payload: dict = client.get(BOARD_PATH, {"projectKeyOrId": str(project_id)})
    return _select_board(payload.get("values") or [], project_key)


def resolve_board(
    project_key: Optional[str] = None, refresh: bool = False, client: Optional[JiraClient] = None
) -> Board:
    """Resolve a project key to its board, caching the result in the repository scope.

    With a warm cache no HTTP call is made at all, which also means no credentials are needed: the
    output is built from the stored domain and board id alone.

    Parameters:
        project_key: The project key. Falls back to the stored ``jira.project_key``.
        refresh: When True, ignore the cache and resolve the board again.
        client: An existing client to reuse. One is created on demand when omitted.

    Raises:
        click.ClickException: If the project key or the domain is not configured, or the project has
            no board.

    Returns:
        Board: The resolved board.
    """
    store: Store = Store.get_instance()
    resolved_key: str = project_key or store.require(JIRA_PROJECT_KEY_KEY)
    domain: str = store.require(JIRA_DOMAIN_KEY)
    if not refresh:
        cached: Optional[int] = _cached_board_id(store, resolved_key)
        if cached is not None:
            return Board(id=cached, cloud_domain=domain)
    board_id: int = _fetch_board_id(client or JiraClient(), resolved_key)
    _cache_board_id(store, resolved_key, board_id)
    return Board(id=board_id, cloud_domain=domain)


@click.command(
    name="jira-board",
    short_help="Prints the Agile board of a Jira project as JSON.",
    help="""Resolves a Jira project key to its Agile board and prints `{"boardId": ..., "cloudDomain":
    ...}` to stdout, and nothing else, so the output can be captured with command substitution. The
    board id is cached in the current clone once resolved, so later runs answer without any HTTP
    call. `boardId` is an integer, not a string as the shell version emitted it.""",
    epilog="""
    Args:\n
        project_key: str - Jira project key. Defaults to the stored jira.project_key.
    """,
)
@cli_metadata(flags={"no_init"})
@click.argument("project_key", required=False)
@click.option(
    "--refresh",
    is_flag=True,
    default=False,
    help="Ignore the cached board id and resolve it from Jira again. Use it after the project's "
    "boards changed, or to pick a different board when the project has several.",
)
def jira_board(project_key: Optional[str], refresh: bool) -> None:
    """Print the Agile board of a Jira project as JSON.

    Parameters:
        project_key: The Jira project key, or None to use the stored one.
        refresh: Whether to bypass the cached board id.

    Raises:
        click.ClickException: If the settings are missing, or the board cannot be resolved.

    Returns:
        None
    """
    click.echo(json.dumps(resolve_board(project_key, refresh).to_dict()))
