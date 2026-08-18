""" Tests for the parse_remote_branches module. """

import subprocess
from types import SimpleNamespace
from unittest.mock import call, patch

from mega_snake.remote_branches import parse_remote_branches as module


def test_delete_branches_deletes_local_branch_when_it_exists() -> None:
    """When the local ref exists, the operations must occur in order:
    (1) remote push -d, (2) local ref check, (3) local branch -D.
    The remote success message must be reported, followed by the local deletion message."""

    def fake_run_operation(cwd: str, _description: str, check: bool = True) -> SimpleNamespace:
        if cwd.startswith("git push -d"):
            return SimpleNamespace(stdout="deleted remote", returncode=0)
        if cwd.startswith("git rev-parse"):
            assert check is False
            return SimpleNamespace(stdout="", returncode=0)
        return SimpleNamespace(stdout="deleted local", returncode=0)

    with patch.object(module, "run_operation", side_effect=fake_run_operation) as run_operation, patch.object(
        module, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        module.delete_branches(["feature/foo"])

    assert run_operation.call_count == 3
    first_call, second_call, third_call = run_operation.call_args_list
    assert first_call == call('git push -d "origin" "feature/foo" --no-verify 2>&1', "Deleting remote branch feature/foo")
    assert second_call == call(
        'git rev-parse --verify --quiet "refs/heads/feature/foo"',
        "Checking if local branch feature/foo exists",
        check=False,
    )
    assert third_call == call('git branch -D "feature/foo"', "Deleting local branch feature/foo")
    assert ws_success.call_count == 2


def test_delete_branches_skips_local_delete_when_branch_never_checked_out() -> None:
    """A remote branch from another author that was never checked out locally has no
    matching local ref. `git branch -D` must NOT be attempted for it (it would fail),
    while the remote deletion still succeeds and is reported."""
    calls: list[str] = []

    def fake_run_operation(cwd: str, _description: str, check: bool = True) -> SimpleNamespace:
        calls.append(cwd)
        if cwd.startswith("git push -d"):
            return SimpleNamespace(stdout="deleted remote", returncode=0)
        if cwd.startswith("git rev-parse"):
            assert check is False
            return SimpleNamespace(stdout="", returncode=1)
        raise AssertionError("git branch -D must not be called when the local ref does not exist")

    with patch.object(module, "run_operation", side_effect=fake_run_operation) as run_operation, patch.object(
        module, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        module.delete_branches(["someone-elses/branch"])

    assert run_operation.call_count == 2
    assert not any(c.startswith("git branch -D") for c in calls)
    ws_success.assert_called_once_with("deleted remote")


def test_delete_branches_continues_when_remote_deletion_fails() -> None:
    """A failed remote deletion must not stop the loop. The function must continue to the
    next branch and complete its full remote + local deletion cycle for that branch."""
    calls: list[str] = []

    def fake_run_operation(cwd: str, _description: str, check: bool = True) -> SimpleNamespace:
        calls.append(cwd)
        if "broken-branch" in cwd and cwd.startswith("git push -d"):
            raise subprocess.SubprocessError("push failed")
        if "good-branch" in cwd and cwd.startswith("git push -d"):
            return SimpleNamespace(stdout="deleted remote", returncode=0)
        if "good-branch" in cwd and cwd.startswith("git rev-parse"):
            return SimpleNamespace(stdout="", returncode=1)
        raise AssertionError(f"Unexpected call: {cwd}")

    with patch.object(module, "run_operation", side_effect=fake_run_operation) as run_operation, patch.object(
        module, "require_remote", return_value="origin"
    ), patch.object(module, "ws_success") as ws_success:
        module.delete_branches(["broken-branch", "good-branch"])

    assert run_operation.call_count == 3
    assert any("broken-branch" in c and c.startswith("git push -d") for c in calls)
    assert not any("good-branch" in c and c.startswith("git branch -D") for c in calls)
    ws_success.assert_called_once_with("deleted remote")
