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
from mega_snake.constants import RELEASE_TYPE_OPT

NUM_RETRIES = 3


@click.command(
    name="create-release",
    short_help="Creates a new release on GitHub with the given parameters.",
    help="Creates a GitHub release and tag: the new tag is derived from the latest release tag plus"
    " the given suffix, and the publication is delegated to the gh CLI.",
    epilog="""
    usage: mgsnake create-release <tag_suffix> <release_type> [notes] [branch]\n
    Args:\n
        tag_suffix: str - suffix to add to the tag\n
        release_type: char - 'p' (prerelease) | 'l' (latest) | 'r' (regular release)\n
        notes: Optional[str] - release notes\n
        branch: Optional[str] - branch to create the release from. Default is the current branch.
    """,
)
@click.argument("tag-suffix", type=click.STRING, required=True)
@click.argument("release-type", type=click.Choice(list(RELEASE_TYPE_OPT.keys()), False), required=True)
@click.argument("notes", type=click.STRING, required=False, default=None)
@click.argument("branch", type=click.STRING, required=False, default=None)
def create_release(tag_suffix: str, release_type: str, notes: Optional[str], branch: Optional[str]) -> None:
    """
    Creates a new release on GitHub with the given parameters.

    Builds the new tag from the latest release tag plus tag_suffix and publishes it via the gh
    CLI. Type 'l' asks for confirmation before replacing the latest release; type 'r' publishes
    without the latest mark and restores the previous latest release if GitHub moved it anyway.

    Args:
        tag_suffix: str - Suffix to append to the new tag.
        release_type: str - 'p' (prerelease), 'l' (latest) or 'r' (regular, keeps current latest).
        notes: Optional[str] - Release notes; ignored when shorter than 6 characters.
        branch: Optional[str] - Branch to create the release from; defaults to the current branch.

    Returns:
        None
    """
    try:
        tag_flag: str = RELEASE_TYPE_OPT[release_type]
        if release_type not in RELEASE_TYPE_OPT:
            raise ValueError(f"Invalid release type: {release_type}. Exiting.")
    except (IndexError, ValueError) as e:
        raise IndexError(f"release_type must be one of: {RELEASE_TYPE_OPT.keys()}") from e
    if not branch:
        branch = get_current_commit()
    handler.git_fetch()

    if release_type.lower() == "l":
        prompt: str = "\nAre you sure you want to create a new latest release?"
        yes_no_options: list[str] = ["y", "n"]
        if get_validated_input(prompt, yes_no_options) == "n":
            ws_info("Exiting.")
            return
    if release_type not in RELEASE_TYPE_OPT:
        raise ValueError(
            f"Invalid release type: {release_type}; Please enter one of:\n {' | '.join(RELEASE_TYPE_OPT.keys())}"
        )

    # getting the release notes
    notes_release: str = _get_notes(notes)

    # getting the latest release
    latest_release: Release = get_latest_release()

    # getting the new tag
    new_tag: str = latest_release.get_release_tag(tag_suffix)
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
