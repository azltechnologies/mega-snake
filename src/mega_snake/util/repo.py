"""Process-wide snapshot of the git repository the commands operate on.

This module is the single place that talks to git about the repository itself. Every query about
the remote, the main branch or HEAD lives here, so no command has to re-derive them and no two
callers can disagree about the answer.

There are deliberately **two levels** of resolution, because they cost very different things:

- :meth:`Repo.resolve_remote` (and the helpers built on it) answers "which remote?" with a single
  ``git remote``. It is cheap, it never contacts the network, and it is what light-weight commands
  such as ``create-release`` and ``working-env`` use.
- Instantiating :class:`Repo` resolves the **full snapshot** — main branch, its hashes, HEAD — and
  offers to fetch and prune first. That prompt is why the full snapshot is never triggered
  implicitly by the cheap helpers.

Both levels memoize onto class attributes, so within one process git is asked once and the user is
prompted once.
"""

import re
import subprocess
from typing import ClassVar, Optional, Self

from mega_snake.util.formatting import InternalStateError, ws_warning
from mega_snake.util.util import (
    LOCAL_PREFIX,
    REMOTE_PREFIX,
    get_typed_validated_input,
    get_validated_input,
    run_operation,
)

NO_REMOTE_MESSAGE = "No remote repository found. Please add a remote repository to the current repository."


