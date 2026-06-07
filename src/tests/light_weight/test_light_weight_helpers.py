"""Additional tests for light_weight helpers."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import subprocess

import pytest

from mega_snake.light_weight.create_release import _get_notes, create_release
from mega_snake.light_weight.echo import echo
from mega_snake.light_weight.jks_expired_certs import expired_certs
from mega_snake.light_weight.release import Release, _create_release_list, get_latest_release


def test_create_release_flows() -> None:
    """Cover create_release success/cancel and helper notes."""
    assert _get_notes(None) == ""
    assert _get_notes("  release notes  ") == '--notes "release notes"'

    latest = SimpleNamespace(tag_name="v1.0.0", get_release_tag=lambda suffix: f"v1.0.0-{suffix}.0")
    with patch("mega_snake.light_weight.create_release.handler.git_fetch"), patch(
        "mega_snake.light_weight.create_release.get_latest_release", return_value=latest
    ), patch("mega_snake.light_weight.create_release.handler.publish_release"), patch(
        "mega_snake.light_weight.create_release.get_current_commit", return_value="abc"
    ), patch(
        "mega_snake.light_weight.create_release.get_validated_input", return_value="n"
    ):
        create_release.callback("foo", "l", None, None)

    with patch("mega_snake.light_weight.create_release.handler.git_fetch"), patch(
        "mega_snake.light_weight.create_release.get_latest_release", side_effect=[latest, latest]
    ), patch("mega_snake.light_weight.create_release.handler.publish_release"), patch(
        "mega_snake.light_weight.create_release.handler.set_release_to_latest"
    ) as set_latest:
        create_release.callback("foo", "r", "notes ok", "branch")
        set_latest.assert_not_called()

    newer = SimpleNamespace(tag_name="v2.0.0", get_release_tag=lambda suffix: f"v2.0.0-{suffix}.0")
    with patch("mega_snake.light_weight.create_release.handler.git_fetch"), patch(
        "mega_snake.light_weight.create_release.get_latest_release", side_effect=[latest, newer]
    ), patch("mega_snake.light_weight.create_release.handler.publish_release"), patch(
        "mega_snake.light_weight.create_release.handler.set_release_to_latest"
    ) as set_latest:
        create_release.callback("foo", "r", "notes ok", "branch")
        set_latest.assert_called_once_with(latest.tag_name)

    with pytest.raises(KeyError):
        create_release.callback("foo", "x", None, "branch")


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

    with patch("subprocess.run", side_effect=[subprocess.CalledProcessError(1, "x")]):
        assert rel.get_release_tag("x").startswith("v1.0.0-x.")

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
