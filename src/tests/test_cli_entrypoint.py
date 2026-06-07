"""Focused tests for CLI initialization branches."""

import os
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import patch

import click
import pytest

from mega_snake import __main__ as app_main
from mega_snake.util.formatting import WorkspaceError


def test_cli_skips_initialization_for_shell_path_subcommand() -> None:
    """shell-path should bypass app property initialization."""
    ctx = click.Context(app_main.cli)
    ctx.invoked_subcommand = "shell-path"
    ctx.obj = {}

    with ctx.scope():
        with patch("mega_snake.__main__.init_app_properties") as init_app_properties:
            assert app_main.cli.callback("INFO") is None

    init_app_properties.assert_not_called()


def test_cli_uses_light_weight_mode_for_skip_commands() -> None:
    """Commands marked with the skip flag should initialize in light-weight mode."""
    ctx = click.Context(app_main.cli)
    ctx.invoked_subcommand = "echo"
    ctx.obj = {}
    skip_command = SimpleNamespace(callback=SimpleNamespace(flags={"flags": {"skip"}}))

    with ctx.scope():
        with patch.dict(os.environ, {"MEGA_SNAKE_SHELL": "bash"}), patch.object(
            app_main.cli, "get_command", return_value=skip_command
        ), patch("mega_snake.__main__.init_app_properties") as init_app_properties:
            app_main.cli.callback("INFO")

    init_app_properties.assert_called_once_with("INFO", "bash", True)


def test_cli_reports_missing_commands() -> None:
    """Unknown subcommands should be reported through the shared error path."""
    ctx = click.Context(app_main.cli)
    ctx.invoked_subcommand = "missing"
    ctx.obj = {}

    with ctx.scope():
        with patch.object(app_main.cli, "get_command", return_value=None), patch(
            "mega_snake.__main__.get_traceback", return_value="TRACE"
        ), patch("click.echo") as echo_mock:
            with pytest.raises(SystemExit, match="Command 'missing' not found"):
                app_main.cli.callback("INFO")

    echo_mock.assert_any_call("Error during initialization: Command 'missing' not found", err=True)
    echo_mock.assert_any_call("TRACE", err=True)


@pytest.mark.parametrize(
    ("shell_value", "expected_message"),
    [
        (None, "Environment variable 'MEGA_SNAKE_SHELL' is not set"),
        ("fish", "Unsupported shell: fish. Supported shells are: bash, zsh, powershell, pwsh"),
    ],
)
def test_cli_requires_a_supported_shell_env(shell_value: str | None, expected_message: str) -> None:
    """CLI initialization should validate the shell environment variable."""
    ctx = click.Context(app_main.cli)
    ctx.obj = {}
    env_patch = {} if shell_value is None else {"MEGA_SNAKE_SHELL": shell_value}

    with ctx.scope():
        with patch.dict(os.environ, env_patch, clear=True), patch(
            "mega_snake.__main__.get_traceback", return_value="TRACE"
        ), patch("click.echo") as echo_mock:
            with pytest.raises(SystemExit, match=expected_message):
                app_main.cli.callback("INFO")

    echo_mock.assert_any_call(f"Error during initialization: {expected_message}", err=True)
    echo_mock.assert_any_call("TRACE", err=True)


def test_running_main_module_wraps_cli_errors() -> None:
    """The __main__ block should wrap unexpected cli.main errors as WorkspaceError."""
    with patch("mega_snake.util.cli_group.CliGroup.main", side_effect=RuntimeError("boom")):
        # Remove the module from sys.modules to allow runpy.run_module to execute it cleanly
        modules_to_remove = [key for key in sys.modules if key.startswith("mega_snake.__main__")]
        removed_modules = {key: sys.modules.pop(key) for key in modules_to_remove}
        try:
            with pytest.raises(WorkspaceError, match="Error during cli execution"):
                runpy.run_module("mega_snake.__main__", run_name="__main__")
        finally:
            # Restore the modules
            sys.modules.update(removed_modules)
