"""Branch models for the remote-branches commands.

The model pairs every local branch with its remote counterpart (when one exists) into a single
:class:`GitBranch`, so merge status can be judged per side and reported once per logical branch
instead of once per reference.
"""

from dataclasses import dataclass, InitVar, field
from datetime import datetime, timezone
from typing import ClassVar, Optional, Self

from mega_snake.util.formatting import InternalStateError, ws_info
from mega_snake.util.repo import Repo
from mega_snake.util.util import (
    LOCAL_PREFIX,
    REMOTE_PREFIX,
    get_command_return_code,
    run_operation,
)


@dataclass
class Commit(Repo):
    """Tip commit of a branch: hash, subject, author and timestamp.

    Inheriting from :class:`Repo` is what gives every branch model access to the cached repository
    snapshot (main branch, hashes, remote) through plain attribute lookup, and what makes the first
    instantiation resolve that snapshot.

    Attributes:
        hash: The full commit hash of the branch tip.
        message: The commit subject (``%(subject)``), a single line.
        mail: The author email, already trimmed of its angle brackets.
        date: Init-only unix timestamp; consumed by ``__post_init__`` and not stored as such.
        dt_time: The author date as a timezone-aware datetime, used as the sort key.
        str_time: The author date rendered for the report, e.g. ``2025-01-01T00:00:00Z``.
    """

    hash: str
    message: str
    mail: str
    date: InitVar[float]
    dt_time: datetime = field(init=False, repr=False)
    str_time: str = field(init=False)

    def __post_init__(self, date: float) -> None:
        """Derive the datetime representations from the unix timestamp.

        Parameters:
            date: The author date as a unix timestamp.

        Raises:
            None

        Returns:
            None
        """
        self.dt_time = datetime.fromtimestamp(date, tz=timezone.utc)
        self.str_time = self.dt_time.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Branch(Commit):
    """A branch reference plus its merge status against the main branch.

    The merge status is always resolved against the hash :meth:`Repo.get_main_hash` returns — the
    remote main branch when available — so a branch is judged against the main branch as the remote
    has it, never against a local copy that may be behind.

    This is an abstract model: only the subclasses know which reference prefix they carry, so
    instantiating it directly raises from :meth:`_ref_prefix`.

    Attributes:
        name: The fully qualified reference, e.g. ``refs/heads/feature``.
        short_name: The plain branch name, with the reference prefix stripped. This is the form the
            deletion commands take and the form the report shows.
        merged_on_main: Whether this side's work is already on the main branch, by ancestry, rebase
            or squash.
        main_common_ancestor: The merge base with the main branch, or an empty string when the two
            share no history at all (an orphan branch).
    """

    name: str
    short_name: str = field(init=False)
    merged_on_main: bool = field(init=False)
    main_common_ancestor: str = field(init=False)

    def _ref_prefix(self) -> str:
        """Return the fully qualified reference prefix this branch kind carries.

        Parameters:
            None

        Raises:
            InternalStateError: Always, when reached on the base class: only the subclasses know
                their prefix, so instantiating Branch directly is a programming error.

        Returns:
            str: The reference prefix, without the trailing slash.
        """
        raise InternalStateError(
            "Branch is an abstract model; instantiate LocalBranch or RemoteBranch instead. This is a bug."
        )

    def __post_init__(self, date: float) -> None:
        """Compute the short name, the merge status and the common ancestor with main.

        Parameters:
            date: The author date as a unix timestamp, forwarded to the Commit initialization.

        Raises:
            None

        Returns:
            None
        """
        self.short_name = self.name.removeprefix(f"{self._ref_prefix()}/")
        # TODO: memoize the merge verdict on the tip hash instead of re-deriving it per side.
        # This method runs once per *side*, so a paired branch pays for the whole analysis twice —
        # and for an in-sync branch (trackshort "=", the majority) both sides hold the exact same
        # `self.hash`, so the second run re-derives an answer from byte-identical inputs. Worst case
        # per side that is 6 git invocations (merge-base --is-ancestor, merge-base, git cherry,
        # rev-parse ^{tree}, commit-tree, git cherry), each spawned through run_operation as a shell
        # child, i.e. 2 processes apiece; _on_initialized then adds a seventh per logical branch. On
        # a 200-branch repository that is on the order of 2500 git invocations, roughly half of them
        # buying nothing.
        # The fix is a class-level dict[str, tuple[bool, str]] keyed on the tip hash, holding
        # (merged_on_main, main_common_ancestor) and consulted at the top of this method. It is safe
        # because both inputs — the tip hash and Repo.get_main_hash() — are fixed for the lifetime of
        # the snapshot, so the cache cannot go stale within a run; it must be cleared in Repo.reset()
        # alongside the rest of the snapshot state, or the tests will leak verdicts between cases.
        main_hash: str = self.get_main_hash()
        merged_on_main: bool = (
            get_command_return_code(
                f"git merge-base --is-ancestor {self.hash} {main_hash}",
                "Checking if branch is merged on main",
            )
            == 0
        )
        # An orphan branch has no common ancestor with main; merge-base then exits non-zero with no
        # output, which the squash/rebase checks below read as "nothing to compare against".
        self.main_common_ancestor = run_operation(
            f"git merge-base {self.hash} {main_hash}", "Getting main common ancestor", check=False, timeout=3
        ).stdout.strip()
        self.merged_on_main = merged_on_main
        if not merged_on_main and self.short_name != self.MAIN_BRANCH:
            self.merged_on_main = self.is_squash_or_rebase_merged(main_hash)
        super().__post_init__(date)

    def is_squash_or_rebase_merged(self, main_hash: str) -> bool:
        """Detect whether the branch was integrated into main through a squash or rebase merge.

        In both styles the branch tip commit itself is no longer an ancestor of the main branch.
        Without a common ancestor there is no shared history to compare against, so the branch is
        reported as not merged. Otherwise both integration styles are checked, because they leave
        opposite traces in the history and one check cannot stand in for the other: a rebase replays
        every branch commit individually on main, while a squash collapses all of them into a single
        commit whose patch matches none of the originals.

        Parameters:
            main_hash: The main branch commit hash to compare against.

        Raises:
            None

        Returns:
            bool: True if the branch's changes are already applied on main, False otherwise.
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
        """Check whether every commit of the branch is already applied on the main branch.

        ``git cherry`` compares the branch commits against the main branch by patch id, marking with
        "-" the ones already present there even when they were introduced by a different commit,
        which is exactly what a rebase merge produces. The branch counts as merged only when every
        commit is marked that way. An empty output means the branch has no commits of its own, a case
        the ancestry check already covers, so it is deliberately not treated as merged here.

        Parameters:
            main_hash: The main branch commit hash to compare against.

        Raises:
            None

        Returns:
            bool: True if all the branch commits are already applied on main, False otherwise.
        """
        cherry_output: str = run_operation(
            f"git cherry {main_hash} {self.hash}", "Checking if every branch commit is already applied to main"
        ).stdout.strip()
        if not cherry_output:
            return False
        return all(line.startswith("-") for line in cherry_output.splitlines())

    def _is_squash_merged(self, main_hash: str) -> bool:
        """Check whether the combined diff of the branch is already applied on the main branch.

        A squash merge produces a single commit holding the whole branch diff, so no individual branch
        commit matches it. To compare like with like, the branch tip tree is turned into a synthetic
        commit parented on the common ancestor, which gives it the same patch id as the squashed commit
        on main, and ``git cherry`` is asked whether that patch is already there. The synthetic commit is
        never referenced, so it stays dangling and is reclaimed by the next garbage collection.

        Parameters:
            main_hash: The main branch commit hash to compare against.

        Raises:
            None

        Returns:
            bool: True if the combined branch diff is already applied on main, False otherwise.
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
    """A branch under ``refs/heads``, carrying its configured upstream (when any).

    Attributes:
        upstream: The fully qualified reference this branch tracks (``%(upstream)``), or None when
            it tracks nothing. It is the key :meth:`GitBranch.pair_remotes` matches on, so a branch
            with no upstream can never be paired and is reported as local-only.
    """

    upstream: Optional[str]

    def _ref_prefix(self) -> str:
        """Return the local reference prefix.

        Parameters:
            None

        Raises:
            None

        Returns:
            str: The ``refs/heads`` prefix.
        """
        return LOCAL_PREFIX


