"""Test for LogViewerWatcher"""

from typing import Generator
from unittest.mock import patch, MagicMock
import inspect
import pytest
from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher, SUBSTITUTE_LOG_DATE_TAG

DATE_PATTERN = "_YYYY-MM-DD"
LOG_TEST_SETTING = "logViewer.tests"
LOG_TEST_QUERY = f'.settings.["{LOG_TEST_SETTING}"]'
DICT_RESULT = {"title": "my title", "pattern": "my pattern", "autoScroll": True}


def dict_side_effect(instance: LogWatcher, _wk: str) -> dict[str, str]:
    """Side effect for jq.compile"""
    command_signature = inspect.signature(LogWatcher.__init__).parameters
    result = {}
    for k in (k for k, _p in command_signature.items() if k != "self"):
        result[k] = vars(instance)[k]
    return result



@pytest.fixture(name="get_input_call")
def fixture_bget_input_call() -> Generator[MagicMock]:
    """Mock get_input_call"""
    with patch(
        "mega_snake.config_environment.models.log_viewer_watcher.VscodeInput.TODAY_TIMESTAMP.get_input_call"
    ) as mock:
        mock.return_value = DATE_PATTERN
        yield mock


@pytest.fixture(name="_log_watcher_query")
def fixture_log_watcher_query() -> Generator[MagicMock]:
    """Mock log_watcher_query"""
    with patch(
        "mega_snake.config_environment.models.log_viewer_watcher.LOG_WATCHER_QUERY", LOG_TEST_QUERY
    ) as mock:
        yield mock


@pytest.fixture(name="to_dict")
def fixture_to_dict() -> Generator[MagicMock]:
    """Mock to_dict"""
    with patch.object(LogWatcher,"to_dict") as mock:
        dicto = mock.call_args_list
        mock.return_value = dicto
        yield mock


def test_to_dict() -> None:
    """Test to_dict"""
    param = "path/to/working"
    for member in LogWatcher:
        result = member.to_dict(param)
        assert result["title"] == member.title
        assert result["pattern"] == f"{param}/{member.pattern}"
        assert result["autoScroll"] is True


def test_get_pattern_date(get_input_call: MagicMock) -> None:
    """Test get_pattern_date"""
    param = "path/to/working"
    for member in LogWatcher:
        result = member.get_pattern_date(param)
        assert result == f"> '{param}/{member.pattern.replace(SUBSTITUTE_LOG_DATE_TAG, f'_{DATE_PATTERN}.log')}' 2>&1"
        get_input_call.assert_called_once()
        get_input_call.reset_mock()


def test_add_watcher(_log_watcher_query: MagicMock) -> None:
    """Test add_tasks_task"""
    working_path = "path/to/working"

    def _get_data_copy() -> dict[str, str]:
        return {"settings": {LOG_TEST_SETTING: [{"title": "task1"}, {"title": "task2"}]}}

    # Test when the pattern is found
    for inst in LogWatcher:
        jd = _get_data_copy()
        jd["settings"][LOG_TEST_SETTING].append({"title": inst.title})
        tasks_found: list[dict[str, str]] = [d for d in jd["settings"][LOG_TEST_SETTING] if d["title"] == inst.title]
        assert len(tasks_found) == 1
        result = inst.add_watcher(jd, working_path)
        assert result is None

    # Test when the pattern is not found
    for inst in LogWatcher:
        to_dict:MagicMock = MagicMock(side_effect=lambda wk, inst=inst: dict_side_effect(inst, wk))
        inst.to_dict = to_dict
        jd = _get_data_copy()
        tasks_found: list[dict[str, str]] = [d for d in jd["settings"][LOG_TEST_SETTING] if d["title"] == inst.title]
        assert not tasks_found
        result = inst.add_watcher(jd, working_path)
        tasks_found = [d for d in result["settings"][LOG_TEST_SETTING] if d["title"] == inst.title]
        assert tasks_found
        assert len(tasks_found) == 1
        to_dict.assert_called_once_with(working_path)
        assert tasks_found[0]["title"] == inst.title
        assert tasks_found[0]["pattern"] == inst.pattern

    # Test when the pattern is found but has multiple entries
    for inst in LogWatcher:
        to_dict:MagicMock = MagicMock(side_effect=lambda wk, inst=inst: dict_side_effect(inst, wk))
        inst.to_dict = to_dict
        jd = _get_data_copy()
        jd["settings"][LOG_TEST_SETTING].append({"title": inst.title})
        jd["settings"][LOG_TEST_SETTING].append({"title": inst.title})
        tasks_found: list[dict[str, str]] = [d for d in jd["settings"][LOG_TEST_SETTING] if d["title"] == inst.title]
        assert len(tasks_found) == 2
        result = inst.add_watcher(jd, working_path)
        tasks_found = [d for d in result["settings"][LOG_TEST_SETTING] if d["title"] == inst.title]
        assert tasks_found
        assert len(tasks_found) == 1
        to_dict.assert_called_once_with(working_path)
        assert tasks_found[0]["title"] == inst.title
        assert tasks_found[0]["pattern"] == inst.pattern
