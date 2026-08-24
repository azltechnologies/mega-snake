"""Tests for the diff-tree command, its pre-flight wrapper and its helpers."""

from types import SimpleNamespace
from unittest.mock import mock_open, patch
import click
import pytest

from mega_snake.diff_tree.file_type import FileType
from mega_snake.util.formatting import InternalStateError
from mega_snake.diff_tree import module as diff_module
from mega_snake.diff_tree import diff_tree as diff_tree_cmd
from mega_snake.util.cli_group import ATTR_METADATA


def test_diff_tree_wrapper_has_skip_flag() -> None:
    """diff-tree is light-weight (skip), so a missing workspace_temp folder doesn't crash the CLI
    before its own pre-flight check gets the chance to offer creating it."""
    assert getattr(diff_module.wrapper, ATTR_METADATA) == {"flags": {"skip"}}


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


def test_file_type_and_diff_tree_helpers() -> None:
    """Cover FileType and diff_tree helper functions."""
    FileType.ADDED.add("a.txt")
    assert FileType.from_symbol("A") == FileType.ADDED
    assert "files changed" in FileType.get_changes()
    # A status letter this enum does not cover means git grew one we never added: our bug, not
    # a bad value the user supplied, so it must not report as an ordinary ValueError.
    with pytest.raises(InternalStateError, match="No FileType with symbol 'X' found"):
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
        run_operation.return_value = SimpleNamespace(returncode=0, stdout="tree")
        with pytest.raises(ValueError, match="Invalid commit hash: abc"):
            diff_tree_cmd.diff_tree.callback(
                origin_hash="abc", target_hash=None, delete_original_files=False, scope="c"
            )


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


def test_get_pending_changes_report_per_scope() -> None:
    """The report only covers what the scope includes: nothing for the committed scope, the index
    for the staged one, and the working tree on top of it for the unstaged one."""
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        assert diff_tree_cmd._get_pending_changes_report("c", []) == ""
        run_operation.assert_not_called()

    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = "staged.txt"
        report = diff_tree_cmd._get_pending_changes_report("s", [])
    assert report == "Staged files:\n- staged.txt\n\n"
    run_operation.assert_called_once_with("git diff --cached --name-only", "getting staged files")

    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout="modified.txt"),  # unstaged files
            SimpleNamespace(stdout="staged.txt"),  # staged files
        ]
        report = diff_tree_cmd._get_pending_changes_report("u", ["new.txt"])
    # unstaged first, so the commit list below keeps reading from newest to oldest
    assert report == "Unstaged files:\n- modified.txt\n- new.txt\n\nStaged files:\n- staged.txt\n\n"


def test_get_pending_changes_report_skips_the_empty_sections() -> None:
    """A section with no file is left out entirely instead of printing an empty heading."""
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.side_effect = [
            SimpleNamespace(stdout=""),  # unstaged files: none
            SimpleNamespace(stdout="staged.txt"),  # staged files
        ]
        assert diff_tree_cmd._get_pending_changes_report("u", []) == "Staged files:\n- staged.txt\n\n"

    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = ""
        assert diff_tree_cmd._get_pending_changes_report("u", []) == ""


