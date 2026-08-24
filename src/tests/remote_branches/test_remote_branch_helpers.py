"""Tests for the branch models (mega_snake.remote_branches.remote_branch)."""

import contextlib
import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Iterator, Optional
from unittest.mock import patch

import pytest

from mega_snake.remote_branches.remote_branch import (
    Branch,
    BranchLoader,
    Commit,
    GitBranch,
    LocalBranch,
    RemoteBranch,
)
from mega_snake.util.formatting import InternalStateError
from mega_snake.util.repo import Repo

# Distinct hashes everywhere so a crossed comparison (local main vs remote main vs a branch tip)
# cannot pass by coincidence.
LOCAL_MAIN_HASH = "localmain111"
REMOTE_MAIN_HASH = "remotemain222"
FEATURE_HASH = "feature333"
ANCESTOR_HASH = "ancestor444"
OCTOPUS_HASH = "octopus555"
TREE_HASH = "tree666"
SYNTHETIC_HASH = "synthetic777"

FEATURE_DATE = 1735689600.0  # 2025-01-01T00:00:00Z


@pytest.fixture(autouse=True)
def seeded_repo() -> Iterator[None]:
    """Seed the Repo snapshot so the models never trigger the real (interactive) resolution."""
    Repo.reset()
    Repo.REMOTE = "origin"
    Repo.MAIN_BRANCH = "master"
    Repo.MAIN_LOCAL_HASH = LOCAL_MAIN_HASH
    Repo.MAIN_REMOTE_HASH = REMOTE_MAIN_HASH
    Repo.HEAD = "headhash"
    Repo.BRANCH_HEAD = "feature"
    Repo._INITIALIZED = True
    yield
    Repo.reset()


@contextlib.contextmanager
def scripted_git(
    merged_hashes: tuple[str, ...] = (),
    cherry: str = "+ c1 one",
    cherry_synthetic: str = "+ synthetic",
    ancestor: str = ANCESTOR_HASH,
) -> Iterator[SimpleNamespace]:
    """Patch the git plumbing the models call, answering from the scripted values.

    ``merged_hashes`` are the tips ``merge-base --is-ancestor`` reports as merged; ``cherry`` is the
    per-commit patch-id listing, ``cherry_synthetic`` the one for the synthetic squash commit.
    Yields a namespace exposing both mocks for command assertions.
    """

    def fake_run_operation(command: str, description: str, check: bool = True, timeout: Optional[float] = None):
        """Route each known git command to its scripted answer."""
        if command.startswith("git merge-base --octopus "):
            return SimpleNamespace(stdout=f"{OCTOPUS_HASH}\n")
        if command.startswith("git merge-base "):
            return SimpleNamespace(stdout=f"{ancestor}\n")
        if command.startswith("git cherry ") and command.endswith(SYNTHETIC_HASH):
            return SimpleNamespace(stdout=f"{cherry_synthetic}\n")
        if command.startswith("git cherry "):
            return SimpleNamespace(stdout=f"{cherry}\n")
        if command.startswith("git rev-parse ") and command.endswith("^{tree}"):
            return SimpleNamespace(stdout=f"{TREE_HASH}\n")
        if command.startswith("git commit-tree "):
            return SimpleNamespace(stdout=f"{SYNTHETIC_HASH}\n")
        raise AssertionError(f"unexpected command: {command}")

    def fake_return_code(command: str, description: str, timeout: Optional[float] = None) -> int:
        """Report as merged only the scripted tips."""
        return 0 if any(tip in command for tip in merged_hashes) else 1

    with patch("mega_snake.remote_branches.remote_branch.run_operation", side_effect=fake_run_operation) as run_op, (
        patch(
            "mega_snake.remote_branches.remote_branch.get_command_return_code",
            autospec=True,
            side_effect=fake_return_code,
        )
    ) as return_code:
        yield SimpleNamespace(run_operation=run_op, get_command_return_code=return_code)


def build_local(
    name: str = "refs/heads/feature",
    commit_hash: str = FEATURE_HASH,
    upstream: Optional[str] = "refs/remotes/origin/feature",
    **scripted,
) -> LocalBranch:
    """Build a LocalBranch against the scripted git plumbing."""
    with scripted_git(**scripted):
        return LocalBranch(
            hash=commit_hash, message="feat msg", mail="a@b", date=FEATURE_DATE, name=name, upstream=upstream
        )


