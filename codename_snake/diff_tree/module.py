"""Creates a diff tree of the current branch against master"""

import os
import shutil
from typing import Optional
import click
from directory_tree import DisplayTree
from codename_snake.util.formatting import ws_info, ws_success
from codename_snake.util.util import run_operation, get_main_branch, get_current_commit
from codename_snake.util.props import get_property
from codename_snake.diff_tree.file_type import FileType


@click.command(
    name="createDiffTree",
    short_help="Creates diff tree and commit list of current changes",
    help="Creates a diff tree of changes and a commit list of the current branch against master or a specified commit hash",
    epilog="""The directory tree and commit list are created within $WS_TEMP path.\n
    usage: snake createDiffTree [OPTIONS]\n
    OPTIONS:\n
        -c | --commit-hash: Optional[str] - Commit hash to compare against instead of master\n
        -d | --delete-original-files: bool - Delete the generated copy of the original files in the diff tree\n
    """,
)
@click.option("--commit-hash", "-c", type=click.STRING, default=None, help="Commit hash to compare against instead of master")
@click.option("--delete-original-files", "-d", is_flag=True, help="Delete the generated copy of the original files in the diff tree")
def main(commit_hash: Optional[str], delete_original_files: bool) -> None:
    """
    Creates a diff tree of the current branch against master or a specified commit hash.

    Args:
        commit_hash: str
        delete_original_files: bool
    """
    tree_output: str = f"{get_property("working_path")}/diff_tree"
    diff_commit_file: str = f"{tree_output}/diff_commit.txt"
    diff_tree_dummy_repo: str = f"{tree_output}/diff_tree_dummy_repo"

    # check if tree_output directory exists. if so, delete it
    if os.path.exists(tree_output):
        run_operation(f"rm -rf {tree_output}", "Deleting existing diff tree output directory")
        # create the tree_output directory
        run_operation(f"mkdir -p {diff_tree_dummy_repo}/", "Creating diff tree output directory")

    current_branch: str = get_current_commit()
    main_branch: str
    if commit_hash is None:
        main_branch = get_main_branch()
        ws_info(f"Main branch: {main_branch}")
    else:
        commit_validation: str = run_operation(
            f"git cat-file -t {commit_hash} 2>/dev/null", f"Checking if commit hash '{commit_hash}' is valid"
        ).stdout.strip()
        if commit_validation != "commit":
            raise ValueError(f"Invalid commit hash: {commit_hash}")
        main_branch = commit_hash
    diff_str: str = run_operation(
        f"git diff-tree -r {main_branch} {current_branch}", f"getting differences between '{main_branch}' and '{current_branch}' branches"
    ).stdout.strip()
    # check if there are no differences
    if not diff_str:
        ws_success("No differences found between the current branch and the main branch")
        return

    # iterate over the differences and write them to the output file
    for diff in diff_str.split("\n"):
        columns: list[str] = diff.split("\t")
        symbol = columns[0].split(" ")[4]
        path: str = columns[1]
        FileType.from_symbol(symbol).add(path)
    _create_files(diff_tree_dummy_repo, main_branch, not delete_original_files)
    _display_inner_tree(diff_tree_dummy_repo, f"{tree_output}/diff_tree.txt", not delete_original_files)
    ws_success(f"Diff tree created at {tree_output}/diff_tree.txt")
    # write the commit list to the file
    commits: str = run_operation(
        f" git log --pretty=format:'%ad %H%n%B' --date=short {current_branch}...{main_branch}", "Writing commit list to file"
    ).stdout.strip()
    with open(diff_commit_file, "w", encoding="utf-8") as diff_commit:
        diff_commit.write(commits)
    run_operation(f"code {diff_commit_file}", "opening diff commit file")
    ws_success(f"Commit list created at {diff_commit_file}")
    if delete_original_files:
        shutil.rmtree(diff_tree_dummy_repo)
        ws_success("Deleted the generated copy of the original files in the diff tree")


def _create_files(location: str, main_branch: str, show_contents: bool) -> None:
    """
    Creates new files for each file type in the specified location.

    Args:
        location: str
    """
    contents: str
    for file_type in FileType:
        for file in file_type.files:
            new_file_path: str = f"{location}/{file} - {file_type.symbol}"
            os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
            contents = (
                ""
                if not show_contents or file_type.id_type == "A"
                else run_operation(f"git show {main_branch}:{file}", "Getting file contents").stdout
            )
            with open(new_file_path, "w", encoding="utf-8") as new_file:
                new_file.write(contents)


def _display_inner_tree(root_dir: str, output_file: str, show_contents: bool) -> None:
    """
    Display the tree of a directory's contents, hiding the root directory.

    Args:
        root_dir (str): The directory whose contents are to be displayed.
        output_file (str): The file to write the tree to.

    Returns:
        None
    """
    tree: str = DisplayTree(f"{root_dir}", stringRep=True, header=False)
    tree = f"{tree}\n{FileType.get_changes()}"
    lines: list[str] = tree.splitlines()
    lines[0] = "."
    tree = "\n".join(lines)
    with open(output_file, "w", encoding="utf-8") as diff_tree:
        diff_tree.write(tree)
    if show_contents:
        for root, _, files in os.walk(root_dir):
            for filename in files:
                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, filename[:-4])
                try:
                    os.rename(old_path, new_path)
                except OSError as e:
                    raise OSError(f"Failed to rename file {old_path} to {new_path}") from e
    run_operation(f"code {output_file}", "opening diff tree file")
