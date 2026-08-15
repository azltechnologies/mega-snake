"""Tests for shell initialization helper commands."""

import logging
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
import pytest

from mega_snake.light_weight import shell_init
from mega_snake.util import formatting


@pytest.mark.parametrize(
    ("shell_name", "expected_file"),
    [("bash", "config_setup.sh"), ("powershell", "config_setup.ps1")],
)
def test_shell_path_prints_packaged_script_path(shell_name: str, expected_file: str) -> None:
    """shell-path should print the packaged init script path for supported shells."""
    runner = CliRunner()

    result = runner.invoke(shell_init.shell_path, [shell_name])

    assert result.exit_code == 0
    script_path = Path(result.output.strip())
    assert script_path.name == expected_file
    assert script_path.is_file()


def test_shell_path_requires_existing_script(tmp_path: Path) -> None:
    """shell-path should fail clearly when the packaged script is missing."""
    runner = CliRunner()

    with patch("mega_snake.light_weight.shell_init.files", return_value=tmp_path):
        result = runner.invoke(shell_init.shell_path, ["bash"])

    assert result.exit_code != 0
    assert isinstance(result.exception, FileNotFoundError)
    assert "Configuration script not found" in str(result.exception)


def test_shell_path_rejects_unknown_shell() -> None:
    """shell-path callback should reject shells outside the supported set."""
    with pytest.raises(ValueError, match="Unsupported shell: fish"):
        shell_init.shell_path.callback("fish")


def test_get_local_config_path_prints_helper_value() -> None:
    """get-local-config-path should print the resolved config file path."""
    runner = CliRunner()

    with patch("mega_snake.light_weight.shell_init.get_local_file", return_value="/tmp/local-config.sh"):
        result = runner.invoke(shell_init.get_local_config_path)

    assert result.exit_code == 0
    assert result.output.strip() == "/tmp/local-config.sh"


def test_get_local_config_path_stdout_stays_clean_at_debug_level() -> None:
    """`config_setup.sh` reads this command with `$(...)`, so DEBUG advice must not reach stdout.

    Regression guard: `ws_advice` is emitted by the CLI entry point and the result callback around
    every subcommand. If it ever printed to stdout again, the captured value would become the
    advice lines plus the path, and `mgsnake_reload` would source a non-existent file.
    """
    runner = CliRunner()

    with patch("mega_snake.light_weight.shell_init.get_local_file", return_value="/tmp/local-config.sh"):
        with patch.object(formatting.logger, "level", logging.DEBUG):
            formatting.ws_advice("Invoking subcommand: get-local-config-path")
            result = runner.invoke(shell_init.get_local_config_path)

    assert result.exit_code == 0
    assert result.output.strip() == "/tmp/local-config.sh"
