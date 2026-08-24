"""Tests for the remote-branches-cleanup command."""

import subprocess
from typing import Iterator
from unittest.mock import patch

import pytest

from mega_snake.remote_branches import cleanup_remote_branches as module
from mega_snake.remote_branches.parse_remote_branches import Garbage
from mega_snake.util.repo import Repo

BOTH_SIDES = Garbage(branch="feature", local=True, remote=True)
LOCAL_ONLY = Garbage(branch="merged-and-pruned", local=True, remote=False)
PRUNE_COMMAND = "git fetch --all --prune"


@pytest.fixture(autouse=True)
def seeded_repo() -> Iterator[None]:
    """Seed the Repo snapshot so nothing in the command resolves it interactively."""
    Repo.reset()
    Repo.REMOTE = "origin"
    Repo.MAIN_BRANCH = "master"
    Repo.MAIN_LOCAL_HASH = "localmain111"
    Repo.MAIN_REMOTE_HASH = "remotemain222"
    Repo._INITIALIZED = True
    yield
    Repo.reset()


def test_cleanup_feeds_the_live_inventory_to_the_selection() -> None:
    """The cleanup builds the branch inventory in memory and hands it straight to the selection —
    no report file is read, so it cannot act on a stale listing from a previous run."""
    inventory = ["branch-a", "branch-b"]
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches", return_value=[BOTH_SIDES]
    ) as parsing_branches, patch.object(module, "delete_branches"), patch.object(module, "run_operation"), patch(
        "builtins.open"
    ) as opened:
        loader.from_repository.return_value = inventory
        module.remote_branches_cleanup.callback()

    loader.from_repository.assert_called_once_with()
    parsing_branches.assert_called_once_with(inventory)
    opened.assert_not_called()


def test_cleanup_deletes_the_selection_and_prunes_afterwards() -> None:
    """The selected branches are deleted, and the remote references are pruned right after so the
    listing of the next run does not show what was just removed."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches", return_value=[BOTH_SIDES]
    ), patch.object(module, "delete_branches") as delete_branches, patch.object(
        module, "run_operation"
    ) as run_operation:
        loader.from_repository.return_value = ["branch-a"]
        module.remote_branches_cleanup.callback()

    delete_branches.assert_called_once_with([BOTH_SIDES])
    run_operation.assert_called_once_with(PRUNE_COMMAND, "Fetching all remotes and pruning deleted branches")


def test_cleanup_skips_the_prune_when_nothing_was_deleted_remotely() -> None:
    """Pruning contacts the remote, which a purely local cleanup neither needs nor may be able to
    do — a repository without a remote would fail on it."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches", return_value=[LOCAL_ONLY]
    ), patch.object(module, "delete_branches") as delete_branches, patch.object(
        module, "run_operation"
    ) as run_operation:
        loader.from_repository.return_value = ["branch-a"]
        module.remote_branches_cleanup.callback()

    delete_branches.assert_called_once_with([LOCAL_ONLY])
    run_operation.assert_not_called()


def test_cleanup_with_an_empty_selection_deletes_nothing() -> None:
    """Declining every branch is a legitimate outcome: nothing is deleted and nothing is pruned."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches", return_value=[]
    ), patch.object(module, "delete_branches") as delete_branches, patch.object(
        module, "run_operation"
    ) as run_operation, patch.object(
        module, "ws_info"
    ) as ws_info:
        loader.from_repository.return_value = ["branch-a"]
        module.remote_branches_cleanup.callback()

    delete_branches.assert_not_called()
    run_operation.assert_not_called()
    ws_info.assert_called_once_with("No branches were selected for deletion")


def test_cleanup_without_branches_stops_before_prompting() -> None:
    """A repository with no branches has nothing to offer, so the user is told instead of being
    walked through an empty prompt loop."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches"
    ) as parsing_branches, patch.object(module, "delete_branches") as delete_branches, patch.object(
        module, "ws_info"
    ) as ws_info:
        loader.from_repository.return_value = []
        module.remote_branches_cleanup.callback()

    parsing_branches.assert_not_called()
    delete_branches.assert_not_called()
    ws_info.assert_called_once_with("No branches found in the current repository; nothing to clean up")


def test_cleanup_propagates_an_enumeration_failure_without_deleting_anything() -> None:
    """If the inventory cannot be built, the failure must surface: proceeding with a partial or
    absent listing would delete against an unknown state."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches"
    ) as parsing_branches, patch.object(module, "delete_branches") as delete_branches, patch.object(
        module, "run_operation"
    ) as run_operation:
        loader.from_repository.side_effect = subprocess.SubprocessError("git failed")
        with pytest.raises(subprocess.SubprocessError, match="git failed"):
            module.remote_branches_cleanup.callback()

    parsing_branches.assert_not_called()
    delete_branches.assert_not_called()
    run_operation.assert_not_called()


def test_cleanup_does_not_prune_when_the_deletion_failed() -> None:
    """A deletion that raises must not be followed by the prune: the run stops where it broke,
    instead of reporting success over a failed cleanup."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches", return_value=[BOTH_SIDES]
    ), patch.object(
        module, "delete_branches", side_effect=EnvironmentError("No remote repository found.")
    ), patch.object(
        module, "run_operation"
    ) as run_operation, patch.object(
        module, "ws_success"
    ) as ws_success:
        loader.from_repository.return_value = ["branch-a"]
        with pytest.raises(EnvironmentError, match="No remote repository found"):
            module.remote_branches_cleanup.callback()

    run_operation.assert_not_called()
    ws_success.assert_not_called()
