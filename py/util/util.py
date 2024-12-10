"""
This module contains utility functions for common operations.
"""

import re
import subprocess
import time
from py.util.formatting import ws_advice, ws_warning


def run_operation(cwd: str, description: str) -> subprocess.CompletedProcess[str]:
    """
    Runs the given command and retries on failure up to 3 times.

    Args:
        cwd: str
        description: str

    Returns:
        subprocess.CompletedProcess[str]
    """
    num_retries = 3
    ws_advice(f"Running operation: {description}")
    for attempt in range(1, num_retries + 1):
        try:
            ws_advice(f"Running: {cwd}")
            result = subprocess.run(cwd, shell=True, check=True, capture_output=True, text=True)
            ws_advice(f"{description} successfully on attempt {attempt}!")
            ws_advice(f"stdout: {result.stdout}")
            break  # Exit the loop on successful push
        except subprocess.CalledProcessError as error:
            ws_warning(f"{description} failed on attempt {attempt}. Error: {error.stdout}")
            ws_warning(f"Error details: {error.stderr}")
            if attempt == num_retries:
                raise subprocess.SubprocessError(f"{description} failed after {num_retries} attempts. Error: {error.stderr}") from error
            ws_warning(f"Retrying {description} in 2 seconds...")
            time.sleep(2)  # Wait 2 seconds before retrying
    return result


def get_main_branch() -> str:
    """
    Gets the main branch of the repository.

    Returns:
        str
    """
    remotes: list[str] = run_operation("git remote", "Getting remotes").stdout.strip().split("\n")
    if not remotes:
        raise ValueError("No remotes found in the current repository")
    if len(remotes) > 1:
        raise NotImplementedError("Multiple remotes found in the current repository; Operations with multiple remotes are not supported")
    ws_warning(f"{len(remotes)}")
    result = run_operation(f"git remote show {remotes[0]}", "Getting main branch").stdout.strip()
    if not result:
        raise LookupError(f"No main branch found in the current repository for remote {remotes[0]}")
    pattern = r"^(\s*HEAD branch:\s*)(\S+)"
    match = re.search(pattern, result, re.MULTILINE)
    if match:
        return match.group(2)
    raise LookupError("No main branch found in the current repository")


def get_current_commit() -> str:
    """
    Gets the current branch of the repository.

    Returns:
        str
    """
    result = run_operation("git rev-parse HEAD", "Getting current branch").stdout.strip()
    return result


def get_validated_input(prompt: str, valid_values: list[str]) -> str:
    """
    Get user input and validate against allowed values

    Args:
        prompt: str
        valid_values: set[str]
    """
    tries: int = 0
    while True:
        user_input = input(f"\n{prompt}\n").lower()
        # convert to lowercase all the values in valid_values
        valid_values = [value.lower() for value in valid_values]
        if user_input in valid_values:
            return user_input
        print(f"Invalid input. Please enter one of:\n {' | '.join(valid_values)}")
        tries += 1
        if tries > 3:
            raise KeyError(f"Too many invalid inputs for '{prompt}'. Exiting.")
