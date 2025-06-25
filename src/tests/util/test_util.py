"""Test cases for util.py"""

import builtins
import os
from unittest.mock import MagicMock, patch, mock_open
from typing import Generator, Callable
from types import SimpleNamespace
import pytest
from tests.test_util.util_test import param_injector, get_mock
from tests.test_util.side_effect_wrapper import SideEffectWrapper
from codename_snake.util.util import (
    load_json_with_comments
)
from codename_snake.constants import LOGGING_NAME_TO_LEVEL


def test_load_json_with_comments() -> None:
    """Test load_json_with_comments function."""
    m_open: MagicMock = mock_open()
    file_mock: MagicMock = m_open.return_value
    read_mock: MagicMock = file_mock.read
    read_mock.return_value = '{"key": "value"}'
    expected_result = {"key": "value"}

    with patch("builtins.open", m_open):
        result = load_json_with_comments("dummy_path")

    assert result == expected_result

    # Test empty file
    read_mock.return_value = ""
    expected_result = {}
    with patch("builtins.open", m_open):
        result = load_json_with_comments("dummy_path")
    assert result == expected_result
