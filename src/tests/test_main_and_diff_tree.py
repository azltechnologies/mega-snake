"""Additional tests for main CLI and diff_tree helpers."""

import os
from types import SimpleNamespace
from unittest.mock import mock_open, patch
import click
import pytest
from click.testing import CliRunner

from codename_snake import __main__ as app_main
from codename_snake.diff_tree.file_type import FileType
from codename_snake.diff_tree import module as diff_module


def test_main_cli_and_post_command() -> None:
    """Cover cli init, error path, and post-command."""
    runner = CliRunner()
    with patch.dict(os.environ, {"CODENAME_SNAKE_SHELL": "bash"}):
        with patch("codename_snake.__main__.init_app_properties"):
            result = runner.invoke(app_main.cli, ["createDiffTree", "--help"])
            assert result.exit_code == 0

    error_context = click.Context(app_main.cli)
    error_context.invoked_subcommand = "x"
    error_context.obj = {"exit_code": 2}
    with pytest.raises(SystemExit), error_context.scope():
        app_main.post_command(None)


def test_file_type_and_diff_tree_helpers() -> None:
    """Cover FileType and diff_tree helper functions."""
    FileType.ADDED.add("a.txt")
    assert FileType.from_symbol("A") == FileType.ADDED
    assert "files changed" in FileType.get_changes()
    with pytest.raises(ValueError):
        FileType.from_symbol("X")

    # Reset global enum state for test isolation
    for ft in FileType:
        ft.files_added = 0
        ft.files.clear()
    with patch("codename_snake.diff_tree.module.run_operation") as run_operation, patch(
        "builtins.open", mock_open()
    ), patch("codename_snake.diff_tree.module.os.makedirs"), patch(
        "codename_snake.diff_tree.module.os.path.dirname", return_value="/tmp"
    ):
        run_operation.return_value.stdout = "content"
        diff_module._create_files("/tmp/root", "main", True)

    with patch("codename_snake.diff_tree.module.DisplayTree", return_value="root\na"), patch(
        "builtins.open", mock_open()
    ), patch("codename_snake.diff_tree.module.run_operation"), patch(
        "codename_snake.diff_tree.module.os.walk", return_value=[("/tmp", [], ["a 🅐"])]
    ), patch("codename_snake.diff_tree.module.os.rename"):
        diff_module._display_inner_tree("/tmp", "/tmp/out.txt", True)


def test_diff_tree_main_paths() -> None:
    """Cover diff_tree main with empty and non-empty diffs."""
    with patch("codename_snake.diff_tree.module.get_property", return_value="/tmp"), patch(
        "codename_snake.diff_tree.module.os.path.exists", return_value=False
    ), patch("codename_snake.diff_tree.module.get_current_commit", return_value="head"), patch(
        "codename_snake.diff_tree.module.get_remote", return_value="origin"
    ), patch("codename_snake.diff_tree.module.get_main_branch", return_value="main"), patch(
        "codename_snake.diff_tree.module.run_operation"
    ) as run_operation:
        run_operation.return_value.stdout = ""
        diff_module.main.callback(None, False)

    with patch("codename_snake.diff_tree.module.get_property", return_value="/tmp"), patch(
        "codename_snake.diff_tree.module.os.path.exists", return_value=True
    ), patch("codename_snake.diff_tree.module.get_current_commit", return_value="head"), patch(
        "codename_snake.diff_tree.module.run_operation"
    ) as run_operation, patch(
        "codename_snake.diff_tree.module._create_files"
    ), patch("codename_snake.diff_tree.module._display_inner_tree"), patch(
        "codename_snake.diff_tree.module.shutil.rmtree"
    ), patch(
        "builtins.open", mock_open()
    ):
        run_operation.side_effect = [
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="commit"),
            SimpleNamespace(stdout=":000000 100644 0000000 1111111 A\tfile.txt"),
            SimpleNamespace(stdout="commit log"),
            SimpleNamespace(stdout="diff content"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout=""),
        ]
        diff_module.main.callback("abc", True)
