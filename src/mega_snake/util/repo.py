"""Process-wide snapshot of the git repository the commands operate on.

The snapshot (remote, main branch, relevant hashes) is resolved once per process, on the first
instantiation of :class:`Repo` or any of its subclasses, and cached as class attributes so every
consumer shares the same answers without re-running git or re-prompting the user.
"""

import re
from typing import ClassVar, Optional, Self

from mega_snake.util.formatting import InternalStateError
from mega_snake.util.util import (
    LOCAL_PREFIX,
    REMOTE_PREFIX,
    get_remote,
    get_typed_validated_input,
    get_validated_input,
    run_operation,
)


class Repo:
    """Cached repository snapshot shared by every command that needs git context.

    The class attributes are populated exactly once per process (see ``__new__``); subclasses such
    as the branch models read them through normal attribute lookup. Working without a remote is
    supported: the main branch is then asked to the user and the remote-side values stay ``None``.
    """

    REMOTE: ClassVar[Optional[str]] = None
    HEAD: ClassVar[str] = ""
    BRANCH_HEAD: ClassVar[Optional[str]] = None
    MAIN_BRANCH: ClassVar[str] = ""
    MAIN_LOCAL_HASH: ClassVar[str] = ""
    MAIN_REMOTE_HASH: ClassVar[Optional[str]] = None
    _INITIALIZED: ClassVar[bool] = False

    def __new__(cls, *args, **kwargs) -> Self:
        """Resolve the repository snapshot before the first instance (of any subclass) is built.

        The extra positional/keyword arguments are accepted (and ignored) because dataclass
        subclasses forward their ``__init__`` arguments here.

        Parameters:
            args: Positional arguments forwarded by subclass constructors (ignored).
            kwargs: Keyword arguments forwarded by subclass constructors (ignored).

        Raises:
            LookupError: If the main branch cannot be resolved (propagated from get_repo_details).

        Returns:
            Self: The new instance.
        """
        if not Repo._INITIALIZED:
            Repo.REMOTE = get_remote()
            if (
                Repo.REMOTE
                and get_validated_input(
                    "Do you want to fetch and prune the remote branches before proceeding?", ["y", "n"]
                )
                == "y"
            ):
                run_operation(f"git fetch {Repo.REMOTE} --prune", "Fetching and pruning remotes", timeout=15)
            cls.get_repo_details()
            Repo._INITIALIZED = True
        return super().__new__(cls)

    @classmethod
    def get_main_hash(cls) -> str:
        """Return the hash the merge checks must compare against.

        The remote main hash wins over the local one, so a branch is always judged against the main
        branch as the remote has it and never against a local copy that may be behind.

        Parameters:
            None

        Raises:
            InternalStateError: If neither hash is available, which get_repo_details already ruled
                out during initialization.

        Returns:
            str: The remote main branch hash when available, the local one otherwise.
        """
        main_hash: Optional[str] = cls.MAIN_REMOTE_HASH if cls.MAIN_REMOTE_HASH else cls.MAIN_LOCAL_HASH
        if not main_hash:
            raise InternalStateError(
                "Neither the remote nor the local main branch hash is available, "
                "a state initialization already ruled out. This is a bug."
            )
        return main_hash

    @classmethod
    def get_repo_details(cls) -> None:
        """Resolve and cache the repository details (main branch, hashes, current branch).

        With a remote, the main branch comes from the local ``refs/remotes/{remote}/HEAD`` symbolic
        reference, falling back to asking the remote itself (``git remote show``) when that
        reference was never set up. Without a remote, the user is asked to pick the main branch
        among the local ones.

        Parameters:
            None

        Raises:
            LookupError: If the main branch cannot be resolved, or resolves to no commit at all.
            KeyError: If the user exhausts the attempts to name an existing local branch.

        Returns:
            None
        """
        main_branch: str
        main_ref: Optional[str] = None
        if Repo.REMOTE:
            main_ref = run_operation(
                f"git symbolic-ref --quiet {REMOTE_PREFIX}/{Repo.REMOTE}/HEAD",
                "Getting main branch",
                check=False,
            ).stdout.strip()
            if main_ref:
                main_branch = main_ref.removeprefix(f"{REMOTE_PREFIX}/{Repo.REMOTE}/")
            else:
                # The symbolic reference is only created by clone/set-head, so a hand-added remote
                # may not have it; the remote itself is then the only authority on its HEAD branch.
                listing: str = run_operation(
                    f"git remote show {Repo.REMOTE}", "Getting main branch from the remote"
                ).stdout.strip()
                match = re.search(r"^\s*HEAD branch:\s*(\S+)", listing, re.MULTILINE)
                if not match:
                    raise LookupError(f"No main branch found in the current repository for remote {Repo.REMOTE}")
                main_branch = match.group(1)
                main_ref = f"{REMOTE_PREFIX}/{Repo.REMOTE}/{main_branch}"
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
        Repo.MAIN_BRANCH = main_branch
        Repo.HEAD = cls._resolve_ref("HEAD")
        Repo.MAIN_LOCAL_HASH = cls._resolve_ref(f"{LOCAL_PREFIX}/{main_branch}")
        Repo.MAIN_REMOTE_HASH = cls._resolve_ref(main_ref) if main_ref else None
        if not Repo.MAIN_LOCAL_HASH and not Repo.MAIN_REMOTE_HASH:
            raise LookupError(
                f"The main branch '{main_branch}' resolves to no commit, neither locally nor on the remote. "
                "Fetch the remote or create the branch locally and try again."
            )
        branch_head: str = run_operation(
            "git branch --show-current", "Getting current branch", timeout=3
        ).stdout.strip()
        Repo.BRANCH_HEAD = branch_head if branch_head else None

    @staticmethod
    def _resolve_ref(ref: str) -> str:
        """Resolve a reference to its commit hash, tolerating a missing reference.

        A missing reference is an ordinary answer here (e.g. the local main branch was deleted, or
        the remote main was never fetched), so the resolution is not retried nor treated as an
        error: the empty string simply reports the absence.

        Parameters:
            ref: The reference to resolve, e.g. ``HEAD`` or ``refs/heads/master``.

        Raises:
            None

        Returns:
            str: The commit hash, or an empty string when the reference does not exist.
        """
        return run_operation(
            f"git rev-parse --verify --quiet {ref}", f"Resolving reference '{ref}'", check=False, timeout=3
        ).stdout.strip()

    @classmethod
    def reset(cls) -> None:
        """Clear the cached snapshot so the next instantiation resolves it again (used by tests).

        Parameters:
            None

        Raises:
            None

        Returns:
            None
        """
        Repo._INITIALIZED = False
        Repo.REMOTE = None
        Repo.HEAD = ""
        Repo.BRANCH_HEAD = None
        Repo.MAIN_BRANCH = ""
        Repo.MAIN_LOCAL_HASH = ""
        Repo.MAIN_REMOTE_HASH = None