@dataclass
class RemoteBranch(Branch):
    """A remote-tracking branch under ``refs/remotes/{remote}``.

    It adds no field of its own: what distinguishes it from a local branch is the reference prefix
    it strips and the guarantee, enforced in ``__new__``, that a remote main branch actually exists
    to compare it against.
    """

    def __new__(cls, *args, **kwargs) -> Self:
        """Refuse to model a remote branch when the repository has no remote at all.

        The guard covers the remote **name** only, which is what :meth:`_ref_prefix` needs to strip
        the reference prefix, and whose absence really would be our defect: the loader enumerates
        remote references only when a remote exists, so getting here without one means the loader
        and this model drifted apart.

        It deliberately does **not** require a remote main hash. A repository whose remote main
        reference was never fetched (or was pruned) while other remote branches were is an ordinary
        environment state, not a defect — and one :meth:`Repo.get_main_hash` already handles by
        falling back to the local main hash. Demanding it here contradicted that fallback and
        reported a perfectly fixable situation as a bug in ``mgsnake``.

        Parameters:
            args: Positional arguments forwarded by the dataclass constructor (ignored).
            kwargs: Keyword arguments forwarded by the dataclass constructor (ignored).

        Raises:
            InternalStateError: If the snapshot was resolved without a remote and a RemoteBranch is
                being created anyway.

        Returns:
            Self: The new instance.
        """
        instance = super().__new__(cls, *args, **kwargs)
        if not cls.REMOTE:
            raise InternalStateError(
                "The repository snapshot was resolved without a remote, "
                "but a RemoteBranch instance is being created. This is a bug."
            )
        return instance

    def _ref_prefix(self) -> str:
        """Return the remote-tracking reference prefix for the resolved remote.

        Parameters:
            None

        Raises:
            None

        Returns:
            str: The ``refs/remotes/{remote}`` prefix.
        """
        return f"{REMOTE_PREFIX}/{self.REMOTE}"


