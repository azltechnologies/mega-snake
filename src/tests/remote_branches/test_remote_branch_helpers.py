"""Additional tests for remote branch helpers."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch
import subprocess

import pytest

from mega_snake.remote_branches.remote_branch import Commit, RemoteBranch
from mega_snake.remote_branches.parse_remote_branches import define_branches, parsing_branches, delete_branches
from mega_snake.remote_branches.details_remote_branches import execute
from mega_snake.remote_branches.cleanup_remote_branches import remote_branches_cleanup


def test_commit_and_remote_branch_builders() -> None:
    """Cover commit/branch builders and formatting."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),
            SimpleNamespace(stdout="msg\nline2"),
            SimpleNamespace(stdout="1735689600"),
            SimpleNamespace(stdout=" remotes/origin/main "),
            SimpleNamespace(stdout="author@test.com"),
            SimpleNamespace(stdout="def456"),
        ]
        branch = RemoteBranch.from_branch("remotes/origin/feature", "A", "main", "origin")
        assert branch.branch == "feature"
        assert branch.merged_on_main
        assert "author@test.com" == branch.mail
        assert "abc123" == branch.commit.commit_hash
        assert "|" in branch.printing_remote_branches_details()

    base = RemoteBranch.from_string("1|abc|2025-01-01T00:00:00Z|a@b|main|def|msg")
    older = RemoteBranch("old", False, Commit.from_strings("old", "2024-01-01T00:00:00Z", "m"), "a@b", "z")
    assert older < base
    assert define_branches("") is None
    with pytest.raises(ValueError):
        RemoteBranch.from_string("")


def test_parse_and_delete_helpers() -> None:
    """Cover parse/delete helper logic."""
    branch_main = RemoteBranch("main", True, Commit.from_strings("a", "2025-01-01T00:00:00Z", "m"), "a@b", "x")
    branch_feature = RemoteBranch("feature", True, Commit.from_strings("b", "2025-01-02T00:00:00Z", "m"), "a@b", "x")
    with patch("mega_snake.remote_branches.parse_remote_branches.get_main_branch", return_value="main"), patch(
        "mega_snake.remote_branches.parse_remote_branches.get_validated_input", return_value="y"
    ):
        garbage = parsing_branches([branch_main, branch_feature], "origin")
        assert garbage == ["feature"]

    with patch("mega_snake.remote_branches.parse_remote_branches.run_operation") as run_operation:
        run_operation.return_value.stdout = "deleted"
        delete_branches(["f1"])
        run_operation.side_effect = subprocess.SubprocessError()
        delete_branches(["f2"])


def test_details_and_cleanup_commands() -> None:
    """Cover details and cleanup command flows."""
    remote_branch = RemoteBranch("feature", True, Commit.from_strings("abc", "2025-01-01T00:00:00Z", "msg"), "a@b", "x")

    with patch("mega_snake.remote_branches.details_remote_branches.get_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.details_remote_branches.get_main_branch", return_value="main"
    ), patch(
        "mega_snake.remote_branches.details_remote_branches.get_property", return_value="/tmp"
    ), patch(
        "mega_snake.remote_branches.details_remote_branches.os.path.exists", return_value=False
    ), patch(
        "mega_snake.remote_branches.details_remote_branches.RemoteBranch.from_branch", return_value=remote_branch
    ), patch(
        "mega_snake.remote_branches.details_remote_branches.run_operation"
    ) as run_operation, patch(
        "builtins.open", mock_open()
    ):
        run_operation.side_effect = [
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="  remotes/origin/feature"),
            SimpleNamespace(stdout=""),
        ]
        execute("A")
        with pytest.raises(ValueError):
            execute("X")

    with patch("mega_snake.remote_branches.cleanup_remote_branches.get_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.get_validated_input", side_effect=["n"]
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.get_output_file", return_value="/tmp/branches.txt"
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.os.path.exists", return_value=True
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.open",
        mock_open(read_data="1|abc|2025-01-01T00:00:00Z|a@b|feature|x|msg"),
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.parsing_branches", return_value=["feature"]
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.delete_branches"
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.run_operation"
    ):
        remote_branches_cleanup.callback()

    with patch("mega_snake.remote_branches.cleanup_remote_branches.get_remote", return_value=None):
        with pytest.raises(LookupError):
            remote_branches_cleanup.callback()

    with patch("mega_snake.remote_branches.cleanup_remote_branches.get_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.get_validated_input", side_effect=["y", "m"]
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.remote_branches_details"
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.get_output_file", return_value="/tmp/missing.txt"
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.os.path.exists", return_value=False
    ):
        with pytest.raises(FileNotFoundError):
            remote_branches_cleanup.callback()

    with patch("mega_snake.remote_branches.cleanup_remote_branches.get_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.get_validated_input", side_effect=["n"]
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.get_output_file", return_value="/tmp/branches.txt"
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.os.path.exists", return_value=True
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.open", mock_open(read_data="")
    ):
        with pytest.raises(IOError):
            remote_branches_cleanup.callback()
