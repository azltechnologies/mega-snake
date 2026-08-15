"""Tests for the board issue download: projection, active-sprint flagging and file output."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
import click
import pytest

from mega_snake.constants import JIRA_BOARD_ID_KEY, JIRA_SPRINT_FIELD_KEY, JIRA_STORY_POINTS_FIELD_KEY
from mega_snake.jira_api.issues import (
    ALL_FIELDS,
    DEFAULT_OUTPUT_FILE,
    SEARCH_EXPAND,
    download_board_issues,
    jira_issues,
)
from mega_snake.util.store import Store

from tests.jira_api.jira_doubles import BOARD_ID, FakeResponse, make_client

RESOURCES = Path(__file__).resolve().parents[1] / "resources" / "jira"
STORY_POINTS_FIELD = "customfield_99999"
SPRINT_FIELD = "customfield_88888"
FILTER_ID = "999"

RAW_ISSUES = json.loads((RESOURCES / "board_issues_raw.json").read_text(encoding="utf-8"))

CONFIGURATION_RESPONSE = FakeResponse({"filter": {"id": FILTER_ID}, "name": "TAROTAPP board"})
SPRINT_ONE = {"id": 42, "name": "Sprint 1", "startDate": None, "endDate": None}


def _prime(store: Store) -> None:
    """Cache the board id and the custom field ids so only the download itself makes requests."""
    store.set(JIRA_BOARD_ID_KEY, str(BOARD_ID))
    store.set(JIRA_STORY_POINTS_FIELD_KEY, STORY_POINTS_FIELD)
    store.set(JIRA_SPRINT_FIELD_KEY, SPRINT_FIELD)


def _responses(issue_pages: list[list[dict]], sprints: list[dict], sprint_keys: list[str]) -> list[FakeResponse]:
    """Queue the whole conversation a download makes with a warm board and field cache."""
    responses = [CONFIGURATION_RESPONSE]
    for index, page in enumerate(issue_pages):
        payload: dict = {"issues": page}
        if index < len(issue_pages) - 1:
            payload["nextPageToken"] = f"page-{index + 1}"
        responses.append(FakeResponse(payload))
    responses.append(FakeResponse({"values": sprints}))
    for _ in sprints:
        responses.append(FakeResponse({"issues": [{"key": key} for key in sprint_keys]}))
    return responses


def test_active_sprint_flag_is_true_only_for_sprint_members(jira_workspace: Path) -> None:
    """The exact set of flagged keys is asserted, and the rest is asserted false explicitly."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [SPRINT_ONE], ["TAROTAPP-1"]))
    output = jira_workspace / "issues.json"

    download_board_issues(output=str(output), client=client)
    issues = json.loads(output.read_text(encoding="utf-8"))

    assert {issue["key"] for issue in issues if issue["activeSprint"]} == {"TAROTAPP-1"}
    assert [issue["key"] for issue in issues if not issue["activeSprint"]] == ["TAROTAPP-0", "TAROTAPP-2"]


def test_no_active_sprint_marks_everything_false(jira_workspace: Path) -> None:
    """A kanban board has no active sprint, and that is not an error."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [], []))
    output = jira_workspace / "issues.json"

    download_board_issues(output=str(output), client=client)
    issues = json.loads(output.read_text(encoding="utf-8"))

    assert [issue["activeSprint"] for issue in issues] == [False, False, False]


def test_output_is_a_valid_json_array_of_projected_issues(jira_workspace: Path) -> None:
    """The file is a JSON array, and each entry carries the projected schema plus the flag."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [], []))
    output = jira_workspace / "issues.json"

    download_board_issues(output=str(output), client=client)
    issues = json.loads(output.read_text(encoding="utf-8"))

    assert isinstance(issues, list)
    assert list(issues[0].keys()) == ["id", "link", "key", "fields", "activeSprint"]
    assert issues[0]["fields"]["storyPoints"] == 5


def test_the_board_filter_drives_the_search(jira_workspace: Path) -> None:
    """The board's own filter is what defines "every issue of the board"."""
    _prime(Store.get_instance())
    client, session = make_client(_responses([[]], [], []))

    download_board_issues(output=str(jira_workspace / "issues.json"), client=client)

    assert session.calls[1][1] == {
        "jql": f"filter={FILTER_ID}",
        "fields": ALL_FIELDS,
        "expand": SEARCH_EXPAND,
        "maxResults": "100",
    }


