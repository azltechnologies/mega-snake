"""Shared fixtures for the Jira module tests."""

from pathlib import Path

import pytest

from mega_snake.constants import JIRA_DOMAIN_KEY, JIRA_EMAIL_KEY, JIRA_PROJECT_KEY_KEY, JIRA_TOKEN_ENV
from mega_snake.util.store import Store, env_var_name

from tests.jira_api.jira_doubles import DOMAIN, EMAIL, PROJECT_KEY, TOKEN

STORE_KEYS = (JIRA_DOMAIN_KEY, JIRA_EMAIL_KEY, JIRA_PROJECT_KEY_KEY, "jira.board_id")


@pytest.fixture(name="jira_workspace")
def jira_workspace_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated home, a git repository, a fresh store and a configured Jira account."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    for key in STORE_KEYS:
        monkeypatch.delenv(env_var_name(key), raising=False)
    monkeypatch.setenv(JIRA_TOKEN_ENV, TOKEN)
    monkeypatch.chdir(repo)
    Store.reset_instance()
    store = Store.get_instance()
    store.set(JIRA_DOMAIN_KEY, DOMAIN)
    store.set(JIRA_EMAIL_KEY, EMAIL)
    store.set(JIRA_PROJECT_KEY_KEY, PROJECT_KEY)
    yield repo
    Store.reset_instance()