def test_diff_tree_main_writes_the_pending_changes_above_the_commits() -> None:
    """The commit file keeps the commits, with the uncommitted work reported on top of them."""
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
        ) as m_open:
            run_operation.side_effect = [
                SimpleNamespace(stdout="commit", returncode=0),  # commit hash validation
                SimpleNamespace(stdout=""),  # untracked files
                SimpleNamespace(stdout=":000000 100644 0000000 1111111 A\tfile.txt"),  # raw diff
                SimpleNamespace(stdout=""),  # numstat
                SimpleNamespace(stdout="2026-08-14 abc123\nmsg"),  # commit list
                SimpleNamespace(stdout="modified.txt"),  # unstaged files
                SimpleNamespace(stdout="staged.txt"),  # staged files
                SimpleNamespace(stdout=""),  # opening commit file
                SimpleNamespace(stdout="diff content"),  # changes
                SimpleNamespace(stdout=""),  # opening changes file
            ]
            diff_tree_cmd.diff_tree.callback(
                origin_hash="abc", target_hash=None, delete_original_files=True, scope="u"
            )

        written = [call.args[0] for call in m_open().write.call_args_list]
        assert "Unstaged files:\n- modified.txt\n\nStaged files:\n- staged.txt\n\n2026-08-14 abc123\nmsg" in written
    finally:
        for file_type in FileType:
            file_type.files_added = 0
            file_type.files.clear()


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
                SimpleNamespace(stdout="commit", returncode=0),  # commit hash validation
                SimpleNamespace(stdout="new.txt"),  # untracked files
                SimpleNamespace(stdout=""),  # raw diff: nothing tracked changed
                SimpleNamespace(stdout=""),  # numstat
                SimpleNamespace(stdout="commit log"),  # commit list
                SimpleNamespace(stdout=""),  # unstaged files
                SimpleNamespace(stdout=""),  # staged files
                SimpleNamespace(stdout=""),  # opening commit file
                SimpleNamespace(stdout="diff content"),  # changes
                SimpleNamespace(stdout=""),  # opening changes file
            ]
            diff_tree_cmd.diff_tree.callback(
                origin_hash="abc", target_hash=None, delete_original_files=True, scope="u"
            )

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
            SimpleNamespace(stdout="commit", returncode=0),
            SimpleNamespace(stdout=":000000 100644 0000000 1111111 A\tfile.txt"),
            SimpleNamespace(stdout="-\t-\tasset.webp"),
            SimpleNamespace(stdout="commit log"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="diff content"),
            SimpleNamespace(stdout=""),
        ]
        diff_tree_cmd.diff_tree.callback(
                origin_hash="abc", target_hash=None, delete_original_files=True, scope="c"
            )

    assert create_files.call_args.args[3] == {"asset.webp"}


def test_diff_tree_main_paths() -> None:
    """Cover diff_tree main with empty and non-empty diffs."""
    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=False
    ), patch("mega_snake.diff_tree.diff_tree.get_current_commit", return_value="head"), patch(
        "mega_snake.diff_tree.diff_tree.Repo", **{"return_value.MAIN_BRANCH": "main"}
    ), patch(
        "mega_snake.diff_tree.diff_tree.os.makedirs"
    ), patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value.stdout = ""
        diff_tree_cmd.diff_tree.callback(
                origin_hash=None, target_hash=None, delete_original_files=False, scope="c"
            )

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
            SimpleNamespace(stdout="commit", returncode=0),
            SimpleNamespace(stdout=":000000 100644 0000000 1111111 A\tfile.txt"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="commit log"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(stdout="diff content"),
            SimpleNamespace(stdout=""),
        ]
        diff_tree_cmd.diff_tree.callback(
                origin_hash="abc", target_hash=None, delete_original_files=True, scope="c"
            )


