"""Additional tests for light_weight helpers."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import click
import re
import subprocess

import pytest

from mega_snake.light_weight.create_release import _get_notes, create_release
from mega_snake.light_weight.echo import echo
from mega_snake.light_weight.jks_expired_certs import expired_certs
from mega_snake.light_weight import release as release_module
from mega_snake.light_weight.release import Release, _create_release_list, get_latest_release


def test_create_release_flows() -> None:
    """Cover create_release success/cancel and helper notes."""
    assert _get_notes(None) == ""
    assert _get_notes("  release notes  ") == '--notes "release notes"'

    latest = SimpleNamespace(tag_name="v1.0.0", get_release_tag=lambda part, suffix=None: "v1.0.1")
    with patch("mega_snake.light_weight.create_release.handler.git_fetch"), patch(
        "mega_snake.light_weight.create_release.get_latest_release", return_value=latest
    ), patch("mega_snake.light_weight.create_release.handler.publish_release"), patch(
        "mega_snake.light_weight.create_release.get_current_commit", return_value="abc"
    ), patch(
        "mega_snake.light_weight.create_release.get_validated_input", return_value="n"
    ):
        create_release.callback(release_type="l", notes=None, branch=None, version_part="patch", tag_suffix=None)

    with patch("mega_snake.light_weight.create_release.handler.git_fetch"), patch(
        "mega_snake.light_weight.create_release.get_latest_release", side_effect=[latest, latest]
    ), patch("mega_snake.light_weight.create_release.handler.publish_release"), patch(
        "mega_snake.light_weight.create_release.handler.set_release_to_latest"
    ) as set_latest:
        create_release.callback(
            release_type="r", notes="notes ok", branch="branch", version_part="patch", tag_suffix=None
        )
        set_latest.assert_not_called()

    newer = SimpleNamespace(tag_name="v2.0.0", get_release_tag=lambda part, suffix=None: "v2.0.1")
    with patch("mega_snake.light_weight.create_release.handler.git_fetch"), patch(
        "mega_snake.light_weight.create_release.get_latest_release", side_effect=[latest, newer]
    ), patch("mega_snake.light_weight.create_release.handler.publish_release"), patch(
        "mega_snake.light_weight.create_release.handler.set_release_to_latest"
    ) as set_latest:
        create_release.callback(
            release_type="r", notes="notes ok", branch="branch", version_part="patch", tag_suffix=None
        )
        set_latest.assert_called_once_with(latest.tag_name)

    with pytest.raises(ValueError, match="Invalid release type: x"):
        create_release.callback(
            release_type="x", notes=None, branch="branch", version_part="patch", tag_suffix=None
        )


def test_release_model_and_lookup() -> None:
    """Cover Release model parsing and lookup logic."""
    with patch("mega_snake.light_weight.release.handler.get_commit_from_release", return_value="abc"):
        rel = Release("Title\tLatest\tv1.0.0\t2025-01-01T00:00:00Z")
        assert rel and rel.commit == "abc"

    with pytest.raises(ValueError):
        Release(None)
    with patch("mega_snake.light_weight.release.handler.get_commit_from_release", return_value="abc"):
        releases = _create_release_list("A\tLatest\tv1.0.0\t2025-01-01T00:00:00Z\nB\tDraft\tv0.9.0\t2024-01-01T00:00:00Z")
        assert len(releases) == 2

    with patch("mega_snake.light_weight.release._tag_exists", return_value=False):
        assert rel.get_release_tag("patch") == "v1.0.1"

    with patch("mega_snake.light_weight.release.handler.get_release_list") as get_release_list, patch(
        "mega_snake.light_weight.release.handler.get_commit_from_release", return_value="abc"
    ):
        get_release_list.side_effect = [
            SimpleNamespace(stdout="A\tDraft\tv1.0.0\t2025-01-01T00:00:00Z"),
            SimpleNamespace(stdout="A\tLatest\tv1.0.1\t2025-01-02T00:00:00Z"),
        ]
        latest = get_latest_release()
        assert latest.tag_name == "v1.0.1"


def test_echo_and_expired_certs() -> None:
    """Cover echo command branches and expired certs command."""
    with patch("mega_snake.light_weight.echo.MSG_OPT", {"I": MagicMock(), "A": MagicMock(), "T": MagicMock()}):
        echo.callback("msg", "pro", "epi", "I")
        echo.callback("msg", None, None, "A")
        echo.callback("msg", "pro", "epi", "T")
    with patch("mega_snake.light_weight.echo.MSG_OPT", {"I": MagicMock()}):
        with pytest.raises(ValueError):
            echo.callback("msg", None, None, "X")

    with patch("mega_snake.light_weight.jks_expired_certs.shutil.which", return_value=None):
        with pytest.raises(RuntimeError):
            expired_certs.callback("/tmp/a.jks", "p", False)

    valid_cert = "Alias name: a\nValid from: Mon Jan 01 00:00:00 UTC 2024 until: Mon Jan 01 00:00:00 UTC 2099"
    with patch("mega_snake.light_weight.jks_expired_certs.shutil.which", return_value="/bin/keytool"), patch(
        "mega_snake.light_weight.jks_expired_certs.get_command_return_code", return_value=0
    ), patch("mega_snake.light_weight.jks_expired_certs.run_operation") as run_operation:
        run_operation.side_effect = [SimpleNamespace(stdout="Alias name: a"), SimpleNamespace(stdout=valid_cert)]
        expired_certs.callback("/tmp/a.jks", "p", False)

    with patch("mega_snake.light_weight.jks_expired_certs.shutil.which", return_value="/bin/keytool"), patch(
        "mega_snake.light_weight.jks_expired_certs.get_command_return_code", return_value=1
    ):
        with pytest.raises(RuntimeError):
            expired_certs.callback("/tmp/a.jks", "p", False)

    expired_cert = "Alias name: a\nValid from: Mon Jan 01 00:00:00 UTC 2020 until: Mon Jan 01 00:00:00 UTC 2021"
    with patch("mega_snake.light_weight.jks_expired_certs.shutil.which", return_value="/bin/keytool"), patch(
        "mega_snake.light_weight.jks_expired_certs.get_command_return_code", return_value=0
    ), patch("mega_snake.light_weight.jks_expired_certs.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="Alias name: a"),
            SimpleNamespace(stdout=expired_cert),
            SimpleNamespace(stdout="details"),
        ]
        expired_certs.callback("/tmp/a.jks", "p", True)


@pytest.mark.parametrize(
    "current_tag, version_part, expected",
    [
        pytest.param("v1.2.3", "patch", "v1.2.4", id="patch-increments-the-last-number"),
        pytest.param("v1.2.3", "minor", "v1.3.0", id="minor-resets-the-patch"),
        pytest.param("v1.2.3", "major", "v2.0.0", id="major-resets-minor-and-patch"),
        pytest.param("v0.1.5", "patch", "v0.1.6", id="patch-on-a-zero-major"),
        pytest.param("v1.9.9", "minor", "v1.10.0", id="minor-past-nine-is-not-a-carry"),
        pytest.param("v9.9.9", "major", "v10.0.0", id="major-past-nine-is-not-a-carry"),
    ],
)
def test_get_release_tag_bumps_the_requested_component(current_tag: str, version_part: str, expected: str) -> None:
    """Bumping a component must increment exactly it, and reset every component to its right.

    Resetting is what keeps the sequence monotonic: without it a minor bump on v1.2.3 would yield
    v1.3.3, which is greater than the release that follows it in the next patch cycle.

    Parameters:
        current_tag: The latest release's tag.
        version_part: The component being incremented.
        expected: The tag the new release must carry.

    Raises:
        None

    Returns:
        None
    """
    release = SimpleNamespace(tag_name=current_tag)
    with patch("mega_snake.light_weight.release._tag_exists", return_value=False):
        result = Release.get_release_tag(release, version_part)  # type: ignore[arg-type]

    assert result == expected
    # The components to the left of the bumped one must be untouched, and none may be dropped.
    assert len(result.lstrip("v").split(".")) == 3


def test_get_release_tag_produces_a_tag_the_release_workflow_accepts() -> None:
    """The generated tag must match the 'vX.Y.Z' shape, with no suffix of any kind.

    A tag carrying a suffix cannot be compared against a project's declared version, which is what
    every publish pipeline keying off the tag relies on.
    """
    release = SimpleNamespace(tag_name="v0.1.5")
    with patch("mega_snake.light_weight.release._tag_exists", return_value=False):
        result = Release.get_release_tag(release, "patch")  # type: ignore[arg-type]

    assert re.fullmatch(r"v\d+\.\d+\.\d+", result), f"{result} is not a plain version tag"
    assert "-" not in result, f"{result} still carries a suffix"


@pytest.mark.parametrize(
    "bad_tag",
    [
        pytest.param("v0.1.5-beta.0", id="suffixed-tag"),
        pytest.param("0.1.5", id="missing-v-prefix"),
        pytest.param("v1.2", id="two-components"),
        pytest.param("v1.2.3.4", id="four-components"),
        pytest.param("latest", id="not-a-version"),
    ],
)
def test_get_release_tag_rejects_a_latest_release_without_a_version_tag(bad_tag: str) -> None:
    """A tag the next version cannot be derived from must fail loudly, never be guessed at.

    Parameters:
        bad_tag: The unusable tag carried by the latest release.

    Raises:
        None

    Returns:
        None
    """
    release = SimpleNamespace(tag_name=bad_tag)
    with patch("mega_snake.light_weight.release._tag_exists", return_value=False):
        with pytest.raises(ValueError, match="is not a 'vX.Y.Z' version"):
            Release.get_release_tag(release, "patch")  # type: ignore[arg-type]


def test_get_release_tag_rejects_an_unknown_version_part() -> None:
    """Only the three semantic version components are accepted."""
    release = SimpleNamespace(tag_name="v1.2.3")
    with pytest.raises(ValueError, match="Invalid version part: build"):
        Release.get_release_tag(release, "build")  # type: ignore[arg-type]


def test_get_release_tag_refuses_to_reuse_a_tag_the_fallback_could_not_avoid() -> None:
    """When even the highest known version is taken, publishing must stop rather than reuse a tag.

    Reaching this means the local view of the repository is stale: the derived tag exists but is not
    accounted for by any known version, so publishing would attach the release to the wrong commit.
    """
    release = SimpleNamespace(tag_name="v1.2.3")
    listed = SimpleNamespace(stdout="v1.2.3\n", returncode=0)
    with patch("mega_snake.light_weight.release._tag_exists", return_value=True), patch(
        "mega_snake.light_weight.release.run_operation", return_value=listed
    ):
        with pytest.raises(subprocess.SubprocessError, match="derived from the highest"):
            Release.get_release_tag(release, "patch")  # type: ignore[arg-type]


def test_tag_exists_reports_the_git_lookup_result() -> None:
    """The existence check must key off git's exit status, not off its output."""
    with patch("mega_snake.light_weight.release.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(returncode=0, stdout="")
        assert release_module._tag_exists("v1.2.4") is True
        run_operation.return_value = SimpleNamespace(returncode=1, stdout="")
        assert release_module._tag_exists("v1.2.4") is False
    # `--verify --quiet` is what makes a missing tag a clean non-zero instead of noise on stderr.
    assert "--verify --quiet" in run_operation.call_args.args[0]
    assert run_operation.call_args.kwargs["check"] is False


def test_create_release_defaults_to_a_patch_bump() -> None:
    """The default must be the least surprising bump, and it must reach the tag derivation."""
    version_part_option = next(
        parameter for parameter in create_release.params if parameter.name == "version_part"
    )
    assert version_part_option.default == "patch"
    assert set(version_part_option.type.choices) == {"patch", "minor", "major"}
    # The suffix is an option now, never a required positional: the version itself is derived.
    suffix_option = next(parameter for parameter in create_release.params if parameter.name == "tag_suffix")
    assert suffix_option.default is None
    assert not suffix_option.required


def test_get_release_tag_appends_the_suffix_to_the_bumped_version() -> None:
    """A suffix marks a pre-release build *of the bumped version*, not of the current one.

    Deriving the suffix from the un-bumped version would produce a tag that sorts below the release
    it is meant to precede.
    """
    release = SimpleNamespace(tag_name="v1.2.3")
    with patch("mega_snake.light_weight.release._tag_exists", return_value=False):
        assert Release.get_release_tag(release, "patch", "beta") == "v1.2.4-beta.0"  # type: ignore[arg-type]
        assert Release.get_release_tag(release, "minor", "rc") == "v1.3.0-rc.0"  # type: ignore[arg-type]


def test_get_release_tag_walks_the_counter_past_the_taken_suffixes() -> None:
    """Several pre-release builds of one version must coexist, so the counter finds the first free one."""
    release = SimpleNamespace(tag_name="v1.2.3")
    taken = {"v1.2.4-beta.0", "v1.2.4-beta.1"}
    with patch("mega_snake.light_weight.release._tag_exists", side_effect=lambda tag: tag in taken):
        assert Release.get_release_tag(release, "patch", "beta") == "v1.2.4-beta.2"  # type: ignore[arg-type]


def test_get_release_tag_gives_up_when_every_suffix_slot_is_taken() -> None:
    """An exhausted counter must fail loudly rather than loop forever or reuse a tag."""
    release = SimpleNamespace(tag_name="v1.2.3")
    with patch("mega_snake.light_weight.release._tag_exists", return_value=True):
        with pytest.raises(subprocess.SubprocessError, match="Could not find a free tag for v1.2.4-beta"):
            Release.get_release_tag(release, "patch", "beta")  # type: ignore[arg-type]


def test_get_release_tag_without_a_suffix_never_produces_one() -> None:
    """The plain path must stay plain: a publish pipeline keys off the bare vX.Y.Z shape."""
    release = SimpleNamespace(tag_name="v1.2.3")
    with patch("mega_snake.light_weight.release._tag_exists", return_value=False):
        for empty in (None, ""):
            result = Release.get_release_tag(release, "patch", empty)  # type: ignore[arg-type]
            assert result == "v1.2.4"
            assert "-" not in result


@pytest.mark.parametrize("release_type", ["p", "r"])
def test_create_release_allows_a_suffix_for_non_latest_types(release_type: str) -> None:
    """Pre-releases and non-latest releases are exactly the ones a suffix is meant for.

    Parameters:
        release_type: The release type accepting the suffix.

    Raises:
        None

    Returns:
        None
    """
    latest = SimpleNamespace(tag_name="v1.0.0", get_release_tag=lambda part, suffix=None: f"v1.0.1-{suffix}.0")
    with patch("mega_snake.light_weight.create_release.handler.git_fetch"), patch(
        "mega_snake.light_weight.create_release.get_latest_release", return_value=latest
    ), patch("mega_snake.light_weight.create_release.handler.publish_release") as publish, patch(
        "mega_snake.light_weight.create_release.handler.set_release_to_latest"
    ):
        create_release.callback(
            release_type=release_type, notes=None, branch="b", version_part="patch", tag_suffix="beta"
        )
    assert publish.call_args.args[0] == "v1.0.1-beta.0"


def test_create_release_rejects_a_suffix_on_a_latest_release() -> None:
    """A latest release must carry a plain version, so the combination is refused up front.

    GitHub only grants the latest pointer to a non-prerelease, so publishing a suffixed tag as latest
    would silently produce something other than what was asked for.
    """
    with patch("mega_snake.light_weight.create_release.handler.git_fetch") as git_fetch, patch(
        "mega_snake.light_weight.create_release.get_latest_release"
    ) as get_latest, patch("mega_snake.light_weight.create_release.handler.publish_release") as publish:
        with pytest.raises(
            click.ClickException,
            match="BAD REQUEST: --tag-suffix and the 'l' release type are mutually exclusive",
        ):
            create_release.callback(
                release_type="l", notes=None, branch="b", version_part="patch", tag_suffix="beta"
            )
    # Refused before any side effect: nothing is fetched, resolved or published.
    git_fetch.assert_not_called()
    get_latest.assert_not_called()
    publish.assert_not_called()


def test_create_release_still_allows_a_latest_release_without_a_suffix() -> None:
    """The exclusion must only bite when a suffix is actually given."""
    latest = SimpleNamespace(tag_name="v1.0.0", get_release_tag=lambda part, suffix=None: "v1.0.1")
    with patch("mega_snake.light_weight.create_release.handler.git_fetch"), patch(
        "mega_snake.light_weight.create_release.get_latest_release", return_value=latest
    ), patch("mega_snake.light_weight.create_release.handler.publish_release") as publish, patch(
        "mega_snake.light_weight.create_release.get_validated_input", return_value="y"
    ):
        create_release.callback(
            release_type="l", notes=None, branch="b", version_part="patch", tag_suffix=None
        )
    assert publish.call_args.args[0] == "v1.0.1"


@pytest.mark.parametrize(
    "hand_written_tag",
    [
        pytest.param("v1.2.3-beta", id="a-normal-release-named-like-a-prerelease"),
        pytest.param("v1.2.3-beta.0", id="suffixed-with-a-counter"),
        pytest.param("release-2026-01", id="a-date-based-scheme"),
        pytest.param("v1.2.3+build7", id="build-metadata"),
    ],
)
def test_get_release_tag_refuses_a_hand_written_latest_tag(hand_written_tag: str) -> None:
    """Nothing stops a user from marking a hand-tagged release as latest, so this must fail cleanly.

    GitHub withholds the latest pointer from *prereleases*, but a normal release can carry any tag
    the user typed in the UI. When that tag has no version to increment, the command says so and
    points elsewhere instead of inventing a number.

    Parameters:
        hand_written_tag: The tag carried by the hand-made latest release.

    Raises:
        None

    Returns:
        None
    """
    release = SimpleNamespace(tag_name=hand_written_tag)
    with pytest.raises(ValueError, match="BAD CONFIG") as excinfo:
        Release.get_release_tag(release, "patch")  # type: ignore[arg-type]

    message = str(excinfo.value)
    # The message must name the offending tag and tell the user where to go instead.
    assert hand_written_tag in message
    assert "gh release create" in message


def test_get_release_tag_falls_back_to_the_highest_version_on_collision() -> None:
    """A non-latest release must not make the next one impossible.

    Neither a prerelease nor a `--latest=false` release moves the `latest` pointer, so deriving from
    it twice lands on a tag that already exists. Without the fallback the command becomes single-use:
    the second invocation of any type fails and the user cannot cut a release at all.
    """
    release = SimpleNamespace(tag_name="v1.2.3")
    taken = {"v1.2.3", "v1.2.4"}
    tags = SimpleNamespace(stdout="\n".join(sorted(taken)), returncode=0)
    with patch("mega_snake.light_weight.release._tag_exists", side_effect=lambda tag: tag in taken), patch(
        "mega_snake.light_weight.release.run_operation", return_value=tags
    ):
        assert Release.get_release_tag(release, "patch") == "v1.2.5"  # type: ignore[arg-type]


def test_get_release_tag_never_derives_below_an_existing_tag() -> None:
    """The fallback takes the highest version, not the first free one.

    Walking upwards from the latest pointer would stop at v1.2.5 while v1.3.1 already exists, so the
    new release would sort below one that was already published.
    """
    release = SimpleNamespace(tag_name="v1.2.3")
    taken = {"v1.2.3", "v1.2.4", "v1.3.0", "v1.3.1"}
    tags = SimpleNamespace(stdout="\n".join(sorted(taken)), returncode=0)
    with patch("mega_snake.light_weight.release._tag_exists", side_effect=lambda tag: tag in taken), patch(
        "mega_snake.light_weight.release.run_operation", return_value=tags
    ):
        result = Release.get_release_tag(release, "patch")  # type: ignore[arg-type]

    assert result == "v1.3.2"
    assert result != "v1.2.5", "walked upwards instead of taking the highest version"


def test_highest_version_ignores_tags_that_are_not_versions() -> None:
    """Only 'vX.Y.Z' tags participate; anything else in the repository is noise here.

    The non-version tags are placed *after* the highest one on purpose: a parser that accepted them
    would either crash or contribute a bogus version, and both would be invisible if the noise sat
    below the answer.
    """
    listed = SimpleNamespace(stdout="v1.0.0\nv2.5.1\nrelease-2026\nv9.9.9-beta.0\nnightly\nv3\n", returncode=0)
    with patch("mega_snake.light_weight.release.run_operation", return_value=listed):
        assert release_module._highest_version(fallback=[0, 0, 0]) == [2, 5, 1]


def test_highest_version_falls_back_when_no_version_tag_exists() -> None:
    """A repository with no version tags must keep the version derived from the latest release."""
    listed = SimpleNamespace(stdout="nightly\nrelease-2026\n", returncode=0)
    with patch("mega_snake.light_weight.release.run_operation", return_value=listed):
        assert release_module._highest_version(fallback=[1, 2, 3]) == [1, 2, 3]


def test_highest_version_never_returns_below_the_fallback() -> None:
    """When every tag is older than the latest release, the latest release still wins."""
    listed = SimpleNamespace(stdout="v0.1.0\nv0.2.0\n", returncode=0)
    with patch("mega_snake.light_weight.release.run_operation", return_value=listed):
        assert release_module._highest_version(fallback=[1, 2, 3]) == [1, 2, 3]
