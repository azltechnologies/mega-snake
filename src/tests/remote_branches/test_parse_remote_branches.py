""" Tests for the parse_remote_branches module. """

import subprocess
from types import SimpleNamespace
from typing import Iterator, Optional
from unittest.mock import call, patch

import pytest

from mega_snake.remote_branches import parse_remote_branches as module
from mega_snake.remote_branches.parse_remote_branches import Garbage
from mega_snake.util.formatting import InternalStateError
from mega_snake.util.repo import Repo


@pytest.fixture(autouse=True)
def seeded_repo() -> Iterator[None]:
    """Seed the Repo snapshot so the selection reads a main branch without resolving it for real."""
    Repo.reset()
    Repo.REMOTE = "origin"
    Repo.MAIN_BRANCH = "master"
    Repo.MAIN_LOCAL_HASH = "localmain111"
    Repo.MAIN_REMOTE_HASH = "remotemain222"
    Repo._INITIALIZED = True
    yield
    Repo.reset()


def branch_double(
    short_name: str,
    fully_merged: bool = True,
    local: bool = True,
    remote: bool = True,
    commit_hash: str = "hash123",
) -> SimpleNamespace:
    """Build a GitBranch stand-in for the selection loop.

    The loop only reads the two side markers and the display fields of whichever side exists, so a
    namespace is enough — and it keeps the git plumbing out of a test about the prompting itself.
    """
    side = SimpleNamespace(
        short_name=short_name,
        str_time="2025-01-01T00:00:00Z",
        mail="a@b",
        hash=commit_hash,
        message="msg",
    )
    return SimpleNamespace(
        fully_merged=fully_merged,
        local=side if local else None,
        remote=side if remote else None,
        get_any_branch=lambda: side,
    )


def test_parsing_branches_only_offers_fully_merged_branches_and_never_the_main_one() -> None:
    """An unmerged branch is not a deletion candidate, and the main branch never is either — no
    matter how merged it looks against itself. Only the rest reaches the prompt."""
    branches = [
        branch_double("master"),
        branch_double("merged-feature"),
        branch_double("half-merged", fully_merged=False),
    ]
    with patch.object(module, "get_validated_input", return_value="y") as prompt:
        garbage = module.parsing_branches(branches)

    assert [item.branch for item in garbage] == ["merged-feature"]
    assert "master" not in [item.branch for item in garbage], "the main branch must never be offered"
    prompt.assert_called_once()
    assert "merged-feature" in prompt.call_args.args[0]


def test_parsing_branches_records_the_sides_each_selected_branch_lives_on() -> None:
    """The sides captured here are what the deletion later acts on, so each one must reflect the
    branch it came from rather than a uniform default."""
    branches = [
        branch_double("both-sides", local=True, remote=True),
        branch_double("local-leftover", local=True, remote=False),
        branch_double("never-checked-out", local=False, remote=True),
    ]
    with patch.object(module, "get_validated_input", return_value="y"):
        garbage = module.parsing_branches(branches)

    assert garbage == [
        Garbage(branch="both-sides", local=True, remote=True),
        Garbage(branch="local-leftover", local=True, remote=False),
        Garbage(branch="never-checked-out", local=False, remote=True),
    ]


def test_parsing_branches_keeps_only_the_accepted_branches() -> None:
    """A 'no' answer skips its branch without stopping the review of the following ones."""
    branches = [branch_double("first"), branch_double("second"), branch_double("third")]
    with patch.object(module, "get_validated_input", side_effect=["n", "y", "n"]):
        garbage = module.parsing_branches(branches)

    assert [item.branch for item in garbage] == ["second"]


def test_parsing_branches_stops_the_review_on_finalize() -> None:
    """'finalize' ends the review immediately: the remaining branches are never prompted for, and
    what was already selected is kept."""
    branches = [branch_double("first"), branch_double("second"), branch_double("third")]
    with patch.object(module, "get_validated_input", side_effect=["y", "f"]) as prompt:
        garbage = module.parsing_branches(branches)

    assert [item.branch for item in garbage] == ["first"]
    assert prompt.call_count == 2, "the third branch must never be prompted for"


def test_parsing_branches_with_no_branches_prompts_for_nothing() -> None:
    """An empty inventory is a legitimate outcome, not an error: nothing is asked and nothing is
    selected."""
    with patch.object(module, "get_validated_input") as prompt:
        assert module.parsing_branches([]) == []
    prompt.assert_not_called()


