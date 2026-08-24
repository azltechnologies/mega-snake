"""Tests for the Repo snapshot (mega_snake.util.repo)."""

import subprocess
from types import SimpleNamespace
from typing import Iterator, Optional
from unittest.mock import patch

import pytest

import click

from mega_snake.util.formatting import InternalStateError, resolve_error_code
from mega_snake.util.repo import NO_REMOTE_MESSAGE, Repo

GIT_REMOTE = "git remote"
SYMBOLIC_REF = "git symbolic-ref --quiet refs/remotes/origin/HEAD"
REMOTE_SHOW = "git remote show origin"
HEAD_RESOLVE_LIVE = "git rev-parse --verify --quiet HEAD"
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
    GIT_REMOTE: "origin",
    SYMBOLIC_REF: "refs/remotes/origin/master",
    HEAD_RESOLVE_LIVE: HEAD_HASH,
    LOCAL_MAIN_RESOLVE: LOCAL_MAIN_HASH,
    REMOTE_MAIN_RESOLVE: REMOTE_MAIN_HASH,
    CURRENT_BRANCH: "feature",
    FETCH: "",
}


def test_snapshot_resolves_once_with_a_remote_and_offers_the_fetch() -> None:
    """The first instantiation resolves everything (fetching when accepted) and caches it: a second
    instantiation must not run git nor prompt again."""
    with patch(
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
    with patch(
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
    with patch(
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
    with patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch("mega_snake.util.repo.run_operation", side_effect=run_operation_answering(answers)):
        with pytest.raises(LookupError, match="origin"):
            Repo()
    assert Repo._INITIALIZED is False, "a failed resolution must not mark the snapshot as initialized"


def test_without_a_remote_the_user_names_the_main_branch() -> None:
    """With no remote, the main branch is asked to the user among the existing local branches and
    the remote-side hash stays None."""
    answers = {
        GIT_REMOTE: "",
        LOCAL_BRANCHES: "master\nfeature",
        HEAD_RESOLVE_LIVE: HEAD_HASH,
        LOCAL_MAIN_RESOLVE: LOCAL_MAIN_HASH,
        CURRENT_BRANCH: "",
    }
    with patch(
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
    with patch(
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
    with patch(
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
    with patch(
        "mega_snake.util.repo.get_validated_input", return_value="y"
    ), patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.side_effect = [SimpleNamespace(stdout="origin\n"), subprocess.SubprocessError("could not fetch")]
        with pytest.raises(subprocess.SubprocessError, match="could not fetch"):
            Repo()

    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert issued == [GIT_REMOTE, FETCH], "nothing may be read once the fetch failed"
    assert Repo._INITIALIZED is False


def test_a_user_who_never_names_a_valid_main_branch_stops_the_resolution() -> None:
    """Without a remote the main branch comes from the user; exhausting the attempts must abort
    rather than fall back to a guessed branch the merge checks would then judge against."""
    with patch(
        "mega_snake.util.repo.get_typed_validated_input", side_effect=KeyError("Too many invalid inputs")
    ), patch(
        "mega_snake.util.repo.run_operation",
        side_effect=run_operation_answering({GIT_REMOTE: "", LOCAL_BRANCHES: "master\nfeature"}),
    ):
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
        if command == GIT_REMOTE:
            return SimpleNamespace(stdout="origin\n")
        if command == SYMBOLIC_REF:
            return SimpleNamespace(stdout="refs/remotes/origin/master\n")
        raise subprocess.SubprocessError("rev-parse exploded")

    with patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch("mega_snake.util.repo.run_operation", side_effect=fail_on_reference_resolution):
        with pytest.raises(subprocess.SubprocessError, match="rev-parse exploded"):
            Repo()

    assert Repo._INITIALIZED is False, "a partially written snapshot must never be cached as done"

    # The proof it is not cached: the next instantiation resolves everything again and succeeds.
    with patch(
        "mega_snake.util.repo.get_validated_input", return_value="n"
    ), patch("mega_snake.util.repo.run_operation", side_effect=run_operation_answering(BASE_ANSWERS)):
        Repo()
    assert Repo.MAIN_LOCAL_HASH == LOCAL_MAIN_HASH
    assert Repo.MAIN_REMOTE_HASH == REMOTE_MAIN_HASH


# --------------------------------------------------------------------------------------
# resolve_remote / require_remote / get_remote_url / current_commit
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "listing,expected,prompted",
    [
        ("", None, False),
        ("origin", "origin", False),
        ("origin\nfork", "fork", True),
    ],
    ids=["no-remotes", "single-remote", "several-remotes"],
)
def test_resolve_remote_answers_from_git_and_only_prompts_when_ambiguous(
    listing: str, expected: Optional[str], prompted: bool
) -> None:
    """One remote (or none) is unambiguous and must never interrupt the user; only several remotes
    justify a prompt, and the picked one is the answer."""
    with patch("mega_snake.util.repo.run_operation") as run_operation, patch(
        "mega_snake.util.repo.get_validated_input", return_value="1"
    ) as prompt:
        run_operation.return_value = SimpleNamespace(stdout=f"{listing}\n")
        assert Repo.resolve_remote() == expected

    run_operation.assert_called_once_with("git remote", "Getting remotes")
    assert prompt.called is prompted


def test_resolve_remote_is_answered_once_per_process() -> None:
    """This is the memoization the old module-level cache used to provide: repeated callers reuse
    the answer, so a repository with several remotes prompts exactly once."""
    with patch("mega_snake.util.repo.run_operation") as run_operation, patch(
        "mega_snake.util.repo.get_validated_input", return_value="1"
    ) as prompt:
        run_operation.return_value = SimpleNamespace(stdout="origin\nfork\n")
        assert [Repo.resolve_remote(), Repo.resolve_remote(), Repo.resolve_remote()] == ["fork"] * 3

    run_operation.assert_called_once_with("git remote", "Getting remotes")
    prompt.assert_called_once()


def test_resolve_remote_memoizes_the_absence_of_a_remote_too() -> None:
    """"There is no remote" is an answer, not a missing one: caching only the positive case would
    re-run `git remote` on every call in exactly the repositories that can least afford it."""
    with patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout="\n")
        assert Repo.resolve_remote() is None
        assert Repo.resolve_remote() is None
    run_operation.assert_called_once_with("git remote", "Getting remotes")


def test_resolve_remote_treats_a_failing_git_remote_as_no_remote() -> None:
    """Outside a repository `git remote` fails outright. That is reported with the shared friendly
    message and handled like a repository without remotes, and the failure is memoized so the
    retries are not paid again on the next call."""
    with patch(
        "mega_snake.util.repo.run_operation", side_effect=subprocess.SubprocessError("git remote failed")
    ) as run_operation, patch("mega_snake.util.repo.ws_warning") as ws_warning:
        assert Repo.resolve_remote() is None
        ws_warning.assert_called_once()
        assert NO_REMOTE_MESSAGE in ws_warning.call_args.args[0]

        run_operation.reset_mock()
        assert Repo.resolve_remote() is None
        run_operation.assert_not_called()


def test_resolve_remote_never_fetches_nor_resolves_the_main_branch() -> None:
    """The cheap level must stay cheap: light-weight commands rely on it, and pulling the full
    snapshot in would hand them the fetch prompt they deliberately avoid."""
    with patch("mega_snake.util.repo.run_operation") as run_operation, patch(
        "mega_snake.util.repo.get_validated_input"
    ) as prompt, patch("mega_snake.util.repo.get_typed_validated_input") as branch_prompt:
        run_operation.return_value = SimpleNamespace(stdout="origin\n")
        Repo.resolve_remote()

    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert issued == ["git remote"], "no reference resolution belongs in the cheap path"
    assert not any("fetch" in command for command in issued)
    prompt.assert_not_called()
    branch_prompt.assert_not_called()
    assert Repo._INITIALIZED is False, "answering the remote question is not a full snapshot"
    assert Repo.MAIN_BRANCH == ""


def test_require_remote_returns_the_remote_or_fails_as_an_environment_error() -> None:
    """A repository without a remote is not a misuse of the CLI, so it must not carry the
    invocation-error status: the negative assertion is what pins that distinction, since a
    ClickException would also satisfy a bare `pytest.raises(Exception)`."""
    with patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout="origin\n")
        assert Repo.require_remote() == "origin"

    Repo.reset()
    with patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout="\n")
        with pytest.raises(EnvironmentError, match="No remote repository found") as excinfo:
            Repo.require_remote()

    assert not isinstance(
        excinfo.value, click.ClickException
    ), "a missing remote must not be reported as an invocation error"
    assert resolve_error_code(excinfo.value) == 112, (
        f"a missing remote resolved to {resolve_error_code(excinfo.value)}, expected 112"
    )


def test_get_remote_url_strips_the_git_suffix_and_reports_no_remote_as_none() -> None:
    """The URL feeds links built by other commands, so the `.git` suffix is trimmed; without a
    remote there is no URL to give and git must not be asked for one."""
    with patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="origin\n"),
            SimpleNamespace(stdout="https://github.com/azltechnologies/unix-scripts.git\n"),
        ]
        assert Repo.get_remote_url() == "https://github.com/azltechnologies/unix-scripts"

    Repo.reset()
    with patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout="\n")
        assert Repo.get_remote_url() is None
    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert not any("get-url" in command for command in issued)