def build_remote(
    name: str = "refs/remotes/origin/feature", commit_hash: str = FEATURE_HASH, **scripted
) -> RemoteBranch:
    """Build a RemoteBranch against the scripted git plumbing."""
    with scripted_git(**scripted):
        return RemoteBranch(hash=commit_hash, message="feat msg", mail="a@b", date=FEATURE_DATE, name=name)


def test_commit_derives_both_time_representations_from_the_timestamp() -> None:
    """The datetime and its string form must both come from the unix timestamp, in UTC."""
    commit = Commit(hash="abc", message="msg", mail="a@b", date=FEATURE_DATE)
    assert commit.dt_time == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert commit.str_time == "2025-01-01T00:00:00Z"


def test_short_name_strips_the_prefix_of_each_branch_kind() -> None:
    """A local branch loses `refs/heads/`, a remote one loses `refs/remotes/{remote}/` — so both
    end up with the plain name the deletion commands need."""
    local = build_local(name="refs/heads/feature/foo")
    remote = build_remote(name="refs/remotes/origin/feature/foo")
    assert local.short_name == "feature/foo"
    assert remote.short_name == "feature/foo"
    assert remote.short_name != "origin/feature/foo", "the remote name must not survive in the short name"


def test_branch_base_class_cannot_be_instantiated() -> None:
    """Only the subclasses know their reference prefix, so the base class refuses to build."""
    with scripted_git():
        with pytest.raises(InternalStateError, match="abstract"):
            Branch(hash=FEATURE_HASH, message="msg", mail="a@b", date=FEATURE_DATE, name="refs/heads/x")


def test_merge_checks_compare_against_the_remote_main_hash() -> None:
    """History comparisons must use the remote main hash, never the possibly stale local one."""
    with scripted_git(merged_hashes=(FEATURE_HASH,)) as git:
        LocalBranch(
            hash=FEATURE_HASH, message="m", mail="a@b", date=FEATURE_DATE, name="refs/heads/feature", upstream=None
        )
    ancestor_check = git.get_command_return_code.call_args_list[0].args[0]
    assert ancestor_check == f"git merge-base --is-ancestor {FEATURE_HASH} {REMOTE_MAIN_HASH}"
    assert LOCAL_MAIN_HASH not in ancestor_check
    merge_base = git.run_operation.call_args_list[0].args[0]
    assert merge_base == f"git merge-base {FEATURE_HASH} {REMOTE_MAIN_HASH}"


def test_an_ancestor_tip_is_merged_without_patch_id_checks() -> None:
    """A tip that is an ancestor of main is merged by ancestry alone: no cherry call is issued."""
    branch = build_local(merged_hashes=(FEATURE_HASH,))
    assert branch.merged_on_main is True
    assert branch.main_common_ancestor == ANCESTOR_HASH


def test_a_rebase_merged_branch_is_detected_by_patch_id() -> None:
    """Every commit already applied on main (all cherry lines marked '-') means a rebase merge."""
    branch = build_local(cherry="- c1 one\n- c2 two")
    assert branch.merged_on_main is True


def test_a_squash_merged_branch_is_detected_through_the_synthetic_commit() -> None:
    """When individual commits are missing but the combined diff is applied, the synthetic-commit
    cherry answers '-' and the branch counts as merged."""
    branch = build_local(cherry="+ c1 one\n+ c2 two", cherry_synthetic=f"- {SYNTHETIC_HASH} msg")
    assert branch.merged_on_main is True


def test_a_partially_applied_branch_stays_unmerged() -> None:
    """Some commits applied and a combined diff still missing is neither merge style."""
    branch = build_local(cherry="- c1 one\n+ c2 two", cherry_synthetic=f"+ {SYNTHETIC_HASH} msg")
    assert branch.merged_on_main is False


