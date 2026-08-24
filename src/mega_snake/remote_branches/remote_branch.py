"""Class Module representing a remote branch"""

from dataclasses import dataclass, InitVar, field
import re
from typing import ClassVar, Self, cast
from typing import Optional
from datetime import datetime, timezone
from mega_snake.util.util import (
    run_operation,
    get_typed_validated_input,
    get_validated_input,
    get_command_return_code,
    get_remote,
    LOCAL_PREFIX,
    REMOTE_PREFIX,
)
from mega_snake.util.formatting import InternalStateError, ws_advice, ws_info


@dataclass
class Repo:
    """Class containing some repo properties"""

    REMOTE: ClassVar[Optional[str]]
    HEAD: ClassVar[str]
    BRANCH_HEAD: ClassVar[Optional[str]]
    MAIN_BRANCH: ClassVar[str]
    MAIN_LOCAL_HASH: ClassVar[str]
    MAIN_REMOTE_HASH: ClassVar[Optional[str]]
    _INITIALIZED: ClassVar[bool] = False

    def __new__(cls) -> Self:
        """Override __new__ to ensure that the class is fully initialized before allowing instance creation"""
        if not cls._INITIALIZED:
            cls.REMOTE = get_remote()
            fetch: bool = bool(
                1
                if get_validated_input(
                    "Do you want to fetch and prune the remote branches before proceeding? (y/n): ", ["y", "n"]
                )
                .strip()
                .lower()
                == "y"
                else 0
            )
            if fetch:
                run_operation(f"git fetch {cls.REMOTE} --prune", "Fetching and pruning remotes", timeout=15)
            cls.get_repo_details()
            cls._INITIALIZED = True
        return super().__new__(cls)

    def get_main_hash(self) -> str:
        """_summary_

        Returns:
            str: _description_
        """
        return self.MAIN_REMOTE_HASH if self.MAIN_REMOTE_HASH else self.MAIN_LOCAL_HASH

    @classmethod
    def get_repo_details(cls) -> None:
        """
        Gets the main branch of the repository.

        Returns:
            Tuple[str, str, str, str]
        """
        head: str
        main_branch: str
        local_hash: str
        remote_hash: Optional[str] = None
        remote: Optional[str] = cls.REMOTE
        if remote:
            main_ref: str = run_operation(
                f"git symbolic-ref --quiet {REMOTE_PREFIX}/{remote}/HEAD", "Getting main branch"
            ).stdout.strip()
            main_branch = main_ref.removeprefix(f"{REMOTE_PREFIX}/{remote}/")
            head, local_hash, remote_hash = (
                run_operation(
                    f"git rev-parse HEAD {LOCAL_PREFIX}/{main_branch} {main_ref}", "Getting main hash", timeout=3
                )
                .stdout.strip()
                .splitlines()
            )
        else:
            branches: list[str] = (
                run_operation(
                    f"git for-each-ref --format='%(refname:short)' {LOCAL_PREFIX}", "Getting local branches", timeout=3
                )
                .stdout.strip()
                .splitlines()
            )
            main_branch = get_typed_validated_input(
                p_prompt="Please provide the existing main branch short name (e.g. 'main' or 'master')",
                warn=(
                    "Invalid branch selected. The given branch does not exist in the repository. "
                    "Consider that branch names are case-sensitive. Please try again."
                ),
                valid_values=branches,
                fail_msg=(
                    "The given branch does not exist in the repository. "
                    "Consider that branch names are case-sensitive.\n"
                    "You can see available local branches by running\n"
                    f"git for-each-ref --format='%(refname:short)' {LOCAL_PREFIX}\n"
                    "in the repository."
                ),
            )
            head, local_hash = (
                run_operation(f"git rev-parse HEAD {LOCAL_PREFIX}/{main_branch}", "Getting main hash", timeout=3)
                .stdout.strip()
                .splitlines()
            )
        branch_head: str = run_operation(
            "git branch --show-current", "Getting current branch", timeout=3
        ).stdout.strip()
        cls.HEAD = head
        cls.BRANCH_HEAD = branch_head if branch_head else None
        cls.MAIN_BRANCH = main_branch
        cls.MAIN_LOCAL_HASH = local_hash
        cls.MAIN_REMOTE_HASH = remote_hash


