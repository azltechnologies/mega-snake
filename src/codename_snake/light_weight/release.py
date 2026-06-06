"""Class Module representing a release."""

import dataclasses
from datetime import datetime
import subprocess
from typing import Optional
import codename_snake.light_weight.release_handler as handler
from codename_snake.util.formatting import ws_info, ws_advice


@dataclasses.dataclass
class Release:
    """
    Class containing a named set of properties

    Properties:
        title: str
        release_type: str
        tag_name: str
        date_str: str
        published_at: datetime
        commit: str

    Methods:
        get_release_tag: str
    """

    title: str
    release_type: str
    tag_name: str
    date_str: str
    published_at: datetime
    commit: str

    def __new__(cls, input_string: str) -> "Release | None":
        """Return None when the input string is empty; otherwise create a new Release instance."""
        if input_string is None or not bool(input_string):
            return None
        return super().__new__(cls)

    def __init__(self, input_string: str) -> None:
        """Parse a tab-separated release record and populate the instance attributes."""
        if input_string is not None and bool(input_string):
            result = input_string.split("\t")
            self.title = result[0]
            self.release_type = result[1]
            self.tag_name = result[2]
            self.date_str = result[3]
            self.published_at = datetime.strptime(self.date_str, "%Y-%m-%dT%H:%M:%SZ")
            if self.release_type != "Draft":
                self.commit = handler.get_commit_from_release(self.tag_name)

    def get_release_tag(self, suffix: str) -> str:
        """
        Returns the tag name of the release

        Args:
            release: Release

        Returns:
            str
        """
        tag_name: str = self.tag_name
        position: int = tag_name.find("-")
        if position != -1:
            tag_name = tag_name[:position]
        attemps: int = 20
        new_tag_name: str
        i: int = 0
        for shot in range(1, attemps + 1):
            try:
                new_tag_name = f"{tag_name}-{suffix}.{i}"
                com: str = f"git rev-parse {new_tag_name} 2>&1"
                subprocess.run(com, shell=True, check=True, capture_output=True, text=True)
                ws_info(f"Found an existing tag {new_tag_name} at attempt {shot}!")
            except subprocess.CalledProcessError:
                # If the tag does not exist, this exception will be caught
                ws_info(f"Tag {new_tag_name} is available!")
                return new_tag_name  # Return the first non-existing tag
            i += 1
        # if no tag was found, throw error
        raise subprocess.SubprocessError(
            f"Could not find a non-existing tag for {tag_name}-{suffix} after {attemps} attempts. Exiting."
        )


def _create_release_list(list_string: str) -> list[Release]:
    """
    Converts a string into a list of Release instances

    Args:
        list_string: str

    Returns:
        List[Release]
    """
    if list_string is not None and bool(list_string):
        array_of_strings = list_string.split("\n")
        releases: list[Release] = [Release(f"{string}") for string in array_of_strings]
        releases = [x for x in releases if x is not None]
        # printing the releases size
        ws_advice(f"Releases size: {len(releases)}")
        # sorting the releases
        return sorted(releases, key=lambda r: r.published_at, reverse=True)
    return []


def get_latest_release() -> Release:
    """
    Retrieves the latest release from GitHub.

    Returns:
        Release
    """
    limit: int = 30
    lastest_release: Optional[Release] = None
    while lastest_release is None and limit < 200:
        result: subprocess.CompletedProcess[str] = handler.get_release_list(limit)

        release_list: list[Release] = _create_release_list(f"{result.stdout}")
        try:
            lastest_release = [x for x in release_list if x.release_type == "Latest"][0]
        except IndexError:
            limit += 30
            ws_info(f"Could not find the latest release. Increasing limit to {limit} and retrying.")
    if not lastest_release:
        raise ValueError("Could not find the latest release. Please check your GitHub repository settings.")
    return lastest_release
