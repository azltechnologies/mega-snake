"""Module for the different PR queries."""

from enum import Enum
import json
from typing import Any, Optional
import jq
from mega_snake.config_environment.models.vscode_input import VscodeInput

LOG_WATCHER_QUERY = '.settings.["logViewer.watch"]'
SUBSTITUTE_LOG_DATE_TAG = "_*.log"
SUBSTITUTE_LOGFILE_TAG = "[SUBS_LOGFILE]"
REDIRECT_STR = f"> {SUBSTITUTE_LOGFILE_TAG}.log' 2>&1"


class LogWatcher(Enum):
    """Enum for the different PR queries."""

    GRADLE_BUILD_NO_TEST = ("GRADLE CLEAN BUILD NO TEST", f"logs/clean_build_no_test{SUBSTITUTE_LOG_DATE_TAG}")
    GRADLE_BUILD = ("GRADLE CLEAN BUILD", f"logs/clean_build{SUBSTITUTE_LOG_DATE_TAG}")
    GENERIC = ("GENERIC LOG", f"logs/output{SUBSTITUTE_LOG_DATE_TAG}")
    JAVA_DEBUG = ("JAVA DEBUG LOG", f"logs/java_debug{SUBSTITUTE_LOG_DATE_TAG}")
    PYTHON_SNAKE = ("PYTHON SNAKE LOG", f"logs/python_snake{SUBSTITUTE_LOG_DATE_TAG}")
    MAVEN_CLEAN_INSTALL = ("MAVEN CLEAN INSTALL", f"logs/maven_clean_install{SUBSTITUTE_LOG_DATE_TAG}")
    MAVEN_TEST = ("MAVEN TEST", f"logs/maven_test{SUBSTITUTE_LOG_DATE_TAG}")
    MAVEN_VERIFY = ("MAVEN VERIFY", f"logs/maven_verify{SUBSTITUTE_LOG_DATE_TAG}")
    MAVEN_DEPENDENCY_TREE = ("MAVEN DEPENDENCY TREE", f"logs/maven_dependency_tree{SUBSTITUTE_LOG_DATE_TAG}")
    MAVEN_SPRING_BOOT = ("MAVEN SPRING BOOT RUN", f"logs/maven_spring_boot{SUBSTITUTE_LOG_DATE_TAG}")

    def __init__(self, title: str, pattern: str) -> None:
        """Initialize with a display title and glob pattern for the log file."""
        self.title = title
        self.pattern = pattern

    def to_dict(self, working_path: str) -> dict[str, Any]:
        """Converts the enum to a dictionary."""
        return {"title": self.title, "pattern": f"{working_path}/{self.pattern}", "autoScroll": True}

    def get_pattern_date(self, working_path: str) -> str:
        """
        Returns the pattern with the date suffix.

        Args:
            working_path (str): The working path to append to the pattern
        """
        # Replace the date tag with current timestamp
        log_path = self.pattern.replace(SUBSTITUTE_LOG_DATE_TAG, f"_{VscodeInput.TODAY_TIMESTAMP.get_input_call()}")

        # Construct full path
        full_path = f"'{working_path}/{log_path}"

        # Create redirect string with the full path
        return REDIRECT_STR.replace(SUBSTITUTE_LOGFILE_TAG, full_path)

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