@dataclass
class Commit(Repo):
    """Class containing some commit properties"""

    hash: str
    message: str
    mail: str
    date: InitVar[float] = field(repr=False)
    dt_time: datetime = field(init=False, repr=False)
    str_time: str = field(init=False)

    def __post_init__(self, date: float) -> None:
        """Ensure that the date string is consistent with the datetime object."""
        self.dt_time = datetime.fromtimestamp(date, tz=timezone.utc)
        self.str_time = self.dt_time.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Branch(Commit):
    """_summary_

    Args:
        Commit (_type_): _description_
    """

    name: str
    short_name: str = field(init=False)
    merged_on_main: bool = field(init=False)
    main_common_ancestor: str = field(init=False)
    __PREFIX: ClassVar[str] = ""

    def __post_init__(self, date: float) -> None:
        """_summary_

        Args:
            date (float): _description_
            main_ref (str): _description_
        """
        self.short_name = self.name.removeprefix(f"{self.__PREFIX}/")
        main_hash: str = self.get_main_hash()
        merged_on_main: bool = bool(
            get_command_return_code(
                f"git merge-base --is-ancestor {self.hash} {main_hash}",
                "Checking if branch is merged on main",
            )
        )
        command: str = f"git merge-base {self.hash} {main_hash}"
        self.main_common_ancestor = run_operation(command, "Getting main common ancestor", timeout=3).stdout.strip()
        if not merged_on_main and self.BRANCH_HEAD != self.MAIN_BRANCH:
            self.merged_on_main = self.is_squash_or_rebase_merged(main_hash)
        super().__post_init__(date)

    def is_squash_or_rebase_merged(self, main_hash: str) -> bool:
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
        if not self.main_common_ancestor:
            return False
        if self._is_rebase_merged(main_hash):
            ws_info(f"Branch {self.short_name} appears to be rebase merged into {self.MAIN_BRANCH}")
            return True
        if self._is_squash_merged(main_hash):
            ws_info(f"Branch {self.short_name} appears to be squash merged into {self.MAIN_BRANCH}")
            return True
        return False

    def _is_rebase_merged(self, main_hash: str) -> bool:
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
            f"git cherry {main_hash} {self.hash}", "Checking if every branch commit is already applied to main"
        ).stdout.strip()
        if not cherry_output:
            return False
        return all(line.startswith("-") for line in cherry_output.splitlines())

    def _is_squash_merged(self, main_hash: str) -> bool:
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
        tree: str = run_operation(f"git rev-parse {self.hash}^{{tree}}", "Getting branch tree").stdout.strip()
        synthetic_commit: str = run_operation(
            f"git commit-tree {tree} -p {self.main_common_ancestor} -m squash-check",
            "Creating synthetic commit to compare branch changes against main",
        ).stdout.strip()
        cherry_output: str = run_operation(
            f"git cherry {main_hash} {synthetic_commit}", "Checking if branch changes are already applied to main"
        ).stdout.strip()
        return cherry_output.startswith("-")


@dataclass
class LocalBranch(Branch):
    """_summary_

    Args:
        Commit (_type_): _description_
    """

    upstream: Optional[str]
    __PREFIX: ClassVar[str] = LOCAL_PREFIX


@dataclass
class RemoteBranch(Branch):
    """_summary_

    Args:
        LocalBranch (_type_): _description_
    """

    __PREFIX: ClassVar[str] = REMOTE_PREFIX

    def __new__(cls) -> Self:
        """_summary_"""
        if cls._INITIALIZED and (not cls.REMOTE or not cls.MAIN_REMOTE_HASH):
            raise InternalStateError(
                "Repo class is already initialized without a remote, no remote repo was detected, "
                "but a RemoteBranch instance is being created.\n"
                "You shouldn't be able to create a RemoteBranch instance without a remote. "
                "This is a bug."
            )
        return super().__new__(cls)


