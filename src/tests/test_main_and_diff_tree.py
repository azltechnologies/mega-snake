"""Additional tests for main CLI and diff_tree helpers."""

import os
from types import SimpleNamespace
from unittest.mock import mock_open, patch
import click
import pytest
from click.testing import CliRunner

from mega_snake import __main__ as app_main
from mega_snake.diff_tree.file_type import FileType
from mega_snake.diff_tree import module as diff_module
from mega_snake.diff_tree import diff_tree as diff_tree_cmd


def test_diff_tree_wrapper_has_skip_flag() -> None:
    """diff-tree is light-weight (skip), so a missing workspace_temp folder doesn't crash the CLI
    before its own pre-flight check gets the chance to offer creating it."""
    assert diff_module.wrapper.flags == {"flags": {"skip"}}


def test_diff_tree_wrapper_only_ensures_the_working_path() -> None:
    """The pre-flight check just secures the output folder: diff-tree works without a remote."""
    with patch("mega_snake.diff_tree.module.ensure_working_path") as ensure_working_path, patch(
        "mega_snake.diff_tree.module.complete_app_properties"
    ) as complete_app_properties:
        diff_module.wrapper(None)
    ensure_working_path.assert_called_once_with()
    # the log file only becomes possible once the working path is secured, never before
    complete_app_properties.assert_called_once_with()


def test_diff_tree_wrapper_fails_when_working_path_is_declined() -> None:
    """Declining to create the working path fails cleanly instead of crashing while writing."""
    with patch(
        "mega_snake.diff_tree.module.ensure_working_path",
        side_effect=click.ClickException("Cannot continue without the 'workspace_temp' folder."),
    ), patch("mega_snake.diff_tree.module.complete_app_properties") as complete_app_properties:
        with pytest.raises(click.ClickException, match="Cannot continue without"):
            diff_module.wrapper(None)
    complete_app_properties.assert_not_called()


def test_main_cli_and_post_command() -> None:
    """Cover cli init, error path, and post-command."""
    runner = CliRunner()
    with patch.dict(os.environ, {"MEGA_SNAKE_SHELL": "bash"}):
        with patch("mega_snake.__main__.init_app_properties"):
            result = runner.invoke(app_main.cli, ["diff-tree", "--help"])
            assert result.exit_code == 0
            alias_result = runner.invoke(app_main.cli, ["dt", "--help"])
            assert alias_result.exit_code == 0

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
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation, patch(
        "builtins.open", mock_open()
    ), patch("mega_snake.diff_tree.diff_tree.os.makedirs"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.dirname", return_value="/tmp"
    ):
        run_operation.return_value.stdout = "content"
        diff_tree_cmd._create_files("/tmp/root", "main", True)

    with patch("mega_snake.diff_tree.diff_tree.DisplayTree", return_value="root\na"), patch(
        "builtins.open", mock_open()
    ), patch("mega_snake.diff_tree.diff_tree.run_operation"), patch(
        "mega_snake.diff_tree.diff_tree.os.walk", return_value=[("/tmp", [], ["a 🅐"])]
    ), patch("mega_snake.diff_tree.diff_tree.os.rename"):
        diff_tree_cmd._display_inner_tree("/tmp", "/tmp/out.txt", True)


def test_get_binary_files() -> None:
    """_get_binary_files should identify only entries with '-' in both numstat columns."""
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = "1\t2\ta.txt\n-\t-\tasset.webp\n-\t-\tfont.ttf\n"
        result = diff_tree_cmd._get_binary_files("main head")
    assert result == {"asset.webp", "font.ttf"}
    run_operation.assert_called_once_with(
        "git diff --numstat main head", "getting binary file information for 'main head'"
    )

    # empty numstat output should yield an empty set without crashing
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = ""
        result = diff_tree_cmd._get_binary_files("main head")
    assert result == set()


def test_diff_tree_main_rejects_an_invalid_commit_hash() -> None:
    """A reference that is not a commit is rejected before any diff is attempted against it."""
    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=False
    ), patch("mega_snake.diff_tree.diff_tree.get_current_commit", return_value="head"), patch(
        "mega_snake.diff_tree.diff_tree.os.makedirs"
    ), patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = "tree"
        with pytest.raises(ValueError, match="Invalid commit hash: abc"):
            diff_tree_cmd.diff_tree.callback("abc", False, "c")


def test_get_diff_target_per_scope() -> None:
    """Each scope maps to the git revision arguments that include exactly its changes."""
    assert diff_tree_cmd._get_diff_target("c", "main", "head") == "main head"
    assert diff_tree_cmd._get_diff_target("s", "main", "head") == "--cached main"
    assert diff_tree_cmd._get_diff_target("u", "main", "head") == "main"


def test_get_untracked_files() -> None:
    """Untracked files are only listed for the unstaged scope, and never for the other ones."""
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = "new.txt\nfolder/other.txt\n"
        assert diff_tree_cmd._get_untracked_files("u") == ["new.txt", "folder/other.txt"]
    run_operation.assert_called_once_with("git ls-files --others --exclude-standard", "getting untracked files")

    # a clean working tree yields no entries instead of a single empty path
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = ""
        assert diff_tree_cmd._get_untracked_files("u") == []

    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        assert diff_tree_cmd._get_untracked_files("c") == []
        assert diff_tree_cmd._get_untracked_files("s") == []
        run_operation.assert_not_called()


