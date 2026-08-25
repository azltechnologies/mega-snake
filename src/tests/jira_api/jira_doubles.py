"""HTTP doubles and shared constants for the Jira module tests.

Not a single test in this package touches the network: every request goes through a `FakeSession`
that replays a queued list of responses and records what was asked for.
"""

from typing import Any, Optional

from mega_snake.jira_api.client import JiraClient
from mega_snake.jira_api.models import JiraConfig

DOMAIN = "example.atlassian.net"
BASE_URL = f"https://{DOMAIN}"
EMAIL = "dev@example.com"
TOKEN = "api-token"
PROJECT_KEY = "TAROTAPP"
BOARD_ID = 17
PROJECT_ID = "10001"


class FakeResponse:
    """A canned HTTP response with just the surface `JiraClient` uses."""

    def __init__(
        self, payload: Any = None, status_code: int = 200, text: str = "", invalid_json: bool = False
    ) -> None:
        """Build a canned response."""
        self.payload = payload
        self.status_code = status_code
        self.text = text
        self.invalid_json = invalid_json

    def json(self) -> Any:
        """Return the decoded payload, or fail the way `requests` does on a body that is not JSON."""
        if self.invalid_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self.payload


class FakeSession:
    """A `requests.Session` stand-in that replays queued responses and records the calls."""

    def __init__(self, responses: Optional[list[FakeResponse]] = None) -> None:
        """Queue the responses this session will serve, in order."""
        self.responses: list[FakeResponse] = list(responses or [])
        self.calls: list[tuple[str, Optional[dict]]] = []
        self.headers: dict[str, str] = {}

    def get(self, url: str, params: Optional[dict] = None, timeout: Optional[int] = None) -> FakeResponse:
        """Record the call and return the next queued response."""
        self.calls.append((url, dict(params) if params else None))
        assert timeout is not None, "every request must carry a timeout"
        if not self.responses:
            raise AssertionError(f"unexpected request to {url} with {params}")
        return self.responses.pop(0)

    @property
    def paths(self) -> list[str]:
        """Return the requested paths, without the base URL, in call order."""
        return [url.removeprefix(BASE_URL) for url, _ in self.calls]


def sprint_listing_page(sprints: list[dict], is_last: bool = True) -> FakeResponse:
    """Build one page of `/rest/agile/1.0/board/{id}/sprint`, the way Jira shapes it.

    That endpoint is a `PageBean`: it pages with `startAt`/`maxResults` and closes the walk with
    `isLast`. It never sends a `nextPageToken` -- building the double by hand once made a test pin a
    shape Jira does not produce, and the truncation bug it was meant to catch went through green.
    """
    return FakeResponse({"values": sprints, "isLast": is_last, "maxResults": 50, "startAt": 0})


def sprint_issues_page(keys: list[str], total: int) -> FakeResponse:
    """Build one page of `/rest/agile/1.0/sprint/{id}/issue`, the way Jira shapes it.

    That one is a `SearchResults` bean: same `startAt` paging, but the end of the walk is `total`
    rather than `isLast`. Passing the *overall* total (not the page length) is what makes a
    multi-page fixture behave like the real endpoint.
    """
    return FakeResponse({"issues": [{"key": key} for key in keys], "total": total, "maxResults": 50})


def make_config() -> JiraConfig:
    """Build the connection settings the fakes are wired for."""
    return JiraConfig(domain=DOMAIN, email=EMAIL, token=TOKEN)


def make_client(responses: Optional[list[FakeResponse]] = None) -> tuple[JiraClient, FakeSession]:
    """Build a client whose session is a fake replaying the given responses."""
    client = JiraClient(make_config())
    session = FakeSession(responses)
    client._session = session  # pylint: disable=protected-access
    return client, session
