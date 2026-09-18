"""
Selection and deletion helpers for the branch cleanup: pick the fully merged branches the user
wants gone, then delete each one from the sides (local / remote) where it actually exists.
"""

import subprocess
from typing import NamedTuple, Optional
from mega_snake.util.formatting import ws_error, ws_success, ws_warning
from mega_snake.remote_branches.remote_branch import GitBranch
from mega_snake.util.repo import Repo
from mega_snake.util.util import REMOTE_PREFIX, get_validated_input, run_operation


class Garbage(NamedTuple):
    """A branch selected for deletion, named once per side it exists on.

    The two sides carry **separate** names on purpose. A logical branch pairs a local branch with
    its remote counterpart through ``local.upstream`` — a reference, not a name — so the two are
    free to disagree: ``git branch -m old new`` leaves the local branch called ``new`` while it
    still tracks ``origin/old``. Collapsing both into a single name made the deletion issue
    ``git push -d origin new``, which either fails (nothing was cleaned, and the local deletion
    never ran either) or, when an unrelated ``origin/new`` happens to exist, deletes a branch the
    user was never asked about and whose merge status was never checked.

    A ``None`` side means the branch does not exist there, so the name's presence is the single
    source of truth for where the branch lives: no reference re-probing is needed later. The names
    come from the same enumeration that built the branch inventory.

    Attributes:
        local_name: The local branch name, or None when the branch only exists on the remote.
        remote_name: The branch name **as the remote has it**, or None when the branch only exists
            locally.
    """

    local_name: Optional[str]
    remote_name: Optional[str]


def _targets_main_branch(branch: GitBranch, main_branch: str) -> bool:
    """Report whether any side of the branch is the main branch.

    Every side is inspected, because ``get_any_branch()`` returns the local side whenever it exists
    and would therefore never look at the remote one. The ordinary way to reach that blind spot is
    ``git checkout -b work origin/main``: the branch is fully merged by construction, its local name
    is not the main branch, and the guard that is supposed to make deleting the main branch
    impossible would let it through.

    The local branch's upstream is checked too, for the case where the remote side is absent because
    it was pruned (``[gone]``): the pairing is gone, but the local branch is still an alias of the
    main branch and must not be offered either.

    Parameters:
        branch: The logical branch to inspect.
        main_branch: The resolved main branch name.

    Raises:
        None

    Returns:
        bool: True when any side of the branch is the main branch, False otherwise.
    """
    if any(side.short_name == main_branch for side in (branch.local, branch.remote) if side is not None):
        return True
    upstream: Optional[str] = getattr(branch.local, "upstream", None)
    if upstream is None or not Repo.REMOTE:
        return False
    prefix: str = f"{REMOTE_PREFIX}/{Repo.REMOTE}/"
    return upstream.startswith(prefix) and upstream.removeprefix(prefix) == main_branch


def parsing_branches(branches: list[GitBranch]) -> list[Garbage]:
    """
    Ask the user which of the fully merged branches to delete.

    Only fully merged branches are offered (every side that exists is merged into the main branch),
    and the main branch itself is never a candidate — on any of its sides, see
    :func:`_targets_main_branch`. The user can stop the review early with the 'finalize' answer.

    The prompt shows the remote name next to the local one whenever the two disagree, so the answer
    is given against the branches that are actually going to be deleted rather than against a single
    name standing in for both.

    Parameters:
        branches: The branch inventory to pick candidates from.

    Raises:
        None

    Returns:
        list[Garbage]: The branches the user selected, each side named separately.
    """
    if len(branches) == 0:
        return []
    main_branch: str = Repo.MAIN_BRANCH
    options: list[str] = ["y", "n", "f"]
    del_branches: list[GitBranch] = [
        branch for branch in branches if branch.fully_merged and not _targets_main_branch(branch, main_branch)
    ]

    garbage: list[Garbage] = []
    for parent in del_branches:
        branch = parent.get_any_branch()
        local_name: Optional[str] = parent.local.short_name if parent.local is not None else None
        remote_name: Optional[str] = parent.remote.short_name if parent.remote is not None else None
        parts = [f"{'local' if parent.local else ''}", f"{'remote' if parent.remote else ''}"]
        result = " and ".join([p for p in parts if p])
        naming: str = branch.short_name
        if local_name is not None and remote_name is not None and local_name != remote_name:
            naming = f"{local_name} (known on the remote as '{remote_name}')"
        prompt = (
            f"\nDo you want to delete the following branch?\n"
            f"\tBranch: {naming}\n"
            f"\tDate: {branch.str_time}\n"
            f"\tAuthor: {branch.mail}\n"
            f"\tCommit: {branch.hash}\n"
            f"\tMessage: {branch.message}\n\n"
            f"\tLocation: {result}\n\n"
            f"(y)es | (n)o | (f)inalize\n"
        )
        user_input = get_validated_input(prompt, options)
        if user_input in {"y", "yes"}:
            garbage.append(Garbage(local_name=local_name, remote_name=remote_name))
        elif user_input in {"f", "finalize"}:
            break
    return garbage


