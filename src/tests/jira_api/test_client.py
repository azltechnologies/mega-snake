"""Tests for the Jira Cloud HTTP client: error mapping, pagination, retry policy and lazy import."""

import subprocess
import sys
from pathlib import Path

import click
import pytest

from mega_snake.jira_api.client import (
    BACKOFF_FACTOR,
    DEFAULT_PAGE_SIZE,
    MAX_RETRIES,
    NOT_A_LIST_MESSAGE,
    RETRY_METHODS,
    RETRY_STATUS,
    STATUS_MESSAGES,
    UNEXPECTED_STATUS_MESSAGE,
    JiraClient,
    _build_session,
)
from mega_snake.jira_api.models import JiraConfig

from tests.jira_api.jira_doubles import BASE_URL, FakeResponse, make_client, make_config

SEARCH_PATH = "/rest/api/2/search/jql"


def test_get_returns_the_decoded_body() -> None:
    """The happy path decodes the JSON body and hands it back unchanged."""
    client, session = make_client([FakeResponse({"id": "10001"})])

    assert client.get("/rest/api/2/project/ABC") == {"id": "10001"}
    assert session.calls == [(f"{BASE_URL}/rest/api/2/project/ABC", None)]


def test_get_passes_parameters_for_the_library_to_encode() -> None:
    """Parameters are handed over as a mapping, which is what `curl -G --data-urlencode` did."""
    client, session = make_client([FakeResponse({})])

    client.get(SEARCH_PATH, {"jql": "filter=42 AND status = Done"})

    assert session.calls == [(f"{BASE_URL}{SEARCH_PATH}", {"jql": "filter=42 AND status = Done"})]


@pytest.mark.parametrize("status", sorted(STATUS_MESSAGES))
def test_handled_statuses_raise_their_own_message(status: int) -> None:
    """The shell version asked `jq` whether the *body* looked like an error, so a 401 with an empty
    body passed as success. Failures are decided by the status here, and each one has its own
    actionable message, compared by equality."""
    client, _ = make_client([FakeResponse(status_code=status)])

    with pytest.raises(click.ClickException) as error:
        client.get("/rest/api/2/project/ABC")

    assert str(error.value) == STATUS_MESSAGES[status].format(path="/rest/api/2/project/ABC")


def test_unexpected_status_reports_the_status_and_the_body() -> None:
    """An unmapped failure still fails, and says enough to diagnose it."""
    client, _ = make_client([FakeResponse(status_code=500, text="boom")])

    with pytest.raises(click.ClickException) as error:
        client.get(SEARCH_PATH)

    assert str(error.value) == UNEXPECTED_STATUS_MESSAGE.format(status=500, path=SEARCH_PATH, body="boom")


def test_a_body_that_is_not_json_fails_clearly() -> None:
    """An HTML error page from a proxy must not surface as a raw ValueError."""
    client, _ = make_client([FakeResponse(text="<html>gateway</html>", invalid_json=True)])

    with pytest.raises(click.ClickException) as error:
        client.get(SEARCH_PATH)

    assert "not valid JSON" in str(error.value)


def test_get_list_rejects_an_object() -> None:
    """The array accessor validates the shape instead of lying in the return type."""
    client, _ = make_client([FakeResponse({"not": "a list"})])

    with pytest.raises(click.ClickException) as error:
        client.get_list("/rest/api/3/field")

    assert str(error.value) == NOT_A_LIST_MESSAGE.format(path="/rest/api/3/field")


def test_get_list_returns_the_array() -> None:
    """The field endpoint answers with a bare array, which is returned untouched."""
    client, _ = make_client([FakeResponse([{"id": "customfield_1"}])])

    assert client.get_list("/rest/api/3/field") == [{"id": "customfield_1"}]


