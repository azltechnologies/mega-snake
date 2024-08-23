#!/usr/bin/env python3
"""
    Create a GitHub release for the current project.
"""
import subprocess
import sys
import time
from typing import List
import release
from release import Release

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
    if int(RELEASE_TYPE) not in tag_commands:
        raise ValueError(f"Invalid release type: {RELEASE_TYPE}. Exiting.")
# except for index error and value error together
except (IndexError, ValueError):
    print("Usage: create_release.py <tag_suffix> <release_type> <release_notes>")
    sys.exit(0)

if int(RELEASE_TYPE) == 3:
    prompt: str = input(f"\nAre you sure you want to create a new latest release? y/n: ")
    if prompt != "y":
        print("Exiting.")
        sys.exit(0)
if int(RELEASE_TYPE) not in tag_commands:
    raise ValueError(f"Invalid release type: {RELEASE_TYPE}. Exiting.")
TAG_FLAG: str = tag_commands[int(RELEASE_TYPE)]
for attempt in range(1, NUM_RETRIES + 1):
    try:
        cwd: str = "gh release list 2>&1"
        result = subprocess.run(cwd, shell=True, check=True, capture_output=True, text=True)
        print(f"Retrieved release list successfully on attempt {attempt}!")
        break  # Exit the loop on successful push
    except subprocess.CalledProcessError as error:
        print(f"Retrieve release list failed on attempt {attempt}. Error: {error.stdout}")
        if attempt == NUM_RETRIES:
            print(f"Retrieve release list failed after {NUM_RETRIES} attempts. Giving up.")
        else:
            print("Retrying release list in 2 seconds...")
            time.sleep(2)  # Wait 5 seconds before retrying

release_list: List[Release] = release.create_release_list(f"{result.stdout}")
lastest_release: Release = [x for x in release_list if x.release_type == "Latest"][0]
new_tag: str = lastest_release.get_release_tag(RELEASE_TAG_SUFFIX)
notes_release: str = get_notes(RELEASE_NOTES)
for attempt in range(1, NUM_RETRIES + 1):
    try:
        cwd: str = f"gh release create {new_tag} --title \"{new_tag}\" {notes_release} --generate-notes {TAG_FLAG}"
        result = subprocess.run(cwd, shell=True, check=True, capture_output=True, text=True)
        print(f"Retrieved release list successfully on attempt {attempt}!")
        break  # Exit the loop on successful push
    except subprocess.CalledProcessError as error:
        print(f"Retrieve release list failed on attempt {attempt}. Error: {error.stdout}")
        if attempt == NUM_RETRIES:
            print(f"Retrieve release list failed after {NUM_RETRIES} attempts. Giving up.")
        else:
            print("Retrying release list in 2 seconds...")
            time.sleep(2)  # Wait 5 seconds before retrying