def test_resolve_head_reads_head_without_resolving_the_snapshot() -> None:
    """Light-weight commands (`create-release`, `diff-tree` with an explicit origin) need HEAD but
    must never be made to pay the snapshot's fetch prompt, so this stays a cheap standalone read."""
    with patch("mega_snake.util.repo.run_operation") as run_operation, patch(
        "mega_snake.util.repo.get_validated_input"
    ) as prompt:
        run_operation.return_value = SimpleNamespace(stdout=f"{HEAD_HASH}\n")
        assert Repo.resolve_head() == HEAD_HASH

    run_operation.assert_called_once_with(
        HEAD_RESOLVE_LIVE, "Resolving reference 'HEAD'", check=False, timeout=3
    )
    prompt.assert_not_called()
    assert Repo._INITIALIZED is False, "reading HEAD is not a full snapshot"
    assert Repo._REMOTE_RESOLVED is False, "reading HEAD must not drag the remote question in"
    assert Repo.MAIN_BRANCH == ""


def test_resolve_head_is_answered_once_and_caches_onto_the_head_attribute() -> None:
    """HEAD is memoized like the remote, and the attribute *is* the cache — which is what removes
    the need for a second "current commit" helper alongside it."""
    with patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout=f"{HEAD_HASH}\n")
        assert [Repo.resolve_head(), Repo.resolve_head()] == [HEAD_HASH, HEAD_HASH]

    run_operation.assert_called_once_with(
        HEAD_RESOLVE_LIVE, "Resolving reference 'HEAD'", check=False, timeout=3
    )
    assert Repo.HEAD == HEAD_HASH, "the attribute and the accessor must never diverge"