@dataclass
class GitBranch:
    """A logical branch: the pairing of a local branch and its remote counterpart.

    Either side may be absent — a branch never checked out has no local side, and a branch whose
    remote copy was deleted on merge has no remote side — but never both. The instance is built
    incrementally (see :meth:`from_local`, :meth:`pair_remotes` and :meth:`from_remote`); once the
    last side is assigned, ``__setattr__`` notices and the derived fields are computed in
    :meth:`_on_initialized`. That is why the fields are all ``init=False``: the constructor takes
    nothing, and the builders assign the sides as they discover them.

    Attributes:
        local: The local side, or None when the branch only exists on the remote.
        remote: The remote side, or None when the branch only exists locally.
        track: Git's verbose tracking marker (``%(upstream:track)``), e.g. ``[ahead 1, behind 2]``
            or ``[gone]`` — replaced by ``LOCAL_ONLY``/``REMOTE_ONLY`` when there is no pairing.
        trackshort: Git's compact tracking marker (``%(upstream:trackshort)``), e.g. ``=``, ``>``,
            ``<`` or ``<>`` — replaced by ``SHORT_NA`` when there is no pairing.
        fully_merged: Whether *every* side that exists is merged. This is the deletion criterion:
            one stale side is enough to keep a branch off the cleanup list.
        merge_status: The human-readable verdict shown in the report — ``merged``,
            ``remote merged``, ``local merged`` or ``unmerged``.
        main_common_ancestor: The octopus merge base of every existing tip and the main branch.
        _ready: Whether the incremental construction finished; see :meth:`require_initialization`.
    """

    REMOTE_ONLY: ClassVar[str] = "remote_only"
    LOCAL_ONLY: ClassVar[str] = "local_only"
    SHORT_NA: ClassVar[str] = "-"
    HASH_ABBREV: ClassVar[int] = 12
    # TODO: expose a --format option on remote-branches-details so the user can choose the columns
    # and the output shape instead of this fixed table.
    MD_HEADER: ClassVar[str] = (
        "| Branch | Status | Track | Sync | Local hash | Remote hash | Last commit (UTC) "
        "| Author | Subject | Main ancestor |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )

    track: Optional[str] = field(init=False)
    trackshort: Optional[str] = field(init=False)
    main_common_ancestor: Optional[str] = field(init=False)
    local: Optional[LocalBranch] = field(init=False)
    remote: Optional[RemoteBranch] = field(init=False)
    fully_merged: bool = field(init=False)
    merge_status: str = field(init=False)

    _ready: bool = field(init=False, default=False, repr=False)

    def __setattr__(self, name: str, value: object) -> None:
        """Assign the attribute and finish the setup once the last required field lands.

        Parameters:
            name: The attribute name.
            value: The value to assign.

        Raises:
            None

        Returns:
            None
        """
        object.__setattr__(self, name, value)

        if not self._ready and self._is_initialized():
            object.__setattr__(self, "_ready", True)
            self._on_initialized()

    def _is_initialized(self) -> bool:
        """Report whether every externally provided field has been assigned.

        The derived fields (``merge_status``, ``fully_merged``, ``main_common_ancestor``) are
        excluded: they are computed by ``_on_initialized`` itself.

        Parameters:
            None

        Raises:
            None

        Returns:
            bool: True when every required field is present, False otherwise.
        """
        for name in self.__dataclass_fields__:
            if name not in ("merge_status", "fully_merged", "main_common_ancestor") and not hasattr(self, name):
                return False
        return True

    def get_any_branch(self) -> Branch:
        """Return either the local or the remote side, whichever is available.

        Parameters:
            None

        Raises:
            InternalStateError: If neither side is set, a state the builders never produce.

        Returns:
            Branch: The local branch when present, the remote one otherwise.
        """
        branch: Optional[Branch] = self.local if self.local is not None else self.remote
        if branch is None:
            raise InternalStateError(
                "GitBranch instance must have at least one of 'local' or 'remote' initialized. This is a bug."
            )
        return branch

    def _on_initialized(self) -> None:
        """Compute the derived fields once both sides have been assigned.

        ``fully_merged`` requires every existing side to be merged, so a stale side blocks the
        deletion offer even when the other one was already integrated. The common ancestor is the
        octopus merge-base of every existing tip and the main branch hash.

        Parameters:
            None

        Raises:
            None

        Returns:
            None
        """
        sides: list[bool] = [branch.merged_on_main for branch in (self.local, self.remote) if branch is not None]
        self.fully_merged = bool(sides) and all(sides)
        commits: list[Optional[str]] = [
            getattr(self.remote, "hash", None),
            getattr(self.local, "hash", None),
            Repo.get_main_hash(),
        ]
        command: str = f"git merge-base --octopus {' '.join(commit for commit in commits if commit)}"
        self.main_common_ancestor = run_operation(
            command, "Getting main common ancestor", check=False, timeout=3
        ).stdout.strip()
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
        """Assert that every instance finished its incremental construction.

        Parameters:
            instances: The instances to verify.

        Raises:
            InternalStateError: If any instance is still missing a required field.

        Returns:
            list[Self]: The same list, once verified.
        """
        if not all(instance._ready for instance in instances):
            raise InternalStateError("Not all GitBranch instances are fully initialized. This is a bug.")
        return instances

    @classmethod
    def from_local(
        cls, local_branch: LocalBranch, track: Optional[str] = None, trackshort: Optional[str] = None
    ) -> "GitBranch":
        """Create a GitBranch from a local branch, leaving the remote side open for pairing.

        A branch with no configured upstream can never be paired, so its remote side is closed
        right away and its tracking columns get the ``local_only`` marker instead of git's values.

        Parameters:
            local_branch: The local side of the branch.
            track: The ``%(upstream:track)`` value, e.g. ``[ahead 1, behind 2]`` or ``[gone]``.
            trackshort: The ``%(upstream:trackshort)`` value, e.g. ``<>`` or ``=``.

        Raises:
            None

        Returns:
            GitBranch: The new instance, fully initialized only when it had no upstream.
        """
        new_instance = cls()
        new_instance.local = local_branch
        if local_branch.upstream is None:
            new_instance.track = cls.LOCAL_ONLY
            new_instance.trackshort = cls.SHORT_NA
            new_instance.remote = None
        else:
            new_instance.track = track
            new_instance.trackshort = trackshort
        return new_instance

    @classmethod
    def pair_remotes(cls, instances: list[Self], remotes: list[RemoteBranch]) -> list[RemoteBranch]:
        """Assign each remote branch to the instance whose local upstream points at it.

        Every instance still waiting for its remote side gets one: the matching remote branch when
        it exists, or ``None`` when the upstream is gone (pruned after a merge, or pointing at
        another remote). Either way the instance finishes its construction here.

        Parameters:
            instances: The GitBranch instances built from the local branches.
            remotes: The remote branches enumerated from the resolved remote.

        Raises:
            None

        Returns:
            list[RemoteBranch]: The remote branches no local branch tracks, in input order.
        """
        remote_dict: dict[str, RemoteBranch] = {remote.name: remote for remote in remotes}
        for instance in instances:
            if instance.local is not None and instance.local.upstream is not None:
                instance.remote = remote_dict.pop(instance.local.upstream, None)
        return list(remote_dict.values())

    @classmethod
    def from_remote(cls, remote_branch: RemoteBranch) -> "GitBranch":
        """Create a GitBranch from a remote branch no local branch tracks.

        Parameters:
            remote_branch: The remote side of the branch.

        Raises:
            None

        Returns:
            GitBranch: The new, fully initialized instance.
        """
        new_instance = cls()
        new_instance.local = None
        new_instance.track = cls.REMOTE_ONLY
        new_instance.trackshort = cls.SHORT_NA
        new_instance.remote = remote_branch
        return new_instance

    def __lt__(self, other: "GitBranch") -> bool:
        """Order GitBranch instances by the timestamp of their tip commit.

        Parameters:
            other: The instance to compare against.

        Raises:
            None

        Returns:
            bool: True when this branch's tip commit is older than the other's.
        """
        return self.get_any_branch().dt_time < other.get_any_branch().dt_time

    def to_markdown_row(self) -> str:
        """Render the branch as one row of the markdown report table.

        Both hashes are shown (abbreviated) because the two sides can legitimately diverge; a
        missing side renders as ``-``. Pipes in free-text cells are escaped so a commit subject
        cannot tear the table apart.

        Parameters:
            None

        Raises:
            None

        Returns:
            str: The markdown table row, without a trailing newline.
        """
        branch: Branch = self.get_any_branch()
        return (
            f"| {self._escape_cell(branch.short_name)} "
            f"| {self.merge_status} "
            f"| {self._escape_cell(self.track) if self.track else self.SHORT_NA} "
            f"| {self._escape_cell(self.trackshort) if self.trackshort else self.SHORT_NA} "
            f"| {self.hash_cell(getattr(self.local, 'hash', None))} "
            f"| {self.hash_cell(getattr(self.remote, 'hash', None))} "
            f"| {branch.str_time} "
            f"| {self._escape_cell(branch.mail)} "
            f"| {self._escape_cell(branch.message)} "
            f"| {self.hash_cell(self.main_common_ancestor)} |"
        )

    @staticmethod
    def _escape_cell(value: str) -> str:
        """Escape the characters that would break a markdown table cell.

        Parameters:
            value: The raw cell text.

        Raises:
            None

        Returns:
            str: The text with every pipe escaped.
        """
        return value.replace("|", "\\|")

    @classmethod
    def hash_cell(cls, value: Optional[str]) -> str:
        """Render a commit hash cell, abbreviated, with a placeholder for a missing hash.

        Parameters:
            value: The full commit hash, or None/empty when the side does not exist.

        Raises:
            None

        Returns:
            str: The abbreviated hash, or the ``-`` placeholder.
        """
        return value[: cls.HASH_ABBREV] if value else cls.SHORT_NA


class BranchLoader:
    """Builds the GitBranch inventory of the repository.

    This is the single entry point both remote-branches commands use: ``remote-branches-details``
    renders the inventory to a markdown report, and ``remote-branches-cleanup`` feeds the very same
    inventory to its interactive deletion, so the two can never disagree about what exists.
    """

    @staticmethod
    def from_repository() -> list[GitBranch]:
        """Enumerate every local and remote branch and pair them into GitBranch instances.

        Instantiating :class:`Repo` first resolves the snapshot (offering the fetch/prune), so the
        references enumerated here are as fresh as the user wanted them. The remote listing is
        restricted to the resolved remote and skips its symbolic ``HEAD`` reference.

        Parameters:
            None

        Raises:
            InternalStateError: If a ``git for-each-ref`` line does not carry the expected fields,
                or if any instance ends up partially built.

        Returns:
            list[GitBranch]: Every branch of the repository, local sides first.
        """
        Repo()
        result: list[GitBranch] = []
        command: str = (
            "git for-each-ref --format="
            "'%(objectname)%09%(authordate:unix)%09%(authoremail:trim)%09%(refname)"
            "%09%(upstream)%09%(upstream:track)%09%(upstream:trackshort)%09%(subject)'"
            f" {LOCAL_PREFIX}"
        )
        lines: list[str] = run_operation(command, "Getting local branches", timeout=5).stdout.strip().splitlines()
        raw_local: list[list[str]] = [line.split("\t") for line in lines if line.strip()]
        for raw in raw_local:
            if len(raw) < 8:
                raise InternalStateError(
                    f"Unexpected output from git for-each-ref: {raw}. Expected at least 8 tab-separated fields."
                )
            # The subject is the last field precisely so a tab inside it can be stitched back.
            raw[7] = "\t".join(raw[7:])
            local_branch = LocalBranch(
                hash=raw[0],
                date=float(raw[1]),
                mail=raw[2],
                name=raw[3],
                upstream=raw[4] if raw[4] else None,
                message=raw[7],
            )
            result.append(GitBranch.from_local(local_branch, raw[5] if raw[5] else None, raw[6] if raw[6] else None))
        remote_branches: list[RemoteBranch] = []
        if Repo.REMOTE:
            command = (
                "git for-each-ref --format="
                "'%(objectname)%09%(authordate:unix)%09%(authoremail:trim)%09%(refname)%09%(subject)'"
                f" {REMOTE_PREFIX}/{Repo.REMOTE}"
            )
            lines = run_operation(command, "Getting remote branches", timeout=5).stdout.strip().splitlines()
            raw_remote: list[list[str]] = [line.split("\t") for line in lines if line.strip()]
            for raw in raw_remote:
                if len(raw) < 5:
                    raise InternalStateError(
                        f"Unexpected output from git for-each-ref: {raw}. Expected at least 5 tab-separated fields."
                    )
                if raw[3] == f"{REMOTE_PREFIX}/{Repo.REMOTE}/HEAD":
                    continue
                raw[4] = "\t".join(raw[4:])
                remote_branches.append(
                    RemoteBranch(hash=raw[0], date=float(raw[1]), mail=raw[2], name=raw[3], message=raw[4])
                )
        remote_branches = GitBranch.pair_remotes(result, remote_branches)
        result.extend(GitBranch.from_remote(branch) for branch in remote_branches)
        return GitBranch.require_initialization(result)
