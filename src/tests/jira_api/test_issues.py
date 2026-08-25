"""Tests for the board issue download: projection, active-sprint flagging and file output."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
import click
import pytest

from mega_snake.constants import JIRA_BOARD_ID_KEY, JIRA_SPRINT_FIELD_KEY, JIRA_STORY_POINTS_FIELD_KEY
from mega_snake.jira_api.board import BOARD_PATH, PROJECT_PATH_TEMPLATE
from mega_snake.jira_api.issues import (
    ALL_FIELDS,
    BOARD_CONFIGURATION_TEMPLATE,
    DEFAULT_OUTPUT_FILE,
    download_board_issues,
    jira_issues,
)
from mega_snake.jira_api.projection import FIELD_PATH
from mega_snake.util.store import SCOPE_REPO, Store

from tests.jira_api.jira_doubles import (
    BOARD_ID,
    PROJECT_ID,
    PROJECT_KEY,
    FakeResponse,
    make_client,
    sprint_issues_page,
    sprint_listing_page,
)

RESOURCES = Path(__file__).resolve().parents[1] / "resources" / "jira"
STORY_POINTS_FIELD = "customfield_99999"
SPRINT_FIELD = "customfield_88888"
FILTER_ID = "999"
# The historic ids, used as the *stale* cache in the --refresh tests. The raw fixture carries them
# too, with different values (999 story points, a closed "Historic sprint"), so which id the
# projection used can be asserted on the output data instead of on a call count.
STALE_STORY_POINTS_FIELD = "customfield_10016"
STALE_SPRINT_FIELD = "customfield_10020"
REFRESHED_BOARD_ID = 5150

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
    responses.append(sprint_listing_page(sprints))
    for _ in sprints:
        responses.append(sprint_issues_page(sprint_keys, len(sprint_keys)))
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

    # Compared by equality rather than by `"jql" in params`: `expand` has to be asserted *absent*,
    # and only an equality assertion fails if someone reinstates it. `changelog` is the full
    # transition history of every field of every issue, inline, and `project_issue` reads none of it.
    assert session.calls[1][1] == {
        "jql": f"filter={FILTER_ID}",
        "fields": ALL_FIELDS,
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
    """The two endpoints page differently, and each one is walked the way Jira actually pages it.

    `/rest/api/2/search/jql` sends `nextPageToken`; `/rest/agile/1.0/sprint/{id}/issue` is an Agile
    bean that pages with `startAt`/`total` and never sends a token. This test used to serve a token
    for the sprint endpoint too, so it pinned the behaviour of the double instead of Jira's, and
    stayed green while the second page of sprint keys was never requested.
    """
    _prime(Store.get_instance())
    client, session = make_client(
        [
            CONFIGURATION_RESPONSE,
            FakeResponse({"issues": [RAW_ISSUES[0]], "nextPageToken": "p1"}),
            FakeResponse({"issues": [RAW_ISSUES[1]]}),
            sprint_listing_page([SPRINT_ONE]),
            sprint_issues_page(["TAROTAPP-1"], total=2),
            sprint_issues_page(["TAROTAPP-0"], total=2),
        ]
    )
    output = jira_workspace / "issues.json"

    download_board_issues(output=str(output), client=client)
    issues = json.loads(output.read_text(encoding="utf-8"))

    assert [issue["key"] for issue in issues] == ["TAROTAPP-1", "TAROTAPP-0"]
    assert all(issue["activeSprint"] for issue in issues)
    assert len(session.calls) == 6


def test_a_sprint_key_on_the_second_page_is_still_flagged(jira_workspace: Path) -> None:
    """The regression test for reading an Agile endpoint with the token paginator.

    `TAROTAPP-1` lives on the *second* page of the sprint's issue listing. With a paginator that
    waits for a `nextPageToken` the endpoint never sends, page two is never requested and the issue
    is written out as `activeSprint: false` -- wrong data, no warning, exit code 0.
    """
    _prime(Store.get_instance())
    client, session = make_client(
        [
            CONFIGURATION_RESPONSE,
            FakeResponse({"issues": RAW_ISSUES}),
            sprint_listing_page([SPRINT_ONE]),
            sprint_issues_page(["TAROTAPP-9"], total=2),
            sprint_issues_page(["TAROTAPP-1"], total=2),
        ]
    )
    output = jira_workspace / "issues.json"

    download_board_issues(output=str(output), client=client)
    issues = json.loads(output.read_text(encoding="utf-8"))

    assert {issue["key"] for issue in issues if issue["activeSprint"]} == {"TAROTAPP-1"}
    assert [params["startAt"] for _, params in session.calls[-2:]] == ["0", "1"]


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

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "3 issues written to" in captured.err


def test_command_defaults_the_output_to_the_working_path(jira_workspace: Path) -> None:
    """Without -o the file lands in the working path, which the command secures first."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [], []))
    working_path = jira_workspace / "workspace_temp"
    working_path.mkdir()

    with patch(
        "mega_snake.jira_api.issues.ensure_working_path", return_value=str(working_path)
    ) as ensure_working_path_mock, patch("mega_snake.jira_api.issues.complete_app_properties"), patch(
        "mega_snake.jira_api.issues.JiraClient", return_value=client
    ):
        result = CliRunner().invoke(jira_issues, [])

    assert result.exit_code == 0
    assert (working_path / DEFAULT_OUTPUT_FILE).is_file()
    # The command resolves the default path itself and passes it down, so download_board_issues()
    # never has to fall back to ensure_working_path() a second time for the same run.
    ensure_working_path_mock.assert_called_once()


