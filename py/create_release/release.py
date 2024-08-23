"""Class Module representing a release."""

import dataclasses
import datetime
import subprocess
import sys
import time
from typing import List

@dataclasses.dataclass
class Release:
    """Class containing a named set of properties"""
    
    title: str
    release_type: str
    tag_name: str
    date_str: str
    published_at: datetime
    commit: str
    def __new__(cls, input_string: str):
        if input_string is None or not bool(input_string):
            return None
        return super().__new__(cls)
    
    def __init__(self, input_string: str):
        if input_string is not None and bool(input_string):
            result = input_string.split('\t')
            self.title = result[0]
            self.release_type = result[1]
            self.tag_name = result[2]
            self.date_str = result[3]
            self.published_at = datetime.datetime.strptime(self.date_str, "%Y-%m-%dT%H:%M:%SZ")
            num_retries = 3
            if self.release_type != 'Draft':
                for attempt in range(1, num_retries + 1):
                    try:
                        cwd: str =  f"git rev-list -n 1  \"{self.tag_name}\" 2>&1"
                        #print(f"runnning: {cwd}")
                        self.commit = subprocess.run(
                            cwd,
                            shell=True,
                            check=True,
                            capture_output=True,
                            text=True
                        ).stdout.strip()
                        #print(f"Retrieve commit for {self.tag_name} successfully on attempt {attempt}!")
                        break  # Exit the loop on successful push
                    except subprocess.CalledProcessError as error:
                        print(f"Retrieve commit for {self.tag_name} failed on attempt {attempt}. Error: {error.stdout}")
                        if attempt == num_retries:
                            print(f"Retrieve commit for {self.tag_name} failed after {num_retries} attempts. Giving up.")
                            sys.exit(1)
                        else:
                            print("Retrying commit for {self.tag_name} in 2 seconds...")
                            time.sleep(2)  # Wait 5 seconds before retrying


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
        attemps: int = 12
        new_tag_name: str = None
        i: int = 0
        for shot in range(1, attemps + 1):
            try:
                new_tag_name = f"{tag_name}-{suffix}.{i}"
                com: str = f"git rev-parse {new_tag_name} 2>&1"
                subprocess.run(com, shell=True, check=True, capture_output=True, text=True)
                print(f"Found an existing tag {new_tag_name} at attempt {shot}!")
            except subprocess.CalledProcessError:
                # If the tag does not exist, this exception will be caught
                print(f"Tag {new_tag_name} is available!")
                return new_tag_name  # Return the first non-existing tag
            i += 1
        # if no tag was found, throw error
        raise ValueError(f"Could not find a non-existing tag after {attemps} attempts. Exiting.")
    

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

