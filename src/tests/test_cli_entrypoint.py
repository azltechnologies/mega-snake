"""Focused tests for CLI initialization branches."""

import os
import runpy
import sys
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from mega_snake import __main__ as app_main
from mega_snake.util.formatting import WorkspaceError


@pytest.mark.parametrize("command_name", ["shell-path", "generate-docs"])
def test_cli_skips_initialization_for_no_init_subcommands(command_name: str) -> None:
    """no_init commands should bypass app property initialization."""
    ctx = click.Context(app_main.cli)
    ctx.invoked_subcommand = command_name
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


def test_get_version_returns_installed_package_version() -> None:
    """get_version should return the installed distribution version."""
    with patch("mega_snake.__main__.get_package_version", return_value="1.2.3"):
        assert app_main.get_version() == "1.2.3"


def test_get_version_falls_back_when_package_not_found() -> None:
    """get_version should fall back to 'unknown' when the package metadata is missing."""
    with patch("mega_snake.__main__.get_package_version", side_effect=PackageNotFoundError):
        assert app_main.get_version() == "unknown"


@pytest.mark.parametrize("flag", ["-v", "--version"])
def test_cli_version_flag_prints_version_and_exits(flag: str) -> None:
    """`mgsnake -v` / `mgsnake --version` should print the version and exit successfully."""
    runner = CliRunner()
    with patch("mega_snake.__main__.get_package_version", return_value="9.9.9"):
        result = runner.invoke(app_main.cli, [flag])
    assert result.exit_code == 0
    assert "9.9.9" in result.output


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


def test_cli_resolves_a_command_through_its_name_and_its_alias() -> None:
    """The entry point must reach the same command by its real name and by a registered alias.

    Aliases are separate hidden command objects, so resolving one is not implied by resolving the
    other: this walks the actual registry the way a user's shell does.
    """
    runner = CliRunner()
    with patch.dict(os.environ, {"MEGA_SNAKE_SHELL": "bash"}), patch(
        "mega_snake.__main__.init_app_properties"
    ):
        by_name = runner.invoke(app_main.cli, ["diff-tree", "--help"])
        by_alias = runner.invoke(app_main.cli, ["dt", "--help"])

    assert by_name.exit_code == 0, by_name.output
    assert by_alias.exit_code == 0, by_alias.output
    # Both spellings must land on the same command, not merely both succeed.
    assert "--origin-hash" in by_name.output
    assert "--origin-hash" in by_alias.output


def test_post_command_exits_with_the_exit_code_left_in_the_context() -> None:
    """A non-zero `exit_code` in the context must terminate the process with that exact status.

    The value is a channel between a module wrapper and the shell, so propagating *some* failure is
    not enough: the specific number is what the caller branches on.
    """
    context = click.Context(app_main.cli)
    context.invoked_subcommand = "x"
    context.obj = {"exit_code": 2}
    with pytest.raises(SystemExit) as excinfo, context.scope():
        app_command_post = app_main.post_command
        app_command_post(None)
    assert excinfo.value.code == 2


def test_post_command_does_not_exit_without_an_exit_code() -> None:
    """A successful command must return normally: only a non-zero code terminates the process."""
    context = click.Context(app_main.cli)
    context.invoked_subcommand = "x"
    context.obj = {}
    with context.scope():
        assert app_main.post_command(None) is None
