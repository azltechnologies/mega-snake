"""Module for the different PR queries."""

from enum import Enum
import json
from typing import Any, Optional
import jq

GH_PR_QUERY = '.settings.["githubPullRequests.queries"]'


class PrQueries(Enum):
    """Enum for the different PR queries."""

    MY_CLOSED_PRS = ("My Closed PRs", "is:closed author:${user}")
    WAITING_FOR_REVIEW = ("Waiting for My Review", "is:open review-requested:${user}")
    ASSIGNED_TO_ME = ("Assigned to Me", "is:open assignee:${user}")
    CREATED_BY_ME = ("Created by Me", "is:open author:${user}")

    def __init__(self, label: str, query: str):
        self.label = label
        self.query = query

    def to_dict(self) -> dict[str, str]:
        """Converts the enum to a dictionary."""
        return {"label": self.label, "query": self.query}

    def add_query(self, json_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Adds the query to the workspace settings."""
        json_input = json_data
        result = jq.compile(GH_PR_QUERY).input(json_data).first()
        search_query: str = f'{GH_PR_QUERY}| map(select(.label == "{self.label}"))'
        if result:
            length_query: str = f"{search_query} | length"
            result = jq.compile(length_query).input(json_data).first()
            if result == 1:
                return None
            if result > 1:
                delete_query = search_query.replace("==", "!=")
                result = jq.compile(delete_query).input(json_data).first()
                jq_query = f"{GH_PR_QUERY} = {json.dumps(result)}"
                json_input = jq.compile(jq_query).input(json_input).first()
        jq_query = f"{GH_PR_QUERY} += [{json.dumps(self.to_dict())}]"
        return jq.compile(jq_query).input(json_input).first()