def test_paginate_stops_when_next_page_token_is_absent() -> None:
    """The endpoint only sends the token while more pages remain, so its absence ends the walk."""
    client, session = make_client([FakeResponse({"issues": [{"key": "A-1"}, {"key": "A-2"}]})])

    assert list(client.paginate_tokens(SEARCH_PATH)) == [{"key": "A-1"}, {"key": "A-2"}]
    assert len(session.calls) == 1


def test_paginate_follows_every_token_in_order() -> None:
    """Three pages, and the full list of tokens actually requested is asserted, in order."""
    client, session = make_client(
        [
            FakeResponse({"issues": [{"key": "A-1"}], "nextPageToken": "t1"}),
            FakeResponse({"issues": [{"key": "A-2"}], "nextPageToken": "t2"}),
            FakeResponse({"issues": [{"key": "A-3"}]}),
        ]
    )

    issues = list(client.paginate_tokens(SEARCH_PATH))

    assert issues == [{"key": "A-1"}, {"key": "A-2"}, {"key": "A-3"}]
    assert [params.get("nextPageToken") for _, params in session.calls] == [None, "t1", "t2"]


def test_paginate_asks_for_a_full_page_by_default() -> None:
    """The page size is sent explicitly rather than left to whatever Jira defaults to."""
    client, session = make_client([FakeResponse({"issues": []})])

    list(client.paginate_tokens(SEARCH_PATH))

    assert session.calls[0][1] == {"maxResults": str(DEFAULT_PAGE_SIZE)}


def test_paginate_tolerates_a_page_without_the_items_key() -> None:
    """A page missing its array is an empty page, not a crash."""
    client, _ = make_client([FakeResponse({"issues": None})])

    assert list(client.paginate_tokens(SEARCH_PATH)) == []


def test_start_at_pagination_walks_until_is_last() -> None:
    """The Agile board endpoints close the walk with `isLast`, never with a missing token."""
    client, session = make_client(
        [
            FakeResponse({"values": [{"id": 1}], "isLast": False}),
            FakeResponse({"values": [{"id": 2}], "isLast": True}),
        ]
    )

    values = list(client.paginate_start_at("/rest/agile/1.0/board/17/sprint", items_key="values"))

    assert values == [{"id": 1}, {"id": 2}]
    assert [params["startAt"] for _, params in session.calls] == ["0", "1"]


def test_start_at_pagination_walks_until_total_is_reached() -> None:
    """The search-shaped Agile beans report `total` instead of `isLast`, and it ends the walk."""
    client, session = make_client(
        [
            FakeResponse({"issues": [{"key": "A-1"}, {"key": "A-2"}], "total": 3}),
            FakeResponse({"issues": [{"key": "A-3"}], "total": 3}),
        ]
    )

    issues = list(client.paginate_start_at("/rest/agile/1.0/sprint/42/issue"))

    assert issues == [{"key": "A-1"}, {"key": "A-2"}, {"key": "A-3"}]
    assert [params["startAt"] for _, params in session.calls] == ["0", "2"]


def test_start_at_advances_by_what_came_back_not_by_the_requested_page_size() -> None:
    """Jira caps `maxResults` server side, so a page shorter than the request is normal.

    Advancing by the requested size would skip everything the server withheld, and treating a short
    page as the end of the walk would truncate at the first capped page. The offset must follow the
    number of items actually served.
    """
    client, session = make_client(
        [
            FakeResponse({"issues": [{"key": "A-1"}], "maxResults": 1, "total": 2}),
            FakeResponse({"issues": [{"key": "A-2"}], "maxResults": 1, "total": 2}),
        ]
    )

    issues = list(client.paginate_start_at("/rest/agile/1.0/sprint/42/issue", {"maxResults": "100"}))

    assert issues == [{"key": "A-1"}, {"key": "A-2"}]
    assert [params["startAt"] for _, params in session.calls] == ["0", "1"]


def test_start_at_pagination_stops_on_an_empty_page() -> None:
    """The backstop: a response carrying neither `isLast` nor `total` cannot loop forever."""
    client, session = make_client([FakeResponse({"issues": [{"key": "A-1"}]}), FakeResponse({"issues": []})])

    assert list(client.paginate_start_at("/rest/agile/1.0/sprint/42/issue")) == [{"key": "A-1"}]
    assert len(session.calls) == 2


