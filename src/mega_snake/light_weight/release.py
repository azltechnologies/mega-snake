"""Class Module representing a release."""

import dataclasses
from datetime import datetime
import re
import subprocess
from typing import Optional
import click
import mega_snake.light_weight.release_handler as handler
from mega_snake.constants import VERSION_PART_OPT
from mega_snake.util.formatting import ws_info, ws_advice
from mega_snake.util.props import get_property
from mega_snake.util.util import run_operation

# A tag pattern describes the project's release tags with `$1`, `$2` and `$3` standing for the major,
# minor and patch numbers; everything else is literal, and `$$` is a literal `$`. One string therefore
# both parses an existing tag and builds the next one, so the two can never disagree.
#
# The three placeholders are mandatory because `--version-part` names exactly three components: with a
# fourth there would be no name to address it by, and with two 'patch' would refer to nothing.
#
# This default is the hardcoded first layer of the configuration stack (§4.2). The properties
# file is consulted for an override only, which is why a missing key is a normal outcome and not an
# error.
DEFAULT_TAG_PATTERN: str = "v$1.$2.$3"
# Optional override key. Absent by default; a project that wants a different scheme adds it.
TAG_PATTERN_PROPERTY: str = "release_tag_pattern"
# Matches `$$` first so an escaped dollar is never mistaken for a placeholder.
PLACEHOLDER_PATTERN: re.Pattern = re.compile(r"\$\$|\$([123])")
REQUIRED_PLACEHOLDERS: tuple[str, ...] = ("$1", "$2", "$3")
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

    def get_release_tag(
        self, version_part: str, suffix: Optional[str] = None, tag_pattern: str = DEFAULT_TAG_PATTERN
    ) -> str:
        """
        Builds the next release tag by incrementing one component of this release's version.

        The new tag is derived from the tags the repository already has, so the sequence is
        continuous and needs no input beyond which component to increment. Incrementing a component
        resets the ones to its right, so the result is always greater than what it came from.

        A suffix marks the tag as a pre-release build of that version (``v1.2.4-beta.0``). Since the
        same version can be built several times, the trailing counter grows until the tag is free.

        Args:
            version_part: str - 'patch', 'minor' or 'major'.
            suffix: Optional[str] - Pre-release label to append; no suffix yields a plain version.
            tag_pattern: str - Pattern describing the project's tags, with `$1`, `$2` and `$3`.

        Raises:
            ValueError: If the version component is unknown.
            click.ClickException: If the pattern is unusable or does not match the latest release.
            subprocess.SubprocessError: If no free tag is found for the given suffix.

        Returns:
            str: The new tag, rendered with the pattern, optionally carrying '-<suffix>.N'.
        """
        if version_part not in VERSION_PART_OPT:
            raise ValueError(
                f"Invalid version part: {version_part}; Please enter one of:\n {' | '.join(VERSION_PART_OPT.keys())}"
            )
        # Validating against the latest release doubles as parsing it: the pattern has to describe
        # this repository's tags for the derivation below to mean anything.
        expression: re.Pattern = validate_tag_pattern(tag_pattern, self.tag_name)
        latest_numbers: list[int] = [int(group) for group in expression.match(self.tag_name).groups()]  # type: ignore[union-attr]
        # Neither a prerelease nor a `--latest=false` release advances the `latest` pointer, so that
        # pointer alone is not enough to know where the sequence stands: a higher tag can already
        # exist beside it. Deriving from the highest known version *unconditionally* is what makes
        # "a new tag never lands below one already published" hold in every case, not only when the
        # derived tag happens to collide.
        numbers: list[int] = _highest_version(expression, fallback=latest_numbers)
        index: int = VERSION_PART_OPT[version_part]
        numbers[index] += 1
        # Everything to the right of the bumped component restarts, so 1.2.3 with 'minor' is 1.3.0.
        for lower in range(index + 1, len(numbers)):
            numbers[lower] = 0
        base_tag: str = build_tag(tag_pattern, numbers)
        if not suffix:
            # Guards against a stale local view: the tag list is read from the local repository, so a
            # tag fetched by nobody would not have been counted above.
            if _tag_exists(base_tag):
                raise subprocess.SubprocessError(
                    f"Tag {base_tag} already exists even though it was derived from the highest "
                    "version known locally. Fetch the repository (git fetch --tags) and try again."
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


def resolve_tag_pattern(tag_pattern: Optional[str] = None) -> str:
    """
    Decides which tag pattern to use, from the most specific source available.

    Precedence is explicit and lives in one place: what the invocation asked for wins, then whatever
    the project configured, then the default. Keeping the lookup here is what lets a future settings
    layer be added without touching the command or the derivation.

    Args:
        tag_pattern: Optional[str] - The pattern given on the command line, when any.

    Raises:
        None

    Returns:
        str: The tag pattern to use.
    """
    if tag_pattern:
        return tag_pattern
    try:
        configured: str = get_property(TAG_PATTERN_PROPERTY)
    except (KeyError, RuntimeError):
        # Absent key, or no properties at all in light-weight mode: neither is an error, both just
        # mean the project did not configure a pattern.
        return DEFAULT_TAG_PATTERN
    return configured or DEFAULT_TAG_PATTERN


def compile_tag_pattern(pattern: str) -> re.Pattern:
    """
    Turns a tag pattern into the regular expression that recognises those tags.

    Everything outside a placeholder is escaped, so the pattern describes the tag format literally
    rather than acting as a loose regular expression: a `.` in the pattern matches a dot, not any
    character. That is what makes validating the pattern against the repository meaningful.

    Args:
        pattern: str - The tag pattern, e.g. ``v$1.$2.$3``.

    Raises:
        None

    Returns:
        re.Pattern: An anchored expression capturing the three numeric components.
    """
    expression: list[str] = []
    position: int = 0
    for match in PLACEHOLDER_PATTERN.finditer(pattern):
        expression.append(re.escape(pattern[position : match.start()]))
        expression.append(re.escape("$") if match.group() == "$$" else r"(\d+)")
        position = match.end()
    expression.append(re.escape(pattern[position:]))
    return re.compile(f"^{''.join(expression)}$")


def build_tag(pattern: str, numbers: list[int]) -> str:
    """
    Renders a tag from a pattern and its three version numbers.

    The inverse of :func:`compile_tag_pattern`: both walk the same placeholders, so a tag built here
    is always one the compiled expression recognises.

    Args:
        pattern: str - The tag pattern.
        numbers: list[int] - The major, minor and patch numbers, in that order.

    Raises:
        None

    Returns:
        str: The rendered tag.
    """
    rendered: list[str] = []
    position: int = 0
    for match in PLACEHOLDER_PATTERN.finditer(pattern):
        rendered.append(pattern[position : match.start()])
        rendered.append("$" if match.group() == "$$" else str(numbers[int(match.group(1)) - 1]))
        position = match.end()
    rendered.append(pattern[position:])
    return "".join(rendered)


def validate_tag_pattern(pattern: str, latest_tag: str) -> re.Pattern:
    """
    Checks a tag pattern is usable, and that it actually describes this repository's tags.

    Validating against the latest release is what turns a typo into an immediate, explicit error:
    a pattern that parses nothing would otherwise surface much later, as a derivation that cannot
    find any version to build on.

    Args:
        pattern: str - The tag pattern to validate.
        latest_tag: str - The tag of the repository's latest release.

    Raises:
        click.ClickException: If the pattern lacks a placeholder or does not match the latest tag.

    Returns:
        re.Pattern: The compiled expression for the validated pattern.
    """
    missing: list[str] = [holder for holder in REQUIRED_PLACEHOLDERS if holder not in pattern]
    if missing:
        raise click.ClickException(
            f"BAD REQUEST: the tag pattern '{pattern}' is missing {', '.join(missing)}. "
            f"A pattern must contain {', '.join(REQUIRED_PLACEHOLDERS)}, standing for the major, "
            "minor and patch numbers, because those are the components --version-part can increment."
        )
    expression: re.Pattern = compile_tag_pattern(pattern)
    if not expression.match(latest_tag):
        raise click.ClickException(
            f"BAD REQUEST: the tag pattern '{pattern}' does not match the latest release tag "
            f"'{latest_tag}', so there is no version to derive the next one from. Adjust the pattern "
            "so it describes the tags this repository already uses."
        )
    return expression


def _highest_version(expression: re.Pattern, fallback: list[int]) -> list[int]:
    """
    Finds the highest version among the repository's tags that match the release tag pattern.

    Consulted on **every** derivation, not only when a tag collides. Prereleases and
    ``--latest=false`` releases publish tags without moving the ``latest`` pointer, so that pointer is
    never authoritative about where the sequence stands: a higher tag can already exist beside it.
    Scanning once for the maximum is also what keeps a new tag from landing below one that already
    exists — walking the version upwards instead would stop at the first free number, which can sit
    under a higher tag.

    Only tags the pattern recognises are considered, so tags from another scheme -- or pre-release
    builds, which the pattern cannot match -- never raise the ceiling for the next release.

    Args:
        expression: re.Pattern - The compiled release tag pattern.
        fallback: list[int] - Version components to return when no matching tag is found.

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
        match: Optional[re.Match] = expression.match(line.strip())
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
