"""Class Module representing a remote branch"""

import dataclasses
import re
from typing import Optional
from datetime import datetime, timezone
from mega_snake.util.util import run_operation
from mega_snake.util.formatting import ws_advice, ws_info


@dataclasses.dataclass
class Commit:
    """Class containing some commit properties"""

    commit_hash: str
    date_str: str
    # Parse the string into a datetime object
    dt: datetime
    message: str

    def __init__(self, commit_hash: str, dt: datetime, date_str: str, message: str) -> None:
        """Initialize a Commit with its hash, timestamp, formatted date string, and commit message."""
        self.commit_hash = commit_hash
        self.dt = dt
        self.date_str = date_str
        self.message = message

    @classmethod
    def from_branch(cls, branch: str) -> "Commit":
        """Get the commit info from a branch"""
        commit_hash: str = run_operation(
            f"git log -1 --pretty='format:%H'  {branch}", "Getting commit hash"
        ).stdout.strip()
        message: str = run_operation(
            f"git log -1 --pretty='format:%B'  {branch}", "Getting commit message"
        ).stdout.strip()
        # replaing /n with /t
        message = message.replace("\n", "\t")
        message = message.replace("\r", "\t")
        date_int: float = float(
            run_operation(f"git log -1 --pretty='format:%at'  {branch}", "Getting commit date").stdout.strip()
        )
        dt: datetime = datetime.fromtimestamp(date_int, tz=timezone.utc)
        formatted_date: str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return cls(commit_hash, dt, formatted_date, message)

    @classmethod
    def from_strings(cls, commit_hash: str, date_str: str, message: str) -> "Commit":
        """Get the commit info from string values"""
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        return cls(commit_hash, dt, date_str, message)


@dataclasses.dataclass
class RemoteBranch:
    """Class containing some remote branch properties"""

    branch: str
    merged_on_main: bool
    commit: Commit
    mail: str
    main_common_ancestor: str

    def __init__(
        self: "RemoteBranch", branch: str, merged_on_main: bool, commit: Commit, mail: str, main_common_ancestor: str
    ) -> None:
        """Initialize a RemoteBranch with its branch name, merge status, commit info, mail, and common ancestor."""
        self.merged_on_main = merged_on_main
        self.branch = branch
        self.commit = commit
        self.mail = mail
        self.main_common_ancestor = main_common_ancestor

    @classmethod
    def from_string(cls, input_string: str) -> "RemoteBranch":
        """
        Get the remote branch info from a string

        Args:
            input_string: str

        Returns:
            RemoteBranch
        """
        if input_string is not None and bool(input_string):
            result = input_string.split("|")
            result[6] = "|".join(result[6:])
            result = [value.strip() for value in result]
            merged_on_main: bool = bool(int(result[0]))
            commit_hash: str = result[1]
            date: str = result[2]
            mail: str = result[3]
            branch: str = result[4]
            main_common_ancestor: str = result[5]
            message: str = result[6]
            commit: Commit = Commit.from_strings(commit_hash, date, message)
            return cls(branch, merged_on_main, commit, mail, main_common_ancestor)
        raise ValueError("Invalid input string. String is empty or None")

    @classmethod
    def from_branch(cls, branch: str, filter_by: str, main_branch: str, remote: str) -> Optional["RemoteBranch"]:
        """
        Get the remote branch info from a branch

        Args:
            branch: str
            filter_by: str

        Returns:
            RemoteBranch
        """
        pattern_branch = branch
        if pattern_branch.startswith("'") and pattern_branch.endswith("'"):
            pattern_branch = pattern_branch[1:-1]
        elif pattern_branch.startswith('"') and pattern_branch.endswith('"'):
            pattern_branch = pattern_branch[1:-1]
        ws_advice(f"Parsing branch: {pattern_branch} with remote: {remote}")
        pattern1 = rf"(?<=^remotes/{remote}/)\S+"
        match = re.search(pattern1, pattern_branch)
        if not match:
            raise LookupError(f"Unable to parse local branch name for remote branch: {branch}")
        local_branch: str = match.group(0)
        commit: Commit = Commit.from_branch(branch)
        within_branches: str = run_operation(
            f"git branch -a --contains {commit.commit_hash}", "Getting branches containing commit"
        ).stdout.strip()
        if not within_branches:
            raise LookupError(f"Commit {commit.commit_hash} not found in any branch")
        pattern: str = rf"\s*remotes/{remote}/{main_branch}\s*$"
        merged_on_main: bool = bool(re.search(pattern, within_branches, re.MULTILINE))
        main_common_ancestor: str = run_operation(
            f"git merge-base {branch} {main_branch}", "Getting main common ancestor"
        ).stdout.strip()
        if not merged_on_main and local_branch != main_branch:
            merged_on_main = cls.is_squash_or_rebase_merged(branch, main_branch, main_common_ancestor)
        if filter_by == "M" and not merged_on_main:
            return None
        if filter_by == "U" and merged_on_main and local_branch != main_branch:
            return None
        mail: str = run_operation(f"git log -1 --pretty='format:%ae'  {branch}", "Getting commit author").stdout.strip()
        return cls(local_branch, merged_on_main, commit, mail, main_common_ancestor)

    @staticmethod
    def is_squash_or_rebase_merged(branch: str, main_branch: str, main_common_ancestor: str) -> bool:
        """
        Determine whether a branch's changes were already integrated into the main branch
        through a squash or rebase merge, where the branch tip commit itself is no longer an
        ancestor of the main branch.

        Parameters:
            branch: The remote branch reference to check.
            main_branch: The main branch to compare against.
            main_common_ancestor: The common ancestor commit between branch and main_branch.

        Raises:
            None

        Returns:
            bool: True if the branch's changes are already applied to main_branch, False otherwise.
        """
        if not main_common_ancestor:
            return False
        tree: str = run_operation(f"git rev-parse {branch}^{{tree}}", "Getting branch tree").stdout.strip()
        synthetic_commit: str = run_operation(
            f"git commit-tree {tree} -p {main_common_ancestor} -m squash-check",
            "Creating synthetic commit to compare branch changes against main",
        ).stdout.strip()
        cherry_output: str = run_operation(
            f"git cherry {main_branch} {synthetic_commit}", "Checking if branch changes are already applied to main"
        ).stdout.strip()
        if cherry_output.startswith("-"):
            ws_info(f"Branch {branch} appears to be squash/rebase merged into {main_branch}")
            return True
        return False

    def __lt__(self: "RemoteBranch", other: "RemoteBranch") -> bool:
        """Compare two RemoteBranch instances by their commit timestamp."""
        return self.commit.dt < other.commit.dt

    def printing_remote_branches_details(self) -> str:
        """
        Print the remote branch details
        """
        padding = 20
        padding_auth = 50
        padding_branch = 50
        delimiter = " | "
        return (
            f"{self.merged_on_main:3}{delimiter}"
            f"{self.commit.commit_hash:<{padding}}{delimiter}"
            f"{self.commit.date_str:<{padding}}{delimiter}"
            f"{self.mail:<{padding_auth}}{delimiter}"
            f"{self.branch:<{padding_branch}}{delimiter}"
            f"{self.main_common_ancestor:<{padding}}{delimiter}"
            f"{self.commit.message:<{padding}}\n"
        )