def test_delete_branches_deletes_both_sides_when_the_branch_lives_on_both() -> None:
    """When the branch exists on the remote and locally, the operations must occur in order:
    (1) remote push -d, (2) local branch -D. The remote success message must be reported, followed
    by the local deletion message."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        run_operation.return_value = SimpleNamespace(stdout="deleted remote", returncode=0)
        module.delete_branches([Garbage(branch="feature/foo", local=True, remote=True)])

    assert run_operation.call_args_list == [
        call('git push -d "origin" "feature/foo" --no-verify 2>&1', "Deleting remote branch feature/foo"),
        call('git branch -D "feature/foo"', "Deleting local branch feature/foo"),
    ]
    assert ws_success.call_args_list == [
        call("deleted remote"),
        call("Local branch 'feature/foo' deleted successfully"),
    ]


def test_delete_branches_skips_local_delete_when_branch_never_checked_out() -> None:
    """A remote branch from another author that was never checked out locally has no matching local
    reference. `git branch -D` must NOT be attempted for it (it would fail), while the remote
    deletion still happens and is reported."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        run_operation.return_value = SimpleNamespace(stdout="deleted remote", returncode=0)
        module.delete_branches([Garbage(branch="someone-elses/branch", local=False, remote=True)])

    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert commands == ['git push -d "origin" "someone-elses/branch" --no-verify 2>&1']
    assert not any(command.startswith("git branch -D") for command in commands)
    ws_success.assert_called_once_with("deleted remote")


def test_delete_branches_deletes_local_only_branch_without_touching_the_remote() -> None:
    """A branch whose remote counterpart was already deleted when its pull request was merged only
    survives locally. `git push -d` must NOT be attempted for it — there is nothing on the remote to
    delete and the push would fail — while the local deletion still happens."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "require_remote"
    ) as require_remote, patch.object(module, "ws_success") as ws_success:
        run_operation.return_value = SimpleNamespace(stdout="", returncode=0)
        module.delete_branches([Garbage(branch="merged-and-pruned", local=True, remote=False)])

    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert commands == ['git branch -D "merged-and-pruned"']
    assert not any(command.startswith("git push -d") for command in commands)
    ws_success.assert_called_once_with("Local branch 'merged-and-pruned' deleted successfully")
    # a local-only cleanup must work in a repository with no remote configured
    require_remote.assert_not_called()


def test_delete_branches_continues_when_remote_deletion_fails() -> None:
    """A failed remote deletion must not delete the local copy of that branch, and must not stop the
    loop: the next branch has to complete its full remote + local deletion cycle."""

    def fake_run_operation(cwd: str, _description: str) -> SimpleNamespace:
        """Fail the push of the broken branch, succeed for everything else."""
        if "broken-branch" in cwd:
            raise subprocess.SubprocessError("push failed")
        return SimpleNamespace(stdout="deleted remote", returncode=0)

    with patch.object(module, "run_operation", side_effect=fake_run_operation) as run_operation, patch.object(
        module, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        module.delete_branches(
            [
                Garbage(branch="broken-branch", local=True, remote=True),
                Garbage(branch="good-branch", local=True, remote=True),
            ]
        )

    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert commands == [
        'git push -d "origin" "broken-branch" --no-verify 2>&1',
        'git push -d "origin" "good-branch" --no-verify 2>&1',
        'git branch -D "good-branch"',
    ]
    assert not any("broken-branch" in command and command.startswith("git branch -D") for command in commands)
    assert ws_success.call_args_list == [
        call("deleted remote"),
        call("Local branch 'good-branch' deleted successfully"),
    ]


def test_delete_branches_propagates_a_missing_remote_when_one_is_needed() -> None:
    """A branch with a remote side cannot be deleted without a remote: the failure must surface
    instead of being swallowed into a partial local-only deletion."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "require_remote", side_effect=EnvironmentError("No remote repository found.")
    ):
        with pytest.raises(EnvironmentError, match="No remote repository found"):
            module.delete_branches([Garbage(branch="feature", local=True, remote=True)])

    # nothing may be deleted once the remote resolution failed
    run_operation.assert_not_called()


def test_delete_branches_with_nothing_to_delete_does_not_resolve_the_remote() -> None:
    """An empty selection is a legitimate outcome of the prompt loop, so it must be a no-op: no git
    call, and no remote resolution either, which would fail in a repository without a remote."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "require_remote"
    ) as require_remote:
        module.delete_branches([])

    require_remote.assert_not_called()
    run_operation.assert_not_called()


def test_garbage_flags_are_typed_and_ordered_as_the_deletion_expects() -> None:
    """The tuple positions are what the deletion reads, so a silent reordering of the fields would
    swap the two sides: pin the names against the positions."""
    garbage: Optional[Garbage] = Garbage("feature", True, False)
    assert garbage.branch == "feature"
    assert garbage.local is True
    assert garbage.remote is False


def test_delete_branches_only_absorbs_subprocess_failures() -> None:
    """The loop absorbs a failed deletion so one protected branch does not abort the whole cleanup.
    That tolerance must stay scoped to subprocess failures: widening it to a bare Exception would
    swallow a defect in our own code, silently reporting a branch as handled when the run never
    reached the deletion at all."""
    with patch.object(module, "run_operation", side_effect=InternalStateError("this is our bug")), patch.object(
        module, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        with pytest.raises(InternalStateError, match="this is our bug"):
            module.delete_branches(
                [
                    Garbage(branch="first", local=True, remote=True),
                    Garbage(branch="second", local=True, remote=True),
                ]
            )

    # a swallowed bug would let the loop continue and report a deletion that never happened
    ws_success.assert_not_called()
