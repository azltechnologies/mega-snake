"""Dataclasses describing the resolved Jira settings and the objects the commands emit.

Every ``to_dict`` here is a public contract: the JSON these commands print is consumed by the Jira
skills and by the documented ``jq`` recipes, so the key names and their order are the ones the shell
scripts produced, not whatever reads best in Python.
"""

from dataclasses import dataclass
from typing import Optional

from mega_snake.constants import JIRA_DOMAIN_KEY, JIRA_EMAIL_KEY
from mega_snake.jira_api.auth import get_atlassian_token
from mega_snake.util.store import Store


@dataclass(frozen=True)
class JiraConfig:
    """Resolved Jira connection settings."""

    domain: str
    email: str
    token: str

    @staticmethod
    def resolve() -> "JiraConfig":
        """Resolve the connection settings through the store precedence chain.

        The domain and the email go through ``environment variable > repo > global``, so
        ``JIRA_DOMAIN``/``JIRA_EMAIL`` keep working exactly as before while the store removes the
        need to export them at all. The token is read from the environment only.

        Parameters:
            None

        Raises:
            click.ClickException: If the domain, the email or the token cannot be resolved.

        Returns:
            JiraConfig: The resolved settings.
        """
        store: Store = Store.get_instance()
        return JiraConfig(
            domain=store.require(JIRA_DOMAIN_KEY),
            email=store.require(JIRA_EMAIL_KEY),
            token=get_atlassian_token(),
        )

    @property
    def base_url(self) -> str:
        """Return the base URL of the Jira Cloud instance.

        Parameters:
            None

        Raises:
            None

        Returns:
            str: The ``https://`` base URL, without a trailing slash.
        """
        return f"https://{self.domain}"


@dataclass(frozen=True)
class Board:
    """A Jira Agile board resolved from a project key."""

    id: int
    cloud_domain: str

    def to_dict(self) -> dict:
        """Render the board as the JSON contract consumed by the Jira skills.

        ``boardId`` is an integer here. The shell version emitted it as a string through ``jq --arg``
        while `getSprintInfo.sh` used it as a number, so the two disagreed; this is the documented
        breaking change that settles it.

        Parameters:
            None

        Raises:
            None

        Returns:
            dict: The board payload, with the same keys the shell script produced.
        """
        return {"boardId": self.id, "cloudDomain": self.cloud_domain}


@dataclass(frozen=True)
class Sprint:
    """An active sprint of a Jira Agile board."""

    id: int
    name: str
    start_date: Optional[str]
    end_date: Optional[str]
    cloud_domain: str
    board_id: int

    @staticmethod
    def from_payload(payload: dict, cloud_domain: str, board_id: int) -> "Sprint":
        """Build a sprint from a raw Agile API entry.

        Parameters:
            payload: One entry of the ``values`` array returned by the sprint endpoint.
            cloud_domain: The Jira Cloud domain, echoed back in the output contract.
            board_id: The board the sprint belongs to.

        Raises:
            None

        Returns:
            Sprint: The parsed sprint.
        """
        return Sprint(
            id=payload.get("id", 0),
            name=payload.get("name", ""),
            start_date=payload.get("startDate"),
            end_date=payload.get("endDate"),
            cloud_domain=cloud_domain,
            board_id=board_id,
        )

    def to_dict(self) -> dict:
        """Render the sprint as the JSON contract consumed by the Jira skills.

        Parameters:
            None

        Raises:
            None

        Returns:
            dict: The sprint payload, with the same keys the shell script produced.
        """
        return {
            "id": self.id,
            "name": self.name,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "cloudDomain": self.cloud_domain,
            "boardId": self.board_id,
        }