def test_a_branch_with_no_own_commits_is_not_a_rebase_merge_by_itself() -> None:
    """An empty cherry output means the branch carries no commits of its own — a case the ancestry
    check owns — so the rebase check must NOT claim it as merged. The squash check still gets its
    turn, and here it is the only thing that can decide.

    The two cases together are what pins this: with an empty cherry output the verdict must follow
    the squash check in *both* directions. Asserting only the merged case would pass just as well
    against a rebase check that wrongly returned True on empty output.
    """
    with scripted_git(cherry="", cherry_synthetic=f"+ {SYNTHETIC_HASH} msg") as git:
        not_merged = LocalBranch(
            hash=FEATURE_HASH, message="m", mail="a@b", date=FEATURE_DATE, name="refs/heads/feature", upstream=None
        )
    assert not_merged.merged_on_main is False, "an empty cherry output alone must not mean merged"
    issued = [issued_call.args[0] for issued_call in git.run_operation.call_args_list]
    assert any(command.startswith("git commit-tree") for command in issued), "the squash check must still run"

    merged = build_local(cherry="", cherry_synthetic=f"- {SYNTHETIC_HASH} msg")
    assert merged.merged_on_main is True, "the squash check alone decides when there is no cherry output"


def test_without_a_common_ancestor_the_patch_id_checks_are_skipped() -> None:
    """An orphan branch shares no history with main: nothing to compare, so it stays unmerged and
    no cherry command is issued."""
    with scripted_git(ancestor="") as git:
        branch = LocalBranch(
            hash=FEATURE_HASH, message="m", mail="a@b", date=FEATURE_DATE, name="refs/heads/orphan", upstream=None
        )
    assert branch.merged_on_main is False
    issued = [issued_call.args[0] for issued_call in git.run_operation.call_args_list]
    assert not any(command.startswith("git cherry") for command in issued)


def test_the_main_branch_itself_is_never_squash_checked() -> None:
    """The main branch trivially matches its own patches; running the squash/rebase detection on it
    would mislabel it, so an unmerged main tip stays unmerged with no cherry calls."""
    with scripted_git() as git:
        branch = LocalBranch(
            hash="aheadmain888", message="m", mail="a@b", date=FEATURE_DATE, name="refs/heads/master", upstream=None
        )
    assert branch.merged_on_main is False
    issued = [issued_call.args[0] for issued_call in git.run_operation.call_args_list]
    assert not any(command.startswith("git cherry") for command in issued)


def test_remote_branch_requires_a_remote_name() -> None:
    """The loader enumerates remote references only when a remote exists, so building a remote
    branch without one means the loader and this model drifted apart — our defect, not the user's."""
    Repo.REMOTE = None
    with scripted_git():
        with pytest.raises(InternalStateError, match="This is a bug"):
            RemoteBranch(hash=FEATURE_HASH, message="m", mail="a@b", date=FEATURE_DATE, name="refs/remotes/origin/x")


def test_remote_branch_works_when_the_remote_main_reference_was_never_fetched() -> None:
    """A remote whose main reference was never fetched (or was pruned), while other remote branches
    were, is an ordinary environment state — not a defect in mgsnake.

    Repo.get_main_hash already covers it by falling back to the local main hash, so the branch must
    simply be judged against that. Refusing here reported a situation the user fixes with a single
    `git fetch` as an internal bug, with exit 100 and a traceback.
    """
    Repo.MAIN_REMOTE_HASH = None
    with scripted_git(merged_hashes=(FEATURE_HASH,)) as git:
        branch = RemoteBranch(
            hash=FEATURE_HASH, message="m", mail="a@b", date=FEATURE_DATE, name="refs/remotes/origin/feature"
        )

    assert branch.short_name == "feature"
    ancestor_check = git.get_command_return_code.call_args_list[0].args[0]
    assert LOCAL_MAIN_HASH in ancestor_check, "the comparison must fall back to the local main hash"


def test_from_local_without_upstream_finishes_as_local_only() -> None:
    """A branch with no upstream can never be paired: it closes immediately with the local_only
    marker, and its merge status comes from its single side."""
    local = build_local(upstream=None, merged_hashes=(FEATURE_HASH,))
    with scripted_git():
        git_branch = GitBranch.from_local(local)
    assert git_branch.track == GitBranch.LOCAL_ONLY
    assert git_branch.trackshort == GitBranch.SHORT_NA
    assert git_branch.remote is None
    assert git_branch.fully_merged is True
    assert git_branch.merge_status == "merged"
    assert git_branch.main_common_ancestor == OCTOPUS_HASH


def test_from_local_with_upstream_stays_open_until_paired() -> None:
    """A branch with an upstream keeps git's tracking values and waits for pair_remotes to close
    it, so the derived fields are not computed yet."""
    local = build_local()
    with scripted_git():
        git_branch = GitBranch.from_local(local, "[ahead 1]", ">")
    assert git_branch.track == "[ahead 1]"
    assert git_branch.trackshort == ">"
    assert not git_branch._ready
    with pytest.raises(InternalStateError, match="fully initialized"):
        GitBranch.require_initialization([git_branch])


