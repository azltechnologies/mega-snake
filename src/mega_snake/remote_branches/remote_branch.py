"""Class Module representing a remote branch"""

import dataclasses
import re
from typing import Optional
from datetime import datetime, timezone
from mega_snake.util.util import run_operation
from mega_snake.util.formatting import InternalStateError, ws_advice, ws_info


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
    def from_branch(
        cls, branch: str, filter_by: str, main_branch: str, remote: str, local_only: bool = False
    ) -> Optional["RemoteBranch"]:
        """
        Initialize a RemoteBranch instance from a branch name, filtering by merge status against the main branch.
        First, it parses the branch name to extract the local branch name. Then, it retrieves the commit information
        for the branch, checks if the branch is merged into the main branch, and finally constructs a RemoteBranch
        instance if the branch meets the specified filter criteria.

        The merge status is always resolved against ``remotes/{remote}/{main_branch}``, so a branch is judged
        against the main branch as the remote has it and never against a local copy that may be behind. That is
        what makes ``local_only`` meaningful: a branch that only exists locally is still measured against the
        remote main branch, which is where its work was integrated.

        Args:
            branch: str: The reference name of the branch. A remote one carries the full reference
                (e.g., 'remotes/origin/feature-branch'); a local-only one is the plain name (e.g., 'feature-branch').
            filter_by: str: Filter criteria ('M' for merged, 'U' for unmerged).
            main_branch: str: The name of the main branch (e.g., 'main').
            remote: str: The name of the remote repository (e.g., 'origin').
            local_only: bool: Whether the reference is a local branch with no counterpart on the remote, in which
                case the ``remotes/{remote}/`` prefix is legitimately absent.

        Raises:
            InternalStateError: If a remote reference cannot be related back to the remote it was selected from,
                or if the branch tip commit is reported as contained in no branch at all.

        Returns:
            Optional[RemoteBranch]: The described branch, or None when it does not match the requested filter.
        """
        pattern_branch = branch
        if pattern_branch.startswith("'") and pattern_branch.endswith("'"):
            pattern_branch = pattern_branch[1:-1]
        elif pattern_branch.startswith('"') and pattern_branch.endswith('"'):
            pattern_branch = pattern_branch[1:-1]
        ws_advice(f"Parsing branch: {pattern_branch} with remote: {remote}")
        pattern1 = rf"(?<=^remotes/{remote}/)\S+"
        match = re.search(pattern1, pattern_branch)
        # A local-only branch has no `remotes/{remote}/` prefix by definition, and its own name is
        # already the local one. For a remote reference the caller selects branches with a regex that
        # requires that same prefix, so a failure here means the two patterns drifted apart.
        if not match and not local_only:
            raise InternalStateError(
                f"Unable to parse local branch name for remote branch: {branch}. This is a bug."
            )
        local_branch: str = match.group(0) if match else pattern_branch
        commit: Commit = Commit.from_branch(branch)
        within_branches: str = run_operation(
            f"git branch -a --contains {commit.commit_hash}", "Getting branches containing commit"
        ).stdout.strip()
        # The commit was just read off this very branch, so it belongs to at least that one.
        if not within_branches:
            raise InternalStateError(f"Commit {commit.commit_hash} not found in any branch. This is a bug.")
        main_ref: str = f"remotes/{remote}/{main_branch}"
        pattern: str = rf"\s*{main_ref}\s*$"
        merged_on_main: bool = bool(re.search(pattern, within_branches, re.MULTILINE))
        main_common_ancestor: str = run_operation(
            f"git merge-base {branch} {main_ref}", "Getting main common ancestor"
        ).stdout.strip()
        if not merged_on_main and local_branch != main_branch:
            merged_on_main = cls.is_squash_or_rebase_merged(branch, main_ref, main_common_ancestor)
        if filter_by == "M" and not merged_on_main:
            return None
        if filter_by == "U" and merged_on_main and local_branch != main_branch:
            return None
        mail: str = run_operation(f"git log -1 --pretty='format:%ae'  {branch}", "Getting commit author").stdout.strip()
        return cls(local_branch, merged_on_main, commit, mail, main_common_ancestor)

    @staticmethod
    def is_squash_or_rebase_merged(branch: str, main_ref: str, main_common_ancestor: str) -> bool:
        """
        Determine whether a branch's changes were already integrated into the main branch
        through a squash or rebase merge, where the branch tip commit itself is no longer an
        ancestor of the main branch.
        Without a common ancestor there is no shared history to compare against, so the branch is
        reported as not merged. Otherwise both integration styles are checked, because they leave
        opposite traces in the history and one check cannot stand in for the other: a rebase replays
        every branch commit individually on main, while a squash collapses all of them into a single
        commit whose patch matches none of the originals.

        Parameters:
            branch: The remote branch reference to check.
            main_ref: The fully qualified main branch reference to compare against.
            main_common_ancestor: The common ancestor commit between branch and main_ref.

        Raises:
            None

        Returns:
            bool: True if the branch's changes are already applied to main_ref, False otherwise.
        """
        if not main_common_ancestor:
            return False
        if RemoteBranch._is_rebase_merged(branch, main_ref):
            ws_info(f"Branch {branch} appears to be rebase merged into {main_ref}")
            return True
        if RemoteBranch._is_squash_merged(branch, main_ref, main_common_ancestor):
            ws_info(f"Branch {branch} appears to be squash merged into {main_ref}")
            return True
        return False

    @staticmethod
    def _is_rebase_merged(branch: str, main_ref: str) -> bool:
        """
        Check whether every commit of the branch is already applied on the main branch.

        ``git cherry`` compares the branch commits against the main branch by patch id, marking with
        "-" the ones already present there even when they were introduced by a different commit,
        which is exactly what a rebase merge produces. The branch counts as merged only when every
        commit is marked that way. An empty output means the branch has no commits of its own, a case
        the ancestry check already covers, so it is deliberately not treated as merged here.

        Parameters:
            branch: The remote branch reference to check.
            main_ref: The fully qualified main branch reference to compare against.

        Raises:
            None

        Returns:
            bool: True if all the branch commits are already applied on main_ref, False otherwise.
        """
        cherry_output: str = run_operation(
            f"git cherry {main_ref} {branch}", "Checking if every branch commit is already applied to main"
        ).stdout.strip()
        if not cherry_output:
            return False
        return all(line.startswith("-") for line in cherry_output.splitlines())

    @staticmethod
    def _is_squash_merged(branch: str, main_ref: str, main_common_ancestor: str) -> bool:
        """
        Check whether the combined diff of the branch is already applied on the main branch.

        A squash merge produces a single commit holding the whole branch diff, so no individual branch
        commit matches it. To compare like with like, the branch tip tree is turned into a synthetic
        commit parented on the common ancestor, which gives it the same patch id as the squashed commit
        on main, and ``git cherry`` is asked whether that patch is already there. The synthetic commit is
        never referenced, so it stays dangling and is reclaimed by the next garbage collection.

        Parameters:
            branch: The remote branch reference to check.
            main_ref: The fully qualified main branch reference to compare against.
            main_common_ancestor: The common ancestor commit between branch and main_ref.

        Raises:
            None

        Returns:
            bool: True if the combined branch diff is already applied on main_ref, False otherwise.
        """
        tree: str = run_operation(f"git rev-parse {branch}^{{tree}}", "Getting branch tree").stdout.strip()
        synthetic_commit: str = run_operation(
            f"git commit-tree {tree} -p {main_common_ancestor} -m squash-check",
            "Creating synthetic commit to compare branch changes against main",
        ).stdout.strip()
        cherry_output: str = run_operation(
            f"git cherry {main_ref} {synthetic_commit}", "Checking if branch changes are already applied to main"
        ).stdout.strip()
        return cherry_output.startswith("-")

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
