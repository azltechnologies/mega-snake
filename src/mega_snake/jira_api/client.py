"""Minimal Jira Cloud REST client, replacing the `api()` helper of `jira_board_issues.sh`.

Design notes worth keeping in mind before changing anything here:

**`requests` is imported lazily, and that is load-bearing.** The import costs ~100 ms (against ~28 ms
for `urllib.request`), which is nothing next to a 300 ms-30 s Jira round trip but everything for the
other commands, which never make one. Importing it inside ``_build_session`` -- the same trick
``docs_gen`` uses for the root ``cli`` -- means only the Jira commands pay for it. A test pins this
by asserting ``requests`` is absent from ``sys.modules`` after importing the CLI.

**Retrying is delegated to ``urllib3.util.Retry``, on purpose.** Backoff, honouring ``Retry-After``,
and deciding which statuses deserve another attempt is exactly the kind of hand-written code that
produced the defects this module replaces -- and every branch of it would need its own test to meet
the coverage bar. Only idempotent methods are retried, and credential/permission failures never are:
retrying a 401 just delays the error message the user needs to read.

**One ``Session`` for the whole run.** ``jira-issues`` pages through 10-20 requests against the same
host; a pooled session reuses the TCP connection and the TLS handshake instead of paying for both
every time.

**Errors are decided by the HTTP status, never by the shape of the body.** The shell version asked
``jq`` whether the response looked like an error object, so a 401 with an empty body sailed through
as success.
"""

from typing import TYPE_CHECKING, Any, Iterator, Optional

import click

from mega_snake.jira_api.auth import build_basic_header
from mega_snake.jira_api.models import JiraConfig

if TYPE_CHECKING:
    import requests

DEFAULT_TIMEOUT: int = 30
DEFAULT_PAGE_SIZE: int = 100
MAX_RETRIES: int = 3
BACKOFF_FACTOR: float = 0.5
# 401/403/404 are deliberately absent: a bad token or a missing project does not become valid on the
# second attempt, it only makes the user wait longer for the message that explains the problem.
RETRY_STATUS: tuple[int, ...] = (429, 500, 502, 503, 504)
RETRY_METHODS: frozenset[str] = frozenset({"GET"})

ACCEPT_HEADER: str = "application/json"
NEXT_PAGE_TOKEN: str = "nextPageToken"
MAX_RESULTS: str = "maxResults"

# Keyed by status so every handled failure has one message the tests can assert by equality.
STATUS_MESSAGES: dict[int, str] = {
    401: (
        "Jira rejected the credentials (401). The API token is invalid or expired, or it does not "
        "match the configured email. Check JIRA_API_TOKEN and 'mgsnake config get jira.email'."
    ),
    403: (
        "Jira refused the request (403). The account is authenticated but lacks permission for "
        "this resource."
    ),
    404: (
        "Jira could not find the requested resource (404) at {path}. Check the project key, the "
        "board id, and that the account can see them."
    ),
}
UNEXPECTED_STATUS_MESSAGE: str = "Jira returned an unexpected status {status} for {path}: {body}"
INVALID_JSON_MESSAGE: str = "Jira returned a response for {path} that is not valid JSON: {body}"
NOT_A_LIST_MESSAGE: str = "Expected a JSON array from {path}, but Jira answered with something else."


def _build_session(config: JiraConfig) -> "requests.Session":
    """Build a pooled session with retry and authentication already configured.

    Parameters:
        config: The resolved Jira connection settings.

    Raises:
        None

    Returns:
        requests.Session: The configured session.
    """
    import requests  # pylint: disable=import-outside-toplevel  # lazy: see the module docstring
    from requests.adapters import HTTPAdapter  # pylint: disable=import-outside-toplevel
    from urllib3.util import Retry  # pylint: disable=import-outside-toplevel

    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=list(RETRY_STATUS),
        allowed_methods=RETRY_METHODS,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(build_basic_header(config.email, config.token))
    session.headers["Accept"] = ACCEPT_HEADER
    return session


