"""Tests for the Atlassian Authorization header builder."""

import base64
from pathlib import Path

import click
import pytest

from mega_snake.constants import JIRA_DEPRECATED_TOKEN_ENV, JIRA_EMAIL_KEY, JIRA_TOKEN_ENV
from mega_snake.jira_api.auth import AUTHORIZATION_HEADER, build_basic_header, get_atlassian_token
from mega_snake.jira_api.models import JiraConfig
from mega_snake.util.store import Store

from tests.jira_api.jira_doubles import EMAIL, TOKEN


def test_atlassian_header_is_exact_basic_base64(jira_workspace: Path) -> None:
    """The header is compared in full against a base64 computed by hand.

    A containment check on "Basic" would pass for any malformed header that merely starts the same
    way, which is exactly the failure mode worth catching here.
    """
    assert jira_workspace.exists()
    expected = base64.b64encode(f"{EMAIL}:{TOKEN}".encode("utf-8")).decode("ascii")

    # Composed through `JiraConfig.resolve()`, which is what `client._build_session` actually calls:
    # hand-composing the email/token pair here would let the two drift apart without a test noticing.
    config = JiraConfig.resolve()

    assert build_basic_header(config.email, config.token) == {AUTHORIZATION_HEADER: f"Basic {expected}"}


def test_atlassian_header_has_no_trailing_newline(jira_workspace: Path) -> None:
    """`base64 -w 0` was a GNU-only flag; the portable encoder must not reintroduce line breaks.

    A long credential is used on purpose: the default `base64` line wrap kicks in past 76 characters,
    so a short one would pass even with wrapping enabled.
    """
    assert jira_workspace.exists()
    header = build_basic_header("a-very-long-account-address@example.com", "x" * 120)[AUTHORIZATION_HEADER]

    assert "\n" not in header
    assert header == header.strip()


def test_missing_token_raises_click_exception_and_prints_nothing_to_stdout(
    jira_workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The shell version printed its errors to stdout and still returned 1.

    `HEADER=$(get_auth_header atlassian)` therefore captured "Error: ..." and sent it to the API as
    a header. Asserting stdout is *empty* (by equality, not by containment) is what pins that.
    """
    assert jira_workspace.exists()
    monkeypatch.delenv(JIRA_TOKEN_ENV, raising=False)
    monkeypatch.delenv(JIRA_DEPRECATED_TOKEN_ENV, raising=False)

    with pytest.raises(click.ClickException):
        get_atlassian_token()

    assert capsys.readouterr().out == ""


def test_deprecated_token_still_works_and_warns_on_stderr(
    jira_workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """JIRA_MCP_TOKEN keeps working for one release, and the warning must not pollute stdout."""
    assert jira_workspace.exists()
    monkeypatch.delenv(JIRA_TOKEN_ENV, raising=False)
    monkeypatch.setenv(JIRA_DEPRECATED_TOKEN_ENV, "legacy-token")

    assert get_atlassian_token() == "legacy-token"

    captured = capsys.readouterr()
    assert captured.out == ""
    assert JIRA_TOKEN_ENV in captured.err


def test_current_token_wins_over_the_deprecated_one(
    jira_workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """With both set there is nothing to deprecate, so no warning is emitted either."""
    assert jira_workspace.exists()
    monkeypatch.setenv(JIRA_TOKEN_ENV, "current-token")
    monkeypatch.setenv(JIRA_DEPRECATED_TOKEN_ENV, "legacy-token")

    assert get_atlassian_token() == "current-token"
    assert capsys.readouterr().err == ""


def test_missing_email_names_the_command_that_sets_it(jira_workspace: Path) -> None:
    """The email comes from the store, so its error must point at `config set`."""
    assert jira_workspace.exists()
    Store.get_instance().unset(JIRA_EMAIL_KEY)

    with pytest.raises(click.ClickException) as error:
        Store.get_instance().require(JIRA_EMAIL_KEY)

    assert "config set jira.email" in str(error.value)
