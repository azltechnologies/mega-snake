"""Tests for the Repo snapshot (mega_snake.util.repo)."""

import subprocess
from types import SimpleNamespace
from typing import Iterator, Optional
from unittest.mock import patch

import pytest

from mega_snake.util.formatting import InternalStateError
from mega_snake.util.repo import Repo

SYMBOLIC_REF = "git symbolic-ref --quiet refs/remotes/origin/HEAD"
REMOTE_SHOW = "git remote show origin"
HEAD_RESOLVE = "git rev-parse --verify --quiet HEAD"
LOCAL_MAIN_RESOLVE = "git rev-parse --verify --quiet refs/heads/master"
REMOTE_MAIN_RESOLVE = "git rev-parse --verify --quiet refs/remotes/origin/master"
CURRENT_BRANCH = "git branch --show-current"
FETCH = "git fetch origin --prune"
LOCAL_BRANCHES = "git for-each-ref --format='%(refname:short)' refs/heads"

# Distinct hashes so a crossed assignment (local vs remote vs HEAD) cannot pass unnoticed.
HEAD_HASH = "headhash111"
LOCAL_MAIN_HASH = "localhash222"
REMOTE_MAIN_HASH = "remotehash333"


@pytest.fixture(autouse=True)
def clean_repo() -> Iterator[None]:
    """Reset the cached snapshot around every test, since it is process-wide state."""
    Repo.reset()
    yield
    Repo.reset()


def run_operation_answering(answers: dict[str, str]):
    """Build a run_operation double answering each known command with its scripted stdout."""

    def fake_run_operation(command: str, description: str, check: bool = True, timeout: Optional[float] = None):
        """Answer the scripted command, failing the test on an unexpected one."""
        assert command in answers, f"unexpected command: {command}"
        return SimpleNamespace(stdout=f"{answers[command]}\n", returncode=0)

    return fake_run_operation


BASE_ANSWERS: dict[str, str] = {
    SYMBOLIC_REF: "refs/remotes/origin/master",
    HEAD_RESOLVE: HEAD_HASH,
    LOCAL_MAIN_RESOLVE: LOCAL_MAIN_HASH,
    REMOTE_MAIN_RESOLVE: REMOTE_MAIN_HASH,
    CURRENT_BRANCH: "feature",
    FETCH: "",
}


def test_snapshot_resolves_once_with_a_remote_and_offers_the_fetch() -> None:
    """The first instantiation resolves everything (fetching when accepted) and caches it: a second
    instantiation must not run git nor prompt again."""
    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="y"
    ) as prompt, patch(
        "mega_snake.util.repo.run_operation", side_effect=run_operation_answering(BASE_ANSWERS)
    ) as run_operation:
        Repo()

    assert Repo.REMOTE == "origin"
    assert Repo.MAIN_BRANCH == "master"
    assert Repo.HEAD == HEAD_HASH
    assert Repo.MAIN_LOCAL_HASH == LOCAL_MAIN_HASH
    assert Repo.MAIN_REMOTE_HASH == REMOTE_MAIN_HASH
    assert Repo.BRANCH_HEAD == "feature"
    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert FETCH in issued
    prompt.assert_called_once()

    with patch("mega_snake.util.repo.run_operation") as second_run, patch(
        "mega_snake.util.repo.get_validated_input"
    ) as second_prompt:
        Repo()
    second_run.assert_not_called()
    second_prompt.assert_not_called()


def test_declining_the_fetch_skips_it() -> None:
    """Answering 'n' to the fetch prompt must not issue any git fetch."""
    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch(
        "mega_snake.util.repo.run_operation", side_effect=run_operation_answering(BASE_ANSWERS)
    ) as run_operation:
        Repo()
    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert FETCH not in issued


