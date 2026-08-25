"""Tests for the active-sprint report."""

import json
from pathlib import Path

from click.testing import CliRunner
import pytest

from mega_snake.constants import JIRA_BOARD_ID_KEY
from mega_snake.jira_api.sprint import ACTIVE_STATE, SPRINT_PATH_TEMPLATE, get_active_sprints, jira_sprint
from mega_snake.util.store import Store

from tests.jira_api.jira_doubles import BOARD_ID, DOMAIN, make_client, sprint_listing_page

SPRINT_ONE = {"id": 42, "name": "Sprint 1", "startDate": "2026-08-01T00:00:00Z", "endDate": "2026-08-15T00:00:00Z"}
SPRINT_TWO = {"id": 43, "name": "Sprint 2", "startDate": None, "endDate": None}


@pytest.mark.parametrize(
    ("sprints", "expected_length"), [([], 0), ([SPRINT_ONE], 1), ([SPRINT_ONE, SPRINT_TWO], 2)]
)
def test_active_sprints_always_returns_a_list(sprints: list[dict], expected_length: int) -> None:
    """`getSprintInfo.sh` piped `.values[]` without wrapping it in an array.

    One active sprint therefore produced a bare object, and two produced two concatenated objects,
    which is not a JSON document at all. Zero, one and two sprints are all exercised here; the
    single-sprint case is the one that used to be indistinguishable from an array of one.
    """
    client, _ = make_client([sprint_listing_page(sprints)])

    result = get_active_sprints(BOARD_ID, DOMAIN, client)

    assert isinstance(result, list)
    assert len(result) == expected_length


def test_sprint_payload_matches_the_published_contract() -> None:
    """The key set and the values are the ones the shell filter produced."""
    client, _ = make_client([sprint_listing_page([SPRINT_ONE])])

    assert [sprint.to_dict() for sprint in get_active_sprints(BOARD_ID, DOMAIN, client)] == [
        {
            "id": 42,
            "name": "Sprint 1",
            "startDate": "2026-08-01T00:00:00Z",
            "endDate": "2026-08-15T00:00:00Z",
            "cloudDomain": DOMAIN,
            "boardId": BOARD_ID,
        }
    ]


def test_the_active_state_filter_is_sent() -> None:
    """Only active sprints are asked for; filtering client side would page through history."""
    client, session = make_client([sprint_listing_page([])])

    get_active_sprints(BOARD_ID, DOMAIN, client)

    assert session.calls[0][1] == {"state": ACTIVE_STATE, "maxResults": "100", "startAt": "0"}
    assert session.paths == [SPRINT_PATH_TEMPLATE.format(board_id=BOARD_ID)]


def test_kanban_board_yields_an_empty_array_and_a_successful_exit(
    jira_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A board with no active sprint is a normal answer, not a failure."""
    assert jira_workspace.exists()
    Store.get_instance().set(JIRA_BOARD_ID_KEY, str(BOARD_ID))
    client, _ = make_client([sprint_listing_page([])])
    monkeypatch.setattr("mega_snake.jira_api.sprint.JiraClient", lambda *_args, **_kwargs: client)

    result = CliRunner().invoke(jira_sprint, [])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_stdout_contains_only_json(jira_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The command is `no_init` and read with $(...), so the whole stdout has to parse as JSON."""
    assert jira_workspace.exists()
    Store.get_instance().set(JIRA_BOARD_ID_KEY, str(BOARD_ID))
    client, _ = make_client([sprint_listing_page([SPRINT_ONE, SPRINT_TWO])])
    monkeypatch.setattr("mega_snake.jira_api.sprint.JiraClient", lambda *_args, **_kwargs: client)

    result = CliRunner().invoke(jira_sprint, [])

    assert result.exit_code == 0
    assert [sprint["id"] for sprint in json.loads(result.stdout)] == [42, 43]


def test_every_page_of_the_sprint_listing_is_followed() -> None:
    """The board sprint endpoint pages with startAt/isLast, so one page is not the answer.

    Written against the shape Jira actually sends: this used to be read with the `nextPageToken`
    paginator, which the endpoint never sends, so the walk stopped after the first page. A sprint
    dropped here is not a visible failure -- it is every one of its issues silently written out as
    `activeSprint: false`, with exit code 0.
    """
    client, session = make_client(
        [sprint_listing_page([SPRINT_ONE], is_last=False), sprint_listing_page([SPRINT_TWO])]
    )

    sprints = get_active_sprints(BOARD_ID, DOMAIN, client)

    assert [sprint.id for sprint in sprints] == [42, 43]
    assert [params["startAt"] for _, params in session.calls] == ["0", "1"]