class DeletionOutcome(NamedTuple):
    """What a cleanup run actually managed to delete.

    It exists so the caller can report the truth instead of announcing a blanket success: a run
    where every push failed and a run where everything was deleted are otherwise indistinguishable
    once the loop ends.

    Attributes:
        remote_deleted: The remote names that were deleted from the remote.
        local_deleted: The local names that were deleted from the local repository.
        failures: One human-readable line per side that could not be deleted.
    """

    remote_deleted: list[str]
    local_deleted: list[str]
    failures: list[str]


def delete_branches(garbage: list[Garbage]) -> DeletionOutcome:
    """
    Deletes the branches in the garbage list, from the remote and from the local repository.

    A selected branch does not necessarily exist on both sides: a remote branch from another author
    is commonly never checked out locally, and a branch whose remote counterpart was deleted when its
    pull request was merged only survives locally. Each side is therefore attempted only when
    ``Garbage`` carries a name for it — the names were captured by the same enumeration that built
    the inventory, so re-probing the references here would only repeat that answer. Each side is
    also deleted under **its own** name, which the two are free to disagree on (see :class:`Garbage`).

    **The two sides are caught independently, and must stay that way.** One ``except`` around both
    makes a failed local deletion indistinguishable from a successful one: with ``git push -d`` done,
    a failing ``git branch -D`` — a checked-out branch, another worktree, an ``index.lock`` — leaves
    the local copy in place while the run still reports success. That is the destructive half of the
    operation going unreported, which is the worst thing a cleanup command can do. Every attempt
    reports its own outcome, and the failures are returned so the caller can say what survived. A
    failure on either side moves on to the next branch, so a single unreachable or protected branch
    does not abort the whole cleanup.

    The policy the split makes visible: a branch whose remote deletion failed keeps its local copy,
    because the remote copy survived and dropping the local one would leave the user without the copy
    they can act on. State it in the reporting — a policy only a reader of the control flow can infer
    is a policy the user never learns about.

    The remote is only resolved (and required) when at least one selected branch has a remote side,
    so a local-only cleanup works in a repository without remotes.

    Parameters:
        garbage: The branches selected for deletion.

    Raises:
        EnvironmentError: If a branch must be deleted from the remote and no remote is configured.

    Returns:
        DeletionOutcome: What was deleted on each side, and one line per side that was not.
    """
    outcome = DeletionOutcome(remote_deleted=[], local_deleted=[], failures=[])
    if not garbage:
        return outcome
    remote: Optional[str] = Repo.require_remote() if any(item.remote_name for item in garbage) else None
    for garbage_item in garbage:
        remote_name, local_name = garbage_item.remote_name, garbage_item.local_name
        remote_failed: bool = False
        if remote_name is not None:
            try:
                result = run_operation(
                    f'git push -d "{remote}" "{remote_name}" --no-verify 2>&1',
                    f"Deleting remote branch {remote_name}",
                )
                ws_success(result.stdout.strip())
                outcome.remote_deleted.append(remote_name)
            except subprocess.SubprocessError:
                remote_failed = True
                message = f"Remote branch '{remote_name}' could not be deleted from '{remote}'; it is still there"
                ws_warning(message)
                outcome.failures.append(message)
        if remote_failed and local_name is not None:
            # Deliberately conservative, and unchanged by the split: the remote copy survived, so
            # dropping the local one would leave the user without the only copy they can act on
            # until the next fetch. Now it is stated instead of being silently implied by the
            # shared except.
            message = (
                f"Local branch '{local_name}' was left alone because its remote copy "
                f"'{remote_name}' could not be deleted"
            )
            ws_warning(message)
            outcome.failures.append(message)
        elif local_name is not None:
            try:
                run_operation(f'git branch -D "{local_name}"', f"Deleting local branch {local_name}")
                ws_success(f"Local branch '{local_name}' deleted successfully")
                outcome.local_deleted.append(local_name)
            except subprocess.SubprocessError:
                # Worth an error rather than a warning when the remote copy is already gone: the
                # branch now exists only here, and the user was told it was being removed.
                if remote_name is None:
                    message = f"Local branch '{local_name}' could not be deleted; it is still present"
                    ws_warning(message)
                else:
                    message = (
                        f"Local branch '{local_name}' could not be deleted, but its remote copy "
                        f"'{remote_name}' is already gone; it now only exists locally"
                    )
                    ws_error(message)
                outcome.failures.append(message)
    return outcome
