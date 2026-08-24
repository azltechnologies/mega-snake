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
    remote_short_name: Optional[str] = None,
    upstream: Optional[str] = None,
) -> SimpleNamespace:
    """Build a GitBranch stand-in for the selection loop.

    The loop only reads the two side markers, the upstream and the display fields of whichever side
    exists, so a namespace is enough — and it keeps the git plumbing out of a test about the
    prompting itself.

    ``remote_short_name`` exists because the two sides are paired by ``local.upstream``, not by
    name, so they are free to disagree (``git branch -m`` is the ordinary way to get there). A
    builder that could only produce matching names would make that case untestable, which is how it
    shipped in the first place.

    Parameters:
        short_name: The local side's name, and the remote one's unless overridden.
        fully_merged: Whether every existing side is merged into the main branch.
        local: Whether the local side exists.
        remote: Whether the remote side exists.
        commit_hash: The tip commit hash shown in the prompt.
        remote_short_name: The remote side's name when it differs from the local one.
        upstream: The local side's upstream reference, as git reports it.

    Raises:
        None

    Returns:
        SimpleNamespace: The GitBranch stand-in.
    """

    def side_of(name: str) -> SimpleNamespace:
        """Build one side of the branch with the display fields the prompt reads."""
        return SimpleNamespace(
            short_name=name,
            str_time="2025-01-01T00:00:00Z",
            mail="a@b",
            hash=commit_hash,
            message="msg",
        )

    local_side = side_of(short_name) if local else None
    if local_side is not None:
        local_side.upstream = upstream
    remote_side = side_of(remote_short_name or short_name) if remote else None
    any_side = local_side if local_side is not None else remote_side
    return SimpleNamespace(
        fully_merged=fully_merged,
        local=local_side,
        remote=remote_side,
        get_any_branch=lambda: any_side,
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

    assert [item.local_name for item in garbage] == ["merged-feature"]
    assert "master" not in [item.local_name for item in garbage], "the main branch must never be offered"
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
        Garbage(local_name="both-sides", remote_name="both-sides"),
        Garbage(local_name="local-leftover", remote_name=None),
        Garbage(local_name=None, remote_name="never-checked-out"),
    ]


def test_parsing_branches_keeps_only_the_accepted_branches() -> None:
    """A 'no' answer skips its branch without stopping the review of the following ones."""
    branches = [branch_double("first"), branch_double("second"), branch_double("third")]
    with patch.object(module, "get_validated_input", side_effect=["n", "y", "n"]):
        garbage = module.parsing_branches(branches)

    assert [item.local_name for item in garbage] == ["second"]


def test_parsing_branches_stops_the_review_on_finalize() -> None:
    """'finalize' ends the review immediately: the remaining branches are never prompted for, and
    what was already selected is kept."""
    branches = [branch_double("first"), branch_double("second"), branch_double("third")]
    with patch.object(module, "get_validated_input", side_effect=["y", "f"]) as prompt:
        garbage = module.parsing_branches(branches)

    assert [item.local_name for item in garbage] == ["first"]
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
        module.Repo, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        run_operation.return_value = SimpleNamespace(stdout="deleted remote", returncode=0)
        module.delete_branches([Garbage(local_name="feature/foo", remote_name="feature/foo")])

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
        module.Repo, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        run_operation.return_value = SimpleNamespace(stdout="deleted remote", returncode=0)
        module.delete_branches([Garbage(local_name=None, remote_name="someone-elses/branch")])

    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert commands == ['git push -d "origin" "someone-elses/branch" --no-verify 2>&1']
    assert not any(command.startswith("git branch -D") for command in commands)
    ws_success.assert_called_once_with("deleted remote")


def test_delete_branches_deletes_local_only_branch_without_touching_the_remote() -> None:
    """A branch whose remote counterpart was already deleted when its pull request was merged only
    survives locally. `git push -d` must NOT be attempted for it — there is nothing on the remote to
    delete and the push would fail — while the local deletion still happens."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module.Repo, "require_remote"
    ) as require_remote, patch.object(module, "ws_success") as ws_success:
        run_operation.return_value = SimpleNamespace(stdout="", returncode=0)
        module.delete_branches([Garbage(local_name="merged-and-pruned", remote_name=None)])

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
        module.Repo, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        module.delete_branches(
            [
                Garbage(local_name="broken-branch", remote_name="broken-branch"),
                Garbage(local_name="good-branch", remote_name="good-branch"),
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
        module.Repo, "require_remote", side_effect=EnvironmentError("No remote repository found.")
    ):
        with pytest.raises(EnvironmentError, match="No remote repository found"):
            module.delete_branches([Garbage(local_name="feature", remote_name="feature")])

    # nothing may be deleted once the remote resolution failed
    run_operation.assert_not_called()


def test_delete_branches_with_nothing_to_delete_does_not_resolve_the_remote() -> None:
    """An empty selection is a legitimate outcome of the prompt loop, so it must be a no-op: no git
    call, and no remote resolution either, which would fail in a repository without a remote."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module.Repo, "require_remote"
    ) as require_remote:
        module.delete_branches([])

    require_remote.assert_not_called()
    run_operation.assert_not_called()