def test_diff_tree_main_includes_untracked_files_in_unstaged_scope() -> None:
    """With the unstaged scope, untracked files are reported as added even though git diff ignores
    them, and the run is not considered empty when they are the only change."""
    for file_type in FileType:
        file_type.files_added = 0
        file_type.files.clear()
    try:
        with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
            "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=True
        ), patch("mega_snake.diff_tree.diff_tree.get_current_commit", return_value="head"), patch(
            "mega_snake.diff_tree.diff_tree.run_operation"
        ) as run_operation, patch(
            "mega_snake.diff_tree.diff_tree._create_files"
        ), patch("mega_snake.diff_tree.diff_tree._display_inner_tree"), patch(
            "mega_snake.diff_tree.diff_tree.shutil.rmtree"
        ), patch("mega_snake.diff_tree.diff_tree.os.makedirs"), patch(
            "builtins.open", mock_open()
        ):
            run_operation.side_effect = [
                SimpleNamespace(stdout="commit"),  # commit hash validation
                SimpleNamespace(stdout="new.txt"),  # untracked files
                SimpleNamespace(stdout=""),  # raw diff: nothing tracked changed
                SimpleNamespace(stdout=""),  # numstat
                SimpleNamespace(stdout="commit log"),  # commit list
                SimpleNamespace(stdout=""),  # opening commit file
                SimpleNamespace(stdout="diff content"),  # changes
                SimpleNamespace(stdout=""),  # opening changes file
            ]
            diff_tree_cmd.diff_tree.callback("abc", True, "u")

        assert FileType.ADDED.files == ["new.txt"]
        commands = [call.args[0] for call in run_operation.call_args_list]
        assert "git diff --raw --no-renames abc" in commands
        assert "git diff abc" in commands
    finally:
        for file_type in FileType:
            file_type.files_added = 0
            file_type.files.clear()


def test_create_files_skips_binary_contents() -> None:
    """_create_files should write a placeholder for binary files instead of calling git show."""
    FileType.MODIFED.add("asset.webp")
    FileType.MODIFED.add("text.txt")
    try:
        with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation, patch(
            "builtins.open", mock_open()
        ) as m_open, patch("mega_snake.diff_tree.diff_tree.os.makedirs"), patch(
            "mega_snake.diff_tree.diff_tree.os.path.dirname", return_value="/tmp"
        ):
            run_operation.return_value.stdout = "text content"
            diff_tree_cmd._create_files("/tmp/root", "main", True, {"asset.webp"})

        written_contents = [call.args[0] for call in m_open().write.call_args_list]
        assert "Binary file (contents not shown)" in written_contents
        assert "text content" in written_contents
        run_operation.assert_called_once_with("git show main:text.txt", "Getting file contents")
    finally:
        for ft in FileType:
            ft.files_added = 0
            ft.files.clear()


def test_diff_tree_main_computes_binary_files() -> None:
    """diff_tree main should compute binary files and forward them to _create_files."""
    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=True
    ), patch("mega_snake.diff_tree.diff_tree.get_current_commit", return_value="head"), patch(
        "mega_snake.diff_tree.diff_tree.run_operation"
    ) as run_operation, patch(
        "mega_snake.diff_tree.diff_tree._create_files"
    ) as create_files, patch("mega_snake.diff_tree.diff_tree._display_inner_tree"), patch(
        "mega_snake.diff_tree.diff_tree.shutil.rmtree"
    ), patch("mega_snake.diff_tree.diff_tree.os.makedirs"), patch(
        "builtins.open", mock_open()
    ):
        run_operation.side_effect = [
            SimpleNamespace(stdout="commit"),
            SimpleNamespace(stdout=":000000 100644 0000000 1111111 A\tfile.txt"),
            SimpleNamespace(stdout="-\t-\tasset.webp"),
            SimpleNamespace(stdout="commit log"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="diff content"),
            SimpleNamespace(stdout=""),
        ]
        diff_tree_cmd.diff_tree.callback("abc", True, "c")

    assert create_files.call_args.args[3] == {"asset.webp"}


def test_diff_tree_main_paths() -> None:
    """Cover diff_tree main with empty and non-empty diffs."""
    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=False
    ), patch("mega_snake.diff_tree.diff_tree.get_current_commit", return_value="head"), patch(
        "mega_snake.diff_tree.diff_tree.get_remote", return_value="origin"
    ), patch("mega_snake.diff_tree.diff_tree.get_main_branch", return_value="main"), patch(
        "mega_snake.diff_tree.diff_tree.os.makedirs"
    ), patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = ""
        diff_tree_cmd.diff_tree.callback(None, False, "c")

    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=True
    ), patch("mega_snake.diff_tree.diff_tree.get_current_commit", return_value="head"), patch(
        "mega_snake.diff_tree.diff_tree.run_operation"
    ) as run_operation, patch(
        "mega_snake.diff_tree.diff_tree._create_files"
    ), patch("mega_snake.diff_tree.diff_tree._display_inner_tree"), patch(
        "mega_snake.diff_tree.diff_tree.shutil.rmtree"
    ), patch("mega_snake.diff_tree.diff_tree.os.makedirs"), patch(
        "builtins.open", mock_open()
    ):
        run_operation.side_effect = [
            SimpleNamespace(stdout="commit"),
            SimpleNamespace(stdout=":000000 100644 0000000 1111111 A\tfile.txt"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="commit log"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="diff content"),
            SimpleNamespace(stdout=""),
        ]
        diff_tree_cmd.diff_tree.callback("abc", True, "c")
