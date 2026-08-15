"""Tests for the resolved Jira settings dataclass."""

from pathlib import Path

import click
import pytest

from mega_snake.constants import JIRA_DOMAIN_KEY, JIRA_EMAIL_KEY, JIRA_TOKEN_ENV
from mega_snake.jira_api.models import JiraConfig
from mega_snake.util.store import Store

from tests.jira_api.jira_doubles import DOMAIN, EMAIL, TOKEN


def test_resolve_reads_the_domain_and_email_from_the_store(jira_workspace: Path) -> None:
    """The two identifiers come from the store; only the credential comes from the environment."""
    assert jira_workspace.exists()

    assert JiraConfig.resolve() == JiraConfig(domain=DOMAIN, email=EMAIL, token=TOKEN)


def test_resolve_lets_the_environment_override_the_store(
    jira_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exported variable still wins, which is what keeps the pre-store workflows working."""
    assert jira_workspace.exists()
    monkeypatch.setenv("JIRA_DOMAIN", "other.atlassian.net")

    assert JiraConfig.resolve().domain == "other.atlassian.net"


def test_resolve_fails_when_the_token_is_missing(jira_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing credential is an error, not an empty Basic header sent to Jira."""
    assert jira_workspace.exists()
    monkeypatch.delenv(JIRA_TOKEN_ENV, raising=False)

    with pytest.raises(click.ClickException) as error:
        JiraConfig.resolve()

    assert JIRA_TOKEN_ENV in str(error.value)


@pytest.mark.parametrize("missing_key", [JIRA_DOMAIN_KEY, JIRA_EMAIL_KEY])
def test_resolve_names_the_command_that_sets_a_missing_setting(jira_workspace: Path, missing_key: str) -> None:
    """Each missing identifier points at the exact `config set` that would define it."""
    assert jira_workspace.exists()
    Store.get_instance().unset(missing_key)

    with pytest.raises(click.ClickException) as error:
        JiraConfig.resolve()

    assert f"config set {missing_key} <value>" in str(error.value)


def test_base_url_is_https_without_a_trailing_slash() -> None:
    """Paths are concatenated straight onto this, so a trailing slash would double up."""
    assert JiraConfig(domain=DOMAIN, email=EMAIL, token=TOKEN).base_url == f"https://{DOMAIN}"
