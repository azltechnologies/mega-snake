"""Download every issue of a board and flag the ones in the active sprint.

This is the native replacement for `jira_board_issues.sh`, and the whole pipeline now lives in one
process and in memory:

1. resolve the board (cached in the repository scope);
2. read the board configuration to get the filter that defines it;
3. page through the JQL search for that filter;
4. project every issue into the compact schema;
5. list the active sprints and page through their issues to collect the keys;
6. flag each issue with ``activeSprint`` and write the file atomically.

Defects of the shell version that disappear along the way: it created a temporary file twice and
leaked the first one on every single run; it dumped the sprint key list to stdout in the middle of a
run whose output was deliberately on stderr; it called ``getJiraBoard``, a shell *function* defined
in a different script, which fails with "command not found" whenever this one is executed rather than
sourced; and it rewrote its whole accumulator file once per page.
"""

import os
from pathlib import Path
from typing import Callable, Iterator, Optional

import click

from mega_snake.jira_api.board import resolve_board
from mega_snake.jira_api.client import JiraClient
from mega_snake.jira_api.models import Board, Sprint
from mega_snake.jira_api.projection import ACTIVE_SPRINT_KEY, FieldIds, project_issue
from mega_snake.jira_api.sprint import get_active_sprints
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.util.props import complete_app_properties, get_property
from mega_snake.util.util import cli_metadata, ensure_working_path, write_json_atomically

BOARD_CONFIGURATION_TEMPLATE: str = "/rest/agile/1.0/board/{board_id}/configuration"
SEARCH_PATH: str = "/rest/api/2/search/jql"
SPRINT_ISSUES_TEMPLATE: str = "/rest/agile/1.0/sprint/{sprint_id}/issue"

DEFAULT_OUTPUT_FILE: str = "jira_board_issues.json"
WORKING_PATH_PROPERTY: str = "working_path"
ALL_FIELDS: str = "*all"
SEARCH_EXPAND: str = "changelog,names,renderedFields"
KEY_FIELD: str = "key"

NO_FILTER_MESSAGE: str = (
    "Board {board_id} exposes no filter in its configuration. Check the board id and that your "
    "account can read its configuration."
)


def _silent(_message: str) -> None:
    """Discard a progress message.

    Parameters:
        _message: The message that will not be shown.

    Raises:
        None

    Returns:
        None
    """


def _get_board_filter_id(client: JiraClient, board_id: int) -> str:
    """Read the id of the filter that defines a board.

    Parameters:
        client: The Jira client to use.
        board_id: The board whose configuration should be read.

    Raises:
        click.ClickException: If the board exposes no filter.

    Returns:
        str: The filter id.
    """
    configuration: dict = client.get(BOARD_CONFIGURATION_TEMPLATE.format(board_id=board_id))
    filter_id: Optional[str] = (configuration.get("filter") or {}).get("id")
    if not filter_id:
        raise click.ClickException(NO_FILTER_MESSAGE.format(board_id=board_id))
    return str(filter_id)


def _iter_board_issues(client: JiraClient, filter_id: str) -> Iterator[dict]:
    """Yield every raw issue matched by the board's filter.

    Parameters:
        client: The Jira client to use.
        filter_id: The filter that defines the board.

    Raises:
        click.ClickException: If any page fails.

    Returns:
        Iterator[dict]: The raw issues, page after page.
    """
    return client.paginate_tokens(
        SEARCH_PATH,
        {"jql": f"filter={filter_id}", "fields": ALL_FIELDS, "expand": SEARCH_EXPAND},
    )


def get_active_sprint_keys(client: JiraClient, board: Board, report: Callable[[str], None] = ws_info) -> set[str]:
    """Collect the keys of every issue in the board's active sprints.

    Parameters:
        client: The Jira client to use.
        board: The board to inspect.
        report: Where progress messages go.

    Raises:
        click.ClickException: If any request fails.

    Returns:
        set[str]: The issue keys in an active sprint, empty for a kanban board or a board whose
            sprint was never started.
    """
    sprints: list[Sprint] = get_active_sprints(board.id, board.cloud_domain, client)
    keys: set[str] = set()
    for sprint in sprints:
        report(f"Active sprint: {sprint.id} - {sprint.name}")
        # An Agile endpoint: it pages with startAt/total, never with nextPageToken. Reading it with
        # the token paginator would stop after the first page, and every sprint issue past it would
        # be written out as activeSprint=false with a successful exit.
        for issue in client.paginate_start_at(
            SPRINT_ISSUES_TEMPLATE.format(sprint_id=sprint.id), {"fields": KEY_FIELD}
        ):
            issue_key: Optional[str] = issue.get("key")
            if issue_key:
                keys.add(issue_key)
    return keys


