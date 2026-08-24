"""Tests for the remote-branches-details command."""

import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Iterator, Optional
from unittest.mock import mock_open, patch

import pytest

from mega_snake.remote_branches import details_remote_branches as module
from mega_snake.remote_branches.remote_branch import GitBranch
from mega_snake.util.repo import Repo

LOCAL_MAIN_HASH = "localmain111"
REMOTE_MAIN_HASH = "remotemain222"


@pytest.fixture(autouse=True)
def seeded_repo() -> Iterator[None]:
    """Seed the Repo snapshot so the report header reads real values without resolving them."""
    Repo.reset()
    Repo.REMOTE = "origin"
    Repo.MAIN_BRANCH = "master"
    Repo.MAIN_LOCAL_HASH = LOCAL_MAIN_HASH
    Repo.MAIN_REMOTE_HASH = REMOTE_MAIN_HASH
    Repo._INITIALIZED = True
    yield
    Repo.reset()


class BranchDouble:
    """GitBranch stand-in exposing what the command reads: the filter flag, the sort key and the
    rendered row.

    It is a real class rather than a namespace because the command sorts the list, and Python
    resolves ``__lt__`` on the type — an instance attribute would never be consulted.
    """

    def __init__(self, short_name: str, fully_merged: bool, row: Optional[str] = None, when: int = 2025) -> None:
        """Build the double for one branch.

        Parameters:
            short_name: The branch name the report shows.
            fully_merged: Whether every existing side of the branch is merged.
            row: The markdown row to render, defaulting to a minimal one carrying the name.
            when: The year of the tip commit, used as the sort key.

        Raises:
            None

        Returns:
            None
        """
        self.fully_merged = fully_merged
        self.row = row if row is not None else f"| {short_name} |"
        self.side = SimpleNamespace(short_name=short_name, dt_time=datetime(when, 1, 1, tzinfo=timezone.utc))

    def get_any_branch(self) -> SimpleNamespace:
        """Return the single side this double carries."""
        return self.side

    def to_markdown_row(self) -> str:
        """Return the scripted markdown row."""
        return self.row

    def __lt__(self, other: "BranchDouble") -> bool:
        """Order by tip commit date, as GitBranch does."""
        return self.side.dt_time < other.side.dt_time


def branch_double(short_name: str, fully_merged: bool, row: Optional[str] = None, when: int = 2025) -> BranchDouble:
    """Build a GitBranch stand-in for the command tests."""
    return BranchDouble(short_name, fully_merged, row, when)


@pytest.mark.parametrize("bad_filter", ["X", "m", "", "AM"])
def test_execute_rejects_an_unknown_filter_before_touching_the_repository(bad_filter: str) -> None:
    """An invalid filter is a bad invocation: it must be refused before any git work happens, so a
    typo never triggers the fetch prompt or the enumeration."""
    with patch.object(module, "BranchLoader") as loader:
        with pytest.raises(ValueError, match="Invalid filter"):
            module.execute(bad_filter)
    loader.from_repository.assert_not_called()


def test_execute_without_branches_fails_instead_of_writing_an_empty_report() -> None:
    """A repository with no branches at all has nothing to describe; writing an empty file would
    hand the user a report that looks valid."""
    with patch.object(module, "BranchLoader") as loader, patch("builtins.open", mock_open()) as opened:
        loader.from_repository.return_value = []
        with pytest.raises(ValueError, match="No branches found"):
            module.execute("A")
    opened.assert_not_called()


@pytest.mark.parametrize(
    "filter_by,expected",
    [
        ("A", ["merged-one", "unmerged-one"]),
        ("M", ["merged-one"]),
        ("U", ["unmerged-one"]),
    ],
)
def test_execute_applies_the_requested_filter(filter_by: str, expected: list[str]) -> None:
    """'M' keeps only fully merged branches, 'U' only the rest, and 'A' keeps both — so each filter
    excludes exactly what the other one keeps."""
    branches = [branch_double("merged-one", True), branch_double("unmerged-one", False)]
    written: list[str] = []

    with patch.object(module, "BranchLoader") as loader, patch.object(module, "run_operation"), patch.object(
        module, "get_output_file", return_value="/tmp/report.md"
    ), patch("builtins.open", mock_open()) as opened:
        loader.from_repository.return_value = branches
        opened.return_value.write.side_effect = written.append
        module.execute(filter_by)

    report = "".join(written)
    reported = [line.split("|")[1].strip() for line in report.splitlines() if line.startswith("| ")]
    listed = [name for name in reported if name in {"merged-one", "unmerged-one"}]
    assert listed == expected
    for excluded in {"merged-one", "unmerged-one"} - set(expected):
        assert excluded not in listed, f"filter '{filter_by}' must exclude {excluded}"