class Repo:
    """Cached repository snapshot shared by every command that needs git context.

    The class attributes are populated exactly once per process (see ``__new__``); subclasses such
    as the branch models read them through normal attribute lookup. Working without a remote is
    supported: the main branch is then asked to the user and the remote-side values stay ``None``.

    Attributes:
        REMOTE: The resolved remote name, or None when the repository has none. Meaningful only
            once ``_REMOTE_RESOLVED`` is set, since None is also a legitimate answer.
        HEAD: The commit HEAD pointed at when the snapshot was taken.
        BRANCH_HEAD: The checked-out branch name, or None on a detached HEAD.
        MAIN_BRANCH: The main branch short name (e.g. ``master``).
        MAIN_LOCAL_HASH: The local main branch tip, or "" when there is no local copy.
        MAIN_REMOTE_HASH: The remote main branch tip, or None without a remote.
        _REMOTE_RESOLVED: Whether the remote question has been answered (see ``REMOTE``).
        _HEAD_RESOLVED: Whether HEAD has been read (see ``HEAD``).
        _INITIALIZED: Whether the full snapshot has been resolved.
    """

    REMOTE: ClassVar[Optional[str]] = None
    HEAD: ClassVar[str] = ""
    BRANCH_HEAD: ClassVar[Optional[str]] = None
    MAIN_BRANCH: ClassVar[str] = ""
    MAIN_LOCAL_HASH: ClassVar[str] = ""
    MAIN_REMOTE_HASH: ClassVar[Optional[str]] = None
    _REMOTE_RESOLVED: ClassVar[bool] = False
    _HEAD_RESOLVED: ClassVar[bool] = False
    _INITIALIZED: ClassVar[bool] = False

    @classmethod
    def resolve_remote(cls) -> Optional[str]:
        """Answer which remote the repository uses, asking git (and the user) only once.

        Resolving is not free: it spawns ``git remote`` and, when the repository has several, it
        prompts the user to pick one. The answer — including "there is none" — is therefore
        memoized on the class, so every later caller reuses it instead of prompting again.

        A failing ``git remote`` (e.g. the current directory is not a repository) is reported as a
        warning and treated as "no remote", so callers get the same friendly handling as a
        repository that simply has none.

        This is the cheap half of the module: it never fetches and never resolves the main branch.

        Parameters:
            None

        Raises:
            None

        Returns:
            Optional[str]: The remote name, or None when there is no remote available.
        """
        if cls._REMOTE_RESOLVED:
            return Repo.REMOTE
        try:
            result: str = run_operation("git remote", "Getting remotes").stdout.strip()
        except subprocess.SubprocessError as error:
            ws_warning(f"{NO_REMOTE_MESSAGE} Unable to get the remotes: {error}")
            result = ""
        remotes: list[str] = [line.strip() for line in result.splitlines() if line.strip()]
        if not remotes:
            Repo.REMOTE = None
        elif len(remotes) == 1:
            Repo.REMOTE = remotes[0]
        else:
            prompt: str = "Multiple remotes found in the current repository; Please select one of the following:\n"
            for index, remote in enumerate(remotes):
                prompt += f"\t{index}: {remote}\n"
            choice = get_validated_input(prompt, [str(index) for index in range(len(remotes))])
            Repo.REMOTE = remotes[int(choice)]
        Repo._REMOTE_RESOLVED = True
        return Repo.REMOTE

    @classmethod
    def require_remote(cls) -> str:
        """Answer which remote the repository uses, failing when it has none.

        This is the single entry point for commands that cannot work without a remote, so they all
        share the same message and the same (memoized) resolution.

        A repository without a remote is not a misuse of the CLI — the user broke no contract — so
        this raises an environment error rather than a ClickException: the exit status then says
        "the environment is not set up", which is a different thing for a script to react to than
        "you called this wrong".

        Parameters:
            None

        Raises:
            EnvironmentError: If the repository has no remote configured.

        Returns:
            str: The remote name.
        """
        remote: Optional[str] = cls.resolve_remote()
        if not remote:
            raise EnvironmentError(NO_REMOTE_MESSAGE)
        return remote

    @classmethod
    def get_remote_url(cls) -> Optional[str]:
        """Return the repository's remote URL, without the trailing ``.git``.

        Parameters:
            None

        Raises:
            None

        Returns:
            Optional[str]: The remote URL, or None when the repository has no remote.
        """
        remote: Optional[str] = cls.resolve_remote()
        if not remote:
            return None
        url: str = run_operation(f"git remote get-url {remote}", "Getting remote URL").stdout.strip()
        return re.sub(r"\.git$", "", url)

    @classmethod
    def resolve_head(cls) -> str:
        """Answer which commit HEAD points at, asking git only once.

        This is the same two-level arrangement as :meth:`resolve_remote`: it is the cheap accessor
        light-weight commands use (``create-release``, ``diff-tree`` with an explicit origin), and
        the full snapshot reuses it rather than reading HEAD a second time. ``HEAD`` is its cache,
        which is why there is no separate "current commit" helper — one implementation, one value.

        The read goes through :meth:`_resolve_ref` like every other reference, so there is one
        implementation of "resolve a ref" in the class. What this adds on top is that HEAD is
        **required**: its callers build a diff range or a release target out of it, and an empty
        string there would silently produce a malformed command rather than a visible failure.

        The absence is detected from the empty result rather than from a non-zero exit, because a
        repository with no commits is an ordinary state, not an operational failure: letting
        ``run_operation`` fail on it would retry three times with a two second pause and report a
        subprocess error instead of the plain fact that there is nothing to point at.

        Parameters:
            None

        Raises:
            LookupError: If HEAD does not resolve to a commit, i.e. the repository has no commits.

        Returns:
            str: The commit hash HEAD points at.
        """
        if not cls._HEAD_RESOLVED:
            head: str = cls._resolve_ref("HEAD")
            if not head:
                raise LookupError(
                    "HEAD does not resolve to any commit. The repository has no commits yet, "
                    "so there is nothing to compare or release from."
                )
            Repo.HEAD = head
            Repo._HEAD_RESOLVED = True
        return Repo.HEAD

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
            Repo.resolve_remote()
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
        cls.resolve_head()
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
        """Clear every cached answer so the next call resolves it again (used by tests).

        Both levels are cleared: the remote question and the full snapshot.

        Parameters:
            None

        Raises:
            None

        Returns:
            None
        """
        Repo._INITIALIZED = False
        Repo._REMOTE_RESOLVED = False
        Repo._HEAD_RESOLVED = False
        Repo.REMOTE = None
        Repo.HEAD = ""
        Repo.BRANCH_HEAD = None
        Repo.MAIN_BRANCH = ""
        Repo.MAIN_LOCAL_HASH = ""
        Repo.MAIN_REMOTE_HASH = None
