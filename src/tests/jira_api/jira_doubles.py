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


def make_config() -> JiraConfig:
    """Build the connection settings the fakes are wired for."""
    return JiraConfig(domain=DOMAIN, email=EMAIL, token=TOKEN)


def make_client(responses: Optional[list[FakeResponse]] = None) -> tuple[JiraClient, FakeSession]:
    """Build a client whose session is a fake replaying the given responses."""
    client = JiraClient(make_config())
    session = FakeSession(responses)
    client._session = session  # pylint: disable=protected-access
    return client, session
