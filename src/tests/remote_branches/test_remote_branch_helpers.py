"""Additional tests for remote branch helpers."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, mock_open, patch
import subprocess

import click
import pytest

from mega_snake.remote_branches.remote_branch import Commit, RemoteBranch
from mega_snake.util.formatting import InternalStateError
from mega_snake.remote_branches.parse_remote_branches import define_branches, parsing_branches, delete_branches
from mega_snake.remote_branches.details_remote_branches import execute, get_local_only_branches
from mega_snake.remote_branches.cleanup_remote_branches import remote_branches_cleanup


def test_commit_and_remote_branch_builders() -> None:
    """Cover commit/branch builders and formatting."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),
            SimpleNamespace(stdout="msg\nline2"),
            SimpleNamespace(stdout="1735689600"),
            SimpleNamespace(stdout=" remotes/origin/main "),
            SimpleNamespace(stdout="def456"),
            SimpleNamespace(stdout="author@test.com"),
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


def test_from_branch_detects_squash_merge() -> None:
    """A branch tip that is no longer an ancestor of main, but whose combined diff was already
    applied as a single squashed commit, should still be flagged as merged_on_main."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),  # commit hash
            SimpleNamespace(stdout="msg"),  # commit message
            SimpleNamespace(stdout="1735689600"),  # commit date
            SimpleNamespace(stdout=" remotes/origin/feature "),  # contains check: no main match
            SimpleNamespace(stdout="base789"),  # merge-base
            SimpleNamespace(stdout="+ c1 one\n+ c2 two"),  # cherry branch: individual commits not on main
            SimpleNamespace(stdout="tree456"),  # rev-parse tree
            SimpleNamespace(stdout="synthetic123"),  # commit-tree
            SimpleNamespace(stdout="- synthetic123 msg"),  # cherry synthetic: combined diff already applied
            SimpleNamespace(stdout="author@test.com"),  # mail
        ]
        branch = RemoteBranch.from_branch("remotes/origin/feature", "A", "main", "origin")
        assert branch.merged_on_main


def test_from_branch_detects_rebase_merge() -> None:
    """A rebase merge replays every branch commit individually on main, so the branch is merged
    once all of its commits are reported as already applied, without building a synthetic commit."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),  # commit hash
            SimpleNamespace(stdout="msg"),  # commit message
            SimpleNamespace(stdout="1735689600"),  # commit date
            SimpleNamespace(stdout=" remotes/origin/feature "),  # contains check: no main match
            SimpleNamespace(stdout="base789"),  # merge-base
            SimpleNamespace(stdout="- c1 one\n- c2 two"),  # cherry branch: every commit already applied
            SimpleNamespace(stdout="author@test.com"),  # mail
        ]
        branch = RemoteBranch.from_branch("remotes/origin/feature", "A", "main", "origin")
        assert branch.merged_on_main
        assert run_operation.call_count == 7


def test_from_branch_partially_applied_branch_stays_unmerged() -> None:
    """A branch with only some of its commits applied on main is not a rebase merge, and it is not
    a squash merge either when its combined diff is missing, so it remains flagged as not merged."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),  # commit hash
            SimpleNamespace(stdout="msg"),  # commit message
            SimpleNamespace(stdout="1735689600"),  # commit date
            SimpleNamespace(stdout=" remotes/origin/feature "),  # contains check: no main match
            SimpleNamespace(stdout="base789"),  # merge-base
            SimpleNamespace(stdout="- c1 one\n+ c2 two"),  # cherry branch: only one commit applied
            SimpleNamespace(stdout="tree456"),  # rev-parse tree
            SimpleNamespace(stdout="synthetic123"),  # commit-tree
            SimpleNamespace(stdout="+ synthetic123 msg"),  # cherry synthetic: not applied yet
            SimpleNamespace(stdout="author@test.com"),  # mail
        ]
        branch = RemoteBranch.from_branch("remotes/origin/feature", "A", "main", "origin")
        assert not branch.merged_on_main


def test_from_branch_compares_against_the_remote_main_reference() -> None:
    """History comparisons must use the remote main reference, not the possibly stale local branch."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),  # commit hash
            SimpleNamespace(stdout="msg"),  # commit message
            SimpleNamespace(stdout="1735689600"),  # commit date
            SimpleNamespace(stdout=" remotes/origin/feature "),  # contains check: no main match
            SimpleNamespace(stdout="base789"),  # merge-base
            SimpleNamespace(stdout="- c1 one"),  # cherry branch: every commit already applied
            SimpleNamespace(stdout="author@test.com"),  # mail
        ]
        RemoteBranch.from_branch("remotes/origin/feature", "A", "main", "origin")
        commands = [call.args[0] for call in run_operation.call_args_list]
        assert "git merge-base remotes/origin/feature remotes/origin/main" in commands
        assert "git cherry remotes/origin/main remotes/origin/feature" in commands


