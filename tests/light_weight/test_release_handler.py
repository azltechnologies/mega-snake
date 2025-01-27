""" Tests for release_handler.py """

from typing import Generator
from unittest.mock import patch, MagicMock
import pytest
from codename_snake.light_weight import release_handler


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock]:
    """Mock run_operation"""
    with patch("codename_snake.light_weight.release_handler.run_operation") as mock:
        yield mock


def test_git_fetch(run_operation: MagicMock) -> None:
    """Test git_fetch"""
    release_handler.git_fetch()
    run_operation.assert_called_once()
    assert "git fetch" in run_operation.call_args[0][0]

def test_get_release_list(run_operation: MagicMock) -> None:
    """Test get_release_list"""
    release_handler.get_release_list()
    run_operation.assert_called_once()
    assert "gh release list" in run_operation.call_args[0][0]

def test_publish_release(run_operation: MagicMock) -> None:
    """Test publish_release"""
    tag_name: str = "tag_name"
    release_type: str = "release_type"
    release_notes: str = "release_notes"
    release_branch: str = "release_branch"
    release_handler.publish_release(tag_name, release_type, release_notes, release_branch)
    run_operation.assert_called_once()
    command:str = run_operation.call_args[0][0]
    assert f"gh release create {tag_name} {release_type}" in command
    assert f'--target "{release_branch}"' in command
    assert f'--title "{tag_name}"' in command
    assert release_notes in command
    assert "--generate-notes" in command

def test_set_release_to_latest(run_operation: MagicMock) -> None:
    """Test set_release_to_latest"""
    tag: str = "tag"
    release_handler.set_release_to_latest(tag)
    run_operation.assert_called_once()
    command:str = run_operation.call_args[0][0]
    assert f"gh release edit {tag}" in command
    assert "--latest" in command

def test_get_commit_from_release(run_operation: MagicMock) -> None:
    """Test get_commit_from_release"""
    tag: str = "tag"
    release_handler.get_commit_from_release(tag)
    run_operation.assert_called_once()
    assert f"git rev-list -n 1  \"{tag}\"" in run_operation.call_args[0][0]