def test_from_remote_finishes_as_remote_only() -> None:
    """A remote branch nobody tracks closes immediately with the remote_only marker."""
    remote = build_remote(merged_hashes=())
    with scripted_git():
        git_branch = GitBranch.from_remote(remote)
    assert git_branch.track == GitBranch.REMOTE_ONLY
    assert git_branch.local is None
    assert git_branch.fully_merged is False
    assert git_branch.merge_status == "unmerged"


def test_pair_remotes_matches_upstreams_and_reports_the_leftovers() -> None:
    """Each waiting instance gets the remote branch its upstream names — or None when it is gone —
    and the remote branches nobody tracks are handed back for their own instances."""
    paired_local = build_local(upstream="refs/remotes/origin/feature", merged_hashes=(FEATURE_HASH, "remotefeat999"))
    gone_local = build_local(
        name="refs/heads/merged-and-pruned",
        commit_hash="pruned000",
        upstream="refs/remotes/origin/merged-and-pruned",
        merged_hashes=("pruned000",),
    )
    paired_remote = build_remote(commit_hash="remotefeat999", merged_hashes=(FEATURE_HASH, "remotefeat999"))
    unpaired_remote = build_remote(name="refs/remotes/origin/other", commit_hash="other111")
    with scripted_git():
        instances = [
            GitBranch.from_local(paired_local, "[ahead 1]", ">"),
            GitBranch.from_local(gone_local, "[gone]", None),
        ]
        leftovers = GitBranch.pair_remotes(instances, [paired_remote, unpaired_remote])

    assert leftovers == [unpaired_remote], "only the remote branch nobody tracks is left over"
    assert instances[0].remote is paired_remote
    assert instances[0].fully_merged is True
    assert instances[0].merge_status == "merged"
    assert instances[1].remote is None, "a gone upstream closes the instance with no remote side"
    assert instances[1].fully_merged is True, "a merged local branch with a pruned remote is fully merged"
    assert instances[1].track == "[gone]", "git's tracking marker must survive the pairing"


def test_one_stale_side_blocks_fully_merged() -> None:
    """fully_merged requires every existing side to be merged: a merged remote with a local copy
    still carrying work (or vice versa) is not a safe deletion candidate."""
    local = build_local(merged_hashes=())
    remote_merged = build_remote(commit_hash="remotefeat999", merged_hashes=("remotefeat999",))
    with scripted_git():
        instance = GitBranch.from_local(local, "[behind 1]", "<")
        GitBranch.pair_remotes([instance], [remote_merged])
    assert instance.fully_merged is False
    assert instance.merge_status == "remote merged"

    local_merged = build_local(merged_hashes=(FEATURE_HASH,))
    remote_stale = build_remote(commit_hash="remotefeat999", merged_hashes=())
    with scripted_git():
        instance = GitBranch.from_local(local_merged, "[ahead 1]", ">")
        GitBranch.pair_remotes([instance], [remote_stale])
    assert instance.fully_merged is False
    assert instance.merge_status == "local merged"


def test_get_any_branch_requires_at_least_one_side() -> None:
    """An instance with neither side is a bug the builders never produce."""
    instance = GitBranch()
    object.__setattr__(instance, "local", None)
    object.__setattr__(instance, "remote", None)
    with pytest.raises(InternalStateError, match="This is a bug"):
        instance.get_any_branch()


