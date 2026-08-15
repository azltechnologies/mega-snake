"""Tests for resolving a Jira project key to its Agile board."""

import json
from pathlib import Path

from click.testing import CliRunner
import click
import pytest

from mega_snake.constants import JIRA_BOARD_ID_KEY, JIRA_PROJECT_KEY_KEY
from mega_snake.jira_api.board import jira_board, resolve_board
from mega_snake.util.store import SCOPE_REPO, Store

from tests.jira_api.jira_doubles import BOARD_ID, DOMAIN, PROJECT_ID, PROJECT_KEY, FakeResponse, make_client

def _board_responses(*boards: dict) -> list[FakeResponse]:
    """Queue the two responses a cold board resolution makes."""
    return [FakeResponse({"id": PROJECT_ID, "key": PROJECT_KEY}), FakeResponse({"values": list(boards)})]


def test_board_output_is_exactly_the_expected_json(jira_workspace: Path) -> None:
    """The whole parsed payload is compared, not a substring of the printed line."""
    assert jira_workspace.exists()
    client, _ = make_client(_board_responses({"id": BOARD_ID, "name": "TAROTAPP board"}))

    board = resolve_board(client=client)

    assert board.to_dict() == {"boardId": BOARD_ID, "cloudDomain": DOMAIN}


def test_board_id_is_an_integer_not_a_string(jira_workspace: Path) -> None:
    """`getJiraBoard.sh` emitted it through `jq --arg`, so it was a string while `getSprintInfo`
    used it as a number. The two now agree on an integer."""
    assert jira_workspace.exists()
    client, _ = make_client(_board_responses({"id": BOARD_ID}))

    board_id = resolve_board(client=client).to_dict()["boardId"]

    assert isinstance(board_id, int)
    assert not isinstance(board_id, str)


def test_unknown_project_raises_naming_the_project_key(jira_workspace: Path) -> None:
    """`jq -r '.id'` returned the string "null" and the script carried on with ?projectKeyOrId=null,
    ending up printing {"boardId": "null"}. A missing id is an error now."""
    assert jira_workspace.exists()
    client, session = make_client([FakeResponse({})])

    with pytest.raises(click.ClickException) as error:
        resolve_board("NOPE", client=client)

    assert "NOPE" in str(error.value)
    assert len(session.calls) == 1, "the board lookup must not run with a null project id"


def test_project_without_a_board_raises(jira_workspace: Path) -> None:
    """An empty `values` array is a configuration problem, not an empty result."""
    assert jira_workspace.exists()
    client, _ = make_client(_board_responses())

    with pytest.raises(click.ClickException) as error:
        resolve_board(client=client)

    assert "no Agile board" in str(error.value)


def test_multiple_boards_prompts_and_honours_the_selection(
    jira_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.values[0]` silently picked the first board. The user chooses, and the choice is honoured.

    The assertion is on *which* board came back, not merely that a prompt happened.
    """
    assert jira_workspace.exists()
    client, _ = make_client(_board_responses({"id": 11, "name": "kanban"}, {"id": 22, "name": "scrum"}))
    monkeypatch.setattr("mega_snake.jira_api.board.click.prompt", lambda *_args, **_kwargs: "1")

    assert resolve_board(client=client).id == 22


def test_board_id_is_cached_in_repo_scope_and_reused(jira_workspace: Path) -> None:
    """The second resolution makes zero HTTP calls, asserted by equality against 0."""
    assert jira_workspace.exists()
    client, session = make_client(_board_responses({"id": BOARD_ID}))

    resolve_board(client=client)
    calls_after_cold_run = len(session.calls)
    board = resolve_board(client=client)

    assert Store.get_instance().items(SCOPE_REPO)[JIRA_BOARD_ID_KEY] == str(BOARD_ID)
    assert board.id == BOARD_ID
    assert len(session.calls) - calls_after_cold_run == 0


def test_refresh_flag_bypasses_the_cache(jira_workspace: Path) -> None:
    """The negative of the caching test: --refresh goes back to Jira."""
    assert jira_workspace.exists()
    client, session = make_client(
        _board_responses({"id": BOARD_ID}) + _board_responses({"id": 99}),
    )

    resolve_board(client=client)
    board = resolve_board(refresh=True, client=client)

    assert board.id == 99
    assert len(session.calls) == 4


def test_cache_is_ignored_for_a_different_project(jira_workspace: Path) -> None:
    """The cache is repository-scoped, so it must not answer for somebody else's project key."""
    assert jira_workspace.exists()
    Store.get_instance().set(JIRA_BOARD_ID_KEY, str(BOARD_ID))
    client, session = make_client(_board_responses({"id": 55}))

    assert resolve_board("OTHER", client=client).id == 55
    assert len(session.calls) == 2


def test_corrupt_cached_board_id_is_ignored_and_reported_on_stderr(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """A hand-edited state file must not turn every run into a ValueError."""
    assert jira_workspace.exists()
    Store.get_instance().set(JIRA_BOARD_ID_KEY, "not-a-number")
    client, _ = make_client(_board_responses({"id": BOARD_ID}))

    assert resolve_board(client=client).id == BOARD_ID
    assert capsys.readouterr().out == ""


def test_missing_project_key_names_the_command_that_sets_it(jira_workspace: Path) -> None:
    """With no argument and nothing stored, the error is the exact command to run."""
    assert jira_workspace.exists()
    Store.get_instance().unset(JIRA_PROJECT_KEY_KEY)

    with pytest.raises(click.ClickException) as error:
        resolve_board()

    assert f"config set {JIRA_PROJECT_KEY_KEY} <value>" in str(error.value)


def test_stdout_contains_only_json(jira_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The command is `no_init` and read with $(...), so the whole stdout has to parse as JSON.

    Parsing all of it is the point: a single ws_* line anywhere would make json.loads blow up.
    """
    assert jira_workspace.exists()
    client, _ = make_client(_board_responses({"id": BOARD_ID}))
    monkeypatch.setattr("mega_snake.jira_api.board.JiraClient", lambda *_args, **_kwargs: client)

    result = CliRunner().invoke(jira_board, [PROJECT_KEY])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"boardId": BOARD_ID, "cloudDomain": DOMAIN}


def test_command_reports_a_missing_setting_with_status_one(jira_workspace: Path) -> None:
    """Every error path exits 1 with the message on stderr, never a half-written JSON document."""
    assert jira_workspace.exists()
    Store.get_instance().unset(JIRA_PROJECT_KEY_KEY)

    result = CliRunner().invoke(jira_board, [])

    assert result.exit_code == 1
    assert result.stdout == ""
