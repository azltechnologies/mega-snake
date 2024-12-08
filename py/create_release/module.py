#!/usr/bin/env python3
"""
    Create a GitHub release for the current project.
"""
import sys
from typing import Optional
import py.create_release.release_handler as handler
from py.create_release.release import Release, get_latest_release
from py.util.formatting import WorkspaceError, ws_info, ws_success
from py.util.util import get_validated_input, get_current_commit
from py.constants import RELEASE_TYPE_OPT

NUM_RETRIES = 3


def main(tag_suffix: str, release_type: str, notes: Optional[str], branch: Optional[str]) -> None:
    """
    Creates a new release on GitHub with the given parameters.

    Args:
        tag_suffix: str
        release_type: int
        notes: Optional[str]
        branch: str

    Returns:
        None
    """
    try:
        tag_flag: str = RELEASE_TYPE_OPT[release_type]
        if release_type not in RELEASE_TYPE_OPT:
            raise ValueError(f"Invalid release type: {release_type}. Exiting.")
    except (IndexError, ValueError) as e:
        WorkspaceError.ws_error("Usage: create_release.py <tag_suffix> <release_type> <release_notes> <release_branch>", e)
        raise e
    if not branch:
        branch = get_current_commit()
    handler.git_fetch()

    if release_type == "l":
        prompt: str = "\nAre you sure you want to create a new latest release? y/n: "
        yes_no_options: list[str] = ["y", "n"]
        if get_validated_input(prompt, yes_no_options) == "y":
            ws_info("Exiting.")
            sys.exit(0)
    if release_type not in RELEASE_TYPE_OPT:
        exc = ValueError(f"Invalid release type: {release_type}. Exiting.")
        WorkspaceError.ws_error(f"Please enter one of:\n {' | '.join(RELEASE_TYPE_OPT.keys())}", exc)
        raise exc
    # getting the latest release
    latest_release: Release = get_latest_release()

    # getting the new tag
    new_tag: str = latest_release.get_release_tag(tag_suffix)

    # getting the release notes
    notes_release: str = get_notes(notes)

    # publishing the release
    handler.publish_release(new_tag, tag_flag, notes_release, branch)

    # fetching the latest changes
    handler.git_fetch()

    if release_type == "r":
        # getting the new latest release
        new_latest: Release = get_latest_release()

        # verifying if the new latest release is the same as the previous one
        if new_latest.tag_name == latest_release.tag_name:
            ws_success("The latest release was not updated. All good.")
        else:
            ws_info("The latest was replaced. Restablishing the previous latest release.")
            handler.set_release_to_latest(latest_release.tag_name)
            ws_success("The latest release was successfully restored.")


def get_notes(notes: Optional[str]) -> str:
    """
    Returns the notes for the release
    """
    # checking if notes is empty or is smaller than 6 characters
    if not notes or len(notes.strip()) < 6:
        return ""
    return f'--notes "{notes.strip()}"'