def test_diff_tree_target_replaces_head_in_every_derived_command() -> None:
    """--target must move the far end of the comparison off HEAD, everywhere it is used.

    The target reaches git through three independent commands (the raw diff, the numstat used for
    binary detection, and the commit log). Asserting only one of them would let the other two keep
    comparing against HEAD, which is exactly the drift this option exists to avoid.
    """
    for file_type in FileType:
        file_type.files_added = 0
        file_type.files.clear()
    try:
        with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
            "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=False
        ), patch("mega_snake.diff_tree.diff_tree.get_current_commit") as get_current_commit, patch(
            "mega_snake.diff_tree.diff_tree.run_operation"
        ) as run_operation, patch("mega_snake.diff_tree.diff_tree._create_files"), patch(
            "mega_snake.diff_tree.diff_tree._display_inner_tree"
        ), patch("mega_snake.diff_tree.diff_tree.shutil.rmtree"), patch(
            "mega_snake.diff_tree.diff_tree.os.makedirs"
        ), patch("builtins.open", mock_open()):
            run_operation.side_effect = [
                SimpleNamespace(stdout="commit", returncode=0),  # base validation
                SimpleNamespace(stdout="commit", returncode=0),  # target validation
                SimpleNamespace(stdout=":000000 100644 0000000 1111111 A\tfile.txt"),  # raw diff
                SimpleNamespace(stdout=""),  # numstat
                SimpleNamespace(stdout="commit log"),  # commit list
                SimpleNamespace(stdout=""),  # opening commit file
                SimpleNamespace(stdout="diff content"),  # changes
                SimpleNamespace(stdout=""),  # opening changes file
            ]
            diff_tree_cmd.diff_tree.callback(
                origin_hash="base111", target_hash="tip222", delete_original_files=True, scope="c"
            )

        # HEAD must never be consulted: the whole point is that the range is explicit.
        get_current_commit.assert_not_called()
        issued = [call.args[0] for call in run_operation.call_args_list]
        assert "git cat-file -t tip222 2>/dev/null" in issued, "the target was never validated"
        assert "git diff --raw --no-renames base111 tip222" in issued
        assert "git diff --numstat base111 tip222" in issued
        assert " git log --pretty=format:'%ad %H%n%B' --date=short tip222...base111" in issued
        # No command may still be pointing at the working tree's HEAD.
        assert not [command for command in issued if command.endswith(" base111")], (
            f"a command still compares base111 against HEAD: {issued}"
        )
    finally:
        for file_type in FileType:
            file_type.files_added = 0
            file_type.files.clear()


def test_diff_tree_without_target_still_compares_against_head() -> None:
    """Omitting --target keeps the previous behaviour: the comparison ends at the current HEAD."""
    for file_type in FileType:
        file_type.files_added = 0
        file_type.files.clear()
    try:
        with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
            "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=False
        ), patch(
            "mega_snake.diff_tree.diff_tree.get_current_commit", return_value="headsha"
        ) as get_current_commit, patch(
            "mega_snake.diff_tree.diff_tree.run_operation"
        ) as run_operation, patch("mega_snake.diff_tree.diff_tree._create_files"), patch(
            "mega_snake.diff_tree.diff_tree._display_inner_tree"
        ), patch("mega_snake.diff_tree.diff_tree.shutil.rmtree"), patch(
            "mega_snake.diff_tree.diff_tree.os.makedirs"
        ), patch("builtins.open", mock_open()):
            run_operation.side_effect = [
                SimpleNamespace(stdout="commit", returncode=0),  # base validation
                SimpleNamespace(stdout=":000000 100644 0000000 1111111 A\tfile.txt"),  # raw diff
                SimpleNamespace(stdout=""),  # numstat
                SimpleNamespace(stdout="commit log"),  # commit list
                SimpleNamespace(stdout=""),  # opening commit file
                SimpleNamespace(stdout="diff content"),  # changes
                SimpleNamespace(stdout=""),  # opening changes file
            ]
            diff_tree_cmd.diff_tree.callback(
                origin_hash="base111", target_hash=None, delete_original_files=True, scope="c"
            )

        get_current_commit.assert_called_once_with()
        issued = [call.args[0] for call in run_operation.call_args_list]
        assert "git diff --raw --no-renames base111 headsha" in issued
        # Only the base is validated when no target is given: HEAD needs no validation.
        assert len([command for command in issued if command.startswith("git cat-file")]) == 1
    finally:
        for file_type in FileType:
            file_type.files_added = 0
            file_type.files.clear()


@pytest.mark.parametrize("scope", ["s", "u"])
def test_diff_tree_rejects_target_with_a_working_tree_scope(scope: str) -> None:
    """--target cannot be combined with a scope that reads the index or the working tree.

    Those scopes never consume the far end of the range, so accepting the combination would run a
    diff that silently ignores --target and report it as if it had been honoured.

    Parameters:
        scope: The staged or unstaged scope being rejected.

    Raises:
        None

    Returns:
        None
    """
    with patch("mega_snake.diff_tree.diff_tree.get_property") as get_property, patch(
        "mega_snake.diff_tree.diff_tree.shutil.rmtree"
    ) as rmtree, patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        with pytest.raises(
            click.ClickException,
            match=f"BAD REQUEST: --target-hash and --scope {scope} are mutually exclusive",
        ):
            diff_tree_cmd.diff_tree.callback(
                origin_hash=None, target_hash="tip222", delete_original_files=False, scope=scope
            )
    # Rejected before any side effect: no output folder is resolved, wiped, or touched by git.
    get_property.assert_not_called()
    rmtree.assert_not_called()
    run_operation.assert_not_called()