def test_garbage_names_are_ordered_as_the_deletion_expects() -> None:
    """The tuple positions are what the deletion reads, so a silent reordering of the fields would
    send each name to the wrong side. The two names are deliberately different: identical ones
    cannot tell a correct implementation from one that swapped them."""
    garbage: Optional[Garbage] = Garbage("local-side", "remote-side")
    assert garbage.local_name == "local-side"
    assert garbage.remote_name == "remote-side"
    assert garbage.local_name != garbage.remote_name, "the fixture must discriminate the two sides"


def test_delete_branches_only_absorbs_subprocess_failures() -> None:
    """The loop absorbs a failed deletion so one protected branch does not abort the whole cleanup.
    That tolerance must stay scoped to subprocess failures: widening it to a bare Exception would
    swallow a defect in our own code, silently reporting a branch as handled when the run never
    reached the deletion at all."""
    with patch.object(module, "run_operation", side_effect=InternalStateError("this is our bug")), patch.object(
        module.Repo, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        with pytest.raises(InternalStateError, match="this is our bug"):
            module.delete_branches(
                [
                    Garbage(local_name="first", remote_name="first"),
                    Garbage(local_name="second", remote_name="second"),
                ]
            )

    # a swallowed bug would let the loop continue and report a deletion that never happened
    ws_success.assert_not_called()


def test_parsing_branches_excludes_the_main_branch_from_its_remote_side() -> None:
    """The main branch must be unreachable from every side. `get_any_branch()` returns the local one
    whenever it exists, so a pairing whose *remote* side is main — the ordinary result of
    `git checkout -b work origin/main` — used to slip past the guard entirely. The two names are
    deliberately different: with both sides called 'master' the old one-sided check passes too."""
    branches = [
        branch_double("work", remote_short_name="master"),
        branch_double("merged-feature"),
    ]
    with patch.object(module, "get_validated_input", return_value="y") as prompt:
        garbage = module.parsing_branches(branches)

    assert [item.local_name for item in garbage] == ["merged-feature"], "a side of the main branch was offered"
    assert all(item.remote_name != "master" for item in garbage), "the main branch reached the deletion list"
    assert prompt.call_count == 1, "the user was asked about the main branch"


def test_parsing_branches_excludes_a_local_alias_of_a_pruned_main_branch() -> None:
    """When the remote side was pruned there is no remote name left to compare, but the upstream
    still records what the branch tracks. A local branch tracking the main branch is an alias of it
    and must not be offered either."""
    branches = [
        branch_double("work", remote=False, upstream="refs/remotes/origin/master"),
        branch_double("merged-feature", remote=False, upstream="refs/remotes/origin/merged-feature"),
    ]
    with patch.object(module, "get_validated_input", return_value="y"):
        garbage = module.parsing_branches(branches)

    assert [item.local_name for item in garbage] == ["merged-feature"]


def test_parsing_branches_keeps_the_two_names_apart_when_they_disagree() -> None:
    """Sides are paired by `local.upstream`, not by name, so a renamed local branch keeps tracking
    its old remote counterpart. Each name must reach the deletion on its own side — collapsing them
    made the push target a branch the remote does not have."""
    branches = [branch_double("new", remote_short_name="old")]
    with patch.object(module, "get_validated_input", return_value="y") as prompt:
        garbage = module.parsing_branches(branches)

    assert garbage == [Garbage(local_name="new", remote_name="old")]
    # the prompt must not promise a single name for two different branches
    assert "old" in prompt.call_args.args[0], "the prompt hid the remote name the user is agreeing to delete"


def test_delete_branches_uses_each_name_on_its_own_side() -> None:
    """The push must name the branch as the *remote* has it and the local deletion as the *local*
    repository has it. Using one name for both either fails to clean anything or, when a branch of
    that name happens to exist on the remote, deletes one the user was never asked about."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module.Repo, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success"):
        run_operation.return_value = SimpleNamespace(stdout="deleted remote", returncode=0)
        module.delete_branches([Garbage(local_name="new", remote_name="old")])

    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert commands == ['git push -d "origin" "old" --no-verify 2>&1', 'git branch -D "new"']
    assert not any('push -d "origin" "new"' in command for command in commands), "pushed the local name"
    assert not any('git branch -D "old"' in command for command in commands), "deleted the remote name locally"


def test_delete_branches_reports_a_failed_local_deletion_after_a_successful_push() -> None:
    """The worst-shaped failure: the remote copy is gone and the local one survives, so the branch
    now exists only where the user was told it was being removed. It must be reported, and it must
    reach the caller — a swallowed failure let the run announce a clean cleanup."""
    def fake_run_operation(cwd: str, _description: str) -> SimpleNamespace:
        """Succeed on the push, fail on the local deletion."""
        if cwd.startswith("git branch -D"):
            raise subprocess.SubprocessError("branch is checked out")
        return SimpleNamespace(stdout="deleted remote", returncode=0)

    with patch.object(module, "run_operation", side_effect=fake_run_operation), patch.object(
        module.Repo, "require_remote", return_value="origin"
    ), patch.object(module, "ws_error") as ws_error, patch.object(module, "ws_success") as ws_success:
        outcome = module.delete_branches([Garbage(local_name="feature", remote_name="feature")])

    assert outcome.remote_deleted == ["feature"]
    assert outcome.local_deleted == [], "a failed local deletion was counted as done"
    assert outcome.failures == [
        "Local branch 'feature' could not be deleted, but its remote copy 'feature' is already gone; "
        "it now only exists locally"
    ]
    ws_error.assert_called_once_with(outcome.failures[0])
    assert ws_success.call_args_list == [call("deleted remote")], "reported a local deletion that never happened"


def test_delete_branches_reports_a_failed_local_only_deletion() -> None:
    """With no remote side there is nothing to lose, but the branch still survived a deletion the
    user asked for, so it is a warning rather than silence."""
    with patch.object(
        module, "run_operation", side_effect=subprocess.SubprocessError("index.lock")
    ), patch.object(module.Repo, "require_remote") as require_remote, patch.object(
        module, "ws_warning"
    ) as ws_warning, patch.object(module, "ws_error") as ws_error:
        outcome = module.delete_branches([Garbage(local_name="merged-and-pruned", remote_name=None)])

    require_remote.assert_not_called()
    assert outcome == module.DeletionOutcome(
        remote_deleted=[],
        local_deleted=[],
        failures=["Local branch 'merged-and-pruned' could not be deleted; it is still present"],
    )
    ws_warning.assert_called_once_with(outcome.failures[0])
    ws_error.assert_not_called(), "a local-only leftover is not the destructive half-deleted case"


def test_delete_branches_leaves_the_local_copy_alone_and_says_so_when_the_push_fails() -> None:
    """The policy is unchanged by the split — the remote copy survived, so the local one is kept —
    but it is now stated instead of being an unannounced side effect of a shared except."""
    with patch.object(
        module, "run_operation", side_effect=subprocess.SubprocessError("push failed")
    ) as run_operation, patch.object(module.Repo, "require_remote", return_value="origin"), patch.object(
        module, "ws_warning"
    ) as ws_warning:
        outcome = module.delete_branches([Garbage(local_name="feature", remote_name="feature")])

    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert not any(command.startswith("git branch -D") for command in commands), "deleted the surviving copy"
    assert outcome.failures == [
        "Remote branch 'feature' could not be deleted from 'origin'; it is still there",
        "Local branch 'feature' was left alone because its remote copy 'feature' could not be deleted",
    ]
    assert [issued.args[0] for issued in ws_warning.call_args_list] == outcome.failures


def test_delete_branches_reports_what_it_deleted() -> None:
    """The outcome is the only thing standing between the caller and a blanket success line, so a
    clean run has to be reported side by side, under each side's own name."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module.Repo, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success"):
        run_operation.return_value = SimpleNamespace(stdout="deleted remote", returncode=0)
        outcome = module.delete_branches(
            [Garbage(local_name="new", remote_name="old"), Garbage(local_name=None, remote_name="theirs")]
        )

    assert outcome == module.DeletionOutcome(
        remote_deleted=["old", "theirs"], local_deleted=["new"], failures=[]
    )