def test_from_branch_applies_the_requested_filter() -> None:
    """The filter drops the branches that don't match it: 'M' keeps only merged branches and 'U'
    only the ones still carrying unique work."""
    merged_calls = [
        SimpleNamespace(stdout="abc123\n"),  # commit hash
        SimpleNamespace(stdout="msg"),  # commit message
        SimpleNamespace(stdout="1735689600"),  # commit date
        SimpleNamespace(stdout=" remotes/origin/main "),  # contains check: merged into main
        SimpleNamespace(stdout="base789"),  # merge-base
        SimpleNamespace(stdout="author@test.com"),  # mail
    ]
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = list(merged_calls)
        assert RemoteBranch.from_branch("remotes/origin/feature", "U", "main", "origin") is None

    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),  # commit hash
            SimpleNamespace(stdout="msg"),  # commit message
            SimpleNamespace(stdout="1735689600"),  # commit date
            SimpleNamespace(stdout=" remotes/origin/feature "),  # contains check: no main match
            SimpleNamespace(stdout="base789"),  # merge-base
            SimpleNamespace(stdout="+ c1 one"),  # cherry branch: commit not applied
            SimpleNamespace(stdout="tree456"),  # rev-parse tree
            SimpleNamespace(stdout="synthetic123"),  # commit-tree
            SimpleNamespace(stdout="+ synthetic123 msg"),  # cherry synthetic: not applied
        ]
        assert RemoteBranch.from_branch("remotes/origin/feature", "M", "main", "origin") is None


def test_from_branch_rejects_a_branch_it_cannot_relate_to_the_remote() -> None:
    """Quoted references are accepted, but a reference that doesn't belong to the remote, or a commit
    no branch contains, cannot be described and is reported instead of silently skipped."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),
            SimpleNamespace(stdout="msg"),
            SimpleNamespace(stdout="1735689600"),
            SimpleNamespace(stdout=""),  # contains check: no branch holds the commit
        ]
        with pytest.raises(InternalStateError, match="not found in any branch"):
            RemoteBranch.from_branch("'remotes/origin/feature'", "A", "main", "origin")

    with pytest.raises(InternalStateError, match="Unable to parse local branch name"):
        RemoteBranch.from_branch('"remotes/other/feature"', "A", "main", "origin")


def test_from_branch_describes_a_local_only_branch_against_the_remote_main() -> None:
    """A branch that only exists locally carries no `remotes/<remote>/` prefix, so it must be
    accepted as its own local name instead of being rejected — and it must still be judged against
    the remote main reference, never against the local main copy, which may not have seen the merge."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="abc123\n"),  # commit hash
            SimpleNamespace(stdout="msg"),  # commit message
            SimpleNamespace(stdout="1735689600"),  # commit date
            SimpleNamespace(stdout="  feature\n  remotes/origin/main"),  # contains check: merged into main
            SimpleNamespace(stdout="base789"),  # merge-base
            SimpleNamespace(stdout="author@test.com"),  # mail
        ]
        branch = RemoteBranch.from_branch("feature", "M", "main", "origin", local_only=True)

    assert branch is not None
    assert branch.branch == "feature"
    assert branch.merged_on_main
    commands = [issued.args[0] for issued in run_operation.call_args_list]
    assert "git merge-base feature remotes/origin/main" in commands
    assert "git merge-base feature main" not in commands


