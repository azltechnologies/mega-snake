"""Module for the different PR queries."""

from enum import Enum
import json
from typing import Any, Optional
import jq

LOG_WATCHER_QUERY = '.settings.["logViewer.watch"]'


class LogWatcher(Enum):
    """Enum for the different PR queries."""

    GRADLE_BUILD_NO_TEST = ("GRADLE CLEAN BUILD NO TEST", "logs/clean_build_no_test_*.log")
    GRADLE_BUIL = ("GRADLE CLEAN BUILD", "logs/clean_build_*.log")
    GENERIC = ("GENERIC LOG", "logs/output_*.log")
    JAVA_DEBUG = ("JAVA DEBUG LOG", "logs/java_debug_*.log")
    PYTHON_SNAKE = ("PYTHON SNAKE LOG", "logs/python_snake_*.log")


    def __init__(self, title: str, pattern: str):
        self.title = title
        self.pattern = pattern

    def to_dict(self, working_path: str) -> dict[str, Any]:
        """Converts the enum to a dictionary."""
        return {"title": self.title, "pattern": f"{working_path}/{self.pattern}", "autoScroll": True}

    def add_watcher(self, json_data: dict[str, Any], working_path: str) -> Optional[dict[str, Any]]:
        """Adds the query to the workspace settings."""
        json_input = json_data
        result = jq.compile(LOG_WATCHER_QUERY).input(json_data).first()
        search_query: str = f'{LOG_WATCHER_QUERY}| map(select(.title == "{self.title}"))'
        if result:
            length_query: str = f"{search_query} | length"
            result = jq.compile(length_query).input(json_data).first()
            if result == 1:
                return None
            if result > 1:
                delete_query = search_query.replace("==", "!=")
                result = jq.compile(delete_query).input(json_data).first()
                jq_query = f"{LOG_WATCHER_QUERY} = {json.dumps(result)}"
                json_input = jq.compile(jq_query).input(json_input).first()
        jq_query = f"{LOG_WATCHER_QUERY} += [{json.dumps(self.to_dict(working_path))}]"
        return jq.compile(jq_query).input(json_input).first()
