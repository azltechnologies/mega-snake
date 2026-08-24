"""Build the Authorization header for the services the Jira workflow talks to.

Replaces `get_auth_header.sh`, and fixes three defects it carried:

- The shell version read ``JIRA_MCP_TOKEN`` while the other three scripts read ``JIRA_API_TOKEN``,
  so the same service needed two tokens and nobody knew which one to set. Everything now reads
  ``JIRA_API_TOKEN``; ``JIRA_MCP_TOKEN`` still works as a deprecated fallback and is announced.
- It printed its errors to **stdout** and still returned 1, so ``HEADER=$(get_auth_header atlassian)``
  happily captured ``"Error: ..."`` and sent it to the API as a header. Errors are raised as
  ``click.ClickException`` here, which Click writes to stderr with exit code 1.
- It encoded with ``base64 -w 0``, a GNU-only flag that fails on macOS. ``base64.b64encode`` is
  portable by construction and produces no line breaks to strip.
"""

import base64
import os
from typing import Optional

import click

from mega_snake.constants import (
    GITHUB_TOKEN_ENV,
    JIRA_DEPRECATED_TOKEN_ENV,
    JIRA_EMAIL_KEY,
    JIRA_TOKEN_ENV,
)
from mega_snake.util.formatting import ws_warning
from mega_snake.util.store import Store

APP_ATLASSIAN: str = "atlassian"
APP_GITHUB: str = "github"
SUPPORTED_APPS: tuple[str, ...] = (APP_ATLASSIAN, APP_GITHUB)

AUTHORIZATION_HEADER: str = "Authorization"

UNSUPPORTED_APP_MESSAGE: str = "Unsupported app '{app}'. Supported apps are: {apps}."
MISSING_TOKEN_MESSAGE: str = (
    "Environment variable {env_var} is not set. Create an Atlassian API token at "
    "https://id.atlassian.com/manage-profile/security/api-tokens and export it."
)
MISSING_GITHUB_TOKEN_MESSAGE: str = f"Environment variable {GITHUB_TOKEN_ENV} is not set."
DEPRECATED_TOKEN_MESSAGE: str = (
    f"{JIRA_DEPRECATED_TOKEN_ENV} is deprecated and will be removed in the next minor release. "
    f"Export {JIRA_TOKEN_ENV} instead."
)


def get_atlassian_token() -> str:
    """Resolve the Atlassian API token from the environment.

    Tokens are never read from the persistent store: a plaintext credential inside a state file is
    worse than an environment variable because it persists and is forgotten.

    Parameters:
        None

    Raises:
        click.ClickException: If neither the current nor the deprecated variable is set.

    Returns:
        str: The API token.
    """
    token: Optional[str] = os.environ.get(JIRA_TOKEN_ENV)
    if token:
        return token
    deprecated_token: Optional[str] = os.environ.get(JIRA_DEPRECATED_TOKEN_ENV)
    if deprecated_token:
        # `ws_warning`, like every `ws_*` helper, writes to stderr, so it cannot contaminate the
        # stdout that `$(mgsnake jira-board KEY)` captures. This module used to route around them
        # with a private click.echo helper, from back when they printed to stdout.
        ws_warning(DEPRECATED_TOKEN_MESSAGE)
        return deprecated_token
    raise click.ClickException(MISSING_TOKEN_MESSAGE.format(env_var=JIRA_TOKEN_ENV))


def build_basic_header(email: str, token: str) -> dict[str, str]:
    """Build a HTTP Basic Authorization header from an email/token pair.

    Parameters:
        email: The Atlassian account email.
        token: The Atlassian API token.

    Raises:
        None

    Returns:
        dict[str, str]: A single-entry header mapping.
    """
    encoded: str = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    return {AUTHORIZATION_HEADER: f"Basic {encoded}"}


def get_auth_header(app: str) -> dict[str, str]:
    """Build the Authorization header for the given application.

    Parameters:
        app: One of ``SUPPORTED_APPS``.

    Raises:
        click.ClickException: If the app is unsupported, or a required credential is missing.

    Returns:
        dict[str, str]: The Authorization header for the requested application.
    """
    if app == APP_ATLASSIAN:
        email: str = Store.get_instance().require(JIRA_EMAIL_KEY)
        return build_basic_header(email, get_atlassian_token())
    if app == APP_GITHUB:
        token: Optional[str] = os.environ.get(GITHUB_TOKEN_ENV)
        if not token:
            raise click.ClickException(MISSING_GITHUB_TOKEN_MESSAGE)
        return {AUTHORIZATION_HEADER: f"Bearer {token}"}
    raise click.ClickException(UNSUPPORTED_APP_MESSAGE.format(app=app, apps=", ".join(SUPPORTED_APPS)))