def test_the_full_snapshot_reuses_an_already_read_head() -> None:
    """The snapshot must not read HEAD a second time: a command that already resolved it cheaply
    and then needs the full snapshot pays one `git rev-parse HEAD`, not two."""
    with patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout=f"{HEAD_HASH}\n")
        assert Repo.resolve_head() == HEAD_HASH

    with patch("mega_snake.util.repo.run_operation", side_effect=run_operation_answering(BASE_ANSWERS)) as run_operation, (
        patch("mega_snake.util.repo.get_validated_input", return_value="n")
    ):
        Repo()

    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert HEAD_RESOLVE_LIVE not in issued, "HEAD must not be read twice"
    assert Repo.HEAD == HEAD_HASH


def test_the_full_snapshot_reuses_the_already_answered_remote() -> None:
    """The two levels share one answer: a command that resolved the remote cheaply and then needs
    the full snapshot must not be asked `git remote` (or prompted) a second time."""
    with patch("mega_snake.util.repo.run_operation") as run_operation, patch(
        "mega_snake.util.repo.get_validated_input", return_value="1"
    ) as prompt:
        run_operation.return_value = SimpleNamespace(stdout="origin\nfork\n")
        assert Repo.resolve_remote() == "fork"
        prompt.assert_called_once()

    answers = {
        SYMBOLIC_REF.replace("origin", "fork"): "refs/remotes/fork/master",
        HEAD_RESOLVE_LIVE: HEAD_HASH,
        LOCAL_MAIN_RESOLVE: LOCAL_MAIN_HASH,
        REMOTE_MAIN_RESOLVE.replace("origin", "fork"): REMOTE_MAIN_HASH,
        CURRENT_BRANCH: "feature",
    }
    with patch("mega_snake.util.repo.run_operation", side_effect=run_operation_answering(answers)) as run_operation, (
        patch("mega_snake.util.repo.get_validated_input", return_value="n")
    ) as fetch_prompt:
        Repo()

    issued = [issued_call.args[0] for issued_call in run_operation.call_args_list]
    assert "git remote" not in issued, "the remote question must not be asked twice"
    assert Repo.REMOTE == "fork"
    # the only prompt the full snapshot adds on top of the remote question
    fetch_prompt.assert_called_once()


def test_resolve_head_reports_a_repository_with_no_commits_as_a_lookup_failure() -> None:
    """A repository with no commits resolves HEAD to nothing. That must surface as a clear failure
    rather than an empty string, since the callers build a diff range or a release target out of
    this value and would otherwise issue a malformed command against it.

    It must also not be paid as an operational failure: reading a missing reference is an ordinary
    answer, so the probe runs with check=False and is never retried.
    """
    with patch("mega_snake.util.repo.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(stdout="\n")
        with pytest.raises(LookupError, match="no commits yet"):
            Repo.resolve_head()

    run_operation.assert_called_once()
    assert run_operation.call_args.kwargs["check"] is False, (
        "a missing HEAD must not be retried three times and reported as a subprocess failure"
    )
    assert Repo._HEAD_RESOLVED is False, "a failed read must not be memoized as an answer"
    assert Repo.HEAD == "", "no partial value may be cached"