def test_execute_writes_the_report_newest_first_and_opens_it() -> None:
    """The report is sorted by tip commit date, newest first, written to the resolved output file
    and then opened in the editor."""
    branches = [branch_double("older", True, when=2024), branch_double("newer", True, when=2026)]
    written: list[str] = []

    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "run_operation"
    ) as run_operation, patch.object(module, "get_output_file", return_value="/tmp/report.md"), patch(
        "builtins.open", mock_open()
    ) as opened:
        loader.from_repository.return_value = branches
        opened.return_value.write.side_effect = written.append
        module.execute("A")

    report = "".join(written)
    assert report.index("| newer |") < report.index("| older |"), "newest commit must come first"
    opened.assert_called_once_with("/tmp/report.md", "w", encoding="utf-8")
    run_operation.assert_called_once_with("code /tmp/report.md", "opening remote branches file")


def test_execute_overwrites_a_previous_report_rather_than_appending() -> None:
    """Opening in append mode would stack every run's table into one unusable file, so the write
    mode itself is part of the contract."""
    with patch.object(module, "BranchLoader") as loader, patch.object(module, "run_operation"), patch.object(
        module, "get_output_file", return_value="/tmp/report.md"
    ), patch("builtins.open", mock_open()) as opened:
        loader.from_repository.return_value = [branch_double("feature", True)]
        module.execute("A")

    mode = opened.call_args.args[1]
    assert mode == "w"
    assert mode != "a", "appending would stack the tables of every run"


def test_output_file_is_a_markdown_file_under_the_working_path() -> None:
    """The report is markdown now, so the extension must say so — an editor renders it by type."""
    with patch.object(module, "get_property", return_value="/repo/workspace_temp") as get_property:
        assert module.get_output_file() == "/repo/workspace_temp/remote_branches.md"
    get_property.assert_called_once_with("working_path")


def test_report_header_carries_the_repository_context() -> None:
    """The header must describe the snapshot the report was built from: remote, main branch with
    both of its hashes, the filter and its meaning."""
    report = module.render_markdown_report([branch_double("feature", True)], "M")
    lines = report.splitlines()

    assert lines[0] == "# Branches Report"
    assert f"- **Remote:** {Repo.REMOTE}" in lines
    assert (
        f"- **Main branch:** master (local: {LOCAL_MAIN_HASH[:12]}, remote: {REMOTE_MAIN_HASH[:12]})" in lines
    ), "both main hashes belong in the header, so a stale local main is visible"
    assert "- **Filter:** M (fully merged branches)" in lines
    assert "## Branches (1)" in lines


def test_report_renders_the_table_header_once_above_the_rows() -> None:
    """The markdown table needs its header and separator exactly once, immediately before the rows,
    or the file does not render as a table at all."""
    branches = [branch_double("first", True), branch_double("second", True)]
    lines = module.render_markdown_report(branches, "A").splitlines()

    header_lines = GitBranch.MD_HEADER.splitlines()
    assert lines.count(header_lines[0]) == 1
    assert lines.count(header_lines[1]) == 1
    header_index = lines.index(header_lines[0])
    assert lines[header_index + 1] == header_lines[1], "the separator must directly follow the column names"
    assert lines[header_index + 2 :] == ["| first |", "| second |"]


def test_report_says_so_when_the_filter_matches_nothing() -> None:
    """An empty result is a real answer, so it is stated in prose instead of leaving a headerless
    table the reader would have to interpret."""
    report = module.render_markdown_report([], "M")
    assert "No branches match the filter." in report
    assert GitBranch.MD_HEADER.splitlines()[0] not in report.splitlines(), "no table header without rows"
    assert "## Branches (0)" in report


def test_command_delegates_to_execute_with_its_option() -> None:
    """The click command is only a thin wrapper: whatever --filter-by carries must reach execute."""
    with patch.object(module, "execute") as execute:
        module.remote_branches_details.callback("U")
    execute.assert_called_once_with("U")


def test_execute_propagates_an_enumeration_failure_without_writing_a_report() -> None:
    """git can fail while enumerating the branches. The failure must surface instead of producing
    a report describing a repository state that was never actually read."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "run_operation"
    ) as run_operation, patch.object(module, "ws_success") as ws_success, patch(
        "builtins.open", mock_open()
    ) as opened:
        loader.from_repository.side_effect = subprocess.SubprocessError("git exploded")
        with pytest.raises(subprocess.SubprocessError, match="git exploded"):
            module.execute("A")

    opened.assert_not_called()
    run_operation.assert_not_called()
    ws_success.assert_not_called()


def test_execute_does_not_claim_success_when_the_report_cannot_be_written() -> None:
    """A read-only or full working path makes the write fail. The command must not go on to open a
    file it never wrote, nor report a success that did not happen."""
    with patch.object(module, "BranchLoader") as loader, patch.object(
        module, "run_operation"
    ) as run_operation, patch.object(module, "ws_success") as ws_success, patch.object(
        module, "get_output_file", return_value="/tmp/report.md"
    ), patch(
        "builtins.open", side_effect=PermissionError("read-only file system")
    ):
        loader.from_repository.return_value = [branch_double("feature", True)]
        with pytest.raises(PermissionError, match="read-only file system"):
            module.execute("A")

    run_operation.assert_not_called()
    ws_success.assert_not_called()
