"""Test for VscodeTask model"""

from typing import Generator
from unittest.mock import patch, MagicMock
import pytest
from codename_snake.config_environment.models.vscode_task import VscodeTask, TASKS_VERSION_QUERY

VERSION_TEST = "1.2.3"


@pytest.fixture(name="jq")
def fixture_jq() -> Generator[MagicMock]:
    """Mock jq"""
    with patch("codename_snake.config_environment.models.vscode_task.jq") as mock:

        yield mock


@pytest.fixture(name="json")
def fixture_json() -> Generator[MagicMock]:
    """Mock json"""
    with patch("codename_snake.config_environment.models.vscode_task.json") as mock:
        yield mock


# Test direct enum access
def test_enum_members() -> None:
    """Test the enum members"""
    # iterate over the enum members and check if they have the mandatory attributes
    assert len(VscodeTask) > 0
    for member in VscodeTask:
        assert member.label
        assert member.hidden is not None
        assert member.detail
        assert member.args is not None
        assert member.problem_matcher is not None
        assert member.extra_args is not None


def test_add_logger_args() -> None:
    """Test add_logger_args"""
    for member in [t for t in VscodeTask if t.watcher]:
        args_size = len(member.args)
        mock = MagicMock()
        mock.return_value = "mocked log path"
        member.watcher.get_pattern_date = mock
        member.add_logger_args("path/to/working")
        mock.assert_called_once()
        assert len(member.args) == args_size + 3


def test_to_dict() -> None:
    """Test to_dict"""
    param = "path/to/working"
    for member in VscodeTask:
        mock = MagicMock()
        member.add_logger_args = mock
        result = member.to_dict(param)
        mock.assert_called_once_with(param)
        assert result["label"] == member.label
        assert result["hide"] == member.hidden
        assert result["detail"] == member.detail
        assert result["problemMatcher"] == member.problem_matcher
        if member.task_type:
            assert result["type"] == member.task_type
        if member.command:
            assert result["command"] == member.command
        if member.args:
            assert result["args"] == member.args
        for key, value in member.extra_args.items():
            assert result[key] == value


def test_add_tasks_version() -> None:
    """Test add_tasks_version"""

    def get_data() -> dict[str, str]:
        """Return a copy of the data"""
        return {"tasks": {"tasks": [{"label": "task1"}, {"label": "task2"}]}}

    # Test when the query is found
    prop_tag = TASKS_VERSION_QUERY.rsplit(".", maxsplit=1)[-1]
    for member in VscodeTask:
        data = get_data()
        result = member.add_tasks_version(data)
        assert result
        assert prop_tag in result["tasks"]
        data = get_data()
        data["tasks"][prop_tag] = VERSION_TEST
        result = member.add_tasks_version(data)
        assert result is None


def test_add_tasks_task() -> None:
    """Test add_tasks_task"""
    working_path = "path/to/working"

    def _get_data_copy() -> dict[str, str]:
        return {"tasks": {"tasks": [{"label": "task1"}, {"label": "task2"}]}}

    # Test when the query is found
    for member in VscodeTask:
        jd = _get_data_copy()
        jd["tasks"]["tasks"].append({"label": member.label})
        tasks_found: list[dict[str, str]] = [d for d in jd["tasks"]["tasks"] if d["label"] == member.label]
        assert len(tasks_found) == 1
        result = member.add_tasks_task(jd, working_path)
        assert result is None

    # Test when the query is not found
    for member in VscodeTask:
        jd = _get_data_copy()
        tasks_found: list[dict[str, str]] = [d for d in jd["tasks"]["tasks"] if d["label"] == member.label]
        assert not tasks_found
        result = member.add_tasks_task(jd, working_path)
        tasks_found = [d for d in result["tasks"]["tasks"] if d["label"] == member.label]
        assert tasks_found

    # Test when the query is found but has multiple entries
    for member in VscodeTask:
        jd = _get_data_copy()
        jd["tasks"]["tasks"].append({"label": member.label})
        jd["tasks"]["tasks"].append({"label": member.label})
        tasks_found: list[dict[str, str]] = [d for d in jd["tasks"]["tasks"] if d["label"] == member.label]
        assert len(tasks_found) == 2
        result = member.add_tasks_task(jd, working_path)
        tasks_found = [d for d in result["tasks"]["tasks"] if d["label"] == member.label]
        assert tasks_found