def test_diff_tree_rejects_an_invalid_target() -> None:
    """A target that does not resolve to a commit is rejected, like the base already was."""
    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=False
    ), patch("mega_snake.diff_tree.diff_tree.os.makedirs"), patch(
        "mega_snake.diff_tree.diff_tree.Repo", **{"return_value.MAIN_BRANCH": "master"}
    ), patch(
        "mega_snake.diff_tree.diff_tree.run_operation"
    ) as run_operation:
        run_operation.return_value = SimpleNamespace(returncode=0, stdout="blob")
        with pytest.raises(ValueError, match="Invalid commit hash: notacommit"):
            diff_tree_cmd.diff_tree.callback(
                origin_hash=None, target_hash="notacommit", delete_original_files=False, scope="c"
            )


def test_validate_commit_returns_the_reference_it_was_given() -> None:
    """A valid reference is returned unchanged, so callers can assign it directly."""
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(returncode=0, stdout="commit\n")
        assert diff_tree_cmd._validate_commit("abc123") == "abc123"
    # check=False is load-bearing: a reference that does not exist exits non-zero, and the default
    # check=True would retry it three times and report a subprocess failure instead of the typo.
    run_operation.assert_called_once_with(
        "git cat-file -t abc123 2>/dev/null", "Checking if commit hash 'abc123' is valid", check=False
    )


def test_diff_tree_exposes_the_expected_option_names() -> None:
    """The public flags are part of the command's contract, so a rename must be deliberate.

    Renaming an option silently breaks every script and habit that uses it, and the callback
    signature alone does not pin the user-facing spelling: click derives the parameter name from the
    flag, so a wrong flag with a matching parameter would still satisfy every other test here.
    """
    declared = {
        parameter.name: tuple(parameter.opts) for parameter in diff_tree_cmd.diff_tree.params
    }
    assert declared["origin_hash"] == ("--origin-hash", "-o")
    assert declared["target_hash"] == ("--target-hash", "-t")
    assert declared["scope"] == ("--scope", "-s")
    assert declared["delete_original_files"] == ("--delete-original-files", "-d")
    # The previous spellings must be gone, not merely shadowed by the new ones.
    every_flag = [flag for flags in declared.values() for flag in flags]
    assert "--commit-hash" not in every_flag
    assert "--target" not in every_flag
    assert "-c" not in every_flag


def test_diff_tree_help_documents_the_scope_restriction_on_both_options() -> None:
    """--scope and --target-hash constrain each other, so each one must say so on its own.

    A user reading `--scope` should not have to read `--target-hash` to discover the combination is
    refused, and vice versa: whichever one they look up first has to carry the warning.
    """
    help_by_name = {parameter.name: parameter.help for parameter in diff_tree_cmd.diff_tree.params}

    scope_help = help_by_name["scope"]
    assert "--target-hash" in scope_help, "--scope never mentions the option that restricts it"
    assert "rejected" in scope_help, "--scope does not say the combination is refused"

    target_help = help_by_name["target_hash"]
    assert "--scope c" in target_help, "--target-hash never names the scope it requires"
    assert "rejected" in target_help, "--target-hash does not say the combination is refused"


def test_diff_tree_validates_both_commits_before_touching_the_output() -> None:
    """A rejected invocation must never destroy the previous run's output.

    A mistyped hash is the likeliest rejection there is, so wiping the output directory first would
    leave the user with an empty folder and no fallback, for a run that produced nothing.
    """
    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=True
    ), patch("mega_snake.diff_tree.diff_tree.shutil.rmtree") as rmtree, patch(
        "mega_snake.diff_tree.diff_tree.os.makedirs"
    ) as makedirs, patch("mega_snake.diff_tree.diff_tree.get_current_commit", return_value="head"), patch(
        "mega_snake.diff_tree.diff_tree.run_operation"
    ) as run_operation:
        run_operation.return_value = SimpleNamespace(returncode=0, stdout="blob")
        with pytest.raises(ValueError, match="Invalid commit hash: typo"):
            diff_tree_cmd.diff_tree.callback(
                origin_hash="typo", target_hash=None, delete_original_files=False, scope="c"
            )

    rmtree.assert_not_called()
    makedirs.assert_not_called()


