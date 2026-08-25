"""Test for VscodeTask model"""

from typing import Any, Generator
from unittest.mock import patch, MagicMock
import pytest
from mega_snake.config_environment.models.project_stack import ProjectStack
from mega_snake.config_environment.models.vscode_task import VscodeTask, TASKS_VERSION_QUERY

VERSION_TEST = "1.2.3"


@pytest.fixture(name="jq")
def fixture_jq() -> Generator[MagicMock, None, None]:
    """Mock jq"""
    with patch("mega_snake.config_environment.models.vscode_task.jq") as mock:

        yield mock


@pytest.fixture(name="json")
def fixture_json() -> Generator[MagicMock, None, None]:
    """Mock json"""
    with patch("mega_snake.config_environment.models.vscode_task.json") as mock:
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
        assert isinstance(member.stack, ProjectStack)


def test_stack() -> None:
    """Test that every task belongs to a JVM stack, so none is written for other projects"""
    # every task shipped today drives Gradle, Maven or a Java process
    assert not [member for member in VscodeTask if member.stack is ProjectStack.COMMON]
    assert VscodeTask.GRADLE_BUILD.stack is ProjectStack.GRADLE
    assert VscodeTask.JAVA_REMOTE_DEBUG.stack is ProjectStack.JAVA
    assert VscodeTask.MAVEN_CLEAN_INSTALL.stack is ProjectStack.MAVEN
    # the debug pipeline depends on the Gradle build tasks, so it belongs to the Gradle stack
    for member in (VscodeTask.DEBUG_BUILD, VscodeTask.DEBUG_BUILD_NO_TEST, VscodeTask.DEBUG_NO_BUILD):
        assert member.stack is ProjectStack.GRADLE
    assert VscodeTask.RUN_JAVA_DEBUG.stack is ProjectStack.GRADLE


def test_logger_args() -> None:
    """The redirect is returned, never appended to the member's own args."""
    for member in VscodeTask:
        declared: list[str] = list(member.args)
        if member.watcher:
            mock = MagicMock(return_value="> 'mocked log path' 2>&1")
            with patch.object(member.watcher, "get_pattern_date", mock):
                result: list[str] = member.logger_args("path/to/working")
                mock.assert_called_once_with("path/to/working")
            assert result == [">", "'mocked", "log", "path'", "2>&1"]
        else:
            assert member.logger_args("path/to/working") == []
        assert member.args == declared, f"{member.name} mutated its own args"


def test_to_dict_is_repeatable() -> None:
    """Two `to_dict` calls on the same member emit the redirect exactly once each."""
    member: VscodeTask = VscodeTask.GRADLE_BUILD
    assert member.watcher, "this test needs a task that actually redirects into a watcher"
    declared: list[str] = list(member.args)
    expected: list[str] = [*declared, *member.watcher.get_pattern_date("wp").split(" ")]

    first: dict[str, Any] = member.to_dict("wp")
    second: dict[str, Any] = member.to_dict("wp")

    assert first == second
    assert first["args"] == expected
    assert first["args"].count("2>&1") == 1
    assert member.args == declared, "to_dict wrote the redirect back into the enum member"

    first["args"].append("polluted")
    assert member.args == declared
    assert member.to_dict("wp")["args"] == expected


def test_to_dict() -> None:
    """Test to_dict"""
    param = "path/to/working"
    for member in VscodeTask:
        mock = MagicMock(return_value=[])
        with patch.object(member, "logger_args", mock):
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
        # the stack only decides whether the task is written, it is not part of the task definition
        assert "stack" not in result


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
