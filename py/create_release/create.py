#!/usr/bin/env python3
"""
    Create a GitHub release for the current project.
"""
import sys
import release_handler as handler
from release import Release
import release as rel_func

tag_commands: dict = {
    1: "--prerelease",
    2: "--latest=false",
    3: "--latest"
}

def get_notes(notes: str) -> str:
    """
    Returns the notes for the release
    """
    # checking if notes is empty or is smaller than 6 characters
    if not notes or len(notes.strip()) < 6:
        return ""
    return f"--notes \"{notes.strip()}\""


NUM_RETRIES = 3
try:
    RELEASE_TAG_SUFFIX: str = sys.argv[1]
    RELEASE_TYPE: str = sys.argv[2]
    RELEASE_NOTES: str = sys.argv[3]
    RELEASE_BRANCH: str = sys.argv[4]
    TAG_FLAG: str = tag_commands[int(RELEASE_TYPE)]
    if int(RELEASE_TYPE) not in tag_commands:
        raise ValueError(f"Invalid release type: {RELEASE_TYPE}. Exiting.")
except (IndexError, ValueError):
    print("Usage: create_release.py <tag_suffix> <release_type> <release_notes> <release_branch>")
    sys.exit(0)

handler.git_fetch()

if int(RELEASE_TYPE) == 3:
    prompt: str = input("\nAre you sure you want to create a new latest release? y/n: ")
    if prompt != "y":
        print("Exiting.")
        sys.exit(0)
if int(RELEASE_TYPE) not in tag_commands:
    raise ValueError(f"Invalid release type: {RELEASE_TYPE}. Exiting.")
# getting the latest release
latest_release: Release = rel_func.get_latest_release()

# getting the new tag
new_tag: str = latest_release.get_release_tag(RELEASE_TAG_SUFFIX)

# getting the release notes
notes_release: str = get_notes(RELEASE_NOTES)

# publishing the release
handler.publish_release(new_tag, TAG_FLAG, notes_release, RELEASE_BRANCH)

# fetching the latest changes
handler.git_fetch()

if int(RELEASE_TYPE) == 2:
    # getting the new latest release
    new_latest: Release = rel_func.get_latest_release()

    # verifying if the new latest release is the same as the previous one
    if new_latest.tag_name == latest_release.tag_name:
        print("The latest release was not updated. All good.")
        sys.exit(0)
    else:
        print("The latest was replaced. Restablishing the previous latest release.")
        handler.set_release_to_latest(latest_release.tag_name)