class JiraClient:
    """Minimal Jira Cloud REST client built on a pooled requests.Session."""

    def __init__(self, config: Optional[JiraConfig] = None) -> None:
        """Create a client for the given (or resolved) connection settings.

        Parameters:
            config: The connection settings. Resolved from the store when omitted.

        Raises:
            click.ClickException: If the settings cannot be resolved.

        Returns:
            None
        """
        self.config: JiraConfig = config or JiraConfig.resolve()
        self._session: Optional["requests.Session"] = None

    @property
    def session(self) -> "requests.Session":
        """Return the pooled session, building it on first use.

        Parameters:
            None

        Raises:
            None

        Returns:
            requests.Session: The session shared by every request this client makes.
        """
        if self._session is None:
            self._session = _build_session(self.config)
        return self._session

    def get(self, path: str, params: Optional[dict[str, str]] = None) -> dict:
        """Perform a GET request whose response is a JSON object.

        Parameters:
            path: The absolute API path, e.g. ``/rest/api/2/project/ABC``.
            params: The query parameters, already as plain strings.

        Raises:
            click.ClickException: If the request fails, as described in ``request``.

        Returns:
            dict: The decoded JSON body.
        """
        return self.request(path, params)

    def get_list(self, path: str, params: Optional[dict[str, str]] = None) -> list[dict]:
        """Perform a GET request whose response is a JSON array.

        A few Jira endpoints (``/rest/api/3/field`` among them) answer with a bare array instead of
        an object, so they get their own accessor rather than a lie in the return type.

        Parameters:
            path: The absolute API path.
            params: The query parameters, already as plain strings.

        Raises:
            click.ClickException: If the request fails, or the body is not a JSON array.

        Returns:
            list[dict]: The decoded JSON array.
        """
        payload = self.request(path, params)
        if not isinstance(payload, list):
            raise click.ClickException(NOT_A_LIST_MESSAGE.format(path=path))
        return payload

    def request(self, path: str, params: Optional[dict[str, str]] = None) -> Any:
        """Perform a GET request against the Jira instance and return the decoded body.

        Query parameters are passed as a mapping so `requests` does the URL encoding, which is what
        ``curl -G --data-urlencode`` was doing in the shell version.

        Parameters:
            path: The absolute API path, e.g. ``/rest/api/2/project/ABC``.
            params: The query parameters, already as plain strings.

        Raises:
            click.ClickException: If the response carries a handled error status, an unexpected
                status, or a body that is not valid JSON.

        Returns:
            Any: The decoded JSON body, an object or an array depending on the endpoint.
        """
        response = self.session.get(f"{self.config.base_url}{path}", params=params, timeout=DEFAULT_TIMEOUT)
        status: int = response.status_code
        if status in STATUS_MESSAGES:
            raise click.ClickException(STATUS_MESSAGES[status].format(path=path))
        if status >= 400:
            raise click.ClickException(
                UNEXPECTED_STATUS_MESSAGE.format(status=status, path=path, body=response.text)
            )
        try:
            return response.json()
        except ValueError as error:
            raise click.ClickException(INVALID_JSON_MESSAGE.format(path=path, body=response.text)) from error

    def paginate_tokens(
        self, path: str, params: Optional[dict[str, str]] = None, items_key: str = "issues"
    ) -> Iterator[dict]:
        """Yield every item of a token-paginated endpoint, one page at a time.

        The endpoints used here page with ``nextPageToken`` (not ``startAt``) and only send that
        token while more pages remain. Yielding as the pages arrive keeps the accumulation linear:
        the shell version rewrote its whole accumulator file once per page, which is quadratic in
        I/O.

        Parameters:
            path: The absolute API path.
            params: The query parameters shared by every page.
            items_key: The response key holding the page's items.

        Raises:
            click.ClickException: If any page fails, as described in ``get``.

        Returns:
            Iterator[dict]: Every item across every page, in order.
        """
        query: dict[str, str] = dict(params or {})
        query.setdefault(MAX_RESULTS, str(DEFAULT_PAGE_SIZE))
        while True:
            payload: dict = self.get(path, query)
            yield from payload.get(items_key) or []
            token: Optional[str] = payload.get(NEXT_PAGE_TOKEN)
            if not token:
                return
            query[NEXT_PAGE_TOKEN] = token
