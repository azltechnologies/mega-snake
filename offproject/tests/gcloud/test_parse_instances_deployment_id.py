"""Test the parse_instances_deployment_id module."""

from typing import Generator
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
import pytest
from mega_snake.gcloud.parse_instances_deployment_id import bq_instances_by_deployment_id


def reset_mocks(*mocks: MagicMock) -> None:
    """Reset the mocks."""
    for mock in mocks:
        mock.reset_mock()


@pytest.fixture(name="pyperclip_copy")
def fixture_pyperclip_copy() -> Generator[MagicMock]:
    """Mock pyperclip.copy"""
    with patch("mega_snake.gcloud.parse_instances_deployment_id.pyperclip.copy") as mock:
        yield mock


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock]:
    """Mock run_operation"""
    with patch("mega_snake.gcloud.parse_instances_deployment_id.run_operation") as mock:
        yield mock


@pytest.fixture(name="ws_advice")
def fixture_ws_advice() -> Generator[MagicMock]:
    """Mock ws_advice"""
    with patch("mega_snake.gcloud.parse_instances_deployment_id.ws_advice") as mock:
        yield mock


@pytest.fixture(name="ws_success")
def fixture_formatting_ws_success() -> Generator[MagicMock]:
    """Mock ws_success"""
    with patch("mega_snake.gcloud.parse_instances_deployment_id.ws_success") as mock:
        mock.return_value = None
        yield mock


def test_bq_instances_by_deployment_id_missing_args(
    ws_advice: MagicMock, run_operation: MagicMock, ws_success: MagicMock, pyperclip_copy: MagicMock
) -> None:
    """Test with missing arguments"""

    def re_mocks() -> None:
        """Reset the mocks."""
        reset_mocks(ws_advice, run_operation, ws_success, pyperclip_copy)

    runner = CliRunner()
    result = runner.invoke(bq_instances_by_deployment_id, [])
    assert result.exit_code != 0
    assert "Missing argument" in result.output
    ws_advice.assert_not_called()
    run_operation.assert_not_called()
    ws_success.assert_not_called()
    pyperclip_copy.assert_not_called()
    re_mocks()
    result = runner.invoke(bq_instances_by_deployment_id, ["project"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output
    ws_advice.assert_not_called()
    run_operation.assert_not_called()
    ws_success.assert_not_called()
    pyperclip_copy.assert_not_called()


def test_bq_instances_by_deployment_id_success(
    ws_advice: MagicMock, run_operation: MagicMock, ws_success: MagicMock, pyperclip_copy: MagicMock
) -> None:
    """Test with success"""

    runner = CliRunner()
    other_project: str = "other-project"

    def re_mocks() -> None:
        """Reset the mocks."""
        reset_mocks(ws_advice, run_operation, ws_success, pyperclip_copy)

    # Test with one deployment id
    result = runner.invoke(bq_instances_by_deployment_id, [other_project, "deployment_id"])
    assert result.exit_code == 0
    assert result.exception is None
    assert ws_advice.call_count == 2
    run_operation.assert_called_once()
    ws_success.assert_called_once()
    pyperclip_copy.assert_called_once()

    # Test with multiple deployment ids
    re_mocks()
    result = runner.invoke(bq_instances_by_deployment_id, [other_project, "deployment_id1", "deployment_id2"])
    assert result.exit_code == 0
    assert result.exception is None
    assert ws_advice.call_count == 4
    assert run_operation.call_count == 2
    ws_success.assert_called_once()
    pyperclip_copy.assert_called_once()


def test_bq_instances_by_deployment_id_failure(
    ws_advice: MagicMock, run_operation: MagicMock, ws_success: MagicMock, pyperclip_copy: MagicMock
) -> None:
    """Test with failure"""

    runner = CliRunner()
    other_project: str = "other-project"

    def re_mocks() -> None:
        """Reset the mocks."""
        reset_mocks(ws_advice, run_operation, ws_success, pyperclip_copy)

    # Test with one deployment id
    run_operation.side_effect = Exception("Error")
    result = runner.invoke(bq_instances_by_deployment_id, [other_project, "deployment_id"], catch_exceptions=True)
    assert result.exit_code != 0
    assert not result.output
    assert not result.stdout
    assert result.exception
    ws_advice.assert_not_called()
    run_operation.assert_called_once()
    ws_success.assert_not_called()
    pyperclip_copy.assert_not_called()

    # Test with multiple deployment ids
    re_mocks()
    run_operation.side_effect = Exception("Error")
    result = runner.invoke(bq_instances_by_deployment_id, [other_project, "deployment_id1", "deployment_id2"])
    assert result.exit_code != 0
    assert not result.output
    assert not result.stdout
    assert result.exception
    ws_advice.assert_not_called()
    run_operation.assert_called_once()
    ws_success.assert_not_called()
    pyperclip_copy.assert_not_called()