def test_git_branches_order_by_their_tip_commit_timestamp() -> None:
    """Sorting must follow the tip commit date of whichever side the instance carries."""
    older = build_local(upstream=None)
    newer_remote = build_remote(commit_hash="newer222", **{})
    with scripted_git():
        older_instance = GitBranch.from_local(older)
        newer_instance = GitBranch.from_remote(newer_remote)
    object.__setattr__(newer_remote, "dt_time", datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert older_instance < newer_instance
    assert not newer_instance < older_instance


def test_markdown_row_shows_both_hashes_and_escapes_pipes() -> None:
    """The row must carry both abbreviated hashes, the placeholder for a missing side, and escape
    the pipes of free-text cells so a commit subject cannot tear the table apart."""
    local = build_local(upstream=None, merged_hashes=(FEATURE_HASH,))
    object.__setattr__(local, "message", "feat: add | pipe")
    with scripted_git():
        instance = GitBranch.from_local(local)
    assert instance.to_markdown_row() == (
        f"| feature | merged | local_only | - | {FEATURE_HASH[:12]} | - "
        f"| 2025-01-01T00:00:00Z | a@b | feat: add \\| pipe | {OCTOPUS_HASH[:12]} |"
    )


def _loader_run_operation(local_listing: str, remote_listing: str):
    """Build the run_operation double BranchLoader tests share, scripted per enumeration."""

    def fake_run_operation(command: str, description: str, check: bool = True, timeout: Optional[float] = None):
        """Answer the enumeration and plumbing commands the loader path issues."""
        if command.startswith("git for-each-ref") and command.endswith(" refs/heads"):
            return SimpleNamespace(stdout=local_listing)
        if command.startswith("git for-each-ref") and command.endswith(" refs/remotes/origin"):
            return SimpleNamespace(stdout=remote_listing)
        if command.startswith("git merge-base --octopus "):
            return SimpleNamespace(stdout=f"{OCTOPUS_HASH}\n")
        if command.startswith("git merge-base "):
            return SimpleNamespace(stdout=f"{ANCESTOR_HASH}\n")
        if command.startswith("git cherry "):
            return SimpleNamespace(stdout="+ c1 one\n")
        if command.startswith("git rev-parse ") and command.endswith("^{tree}"):
            return SimpleNamespace(stdout=f"{TREE_HASH}\n")
        if command.startswith("git commit-tree "):
            return SimpleNamespace(stdout=f"{SYNTHETIC_HASH}\n")
        raise AssertionError(f"unexpected command: {command}")

    return fake_run_operation


def test_from_repository_pairs_locals_and_remotes_and_skips_the_head_reference() -> None:
    """The loader enumerates both sides once, pairs them through the upstreams, skips the remote's
    symbolic HEAD, and stitches a tab inside the subject back together."""
    local_listing = (
        "aaa1\t1735689600\ta@b\trefs/heads/master\trefs/remotes/origin/master\t\t=\tinit\n"
        "bbb2\t1735689700\ta@b\trefs/heads/feature\trefs/remotes/origin/feature\t[ahead 1]\t>\tfeat\tmsg\n"
        "ccc3\t1735689800\ta@b\trefs/heads/local-only\t\t\t\tlocal msg\n"
    )
    remote_listing = (
        "eee5\t1735690000\tx@y\trefs/remotes/origin/HEAD\thead ref\n"
        "aaa1\t1735689600\ta@b\trefs/remotes/origin/master\tinit\n"
        "fff6\t1735690100\tc@d\trefs/remotes/origin/feature\tfeat msg\n"
        "ggg7\t1735690200\tc@d\trefs/remotes/origin/other\tother msg\n"
    )
    with patch(
        "mega_snake.remote_branches.remote_branch.run_operation",
        side_effect=_loader_run_operation(local_listing, remote_listing),
    ), patch("mega_snake.remote_branches.remote_branch.get_command_return_code", autospec=True, return_value=1):
        branches = BranchLoader.from_repository()

    by_name = {branch.get_any_branch().short_name: branch for branch in branches}
    assert sorted(by_name) == ["feature", "local-only", "master", "other"], "HEAD must never become a branch"
    assert by_name["feature"].local.hash == "bbb2"
    assert by_name["feature"].remote.hash == "fff6"
    assert by_name["feature"].local.message == "feat\tmsg", "a tab inside the subject must survive"
    assert by_name["feature"].track == "[ahead 1]"
    assert by_name["feature"].trackshort == ">"
    assert by_name["local-only"].remote is None
    assert by_name["local-only"].track == GitBranch.LOCAL_ONLY
    assert by_name["other"].local is None
    assert by_name["other"].track == GitBranch.REMOTE_ONLY
    assert all(branch._ready for branch in branches)


def test_from_repository_without_a_remote_never_enumerates_remote_references() -> None:
    """With no remote there is nothing to enumerate remotely, and no RemoteBranch may be built."""
    Repo.REMOTE = None
    Repo.MAIN_REMOTE_HASH = None
    local_listing = "ccc3\t1735689800\ta@b\trefs/heads/local-only\t\t\t\tlocal msg\n"
    with patch(
        "mega_snake.remote_branches.remote_branch.run_operation",
        side_effect=_loader_run_operation(local_listing, ""),
    ) as run_operation, patch("mega_snake.remote_branches.remote_branch.get_command_return_code", autospec=True, return_value=0):
        branches = BranchLoader.from_repository()
    assert [branch.get_any_branch().short_name for branch in branches] == ["local-only"]
    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert not any("refs/remotes" in command for command in issued)


@pytest.mark.parametrize(
    "local_listing,remote_listing",
    [
        ("aaa1\t1735689600\ta@b\n", ""),
        (
            "aaa1\t1735689600\ta@b\trefs/heads/master\trefs/remotes/origin/master\t\t=\tinit\n",
            "eee5\t1735690000\tx@y\n",
        ),
    ],
    ids=["malformed-local-line", "malformed-remote-line"],
)
def test_from_repository_rejects_a_malformed_enumeration_line(local_listing: str, remote_listing: str) -> None:
    """A for-each-ref line without the expected fields means our format string and our parser
    drifted apart — a bug, reported as such instead of an index error."""
    with patch(
        "mega_snake.remote_branches.remote_branch.run_operation",
        side_effect=_loader_run_operation(local_listing, remote_listing),
    ), patch("mega_snake.remote_branches.remote_branch.get_command_return_code", autospec=True, return_value=1):
        with pytest.raises(InternalStateError, match="tab-separated fields"):
            BranchLoader.from_repository()


def test_from_repository_propagates_a_failing_enumeration() -> None:
    """git can fail while listing the references. Returning a partial inventory would let the
    cleanup act on a repository it never fully read, so the failure must surface."""
    with patch(
        "mega_snake.remote_branches.remote_branch.run_operation",
        side_effect=subprocess.SubprocessError("git exploded"),
    ), patch("mega_snake.remote_branches.remote_branch.get_command_return_code", autospec=True, return_value=1):
        with pytest.raises(subprocess.SubprocessError, match="git exploded"):
            BranchLoader.from_repository()


def test_from_repository_propagates_a_failure_while_describing_a_branch() -> None:
    """The per-branch merge checks run git too. A failure there must not be swallowed into a branch
    silently reported as unmerged — which would quietly hide a deletion candidate."""

    def failing_after_enumeration(
        command: str, description: str, check: bool = True, timeout: Optional[float] = None
    ):
        """Answer the enumeration, then fail on the first merge check."""
        if command.startswith("git for-each-ref") and command.endswith(" refs/heads"):
            return SimpleNamespace(stdout="ccc3\t1735689800\ta@b\trefs/heads/feature\t\t\t\tmsg\n")
        raise subprocess.SubprocessError("merge-base exploded")

    with patch(
        "mega_snake.remote_branches.remote_branch.run_operation", side_effect=failing_after_enumeration
    ), patch("mega_snake.remote_branches.remote_branch.get_command_return_code", autospec=True, return_value=1):
        with pytest.raises(subprocess.SubprocessError, match="merge-base exploded"):
            BranchLoader.from_repository()


def test_from_repository_propagates_a_failing_local_enumeration_specifically() -> None:
    """The local enumeration is the first git call, and its failure must surface on its own.

    Pinning it separately matters: a loader that swallowed this one and carried on with an empty
    local list would still raise later from the remote enumeration, so a test that fails every git
    call cannot tell the two apart. Here only the local listing fails, and nothing downstream runs.
    """

    def fail_only_the_local_listing(
        command: str, description: str, check: bool = True, timeout: Optional[float] = None
    ):
        """Fail the local enumeration; answer anything else as a working repository would."""
        if command.startswith("git for-each-ref") and command.endswith(" refs/heads"):
            raise subprocess.SubprocessError("for-each-ref exploded")
        return SimpleNamespace(stdout="")

    with patch(
        "mega_snake.remote_branches.remote_branch.run_operation", side_effect=fail_only_the_local_listing
    ) as run_operation, patch(
        "mega_snake.remote_branches.remote_branch.get_command_return_code", autospec=True, return_value=1
    ):
        with pytest.raises(subprocess.SubprocessError, match="for-each-ref exploded"):
            BranchLoader.from_repository()

    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert not any("refs/remotes" in command for command in issued), "nothing may run after the failure"