def test_from_branch_still_rejects_an_unrelated_remote_reference() -> None:
    """The local-only escape hatch must not weaken the guard for remote references: one that cannot
    be related back to the remote it was selected from is still a bug, not a local branch."""
    with pytest.raises(InternalStateError, match="Unable to parse local branch name"):
        RemoteBranch.from_branch("remotes/other/feature", "A", "main", "origin", local_only=False)


def test_get_local_only_branches_keeps_only_the_untracked_ones() -> None:
    """Local branches that still exist on the remote are already reported through the remote listing,
    and the main branch is never a deletion candidate, so both are excluded. Everything else — the
    branches a remote-only listing structurally cannot see — is kept."""
    with patch("mega_snake.remote_branches.details_remote_branches.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(
            stdout="main\nfeature\nmerged-and-pruned\n  spaced-out  \n\n"
        )
        local_only = get_local_only_branches(
            ["remotes/origin/feature", "  remotes/origin/release/1.0  "], "origin", "main"
        )

    assert local_only == ["merged-and-pruned", "spaced-out"]
    assert "feature" not in local_only, "a branch that still exists on the remote must not be listed twice"
    assert "main" not in local_only, "the main branch must never be offered for deletion"
    run_operation.assert_called_once_with(
        "git for-each-ref --format='%(refname:short)' refs/heads", "Getting local branches"
    )


