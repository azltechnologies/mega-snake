#!/usr/bin/env python3
"""
Create a GitHub release for the current project.
"""

from typing import Optional
import click
import mega_snake.light_weight.release_handler as handler
from mega_snake.light_weight.release import Release, get_latest_release
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.util.util import get_validated_input, get_current_commit
from mega_snake.constants import RELEASE_TYPE_OPT, VERSION_PART_OPT

NUM_RETRIES = 3


@click.command(
    name="create-release",
    short_help="Creates a new release on GitHub with the given parameters.",
    help="Creates a GitHub release and tag: the new tag is the latest release's version with one of its"
    " components incremented, and the publication is delegated to the gh CLI.",
    epilog="""
    usage: mgsnake create-release <release_type> [notes] [branch]\n
    Args:\n
        release_type: char - 'p' (prerelease) | 'l' (latest) | 'r' (regular release)\n
        notes: Optional[str] - release notes\n
        branch: Optional[str] - branch to create the release from. Default is the current branch.
    """,
)
@click.argument("release-type", type=click.Choice(list(RELEASE_TYPE_OPT.keys()), False), required=True)
@click.argument("notes", type=click.STRING, required=False, default=None)
@click.argument("branch", type=click.STRING, required=False, default=None)
@click.option(
    "--tag-suffix",
    "-s",
    type=click.STRING,
    default=None,
    help="Pre-release label appended to the new tag (v1.2.4-<suffix>.N). Only valid for the 'p' and"
    " 'r' release types: a 'l' release takes over the latest pointer, which GitHub only ever grants"
    " to a plain version, so the two are mutually exclusive.",
)
@click.option(
    "--version-part",
    "-v",
    type=click.Choice(list(VERSION_PART_OPT.keys()), case_sensitive=False),
    default="patch",
    show_default=True,
    help="Which component of the latest release's version to increment: 'patch' (the last number),"
    " 'minor' (the middle one, resetting the patch to zero) or 'major' (the first one, resetting the"
    " other two to zero).",
)
def create_release(
    release_type: str, notes: Optional[str], branch: Optional[str], version_part: str, tag_suffix: Optional[str]
) -> None:
    """
    Creates a new release on GitHub with the given parameters.

    Derives the new tag from the latest release by incrementing the requested version component, then
    publishes it via the gh CLI. Type 'l' asks for confirmation before replacing the latest release;
    type 'r' publishes without the latest mark and restores the previous latest release if GitHub
    moved it anyway.

    Args:
        release_type: str - 'p' (prerelease), 'l' (latest) or 'r' (regular, keeps current latest).
        notes: Optional[str] - Release notes; ignored when shorter than 6 characters.
        branch: Optional[str] - Branch to create the release from; defaults to the current branch.
        version_part: str - Version component to increment: 'patch', 'minor' or 'major'.
        tag_suffix: Optional[str] - Pre-release label for the new tag; rejected for the 'l' type.

    Raises:
        ValueError: If the release type is not one of the supported ones.
        click.ClickException: If a tag suffix is combined with the 'l' release type.

    Returns:
        None
    """
    if release_type not in RELEASE_TYPE_OPT:
        raise ValueError(
            f"Invalid release type: {release_type}; Please enter one of:\n {' | '.join(RELEASE_TYPE_OPT.keys())}"
        )
    # GitHub only grants the 'latest' pointer to a plain version, so a suffixed latest release is a
    # request the platform cannot satisfy: refused here instead of publishing something else.
    if tag_suffix and release_type.lower() == "l":
        raise click.ClickException(
            "BAD REQUEST: --tag-suffix and the 'l' release type are mutually exclusive. A latest "
            "release must carry a plain vX.Y.Z tag, while a suffix marks a pre-release build. Use "
            "one or the other: drop --tag-suffix, or publish with the 'p' or 'r' type."
        )
    tag_flag: str = RELEASE_TYPE_OPT[release_type]
    if not branch:
        branch = get_current_commit()
    handler.git_fetch()

    if release_type.lower() == "l":
        prompt: str = "\nAre you sure you want to create a new latest release?"
        yes_no_options: list[str] = ["y", "n"]
        if get_validated_input(prompt, yes_no_options) == "n":
            ws_info("Exiting.")
            return
    # getting the release notes
    notes_release: str = _get_notes(notes)

    # getting the latest release
    latest_release: Release = get_latest_release()

    # getting the new tag
    new_tag: str = latest_release.get_release_tag(version_part, tag_suffix)
    # publishing the release
    handler.publish_release(new_tag, tag_flag, notes_release, branch)

    # fetching the latest changes
    handler.git_fetch()

    if release_type.lower() == "r":
        # getting the new latest release
        new_latest: Release = get_latest_release()

        # verifying if the new latest release is the same as the previous one
        if new_latest.tag_name == latest_release.tag_name:
            ws_success("The latest release was not updated. All good.")
        else:
            ws_info("The latest was replaced. Restablishing the previous latest release.")
            handler.set_release_to_latest(latest_release.tag_name)
            ws_success("The latest release was successfully restored.")


def _get_notes(notes: Optional[str]) -> str:
    """
    Returns the notes for the release
    """
    # checking if notes is empty or is smaller than 6 characters
    if not notes or len(notes.strip()) < 6:
        return ""
    return f'--notes "{notes.strip()}"'
