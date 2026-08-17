""" Tests for the parse_remote_branches module. """

import subprocess
from types import SimpleNamespace
from unittest.mock import patch
from mega_snake.remote_branches import parse_remote_branches as module


def test_delete_branches_deletes_local_branch_when_it_exists() -> None:
    """When the local ref exists, both the remote push -d and the local `git branch -D`
    must be issued, in that order, and the remote result must not be swallowed by the
    local deletion step."""
    calls: list[str] = []

    def fake_run_operation(cwd: str, _description: str, check: bool = True) -> SimpleNamespace:
        calls.append(cwd)
        if cwd.startswith("git push -d"):
            return SimpleNamespace(stdout="deleted remote", returncode=0)
        if cwd.startswith("git rev-parse"):
            assert check is False
            return SimpleNamespace(stdout="", returncode=0)
        return SimpleNamespace(stdout="deleted local", returncode=0)

    with patch.object(module, "run_operation", side_effect=fake_run_operation) as run_operation, patch.object(
        module, "ws_success"
    ) as ws_success:
        module.delete_branches(["feature/foo"])

    assert run_operation.call_count == 3
    assert any(c.startswith('git push -d origin "feature/foo"') for c in calls)
    assert any(c.startswith('git rev-parse --verify --quiet "refs/heads/feature/foo"') for c in calls)
    assert any(c == 'git branch -D "feature/foo"' for c in calls)
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
        module, "ws_success"
    ) as ws_success:
        module.delete_branches(["someone-elses/branch"])

    assert run_operation.call_count == 2
    assert not any(c.startswith("git branch -D") for c in calls)
    ws_success.assert_called_once_with("deleted remote")


def test_delete_branches_continues_when_remote_deletion_fails() -> None:
    """A failed remote deletion (after retries) must not stop the loop, and must not
    attempt the local branch check/deletion for that branch."""

    def fake_run_operation(cwd: str, _description: str, check: bool = True) -> SimpleNamespace:
        if cwd.startswith("git push -d"):
            raise subprocess.SubprocessError("push failed")
        raise AssertionError("no further git operation should run for a branch whose remote push failed")

    with patch.object(module, "run_operation", side_effect=fake_run_operation) as run_operation, patch.object(
        module, "ws_success"
    ) as ws_success:
        module.delete_branches(["broken-branch"])

    assert run_operation.call_count == 1
    ws_success.assert_not_called()