def test_get_local_only_branches_without_local_branches() -> None:
    """A repository whose only local branch is the main one yields no candidates, rather than an
    empty-string entry from splitting empty output."""
    with patch("mega_snake.remote_branches.details_remote_branches.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout="")
        assert get_local_only_branches(["remotes/origin/main"], "origin", "main") == []


def test_execute_reports_local_branches_with_no_remote_counterpart() -> None:
    """A branch merged through a pull request and pruned from the remote survives only locally, so
    the remote listing cannot see it. It must still reach the report, described as a local-only
    branch, alongside the branches that do exist on the remote."""
    remote_branch = RemoteBranch("feature", True, Commit.from_strings("abc", "2025-01-01T00:00:00Z", "msg"), "a@b", "x")
    local_branch = RemoteBranch("gone", True, Commit.from_strings("def", "2025-01-02T00:00:00Z", "msg"), "a@b", "x")
    written = mock_open()

    with patch("mega_snake.remote_branches.details_remote_branches.require_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.details_remote_branches.get_main_branch", return_value="main"
    ), patch("mega_snake.remote_branches.details_remote_branches.get_property", return_value="/tmp"), patch(
        "mega_snake.remote_branches.details_remote_branches.os.path.exists", return_value=False
    ), patch(
        "mega_snake.remote_branches.details_remote_branches.RemoteBranch.from_branch",
        side_effect=[remote_branch, local_branch],
    ) as from_branch, patch(
        "mega_snake.remote_branches.details_remote_branches.run_operation"
    ) as run_operation, patch(
        "builtins.open", written
    ):
        run_operation.side_effect = [
            SimpleNamespace(stdout=""),  # git fetch --all --prune
            SimpleNamespace(stdout="  main\n  gone\n  remotes/origin/feature"),  # git branch -a
            SimpleNamespace(stdout="main\ngone"),  # git for-each-ref: 'gone' has no remote counterpart
            SimpleNamespace(stdout=""),  # code <output file>
        ]
        execute("A")

    assert from_branch.call_args_list == [
        call("remotes/origin/feature", "A", "main", "origin"),
        call("gone", "A", "main", "origin", local_only=True),
    ]
    report = "".join(chunk.args[0] for chunk in written().write.call_args_list)
    reported = [line.split("|")[4].strip() for line in report.splitlines() if line.strip()]
    assert reported == ["gone", "feature"], "both sources must reach the report, newest commit first"


def test_is_squash_or_rebase_merged_without_common_ancestor() -> None:
    """Without a common ancestor there is nothing to compare, so no git calls are made."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        assert RemoteBranch.is_squash_or_rebase_merged("remotes/origin/feature", "remotes/origin/main", "") is False
        run_operation.assert_not_called()


def test_rebase_check_without_own_commits_falls_through_to_the_squash_check() -> None:
    """An empty git cherry output means the branch has no commits of its own, a case left to the
    ancestry check, so it is not reported as rebased and the squash check still gets its turn."""
    with patch("mega_snake.remote_branches.remote_branch.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout=""),  # cherry branch: no commits of its own
            SimpleNamespace(stdout="tree456"),  # rev-parse tree
            SimpleNamespace(stdout="synthetic123"),  # commit-tree
            SimpleNamespace(stdout="+ synthetic123 msg"),  # cherry synthetic: not applied
        ]
        merged = RemoteBranch.is_squash_or_rebase_merged("remotes/origin/feature", "remotes/origin/main", "base789")
    assert merged is False
    assert run_operation.call_count == 4


def test_parse_and_delete_helpers() -> None:
    """Cover parse/delete helper logic."""
    branch_main = RemoteBranch("main", True, Commit.from_strings("a", "2025-01-01T00:00:00Z", "m"), "a@b", "x")
    branch_feature = RemoteBranch("feature", True, Commit.from_strings("b", "2025-01-02T00:00:00Z", "m"), "a@b", "x")
    with patch("mega_snake.remote_branches.parse_remote_branches.get_main_branch", return_value="main"), patch(
        "mega_snake.remote_branches.parse_remote_branches.get_validated_input", return_value="y"
    ):
        garbage = parsing_branches([branch_main, branch_feature], "origin")
        assert garbage == ["feature"]

    with patch("mega_snake.remote_branches.parse_remote_branches.require_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.parse_remote_branches.ref_exists", return_value=True
    ), patch("mega_snake.remote_branches.parse_remote_branches.run_operation") as run_operation:
        run_operation.return_value.stdout = "deleted"
        run_operation.return_value.returncode = 0
        delete_branches(["f1"])
        run_operation.side_effect = subprocess.SubprocessError()
        delete_branches(["f2"])


def test_details_and_cleanup_commands() -> None:
    """Cover details and cleanup command flows."""
    remote_branch = RemoteBranch("feature", True, Commit.from_strings("abc", "2025-01-01T00:00:00Z", "msg"), "a@b", "x")

    with patch("mega_snake.remote_branches.details_remote_branches.require_remote", return_value="origin"), patch(
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
            SimpleNamespace(stdout=""),  # git fetch --all --prune
            SimpleNamespace(stdout="  remotes/origin/feature"),  # git branch -a
            SimpleNamespace(stdout="feature"),  # git for-each-ref: only the tracked branch
            SimpleNamespace(stdout=""),  # code <output file>
        ]
        execute("A")
        with pytest.raises(ValueError):
            execute("X")

    with patch("mega_snake.remote_branches.cleanup_remote_branches.require_remote", return_value="origin"), patch(
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

    with patch(
        "mega_snake.remote_branches.cleanup_remote_branches.require_remote",
        side_effect=click.ClickException("No remote repository found."),
    ):
        with pytest.raises(click.ClickException, match="No remote repository found"):
            remote_branches_cleanup.callback()

    with patch("mega_snake.remote_branches.cleanup_remote_branches.require_remote", return_value="origin"), patch(
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

    with patch("mega_snake.remote_branches.cleanup_remote_branches.require_remote", return_value="origin"), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.get_validated_input", side_effect=["n"]
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.get_output_file", return_value="/tmp/branches.txt"
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.os.path.exists", return_value=True
    ), patch(
        "mega_snake.remote_branches.cleanup_remote_branches.open", mock_open(read_data="")
    ):
        with pytest.raises(ValueError, match="No branches found in the file"):
            remote_branches_cleanup.callback()