def test_a_board_without_a_filter_fails_clearly(jira_workspace: Path) -> None:
    """No filter means no way to know what the board contains, so it is an error."""
    _prime(Store.get_instance())
    client, _ = make_client([FakeResponse({"name": "broken board"})])

    with pytest.raises(click.ClickException) as error:
        download_board_issues(output=str(jira_workspace / "issues.json"), client=client)

    assert str(BOARD_ID) in str(error.value)


def test_every_page_of_issues_and_of_sprint_keys_is_followed(jira_workspace: Path) -> None:
    """Both the search and the sprint issue listing page with nextPageToken."""
    _prime(Store.get_instance())
    client, session = make_client(
        [
            CONFIGURATION_RESPONSE,
            FakeResponse({"issues": [RAW_ISSUES[0]], "nextPageToken": "p1"}),
            FakeResponse({"issues": [RAW_ISSUES[1]]}),
            FakeResponse({"values": [SPRINT_ONE]}),
            FakeResponse({"issues": [{"key": "TAROTAPP-1"}], "nextPageToken": "s1"}),
            FakeResponse({"issues": [{"key": "TAROTAPP-0"}]}),
        ]
    )
    output = jira_workspace / "issues.json"

    download_board_issues(output=str(output), client=client)
    issues = json.loads(output.read_text(encoding="utf-8"))

    assert [issue["key"] for issue in issues] == ["TAROTAPP-1", "TAROTAPP-0"]
    assert all(issue["activeSprint"] for issue in issues)
    assert len(session.calls) == 6


def test_output_file_is_written_atomically(jira_workspace: Path) -> None:
    """A serialization that dies half way must leave the previous file exactly as it was."""
    _prime(Store.get_instance())
    output = jira_workspace / "issues.json"
    output.write_text("[]\n", encoding="utf-8")
    original_bytes = output.read_bytes()
    client, _ = make_client(_responses([RAW_ISSUES], [], []))

    with patch("json.dump", side_effect=RuntimeError("interrupted")):
        with pytest.raises(RuntimeError):
            download_board_issues(output=str(output), client=client)

    assert output.read_bytes() == original_bytes


def test_temp_files_are_not_leaked(jira_workspace: Path) -> None:
    """The shell version called mktemp twice and lost the first path, leaking a file every run."""
    _prime(Store.get_instance())
    temp_dir = Path(tempfile.gettempdir())
    before = set(temp_dir.iterdir())
    client, _ = make_client(_responses([RAW_ISSUES], [SPRINT_ONE], ["TAROTAPP-1"]))
    output = jira_workspace / "issues.json"

    download_board_issues(output=str(output), client=client)

    assert set(temp_dir.iterdir()) == before
    assert [entry.name for entry in jira_workspace.iterdir() if entry.is_file()] == ["issues.json"]


def test_stdout_is_empty_when_quiet(jira_workspace: Path, capsys: pytest.CaptureFixture) -> None:
    """--quiet means silent, asserted by equality against the empty string."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [SPRINT_ONE], ["TAROTAPP-1"]))
    capsys.readouterr()

    download_board_issues(output=str(jira_workspace / "issues.json"), quiet=True, client=client)

    assert capsys.readouterr().out == ""


def test_progress_is_reported_when_not_quiet(jira_workspace: Path, capsys: pytest.CaptureFixture) -> None:
    """The negative of the quiet test: by default the run narrates what it is doing."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [SPRINT_ONE], ["TAROTAPP-1"]))
    capsys.readouterr()

    download_board_issues(output=str(jira_workspace / "issues.json"), client=client)

    assert "3 issues written to" in capsys.readouterr().out


def test_command_defaults_the_output_to_the_working_path(jira_workspace: Path) -> None:
    """Without -o the file lands in the working path, which the command secures first."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [], []))
    working_path = jira_workspace / "workspace_temp"
    working_path.mkdir()

    with patch("mega_snake.jira_api.issues.ensure_working_path", return_value=str(working_path)), patch(
        "mega_snake.jira_api.issues.complete_app_properties"
    ), patch("mega_snake.jira_api.issues.JiraClient", return_value=client):
        result = CliRunner().invoke(jira_issues, [])

    assert result.exit_code == 0
    assert (working_path / DEFAULT_OUTPUT_FILE).is_file()
