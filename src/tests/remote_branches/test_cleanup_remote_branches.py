"""Tests for the remote-branches-cleanup command."""

import subprocess
from typing import Iterator, Optional
from unittest.mock import call, patch

import pytest

from mega_snake.remote_branches import cleanup_remote_branches as module
from mega_snake.remote_branches.parse_remote_branches import DeletionOutcome, Garbage
from mega_snake.util.repo import Repo

BOTH_SIDES = Garbage(local_name="feature", remote_name="feature")
LOCAL_ONLY = Garbage(local_name="merged-and-pruned", remote_name=None)
PRUNE_COMMAND = "git fetch --all --prune"


def outcome_of(
    remote_deleted: Optional[list[str]] = None,
    local_deleted: Optional[list[str]] = None,
    failures: Optional[list[str]] = None,
) -> DeletionOutcome:
    """Build a deletion outcome, defaulting every side to "nothing happened".

    Every test that patches ``delete_branches`` has to hand back one of these, and the interesting
    part is always a single field; letting a MagicMock stand in instead would make ``remote_deleted``
    truthy no matter what the run did, which is exactly the distinction these tests exist to draw.

    Parameters:
        remote_deleted: The remote names the run deleted.
        local_deleted: The local names the run deleted.
        failures: The failure lines the run collected.

    Raises:
        None

    Returns:
        DeletionOutcome: The outcome to return from a patched ``delete_branches``.
    """
    return DeletionOutcome(
        remote_deleted=remote_deleted or [],
        local_deleted=local_deleted or [],
        failures=failures or [],
    )


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
    ) as parsing_branches, patch.object(
        module, "delete_branches", return_value=outcome_of()
    ), patch.object(module, "run_operation"), patch("builtins.open") as opened:
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
    ), patch.object(
        module, "delete_branches", return_value=outcome_of(remote_deleted=["feature"], local_deleted=["feature"])
    ) as delete_branches, patch.object(
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
    ), patch.object(
        module, "delete_branches", return_value=outcome_of(local_deleted=["merged-and-pruned"])
    ) as delete_branches, patch.object(
        module, "run_operation"
    ) as run_operation:
        loader.from_repository.return_value = ["branch-a"]
        module.remote_branches_cleanup.callback()

    delete_branches.assert_called_once_with([LOCAL_ONLY])
    run_operation.assert_not_called()


def test_cleanup_prunes_on_what_was_deleted_not_on_what_was_selected() -> None:
    """A selection carrying a remote side whose push then failed leaves nothing to prune: the
    decision must read the outcome, not the request. This is the only fixture that separates the two
    — the branch *was* selected with a remote side, and the remote side *was* not deleted."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches", return_value=[BOTH_SIDES]
    ), patch.object(
        module,
        "delete_branches",
        return_value=outcome_of(local_deleted=["feature"], failures=["remote 'feature' could not be deleted"]),
    ), patch.object(
        module, "run_operation"
    ) as run_operation:
        loader.from_repository.return_value = ["branch-a"]
        module.remote_branches_cleanup.callback()

    assert run_operation.call_args_list == [], "pruned despite the remote deletion having failed"


def test_cleanup_reports_every_failure_and_never_claims_a_clean_run() -> None:
    """A swallowed deletion failure must still reach the user: the branch survived, and the closing
    line is the only place the run says so."""
    failure = "Local branch 'feature' could not be deleted; it is still present"
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches", return_value=[BOTH_SIDES]
    ), patch.object(
        module, "delete_branches", return_value=outcome_of(remote_deleted=["feature"], failures=[failure])
    ), patch.object(module, "run_operation"), patch.object(module, "ws_warning") as ws_warning, patch.object(
        module, "ws_success"
    ) as ws_success:
        loader.from_repository.return_value = ["branch-a"]
        module.remote_branches_cleanup.callback()

    assert ws_warning.call_args_list == [
        call("1 branch side(s) could not be deleted:"),
        call(f"\t{failure}"),
    ]
    assert ws_success.call_args_list == [call("Deleted 1 remote and 0 local branches that have been merged "
                                             "into the main branch")]


def test_cleanup_announces_no_success_when_every_deletion_failed() -> None:
    """A run that deleted nothing must not print a success line at all: the counts would both be
    zero, which reads as a clean cleanup that removed nothing on purpose."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "parsing_branches", return_value=[BOTH_SIDES]
    ), patch.object(
        module, "delete_branches", return_value=outcome_of(failures=["remote failed", "local failed"])
    ), patch.object(module, "run_operation"), patch.object(module, "ws_warning"), patch.object(
        module, "ws_success"
    ) as ws_success:
        loader.from_repository.return_value = ["branch-a"]
        module.remote_branches_cleanup.callback()

    ws_success.assert_not_called()


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