def test_explicit_output_never_touches_the_working_path(jira_workspace: Path) -> None:
    """With -o naming the destination, `workspace_temp` is none of this run's business.

    `ensure_working_path` warns, prompts, and raises `UserDeclinedError` (exit 114) when the user
    says no -- for a folder the run was never going to write to. Asserted by equality against zero
    calls, and by the folder still not existing afterwards.
    """
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [], []))
    output = jira_workspace / "elsewhere.json"

    with (
        patch("mega_snake.jira_api.issues.ensure_working_path") as ensure_working_path_mock,
        patch("mega_snake.jira_api.issues.complete_app_properties") as complete_mock,
        patch("mega_snake.jira_api.issues.get_property", return_value=str(jira_workspace / "workspace_temp")),
        patch("mega_snake.jira_api.issues.JiraClient", return_value=client),
    ):
        result = CliRunner().invoke(jira_issues, ["-o", str(output)])

    assert result.exit_code == 0
    assert output.is_file()
    assert ensure_working_path_mock.call_count == 0
    # No working path means no log file to configure, so the deferred initialization is skipped
    # rather than left to raise FileNotFoundError.
    assert complete_mock.call_count == 0
    assert not (jira_workspace / "workspace_temp").exists()


def test_explicit_output_still_completes_logging_when_the_folder_exists(jira_workspace: Path) -> None:
    """The negative of the previous test: an existing folder means --log-level keeps working."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [], []))
    working_path = jira_workspace / "workspace_temp"
    working_path.mkdir()

    with (
        patch("mega_snake.jira_api.issues.ensure_working_path") as ensure_working_path_mock,
        patch("mega_snake.jira_api.issues.complete_app_properties") as complete_mock,
        patch("mega_snake.jira_api.issues.get_property", return_value=str(working_path)),
        patch("mega_snake.jira_api.issues.JiraClient", return_value=client),
    ):
        result = CliRunner().invoke(jira_issues, ["-o", str(jira_workspace / "elsewhere.json")])

    assert result.exit_code == 0
    assert ensure_working_path_mock.call_count == 0
    assert complete_mock.call_count == 1


def test_download_falls_back_to_the_working_path_when_called_without_a_command(jira_workspace: Path) -> None:
    """A direct (non-CLI) caller that omits `output` still gets the working-path default."""
    _prime(Store.get_instance())
    client, _ = make_client(_responses([RAW_ISSUES], [], []))
    working_path = jira_workspace / "workspace_temp"
    working_path.mkdir()

    with patch("mega_snake.jira_api.issues.ensure_working_path", return_value=str(working_path)):
        destination = download_board_issues(client=client)

    assert destination == working_path / DEFAULT_OUTPUT_FILE
    assert destination.is_file()


@pytest.mark.parametrize("flag", ["--refresh", "-r"])
def test_refresh_re_resolves_the_board_and_the_field_ids(jira_workspace: Path, flag: str) -> None:
    """`--refresh` must reach *both* cached lookups, and it is asserted on the projected data.

    Both spellings are run, because the short one is what a user types and a `-r` that never reaches
    the command body would otherwise go unnoticed.

    The flag was wired only to the board resolution once, and nothing failed: the field ids kept
    being answered from the store, so a re-created custom field stayed stale forever with a
    successful exit and no warning. Asserting call counts alone would not have caught it either --
    the field endpoint being requested says nothing about which id the projection then used.

    So the stale cache is primed with the *historic* ids, which the fixture also carries with
    different values (`customfield_10016` is 999 where `customfield_99999` is 5, and the historic
    sprint field holds a closed "Historic sprint"). Every assertion below therefore separates the
    refreshed id from the cached one by value, and each one is paired with its negative.
    """
    store = Store.get_instance()
    store.set(JIRA_BOARD_ID_KEY, str(BOARD_ID))
    store.set(JIRA_STORY_POINTS_FIELD_KEY, STALE_STORY_POINTS_FIELD)
    store.set(JIRA_SPRINT_FIELD_KEY, STALE_SPRINT_FIELD)
    client, session = make_client(
        [
            FakeResponse({"id": PROJECT_ID, "key": PROJECT_KEY}),
            FakeResponse({"values": [{"id": REFRESHED_BOARD_ID, "name": "recreated board"}]}),
            CONFIGURATION_RESPONSE,
            FakeResponse(
                [
                    {"id": STORY_POINTS_FIELD, "name": "Story Points"},
                    {"id": SPRINT_FIELD, "name": "Sprint"},
                ]
            ),
            FakeResponse({"issues": RAW_ISSUES}),
            sprint_listing_page([]),
        ]
    )
    output = jira_workspace / "refreshed.json"

    with (
        patch("mega_snake.jira_api.issues.get_property", return_value=str(jira_workspace / "workspace_temp")),
        patch("mega_snake.jira_api.issues.JiraClient", return_value=client),
    ):
        result = CliRunner().invoke(jira_issues, ["-o", str(output), flag])

    assert result.exit_code == 0, result.output
    issues = json.loads(output.read_text(encoding="utf-8"))
    # The board: the configuration is read for the board Jira just answered with, not the cached one.
    assert BOARD_CONFIGURATION_TEMPLATE.format(board_id=REFRESHED_BOARD_ID) in session.paths
    assert BOARD_CONFIGURATION_TEMPLATE.format(board_id=BOARD_ID) not in session.paths
    assert store.items(SCOPE_REPO)[JIRA_BOARD_ID_KEY] == str(REFRESHED_BOARD_ID)
    # The field ids: asserted through the projected values, which differ between the two ids.
    assert FIELD_PATH in session.paths, "the field endpoint must be queried again"
    assert issues[0]["fields"]["storyPoints"] == 5, "the refreshed field id must drive the projection"
    assert issues[0]["fields"]["storyPoints"] != 999, "999 is what the stale cached id projects"
    assert [sprint["name"] for sprint in issues[0]["fields"]["sprint"]] == ["Sprint 1"]
    assert store.items(SCOPE_REPO)[JIRA_STORY_POINTS_FIELD_KEY] == STORY_POINTS_FIELD
    assert store.items(SCOPE_REPO)[JIRA_SPRINT_FIELD_KEY] == SPRINT_FIELD


def test_without_refresh_both_caches_answer(jira_workspace: Path) -> None:
    """The negative of the test above, and the reason `--refresh` has to exist at all.

    Same primed stale cache, no flag: not one of the three resolving endpoints is requested, and the
    stale story-point id is what the projection uses. Without this half, an implementation that
    ignored the cache entirely would pass the refresh test.
    """
    store = Store.get_instance()
    store.set(JIRA_BOARD_ID_KEY, str(BOARD_ID))
    store.set(JIRA_STORY_POINTS_FIELD_KEY, STALE_STORY_POINTS_FIELD)
    store.set(JIRA_SPRINT_FIELD_KEY, STALE_SPRINT_FIELD)
    client, session = make_client(_responses([RAW_ISSUES], [], []))
    output = jira_workspace / "cached.json"

    with (
        patch("mega_snake.jira_api.issues.get_property", return_value=str(jira_workspace / "workspace_temp")),
        patch("mega_snake.jira_api.issues.JiraClient", return_value=client),
    ):
        result = CliRunner().invoke(jira_issues, ["-o", str(output)])

    assert result.exit_code == 0, result.output
    issues = json.loads(output.read_text(encoding="utf-8"))
    assert issues[0]["fields"]["storyPoints"] == 999, "the cached id is what answers without --refresh"
    assert FIELD_PATH not in session.paths
    assert PROJECT_PATH_TEMPLATE.format(project_key=PROJECT_KEY) not in session.paths
    assert BOARD_PATH not in session.paths
    assert BOARD_CONFIGURATION_TEMPLATE.format(board_id=BOARD_ID) in session.paths


def test_the_old_refresh_board_flag_is_gone(jira_workspace: Path) -> None:
    """The rename is a breaking change, and it is a clean break rather than a silent alias.

    Left as an alias, `--refresh-board` would keep its old meaning -- the board only -- while the
    documentation describes a flag that also refreshes the field ids, which is the worst of the two
    outcomes: a user following the reference gets a stale projection and no error.
    """
    assert jira_workspace.exists()
    spellings = [opt for option in jira_issues.params for opt in option.opts]

    assert sorted(spellings) == ["--output", "--quiet", "--refresh", "-o", "-q", "-r", "project_key"]
    assert "--refresh-board" not in spellings