def test_missing_symbolic_ref_falls_back_to_asking_the_remote() -> None:
    """A hand-added remote has no local HEAD symbolic reference; the main branch must then come
    from `git remote show`, and its remote hash from the reference built out of that answer."""
    answers = dict(BASE_ANSWERS)
    answers[SYMBOLIC_REF] = ""
    answers[REMOTE_SHOW] = "Fetch URL: x\n  HEAD branch: master\n  Remote branches:"
    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch(
        "mega_snake.util.repo.run_operation", side_effect=run_operation_answering(answers)
    ) as run_operation:
        Repo()
    assert Repo.MAIN_BRANCH == "master"
    assert Repo.MAIN_REMOTE_HASH == REMOTE_MAIN_HASH
    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert REMOTE_SHOW in issued


def test_unparseable_remote_show_raises_lookup_error() -> None:
    """A remote listing without a HEAD branch line cannot name the main branch: that is an
    environment problem (LookupError), not a silent default."""
    answers = dict(BASE_ANSWERS)
    answers[SYMBOLIC_REF] = ""
    answers[REMOTE_SHOW] = "Fetch URL: x"
    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch("mega_snake.util.repo.run_operation", side_effect=run_operation_answering(answers)):
        with pytest.raises(LookupError, match="origin"):
            Repo()
    assert Repo._INITIALIZED is False, "a failed resolution must not mark the snapshot as initialized"


def test_without_a_remote_the_user_names_the_main_branch() -> None:
    """With no remote, the main branch is asked to the user among the existing local branches and
    the remote-side hash stays None."""
    answers = {
        LOCAL_BRANCHES: "master\nfeature",
        HEAD_RESOLVE: HEAD_HASH,
        LOCAL_MAIN_RESOLVE: LOCAL_MAIN_HASH,
        CURRENT_BRANCH: "",
    }
    with patch("mega_snake.util.repo.get_remote", return_value=None), patch(
        "mega_snake.util.repo.get_validated_input"
    ) as fetch_prompt, patch(
        "mega_snake.util.repo.get_typed_validated_input", return_value="master"
    ) as branch_prompt, patch(
        "mega_snake.util.repo.run_operation", side_effect=run_operation_answering(answers)
    ):
        Repo()
    assert Repo.MAIN_BRANCH == "master"
    assert Repo.MAIN_LOCAL_HASH == LOCAL_MAIN_HASH
    assert Repo.MAIN_REMOTE_HASH is None
    assert Repo.BRANCH_HEAD is None, "a detached HEAD reports no current branch"
    fetch_prompt.assert_not_called()
    assert branch_prompt.call_args.kwargs["valid_values"] == ["master", "feature"]


def test_a_main_branch_with_no_commit_anywhere_raises_lookup_error() -> None:
    """A main branch resolving to no commit neither locally nor remotely leaves nothing to compare
    against, so the resolution fails instead of caching an unusable snapshot."""
    answers = dict(BASE_ANSWERS)
    answers[LOCAL_MAIN_RESOLVE] = ""
    answers[REMOTE_MAIN_RESOLVE] = ""
    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch("mega_snake.util.repo.run_operation", side_effect=run_operation_answering(answers)):
        with pytest.raises(LookupError, match="resolves to no commit"):
            Repo()


def test_get_main_hash_prefers_the_remote_hash() -> None:
    """The remote main hash wins so branches are judged against the main branch as the remote has
    it; the local hash is only the fallback, and having neither is a bug."""
    Repo.MAIN_REMOTE_HASH = REMOTE_MAIN_HASH
    Repo.MAIN_LOCAL_HASH = LOCAL_MAIN_HASH
    assert Repo.get_main_hash() == REMOTE_MAIN_HASH
    assert Repo.get_main_hash() != LOCAL_MAIN_HASH

    Repo.MAIN_REMOTE_HASH = None
    assert Repo.get_main_hash() == LOCAL_MAIN_HASH

    Repo.MAIN_LOCAL_HASH = ""
    with pytest.raises(InternalStateError, match="This is a bug"):
        Repo.get_main_hash()


