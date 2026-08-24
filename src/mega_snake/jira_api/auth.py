"""Build the Authorization header for the Atlassian API the Jira workflow talks to.

Replaces the credential-handling half of `get_auth_header.sh`, and fixes two defects it carried:

- The shell version read ``JIRA_MCP_TOKEN`` while the other three scripts read ``JIRA_API_TOKEN``,
  so the same service needed two tokens and nobody knew which one to set. Everything now reads
  ``JIRA_API_TOKEN``; ``JIRA_MCP_TOKEN`` still works as a deprecated fallback and is announced.
- It encoded with ``base64 -w 0``, a GNU-only flag that fails on macOS. ``base64.b64encode`` is
  portable by construction and produces no line breaks to strip.

The shell script's GitHub branch and its app-dispatch wrapper (``get_auth_header <app>``) have no
replacement here: no command in this package ever built a GitHub Authorization header, and email/token
resolution for Atlassian happens directly in ``models.py`` (``JiraConfig.resolve``), which calls
``get_atlassian_token`` and ``build_basic_header`` below without going through a dispatcher.
"""

import base64
import os
from typing import Optional

import click

from mega_snake.constants import JIRA_DEPRECATED_TOKEN_ENV, JIRA_TOKEN_ENV
from mega_snake.util.formatting import ws_warning

AUTHORIZATION_HEADER: str = "Authorization"

MISSING_TOKEN_MESSAGE: str = (
    "Environment variable {env_var} is not set. Create an Atlassian API token at "
    "https://id.atlassian.com/manage-profile/security/api-tokens and export it."
)
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
