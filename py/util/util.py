"""
This module contains utility functions for common operations.
"""

import re
import subprocess
import time
from py.util.formatting import ws_advice, ws_warning, WorkspaceError


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
                raise WorkspaceError(f"{description} failed after {num_retries} attempts. Giving up.", error) from error
            ws_warning(f"Retrying {description} in 2 seconds...")
            time.sleep(2)  # Wait 2 seconds before retrying
        except Exception as error:
            raise WorkspaceError("Error creating diff tree", error) from error
    return result


def get_main_branch() -> str:
    """
    Gets the main branch of the repository.

    Returns:
        str
    """
    result = run_operation("git remote show origin", "Getting main branch").stdout.strip()
    if not result:
        e = ValueError("No main branch found in the current repository")
        raise WorkspaceError("No main branch found", e) from e
    pattern = r"^(\s*HEAD branch:\s*)(\S+)"
    match = re.search(pattern, result, re.MULTILINE)
    if match:
        return match.group(2)
    e = ValueError("No main branch found in the current repository")
    raise WorkspaceError("No main branch found", e) from e
