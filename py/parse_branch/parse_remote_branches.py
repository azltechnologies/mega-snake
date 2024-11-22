#!/usr/bin/env python3
"""
    parse_remote_branches script, which allows the user to delete old branches
    that was already been merged into main branch.
"""
import subprocess
import sys
import time
from typing import List
from py.util.remote_branch import RemoteBranch


def define_branches(line: str):
    """
    Converts a string into a remote_branch instance

    Args:
        line: str

    Returns:
        RemoteBranch
    """
    if line is not None and bool(line):
        return RemoteBranch(line)
    return None

options: List[str] = ["y", "n", "f"]
text: str = sys.argv[1]
main_branch: str = sys.argv[2]
array_of_strings = text.split("\n")
branches: List[RemoteBranch] = map(define_branches, array_of_strings)
branches = [x for x in branches if x is not None]
branches = sorted(branches, reverse=False)
garbage: list[str] = []
for branch in branches:
    try:
        if branch.merged_on_main and branch.branch != main_branch:
            prompt = (
                f"\nDo you want to delete the following branch?\n"
                f"\tBranch: {branch.branch}\n"
                f"\tDate: {branch.date_str}\n"
                f"\tAuthor: {branch.mail}\n"
                f"\tCommit: {branch.commit}\n"
                f"\tMessage: {branch.message}\n\n"
                f"(y)es | (n)o | (f)inalize\n"
            )
            while True:
                user_input = input(prompt)
                user_input = user_input[0].lower() if bool(user_input) else user_input
                if user_input in options:
                    break
                print("respond y or n to the question")
            if user_input == "y":
                garbage.append(branch.branch)
            elif user_input == "f":
                break
    except AttributeError:
        print("error here: " + branch + ".")
        print(branch)
        print("Attribute 'merged_on_main' does not exist for this object")

for branch in garbage:
    NUM_RETRIES = 3
    for attempt in range(1, NUM_RETRIES + 1):
        try:
            cwd: str =  f"git push -d origin \"{branch}\" 2>&1"
            result = subprocess.run(
                cwd,
                shell=True,
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"Git push successful on attempt {attempt}!")
            print(result)
            break  # Exit the loop on successful push
        except subprocess.CalledProcessError as error:
            print(f"Git push failed on attempt {attempt}. Error: {error.stdout}")
            if attempt == NUM_RETRIES:
                print(f"Git push failed after {NUM_RETRIES} attempts. Giving up.")
            else:
                print("Retrying git push in 2 seconds...")
                time.sleep(2)  # Wait 5 seconds before retrying
