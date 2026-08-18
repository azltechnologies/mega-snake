""" Tests for the parse_remote_branches module. """

import subprocess
from types import SimpleNamespace
from unittest.mock import call, patch

from mega_snake.remote_branches import parse_remote_branches as module


def _remote_and_local_exist(ref: str) -> bool:
    """Reference probe answering that both sides of every branch exist."""
    return ref.startswith("refs/remotes/") or ref.startswith("refs/heads/")


def test_delete_branches_deletes_both_sides_when_both_references_exist() -> None:
    """When the branch exists on the remote and locally, the operations must occur in order:
    (1) remote push -d, (2) local branch -D, each preceded by the probe for its own reference.
    The remote success message must be reported, followed by the local deletion message."""
    probed: list[str] = []

    def fake_ref_exists(ref: str) -> bool:
        probed.append(ref)
        return _remote_and_local_exist(ref)

    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "ref_exists", side_effect=fake_ref_exists
    ), patch.object(module, "require_remote", return_value="origin"), patch.object(
        module, "ws_success"
    ) as ws_success, patch.object(
        module, "ws_info"
    ) as ws_info:
        run_operation.return_value = SimpleNamespace(stdout="deleted remote", returncode=0)
        module.delete_branches(["feature/foo"])

    assert probed == ["refs/remotes/origin/feature/foo", "refs/heads/feature/foo"]
    assert run_operation.call_args_list == [
        call('git push -d "origin" "feature/foo" --no-verify 2>&1', "Deleting remote branch feature/foo"),
        call('git branch -D "feature/foo"', "Deleting local branch feature/foo"),
    ]
    assert ws_success.call_args_list == [
        call("deleted remote"),
        call("Local branch 'feature/foo' deleted successfully"),
    ]
    ws_info.assert_not_called()


def test_delete_branches_skips_local_delete_when_branch_never_checked_out() -> None:
    """A remote branch from another author that was never checked out locally has no matching local
    reference. `git branch -D` must NOT be attempted for it (it would fail), while the remote
    deletion still happens and is reported."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "ref_exists", side_effect=lambda ref: ref.startswith("refs/remotes/")
    ), patch.object(module, "require_remote", return_value="origin"), patch.object(
        module, "ws_success"
    ) as ws_success:
        run_operation.return_value = SimpleNamespace(stdout="deleted remote", returncode=0)
        module.delete_branches(["someone-elses/branch"])

    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert commands == ['git push -d "origin" "someone-elses/branch" --no-verify 2>&1']
    assert not any(command.startswith("git branch -D") for command in commands)
    ws_success.assert_called_once_with("deleted remote")


def test_delete_branches_deletes_local_only_branch_without_touching_the_remote() -> None:
    """A branch whose remote counterpart was already deleted when its pull request was merged only
    survives locally. `git push -d` must NOT be attempted for it — there is nothing on the remote to
    delete and the push would fail — while the local deletion still happens."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "ref_exists", side_effect=lambda ref: ref.startswith("refs/heads/")
    ), patch.object(module, "require_remote", return_value="origin"), patch.object(
        module, "ws_success"
    ) as ws_success, patch.object(
        module, "ws_info"
    ) as ws_info:
        run_operation.return_value = SimpleNamespace(stdout="", returncode=0)
        module.delete_branches(["merged-and-pruned"])

    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert commands == ['git branch -D "merged-and-pruned"']
    assert not any(command.startswith("git push -d") for command in commands)
    ws_info.assert_called_once_with(
        "Branch 'merged-and-pruned' has no counterpart on 'origin'; skipping the remote deletion"
    )
    ws_success.assert_called_once_with("Local branch 'merged-and-pruned' deleted successfully")


def test_delete_branches_continues_when_remote_deletion_fails() -> None:
    """A failed remote deletion must not delete the local copy of that branch, and must not stop the
    loop: the next branch has to complete its full remote + local deletion cycle."""

    def fake_run_operation(cwd: str, _description: str) -> SimpleNamespace:
        if "broken-branch" in cwd:
            raise subprocess.SubprocessError("push failed")
        return SimpleNamespace(stdout="deleted remote", returncode=0)

    with patch.object(module, "run_operation", side_effect=fake_run_operation) as run_operation, patch.object(
        module, "ref_exists", side_effect=_remote_and_local_exist
    ), patch.object(module, "require_remote", return_value="origin"), patch.object(
        module, "ws_success"
    ) as ws_success:
        module.delete_branches(["broken-branch", "good-branch"])

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


def test_delete_branches_with_nothing_to_delete_does_not_resolve_the_remote() -> None:
    """An empty selection is a legitimate outcome of the prompt loop, so it must be a no-op: no git
    call, and no remote resolution either, which would fail in a repository without a remote."""
    with patch.object(module, "run_operation") as run_operation, patch.object(
        module, "ref_exists"
    ) as ref_exists, patch.object(module, "require_remote") as require_remote:
        module.delete_branches([])

    require_remote.assert_not_called()
    ref_exists.assert_not_called()
    run_operation.assert_not_called()
