"""Root-level fixtures shared by the whole test suite.

The autouse fixture below strips every environment variable the store (`mega_snake.util.store`) or
the Jira auth module (`mega_snake.jira_api.auth`) can read, before each test runs. Without it, a
developer's real shell -- `JIRA_API_TOKEN`, `JIRA_DOMAIN`, `JIRA_MCP_TOKEN`, and so on -- leaks into
any test that does not enumerate that exact variable by hand, which is exactly how two tests once
passed in CI (a clean environment) while failing on a real machine:
`test_resolve_fails_when_the_token_is_missing` (`jira_api/test_models.py`) picked up the real
`JIRA_MCP_TOKEN` as a deprecated-fallback token instead of raising, and
`test_unset_removes_a_secret_shaped_key_left_over_from_a_manual_edit` (`util/test_store.py`) resolved
`jira.api_token` from the real `JIRA_API_TOKEN` instead of `None` -- the environment always outranks
every store scope (§4.4), so it does not matter what `unset` did to the file.

Both failures trace back to fixtures that cleared an *enumerated* list of variables by hand
(`workspace` in `test_store.py`, `jira_workspace` in `jira_api/conftest.py`): correct for the
variables someone remembered to list, silent for anything added later. Deriving
`ISOLATED_ENV_VARS` from the same constants the store and the auth module read is what keeps a new
key covered automatically instead of by omission.

A test that wants one of these variables set (`jira_workspace` injecting the double token, a test
of the deprecated-fallback warning) does so explicitly, with `monkeypatch.setenv`, *after* this
fixture has already cleared it -- that is deliberate injection, not a leak.
"""

from typing import Iterator

import pytest

from mega_snake.constants import (
    JIRA_BOARD_ID_KEY,
    JIRA_DEPRECATED_TOKEN_ENV,
    JIRA_DOMAIN_KEY,
    JIRA_EMAIL_KEY,
    JIRA_PROJECT_KEY_KEY,
    JIRA_SPRINT_FIELD_KEY,
    JIRA_STORY_POINTS_FIELD_KEY,
    JIRA_TOKEN_ENV,
)
from mega_snake.util.store import env_var_name

# Every store key that has a documented environment-variable override (env > repo > global, §4.4).
KNOWN_STORE_KEYS: tuple[str, ...] = (
    JIRA_DOMAIN_KEY,
    JIRA_EMAIL_KEY,
    JIRA_PROJECT_KEY_KEY,
    JIRA_BOARD_ID_KEY,
    JIRA_STORY_POINTS_FIELD_KEY,
    JIRA_SPRINT_FIELD_KEY,
)
# Token variables read from the environment only, never through the store (§4.4: secrets never go in).
ENV_ONLY_VARS: tuple[str, ...] = (JIRA_TOKEN_ENV, JIRA_DEPRECATED_TOKEN_ENV)
ISOLATED_ENV_VARS: tuple[str, ...] = tuple(env_var_name(key) for key in KNOWN_STORE_KEYS) + ENV_ONLY_VARS


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Strip every variable the store or the Jira auth module can read, before each test.

    Parameters:
        monkeypatch: The per-test monkeypatch fixture.

    Raises:
        None

    Yields:
        None
    """
    for variable in ISOLATED_ENV_VARS:
        monkeypatch.delenv(variable, raising=False)
    yield
