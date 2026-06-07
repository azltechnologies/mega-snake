"""
This module contains the functions to handle release operations
"""

import subprocess
from mega_snake.util.util import run_operation


def git_fetch() -> None:
    """
    Fetches the latest changes from the remote repository and retries on failure up to 3 times.

    Returns:
        None
    """
    cwd: str = "git fetch --all 2>&1"
    run_operation(cwd, "Fetch latest changes")


def get_release_list(limit: int) -> subprocess.CompletedProcess[str]:
    """
    Retrieves the list of releases from GitHub and retries on failure up to 3 times.

    Returns:
        subprocess.CompletedProcess[str]
    """
    cwd: str = f"gh release list --limit {limit} 2>&1"
    return run_operation(cwd, "Retrieve release list")


def publish_release(tag_name: str, release_type: str, release_notes: str, release_branch: str) -> None:
    """
    Publishes a release on GitHub with the given parameters and retries on failure up to 3 times.

    Args:
        tag_name: str
        release_type: str
        release_notes: str
        release_branch: str

    Returns:
        None
    """
    cwd: str = (
        f'gh release create {tag_name} {release_type} --target "{release_branch}" '
        f'--title "{tag_name}" {release_notes} --generate-notes'
    )
    run_operation(cwd, "Publish release")


def set_release_to_latest(tag: str) -> None:
    """
    Sets the given release as the latest release on GitHub and retries on failure up to 3 times.

    Args:
        tag: str

    Returns:
        None
    """
    cwd = f"gh release edit {tag} --latest"
    run_operation(cwd, "Set release to latest")


def get_commit_from_release(tag: str) -> str:
    """
    Retrieves the commit hash associated with the given release tag and retries on failure up to 3 times.

    Args:
        tag: str

    Returns:
        str
    """
    cwd = f'git rev-list -n 1  "{tag}" 2>&1'
    return run_operation(cwd, f"Retrieve commit for {tag}").stdout.strip()