def test_reset_clears_the_cached_snapshot() -> None:
    """reset() must return every class attribute to its pristine value so the next instantiation
    resolves the snapshot again."""
    Repo.REMOTE = "origin"
    Repo.HEAD = HEAD_HASH
    Repo.BRANCH_HEAD = "feature"
    Repo.MAIN_BRANCH = "master"
    Repo.MAIN_LOCAL_HASH = LOCAL_MAIN_HASH
    Repo.MAIN_REMOTE_HASH = REMOTE_MAIN_HASH
    Repo._INITIALIZED = True

    Repo.reset()

    assert Repo._INITIALIZED is False
    assert Repo.REMOTE is None
    assert Repo.HEAD == ""
    assert Repo.BRANCH_HEAD is None
    assert Repo.MAIN_BRANCH == ""
    assert Repo.MAIN_LOCAL_HASH == ""
    assert Repo.MAIN_REMOTE_HASH is None


def test_a_failing_git_command_propagates_and_leaves_the_snapshot_unresolved() -> None:
    """git itself can fail (not a repository, a broken object store). The failure must surface
    instead of caching a half-built snapshot that every later command would silently read."""
    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch("mega_snake.util.repo.run_operation", side_effect=subprocess.SubprocessError("git exploded")):
        with pytest.raises(subprocess.SubprocessError, match="git exploded"):
            Repo()

    assert Repo._INITIALIZED is False, "a failed resolution must not be cached as done"
    assert Repo.MAIN_BRANCH == "", "no half-resolved value may survive the failure"
    assert Repo.MAIN_REMOTE_HASH is None


def test_a_failing_fetch_stops_the_resolution_before_reading_any_reference() -> None:
    """The fetch is the first git call and can fail on its own (no network, rejected credentials).
    It must not be swallowed into a silently stale snapshot."""
    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="y"
    ), patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.side_effect = subprocess.SubprocessError("could not fetch")
        with pytest.raises(subprocess.SubprocessError, match="could not fetch"):
            Repo()

    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert issued == [FETCH], "nothing may be read once the fetch failed"
    assert Repo._INITIALIZED is False


def test_a_user_who_never_names_a_valid_main_branch_stops_the_resolution() -> None:
    """Without a remote the main branch comes from the user; exhausting the attempts must abort
    rather than fall back to a guessed branch the merge checks would then judge against."""
    with patch("mega_snake.util.repo.get_remote", return_value=None), patch(
        "mega_snake.util.repo.get_typed_validated_input", side_effect=KeyError("Too many invalid inputs")
    ), patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout="master\nfeature\n")
        with pytest.raises(KeyError, match="Too many invalid inputs"):
            Repo()

    assert Repo._INITIALIZED is False
    assert Repo.MAIN_BRANCH == "", "no branch may be assumed when the user never named one"


def test_a_git_failure_partway_through_leaves_the_snapshot_unusable_not_half_built() -> None:
    """The resolution issues several git calls; one failing *after* the main branch was named is
    the dangerous case, because the class attributes are already partly written. The snapshot must
    not be marked initialized, or every later command would silently reuse those partial values
    instead of resolving again."""

    def fail_on_reference_resolution(
        command: str, description: str, check: bool = True, timeout: Optional[float] = None
    ):
        """Answer the main-branch lookup, then fail while resolving the hashes."""
        if command == SYMBOLIC_REF:
            return SimpleNamespace(stdout="refs/remotes/origin/master\n")
        raise subprocess.SubprocessError("rev-parse exploded")

    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch("mega_snake.util.repo.run_operation", side_effect=fail_on_reference_resolution):
        with pytest.raises(subprocess.SubprocessError, match="rev-parse exploded"):
            Repo()

    assert Repo._INITIALIZED is False, "a partially written snapshot must never be cached as done"

    # The proof it is not cached: the next instantiation resolves everything again and succeeds.
    with patch("mega_snake.util.repo.get_remote", return_value="origin"), patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch("mega_snake.util.repo.run_operation", side_effect=run_operation_answering(BASE_ANSWERS)):
        Repo()
    assert Repo.MAIN_LOCAL_HASH == LOCAL_MAIN_HASH
    assert Repo.MAIN_REMOTE_HASH == REMOTE_MAIN_HASH