def download_board_issues(
    project_key: Optional[str] = None,
    output: Optional[str] = None,
    refresh_board: bool = False,
    quiet: bool = False,
    client: Optional[JiraClient] = None,
) -> Path:
    """Download, project and store every issue of a project's board.

    Parameters:
        project_key: The Jira project key. Falls back to the stored ``jira.project_key``.
        output: The destination file. Defaults to the working path's ``jira_board_issues.json``.
        refresh_board: Whether to re-resolve the board instead of using the cached id.
        quiet: Whether to silence the progress messages.
        client: An existing client to reuse. One is created on demand when omitted.

    Raises:
        click.ClickException: If the settings are missing, a request fails, or the board exposes no
            filter.

    Returns:
        Path: The file the issues were written to.
    """
    report: Callable[[str], None] = _silent if quiet else ws_info
    done: Callable[[str], None] = _silent if quiet else ws_success
    api: JiraClient = client or JiraClient()
    board: Board = resolve_board(project_key, refresh_board, api)
    report(f"Board {board.id} on {board.cloud_domain}")
    filter_id: str = _get_board_filter_id(api, board.id)
    report(f"Board filter: {filter_id}")
    field_ids: FieldIds = FieldIds.resolve(api)
    issues: list[dict] = [project_issue(raw, field_ids) for raw in _iter_board_issues(api, filter_id)]
    report(f"Downloaded {len(issues)} issues.")
    active_keys: set[str] = get_active_sprint_keys(api, board, report)
    if not active_keys:
        report("No active sprint found; every issue will be flagged as activeSprint=false.")
    active_count: int = 0
    for issue in issues:
        in_sprint: bool = issue.get("key") in active_keys
        issue[ACTIVE_SPRINT_KEY] = in_sprint
        active_count += int(in_sprint)
    destination: Path = Path(output) if output else Path(ensure_working_path()) / DEFAULT_OUTPUT_FILE
    write_json_atomically(destination, issues)
    done(f"{len(issues)} issues written to {destination} ({active_count} in an active sprint).")
    return destination


@click.command(
    name="jira-issues",
    short_help="Downloads every issue of a project's board into a JSON file.",
    help="""Downloads every issue of a Jira project's Agile board (epics, stories, tasks, subtasks),
    projects them into the compact schema the Jira skills consume, flags the ones that belong to an
    active sprint, and writes the result as a JSON array. The story points and sprint custom fields
    are resolved by name for the current Jira instance instead of being hardcoded, so the output is
    correct on any tenant. Progress goes to the console; only the file receives the data.""",
    epilog="""
    Args:\n
        project_key: str - Jira project key. Defaults to the stored jira.project_key.
    """,
)
@cli_metadata(flags={"skip"})
@click.argument("project_key", required=False)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Destination file. Defaults to jira_board_issues.json inside the working path.",
)
@click.option(
    "--refresh-board",
    is_flag=True,
    default=False,
    help="Ignore the cached board id and resolve it from Jira again before downloading.",
)
@click.option("--quiet", "-q", is_flag=True, default=False, help="Silence the progress messages.")
def jira_issues(project_key: Optional[str], output: Optional[str], refresh_board: bool, quiet: bool) -> None:
    """Download every issue of a project's board into a JSON file.

    Parameters:
        project_key: The Jira project key, or None to use the stored one.
        output: The destination file, or None to use the working path default.
        refresh_board: Whether to bypass the cached board id.
        quiet: Whether to silence the progress messages.

    Raises:
        click.ClickException: If the settings are missing, or a request fails.

    Returns:
        None
    """
    # The only "skip" command of this module, so the pre-flight lives here rather than in the module
    # wrapper: the other two are "no_init" and must never touch the working path.
    #
    # It only runs when the working path is where the output goes. With -o naming the destination,
    # offering to create `workspace_temp` -- and exiting 114 when the user declines -- would be a
    # prompt about a folder this run never touches. The deferred initialization is still completed
    # whenever the folder happens to exist already, so --log-level keeps working; when it does not,
    # only the log file is lost, and the console output never depended on it.
    resolved_output: str = output or str(Path(ensure_working_path()) / DEFAULT_OUTPUT_FILE)
    if output is None or os.path.isdir(get_property(WORKING_PATH_PROPERTY)):
        # Securing the folder first is what lets complete_app_properties finish where __init__
        # stopped; called with the folder still missing it would raise FileNotFoundError.
        complete_app_properties()
    download_board_issues(project_key, resolved_output, refresh_board, quiet)