@dataclass
class GitBranch:
    """Class containing some remote branch properties"""

    REMOTE_ONLY: ClassVar[str] = "remote_only"
    LOCAL_ONLY: ClassVar[str] = "local_only"
    SHORT_NA: ClassVar[str] = "-"

    track: Optional[str] = field(init=False)
    trackshort: Optional[str] = field(init=False)
    main_common_ancestor: Optional[str] = field(init=False)
    local: Optional[LocalBranch] = field(init=False)
    remote: Optional[RemoteBranch] = field(init=False)
    fully_merged: bool = field(init=False)
    merge_status: str = field(init=False)

    _ready: bool = field(init=False, default=False, repr=False)

    def __setattr__(self, name, value) -> None:
        """Override __setattr__ to ensure that the object is fully initialized before allowing attribute assignment"""
        object.__setattr__(self, name, value)

        if not self._ready and self._is_initialized():
            object.__setattr__(self, "_ready", True)
            self._on_initialized()

    def _is_initialized(self) -> bool:
        """Ensure that all fields have been initialized."""
        for name in self.__dataclass_fields__:
            if name not in ("merge_status", "fully_merged", "main_common_ancestor") and not hasattr(self, name):
                return False
        return True

    def get_any_branch(self) -> Branch:
        """Return either the local or remote branch, whichever is available."""
        branch: Branch
        if self.local is not None:
            branch = self.local
        elif self.remote is not None:
            branch = self.remote
        else:
            raise InternalStateError(
                "GitBranch instance must have at least one of 'local' or 'remote' initialized. This is a bug."
            )
        return branch

    def _on_initialized(self) -> None:
        """Perform any additional setup after the object is fully initialized."""

        if not hasattr(self, "fully_merged"):
            self.fully_merged = getattr(self.remote, "merged_on_main", False) and getattr(
                self.local, "merged_on_main", False
            )
        commits: list[str] = [
            cast(str, getattr(self.remote, "hash", None)),
            cast(str, getattr(self.local, "hash", None)),
            self.get_any_branch().get_main_hash(),
        ]
        command: str = f"git merge-base --octopus {' '.join(filter(None, commits))}"
        self.main_common_ancestor = run_operation(command, "Getting main common ancestor", timeout=3).stdout.strip()
        if self.fully_merged:
            self.merge_status = "merged"
        elif getattr(self.remote, "merged_on_main", False):
            self.merge_status = "remote merged"
        elif getattr(self.local, "merged_on_main", False):
            self.merge_status = "local merged"
        else:
            self.merge_status = "unmerged"

    @classmethod
    def require_initialization(cls, instances: list[Self]) -> list[Self]:
        """Ensure that all instances in the list are fully initialized."""
        if not all(instance._ready for instance in instances):
            raise InternalStateError("Not all GitBranch instances are fully initialized. This is a bug.")
        return instances

    @classmethod
    def from_local(
        cls, local_branch: LocalBranch, track: Optional[str] = None, trackshort: Optional[str] = None
    ) -> "GitBranch":
        """Create a GitBranch instance from a LocalBranch instance."""
        new_instance = cls()
        if local_branch.upstream is None:
            if local_branch.merged_on_main:
                new_instance.fully_merged = True
            track = cls.LOCAL_ONLY
            trackshort = cls.SHORT_NA
        new_instance.local = local_branch
        new_instance.track = track
        new_instance.trackshort = trackshort
        return new_instance

    @classmethod
    def pair_remotes(cls, instances: list[Self], remotes: list[RemoteBranch]) -> list[RemoteBranch]:
        """Match RemoteBranch instances to GitBranch instances based on their local upstreams."""
        remote_dict = {remote.name: remote for remote in remotes}
        local_dict = {
            instance.local.upstream: instance
            for instance in instances
            if instance.local is not None and instance.local.upstream is not None
        }
        for upstream, instance in local_dict.items():
            if upstream in remote_dict:
                instance.remote = remote_dict.pop(upstream)
        return list(remote_dict.values())

    @classmethod
    def from_remote(cls, remote_branch: RemoteBranch) -> "GitBranch":
        """Create a GitBranch instance from a RemoteBranch instance."""
        new_instance = cls()
        new_instance.local = None
        new_instance.track = cls.REMOTE_ONLY
        new_instance.trackshort = cls.SHORT_NA
        new_instance.fully_merged = remote_branch.merged_on_main
        new_instance.remote = remote_branch
        return new_instance

    @classmethod
    def from_branch(
        cls, branch: str, filter_by: str, main_branch: str, remote: str, local_only: bool = False
    ) -> Optional["GitBranch"]:
        """
        Initialize a GitBranch instance from a branch name, filtering by merge status against the main branch.
        First, it parses the branch name to extract the local branch name. Then, it retrieves the commit information
        for the branch, checks if the branch is merged into the main branch, and finally constructs a GitBranch
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
            Optional[GitBranch]: The described branch, or None when it does not match the requested filter.
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
            raise InternalStateError(f"Unable to parse local branch name for remote branch: {branch}. This is a bug.")
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

    def __lt__(self: "GitBranch", other: "GitBranch") -> bool:
        """Compare two GitBranch instances by their commit timestamp."""
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


class BranchLoader:
    """Class to load branches from the repository"""

    @staticmethod
    def from_repository() -> list[GitBranch]:
        """_summary_

        Args:
            branch (str): _description_
            origin (str): _description_
            main (str): _description_

        Raises:
            InternalStateError: _description_

        Returns:
            GitBranch: _description_
        """
        result: list[GitBranch] = []
        command: str = (
            "git for-each-ref --format="
            "'%(objectname)%09%(authordate:unix)%09%(authoremail)%09%(refname)%09%(upstream)%09%(upstream:trackshort)%09%(upstream:track)%09%(subject)'"
            f" {LOCAL_PREFIX}"
        )
        lines: list[str] = run_operation(command, "Getting local branches", timeout=5).stdout.strip().splitlines()
        raw_local: list[list[str]] = [line.split("\t") for line in lines if line.strip()]
        for raw in raw_local:
            if len(raw) < 8:
                raise InternalStateError(
                    f"Unexpected output from git for-each-ref: {raw}. Expected at least 7 tab-separated fields."
                )
            raw[7] = "\t".join(raw[7:])
            local_branch = LocalBranch(
                hash=raw[0],
                date=float(raw[1]),
                mail=raw[2],
                name=raw[3],
                upstream=raw[4] if raw[4] else None,
                message=raw[7],
            )

            track: Optional[str] = raw[5] if raw[5] else None
            trackshort: Optional[str] = raw[6] if raw[6] else None
            result.append(GitBranch.from_local(local_branch, track, trackshort))
        command = (
            "git for-each-ref --format="
            "'%(objectname)%09%(authordate:unix)%09%(authoremail)%09%(refname)%09%(subject)'"
            f" {LOCAL_PREFIX}"
        )
        lines = run_operation(command, "Getting local branches", timeout=5).stdout.strip().splitlines()
        raw_remote: list[list[str]] = [line.split("\t") for line in lines if line.strip()]
        remote_branches: list[RemoteBranch] = []
        for raw in raw_remote:
            if len(raw) < 5:
                raise InternalStateError(
                    f"Unexpected output from git for-each-ref: {raw}. Expected at least 5 tab-separated fields."
                )
            raw[4] = "\t".join(raw[4:])
            remote_branch = RemoteBranch(
                hash=raw[0],
                date=float(raw[1]),
                mail=raw[2],
                name=raw[3],
                message=raw[4],
            )
            remote_branches.append(remote_branch)
        remote_branches = GitBranch.pair_remotes(result, remote_branches)
        result.extend(GitBranch.from_remote(branch) for branch in remote_branches)
        return GitBranch.require_initialization(result)

    @staticmethod
    def from_branch(branch: str) -> "Commit":
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

        return Commit(commit_hash, dt, formatted_date, message, "")

    @staticmethod
    def from_strings(commit_hash: str, date_str: str, message: str, mail: str) -> "Commit":
        """Get the commit info from string values"""
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        return Commit(commit_hash, dt, date_str, message, mail)