def test_start_at_pagination_never_sends_a_next_page_token() -> None:
    """The negative: the Agile API does not understand `nextPageToken`, so none is ever sent."""
    client, session = make_client([FakeResponse({"values": [], "isLast": True})])

    list(client.paginate_start_at("/rest/agile/1.0/board/17/sprint", items_key="values"))

    assert [params.get("nextPageToken") for _, params in session.calls] == [None]


def test_token_pagination_never_sends_start_at() -> None:
    """The mirror negative: the JQL search pages by token, so no offset is ever sent."""
    client, session = make_client([FakeResponse({"issues": []})])

    list(client.paginate_tokens(SEARCH_PATH))

    assert [params.get("startAt") for _, params in session.calls] == [None]


def test_session_is_reused_across_paginated_requests(mocker) -> None:
    """One pooled session for the whole walk: the TCP connection and the TLS handshake are reused.

    Asserted by equality against 1, so building a session per request would fail loudly.
    """
    session_factory = mocker.patch("requests.Session")
    session_factory.return_value.headers = {}
    session_factory.return_value.get.side_effect = [
        FakeResponse({"issues": [{"key": "A-1"}], "nextPageToken": "t1"}),
        FakeResponse({"issues": [{"key": "A-2"}], "nextPageToken": "t2"}),
        FakeResponse({"issues": [{"key": "A-3"}]}),
    ]
    client = JiraClient(make_config())

    assert len(list(client.paginate_tokens(SEARCH_PATH))) == 3
    assert session_factory.call_count == 1


def _mounted_retry(config: JiraConfig):
    """Return the Retry policy mounted on the https adapter of a freshly built session."""
    session = _build_session(config)
    return session.get_adapter("https://example.atlassian.net").max_retries


def test_retry_is_configured_with_the_expected_policy() -> None:
    """The configuration is what this codebase owns; retrying itself belongs to urllib3.

    Exercising real backoff here would test urllib3, which already has its own tests, so the policy
    mounted on the https adapter is inspected and asserted field by field instead.
    """
    retry = _mounted_retry(make_config())

    assert retry.total == MAX_RETRIES
    assert retry.backoff_factor == BACKOFF_FACTOR
    assert tuple(retry.status_forcelist) == RETRY_STATUS
    assert retry.allowed_methods == RETRY_METHODS
    assert retry.respect_retry_after_header is True


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_retry_policy_excludes_non_idempotent_methods(method: str) -> None:
    """Replaying a write is not safe, so only GET is ever retried."""
    assert method not in _mounted_retry(make_config()).allowed_methods


@pytest.mark.parametrize("status", [401, 403, 404])
def test_retry_status_list_excludes_credential_and_permission_failures(status: int) -> None:
    """A bad token does not become valid on the second attempt; retrying only delays the message."""
    assert status not in RETRY_STATUS
    assert status not in _mounted_retry(make_config()).status_forcelist


def test_session_carries_the_authorization_and_accept_headers() -> None:
    """Credentials travel in a header, never on a command line where `ps` would show them."""
    session = _build_session(make_config())

    assert session.headers["Authorization"].startswith("Basic ")
    assert session.headers["Accept"] == "application/json"


def test_requests_is_not_imported_at_module_import_time(tmp_path: Path) -> None:
    """The lazy import is what keeps the other commands from paying ~100 ms they never use.

    Run in a clean interpreter, because this test session has already imported `requests` for the
    tests above. Without this guard a refactor that hoists the import to the top of the module would
    slow every single command down and nobody would notice.
    """
    assert tmp_path.exists()
    script = "import sys, mega_snake.__main__; print('requests' in sys.modules)"

    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True, cwd=str(tmp_path)
    )

    assert result.stdout.strip() == "False"
