"""Test the gcloud module"""

from types import SimpleNamespace
from typing import Generator
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
import pytest
from mega_snake.gcloud import module


@pytest.fixture(name="get_command_return_code")
def fixture_get_command_return_code() -> Generator[MagicMock]:
    """Mock get_command_return_code"""
    with patch("mega_snake.gcloud.module.get_command_return_code") as mock:
        mock.return_value = 0
        yield mock


@pytest.fixture(name="ws_advice")
def fixture_ws_advice() -> Generator[MagicMock]:
    """Mock ws_advice"""
    with patch("mega_snake.gcloud.module.ws_advice") as mock:
        yield mock


def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main)
    assert result.exit_code == 0
    assert "gcloud related commands" in result.output


def test_wrapper(get_command_return_code: MagicMock, ws_advice: MagicMock) -> None:
    """Test the wrapper function"""
    ctx = SimpleNamespace(obj={})
    module.wrapper(ctx)
    get_command_return_code.assert_called_once()
    ws_advice.assert_called_once()
    get_command_return_code.return_value = 1
    get_command_return_code.reset_mock()
    ws_advice.reset_mock()
    with pytest.raises(RuntimeError):
        module.wrapper(ctx)
    get_command_return_code.assert_called_once()
    ws_advice.assert_not_called()