def test_diff_tree_validates_the_target_before_touching_the_output() -> None:
    """The same guarantee must hold for the far end of the comparison, not just the base."""
    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=True
    ), patch("mega_snake.diff_tree.diff_tree.shutil.rmtree") as rmtree, patch(
        "mega_snake.diff_tree.diff_tree.os.makedirs"
    ) as makedirs, patch(
        "mega_snake.diff_tree.diff_tree.Repo", **{"return_value.MAIN_BRANCH": "master"}
    ), patch(
        "mega_snake.diff_tree.diff_tree.run_operation"
    ) as run_operation:
        run_operation.return_value = SimpleNamespace(returncode=0, stdout="tree")
        with pytest.raises(ValueError, match="Invalid commit hash: typo"):
            diff_tree_cmd.diff_tree.callback(
                origin_hash=None, target_hash="typo", delete_original_files=False, scope="c"
            )

    rmtree.assert_not_called()
    makedirs.assert_not_called()


@pytest.mark.parametrize("option", ["origin_hash", "target_hash"])
def test_diff_tree_reports_a_mistyped_hash_as_an_invalid_commit(option: str) -> None:
    """A reference git cannot resolve at all must be reported as the typo it is.

    `git cat-file -t` exits 128 for a name that does not exist, which is the *common* rejection —
    far more likely than a reference that resolves to a tree or a blob. Under the default
    `check=True` that status is treated as an operational failure: retried three times with a
    two-second sleep, then surfaced as a subprocess error that says nothing about the typo.

    Parameters:
        option: Which end of the comparison carries the mistyped hash.

    Raises:
        None

    Returns:
        None
    """
    arguments = {"origin_hash": None, "target_hash": None, "delete_original_files": False, "scope": "c"}
    arguments[option] = "abc123x"
    with patch("mega_snake.diff_tree.diff_tree.get_property", return_value="/tmp"), patch(
        "mega_snake.diff_tree.diff_tree.os.path.exists", return_value=True
    ), patch("mega_snake.diff_tree.diff_tree.shutil.rmtree") as rmtree, patch(
        "mega_snake.diff_tree.diff_tree.os.makedirs"
    ), patch("mega_snake.diff_tree.diff_tree.Repo", **{"return_value.MAIN_BRANCH": "master"}), patch(
        "mega_snake.diff_tree.diff_tree.get_current_commit", return_value="head"
    ), patch(
        "mega_snake.diff_tree.diff_tree.run_operation"
    ) as run_operation:
        # What git actually returns for a name it cannot resolve: non-zero, and nothing on stdout.
        run_operation.return_value = SimpleNamespace(returncode=128, stdout="")
        with pytest.raises(ValueError, match="Invalid commit hash: abc123x"):
            diff_tree_cmd.diff_tree.callback(**arguments)  # type: ignore[arg-type]

    # The lookup must not be retried: a name that does not exist will not start existing.
    assert run_operation.call_count == 1, f"the failing lookup was retried {run_operation.call_count} times"
    assert run_operation.call_args.kwargs["check"] is False
    rmtree.assert_not_called()


def test_validate_commit_rejects_a_reference_that_is_not_a_commit() -> None:
    """A reference that resolves, but not to a commit, is still rejected.

    This is the rarer path the exit status alone cannot catch: git succeeds, so only the payload
    distinguishes a tag or a tree from the commit the diff needs.
    """
    with patch("mega_snake.diff_tree.diff_tree.run_operation") as run_operation:
        run_operation.return_value = SimpleNamespace(returncode=0, stdout="tree\n")
        with pytest.raises(ValueError, match="Invalid commit hash: sometree"):
            diff_tree_cmd._validate_commit("sometree")
