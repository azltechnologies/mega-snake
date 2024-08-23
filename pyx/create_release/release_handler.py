"""
This module contains the functions to handle release operations
"""
import subprocess
import time
from typing import List
from release import Release
NUM_RETRIES = 3

def create_release_list(list_string: str) -> List[Release]:
    """
    Converts a string into a list of Release instances

    Args:
        list_string: str

    Returns:
        List[Release]
    """
    if list_string is not None and bool(list_string):
        array_of_strings = list_string.split("\n")
        releases: List[Release] = [Release(f"{string}") for string in array_of_strings]
        releases = [x for x in releases if x is not None]
        # printing the releases size
        print(f"Releases size: {len(releases)}")
        # sorting the releases
        return sorted(releases, key=lambda r: r.published_at, reverse=True)
    return None

def get_latest_release() -> Release:
    """
    Retrieves the latest release
    """
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

    release_list: List[Release] = create_release_list(f"{result.stdout}")
    lastest_release: Release = [x for x in release_list if x.release_type != "Latest"][0]
    return lastest_release
