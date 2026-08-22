"""Tests for the Jira/GitHub Authorization header builder."""

import base64
from pathlib import Path

import click
import pytest

from mega_snake.constants import GITHUB_TOKEN_ENV, JIRA_DEPRECATED_TOKEN_ENV, JIRA_TOKEN_ENV
from mega_snake.jira_api.auth import (
    APP_ATLASSIAN,
    APP_GITHUB,
    AUTHORIZATION_HEADER,
    SUPPORTED_APPS,
    build_basic_header,
    get_atlassian_token,
    get_auth_header,
)

from tests.jira_api.jira_doubles import EMAIL, TOKEN


def test_atlassian_header_is_exact_basic_base64(jira_workspace: Path) -> None:
    """The header is compared in full against a base64 computed by hand.

    A containment check on "Basic" would pass for any malformed header that merely starts the same
    way, which is exactly the failure mode worth catching here.
    """
    assert jira_workspace.exists()
    expected = base64.b64encode(f"{EMAIL}:{TOKEN}".encode("utf-8")).decode("ascii")

    assert get_auth_header(APP_ATLASSIAN) == {AUTHORIZATION_HEADER: f"Basic {expected}"}


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
        get_auth_header(APP_ATLASSIAN)

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


def test_github_header_is_a_bearer_token(jira_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The GitHub branch is unchanged from the shell version, minus the stdout bug."""
    assert jira_workspace.exists()
    monkeypatch.setenv(GITHUB_TOKEN_ENV, "gh-token")

    assert get_auth_header(APP_GITHUB) == {AUTHORIZATION_HEADER: "Bearer gh-token"}


def test_missing_github_token_raises(jira_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing GitHub token fails instead of building a header that says "Bearer"."""
    assert jira_workspace.exists()
    monkeypatch.delenv(GITHUB_TOKEN_ENV, raising=False)

    with pytest.raises(click.ClickException) as error:
        get_auth_header(APP_GITHUB)

    assert GITHUB_TOKEN_ENV in str(error.value)


def test_unsupported_app_lists_the_supported_ones(jira_workspace: Path) -> None:
    """A typo has to say what the valid answers are."""
    assert jira_workspace.exists()

    with pytest.raises(click.ClickException) as error:
        get_auth_header("bitbucket")

    for app in SUPPORTED_APPS:
        assert app in str(error.value)


def test_missing_email_names_the_command_that_sets_it(jira_workspace: Path) -> None:
    """The email now comes from the store, so its error must point at `config set`."""
    assert jira_workspace.exists()
    from mega_snake.util.store import Store  # local import keeps the module list above tidy

    Store.get_instance().unset("jira.email")

    with pytest.raises(click.ClickException) as error:
        get_auth_header(APP_ATLASSIAN)

    assert "config set jira.email" in str(error.value)
