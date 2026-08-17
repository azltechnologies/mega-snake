"""Class Module representing a release."""

import dataclasses
from datetime import datetime
import re
import subprocess
from typing import Optional
import mega_snake.light_weight.release_handler as handler
from mega_snake.constants import VERSION_PART_OPT
from mega_snake.util.formatting import ws_info, ws_advice
from mega_snake.util.util import run_operation

# Release tags are 'vX.Y.Z'. The prefix is conventional, and the three numeric components are what
# makes a tag comparable, which is what lets the next one be derived instead of typed by hand.
TAG_PREFIX: str = "v"
VERSION_PATTERN: re.Pattern = re.compile(rf"^{TAG_PREFIX}(\d+)\.(\d+)\.(\d+)$")
# How many pre-release builds of the same version the counter will look through before giving up.
SUFFIX_ATTEMPTS: int = 20


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

    def __new__(cls, input_string: str) -> "Release":
        """Override the __new__ method to handle empty or None input strings gracefully
        by raising a ValueError if the input string is empty.
        """
        if input_string is None or not bool(input_string):
            raise ValueError("Input string is empty. Cannot create Release instance.")
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

    def get_release_tag(self, version_part: str, suffix: Optional[str] = None) -> str:
        """
        Builds the next release tag by incrementing one component of this release's version.

        The new tag is derived from the latest release, so the sequence is continuous and needs no
        input beyond which component to increment. Incrementing a component resets the ones to its
        right, so the result is always greater than what it came from.

        A suffix marks the tag as a pre-release build of that version (``v1.2.4-beta.0``). Since the
        same version can be built several times, the trailing counter grows until the tag is free.

        Args:
            version_part: str - 'patch', 'minor' or 'major'.
            suffix: Optional[str] - Pre-release label to append; no suffix yields a plain version.

        Raises:
            ValueError: If the component is unknown, or the current tag is not a 'vX.Y.Z' version.
            subprocess.SubprocessError: If no free tag is found for the given suffix.

        Returns:
            str: The new tag, as 'vX.Y.Z' or 'vX.Y.Z-<suffix>.N'.
        """
        if version_part not in VERSION_PART_OPT:
            raise ValueError(
                f"Invalid version part: {version_part}; Please enter one of:\n"
                f" {' | '.join(VERSION_PART_OPT.keys())}"
            )
        numbers: list[int] = _parse_version(self.tag_name)
        index: int = VERSION_PART_OPT[version_part]
        numbers[index] += 1
        # Everything to the right of the bumped component restarts, so 1.2.3 with 'minor' is 1.3.0.
        for lower in range(index + 1, len(numbers)):
            numbers[lower] = 0
        base_tag: str = f"{TAG_PREFIX}{'.'.join(str(number) for number in numbers)}"
        if not suffix:
            # Neither a prerelease nor a `--latest=false` release advances the `latest` pointer, so
            # deriving from it twice in a row lands on a tag that already exists. Falling back to the
            # highest version in the repository keeps every release type moving the sequence forward,
            # and cannot produce a tag below one that was already published.
            if _tag_exists(base_tag):
                ws_info(f"Tag {base_tag} already exists; deriving from the highest known version instead.")
                numbers = _highest_version(fallback=numbers)
                numbers[index] += 1
                for lower in range(index + 1, len(numbers)):
                    numbers[lower] = 0
                base_tag = f"{TAG_PREFIX}{'.'.join(str(number) for number in numbers)}"
                if _tag_exists(base_tag):
                    raise subprocess.SubprocessError(
                        f"Tag {base_tag} already exists even though it was derived from the highest "
                        "version in the repository. Fetch the repository and try again."
                    )
            ws_info(f"Tag {base_tag} is available!")
            return base_tag
        for attempt in range(SUFFIX_ATTEMPTS):
            candidate: str = f"{base_tag}-{suffix}.{attempt}"
            if not _tag_exists(candidate):
                ws_info(f"Tag {candidate} is available!")
                return candidate
            ws_info(f"Found an existing tag {candidate}!")
        raise subprocess.SubprocessError(
            f"Could not find a free tag for {base_tag}-{suffix} after {SUFFIX_ATTEMPTS} attempts. Exiting."
        )


def _parse_version(tag_name: str) -> list[int]:
    """
    Splits a 'vX.Y.Z' tag into its three numeric components.

    Args:
        tag_name: str - The tag to parse.

    Raises:
        ValueError: If the tag is not a three-component version tag.

    Returns:
        list[int]: The major, minor and patch numbers, in that order.
    """
    match: Optional[re.Match] = VERSION_PATTERN.match(tag_name)
    if not match:
        raise ValueError(
            f"BAD CONFIG: the latest release is tagged '{tag_name}', which is not a "
            f"'{TAG_PREFIX}X.Y.Z' version, so there is no number to increment. This command only "
            "works on semantic version tags. Publish a release tagged that way first, or create "
            "this one by hand with 'gh release create'."
        )
    return [int(group) for group in match.groups()]


def _highest_version(fallback: list[int]) -> list[int]:
    """
    Finds the highest 'vX.Y.Z' tag in the repository.

    Used when the version derived from the ``latest`` release is already taken, which happens because
    prereleases and ``--latest=false`` releases publish tags without moving that pointer. Scanning
    once for the maximum is what keeps a new tag from landing below one that already exists — walking
    the version upwards instead would stop at the first free number, which can sit under a higher tag.

    Args:
        fallback: list[int] - Version components to return when no version tag is found.

    Raises:
        None

    Returns:
        list[int]: The highest version's components, or ``fallback`` when there is none.
    """
    listed: str = run_operation(
        "git tag --list", "Listing tags to find the highest version", check=False
    ).stdout.strip()
    versions: list[list[int]] = []
    for line in listed.split("\n"):
        match: Optional[re.Match] = VERSION_PATTERN.match(line.strip())
        if match:
            versions.append([int(group) for group in match.groups()])
    if not versions:
        return fallback
    return max(max(versions), fallback)


def _tag_exists(tag_name: str) -> bool:
    """
    Reports whether a tag already exists in the repository.

    Args:
        tag_name: str - The tag to look for.

    Raises:
        None

    Returns:
        bool: True when the tag resolves, False otherwise.
    """
    return (
        run_operation(
            f"git rev-parse --verify --quiet {tag_name}",
            f"Checking whether tag {tag_name} already exists",
            check=False,
        ).returncode
        == 0
    )


def _create_release_list(list_string: str) -> list[Release]:
    """
    Creates a list of Release objects from a string containing tab-separated release records.

    Args:
        list_string: str

    Returns:
        list[Release]
    """
    if list_string is not None and bool(list_string):
        array_of_strings = list_string.split("\n")
        releases: list[Release] = [Release(f"{string}") for string in array_of_strings if string.strip()]
        releases = [x for x in releases if x is not None]
        # printing the releases size
        ws_advice(f"Releases size: {len(releases)}")
        # sorting the releases
        return sorted(releases, key=lambda r: r.published_at, reverse=True)
    return []


def get_latest_release() -> Release:
    """
    Retrieves the latest release from GitHub and retries on failure up to 3 times.

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
