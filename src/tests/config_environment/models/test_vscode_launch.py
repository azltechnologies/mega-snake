"""Test for VscodeLaunch model"""

from pathlib import Path
from typing import Any, Generator
from types import SimpleNamespace, MethodType
import inspect
from unittest.mock import patch, MagicMock
import pytest
from mega_snake.config_environment.models.project_stack import (
    ProjectStack,
    SNAKE_MARKER,
    detect_stacks,
    filter_by_stack,
    resolve_stacks,
)
from mega_snake.config_environment.models.vscode_launch import VscodeLaunch, LAUNCH_VERSION_QUERY

VERSION_TEST = "1.2.3"
LAUNCH_TEST_SETTING = "configtests"
LAUNCH_TEST_QUERY = f'.launch.["{LAUNCH_TEST_SETTING}"]'


def dict_side_effect(instance: VscodeLaunch, _wk: str) -> dict[str, str]:
    """Side effect for jq.compile"""
    command_signature = inspect.signature(VscodeLaunch.__init__).parameters
    result = {}
    for k in (k for k, _p in command_signature.items() if k != "self" and _p.annotation.__name__ == "str"):
        result[k.replace("task_","")] = vars(instance)[k]
    return result


@pytest.fixture(name="_launch_config_query")
def fixture_launch_config_query() -> Generator[MagicMock, None, None]:
    """Mock launch_config_query"""
    with patch(
        "mega_snake.config_environment.models.vscode_launch.LAUNCH_CONFIG_QUERY", LAUNCH_TEST_QUERY
    ) as mock:
        yield mock


def test_add_launch_version() -> None:
    """Test add_launch_version"""

    def get_data() -> dict[str, str]:
        """Return a copy of the data"""
        return {"launch": {"configurations": [{"name": "task1"}, {"name": "task2"}]}}

    prop_tag = LAUNCH_VERSION_QUERY.rsplit(".", maxsplit=1)[-1]
    for member in VscodeLaunch:
        data = get_data()
        result = member.add_launch_version(data)
        assert result
        assert prop_tag in result["launch"]
        data = get_data()
        data["launch"][prop_tag] = VERSION_TEST
        result = member.add_launch_version(data)
        assert result is None


def test_logger_args() -> None:
    """The redirect is returned, never appended to the member's own args."""
    for member in VscodeLaunch:
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


def test_to_dict() -> None:
    """Test to_dict"""
    param = "path/to/working"

    list_launch = list(member for member in VscodeLaunch)
    sample: VscodeLaunch = next(m for m in VscodeLaunch if m.task_type == "debugpy")
    fake_launch = SimpleNamespace(**sample.__dict__)
    fake_launch.to_dict = MethodType(VscodeLaunch.to_dict, fake_launch)
    fake_launch.task_type = "fake"
    list_launch.append(fake_launch)
    for member in list_launch:
        mock = MagicMock(return_value=[])
        # `fake_launch` is a bare SimpleNamespace, so it has no `logger_args` of its own to
        # save and restore -- `create=True` lets patch.object add it for the block and delete it
        # again on exit, instead of leaving it stuck on the object for later tests to trip over.
        with patch.object(member, "logger_args", mock, create=True):
            result = member.to_dict(param)
            mock.assert_called_once_with(param)
        assert result["name"] == member.task_name
        assert result["type"] == member.task_type
        assert result["request"] == member.request
        if member.env:
            assert result["env"] == member.env
        if member.args:
            if member.task_type == "debugpy":
                assert result["args"] == " ".join(member.args)
            else:
                assert result["args"] == member.args
        for key, value in member.extra_args.items():
            assert result[key] == value
        # the stack only decides whether the configuration is written, it is not part of it
        assert "stack" not in result


def test_to_dict_is_repeatable() -> None:
    """Two `to_dict` calls on the same configuration emit the redirect exactly once each."""
    member: VscodeLaunch = VscodeLaunch.DEBUG_PYTHON_FILE
    assert member.watcher, "this test needs a configuration that actually redirects into a watcher"
    assert member.task_type == "debugpy", "this test exists to cover the joined-args branch"
    declared: list[str] = list(member.args)
    expected: str = " ".join([*declared, *member.watcher.get_pattern_date("wp").split(" ")])

    first: dict[str, Any] = member.to_dict("wp")
    second: dict[str, Any] = member.to_dict("wp")

    assert first == second
    assert first["args"] == expected
    assert first["args"].count("2>&1") == 1
    assert member.args == declared, "to_dict wrote the redirect back into the enum member"


def test_stack(tmp_path: Path) -> None:
    """Test that every launch configuration declares the stack it belongs to"""
    for member in VscodeLaunch:
        assert isinstance(member.stack, ProjectStack)
    # A launch configuration always debugs one language's runtime, so none of them may be common --
    # the same guard `VscodeTask.test_stack` makes, which this test was missing while
    # `VscodeLaunch.__init__` still defaulted `stack` to `ProjectStack.COMMON`
    assert not [member for member in VscodeLaunch if member.stack is ProjectStack.COMMON]
    assert VscodeLaunch.DEBUG_JAVA.stack is ProjectStack.JAVA
    for member in (VscodeLaunch.DEBUG_PYTHON_FILE, VscodeLaunch.DEBUG_PYTHON_MODULE):
        assert member.stack is ProjectStack.PYTHON
    # the launch that debugs mega-snake itself belongs to the opt-in development stack, so it never
    # reaches a user's Python project: the `python` selection alone must not pull it in
    assert VscodeLaunch.DEBUG_PYTHON_SNAKE.stack is ProjectStack.SNAKE
    assert VscodeLaunch.DEBUG_PYTHON_SNAKE not in filter_by_stack(VscodeLaunch, resolve_stacks(["python"]))
    assert VscodeLaunch.DEBUG_PYTHON_SNAKE not in filter_by_stack(VscodeLaunch, resolve_stacks(["all"]))
    # naming the key is refused too, so the marker file is genuinely the only way in -- which is
    # what actually keeps this launch configuration out of a user's repository
    with pytest.raises(ValueError, match="opt-in"):
        resolve_stacks([ProjectStack.SNAKE.key])
    (tmp_path / SNAKE_MARKER).write_text("", encoding="utf-8")
    assert VscodeLaunch.DEBUG_PYTHON_SNAKE in filter_by_stack(VscodeLaunch, detect_stacks(str(tmp_path)))


def test_add_launch_config(_launch_config_query: MagicMock) -> None:
    """Test add_tasks_task"""
    working_path = "path/to/working"

    def _get_data_copy() -> dict[str, str]:
        return {"launch": {LAUNCH_TEST_SETTING: [{"name": "task1"}, {"name": "task2"}]}}

    substituter:MagicMock = MagicMock( side_effect=lambda *args, **_kwargs: args[0])
    # Test when the pattern is found
    for inst in VscodeLaunch:
        jd = _get_data_copy()
        jd["launch"][LAUNCH_TEST_SETTING].append({"name": inst.task_name})
        tasks_found: list[dict[str, str]] = [
            d for d in jd["launch"][LAUNCH_TEST_SETTING] if d["name"] == inst.task_name
        ]
        assert len(tasks_found) == 1
        result = inst.add_launch_config(jd, substituter, working_path)
        assert result is None

    # Test when the pattern is not found
    for inst in VscodeLaunch:
        to_dict: MagicMock = MagicMock(side_effect=lambda wk, inst=inst: dict_side_effect(inst, wk))
        inst.to_dict = to_dict
        jd = _get_data_copy()
        tasks_found: list[dict[str, str]] = [
            d for d in jd["launch"][LAUNCH_TEST_SETTING] if d["name"] == inst.task_name
        ]
        assert not tasks_found
        result = inst.add_launch_config(jd, substituter, working_path)
        tasks_found = [d for d in result["launch"][LAUNCH_TEST_SETTING] if d["name"] == inst.task_name]
        assert tasks_found
        assert len(tasks_found) == 1
        to_dict.assert_called_once_with(working_path)
        substituter.assert_called_once()
        assert tasks_found[0]["name"] == inst.task_name
        substituter.reset_mock()

    # Test when the pattern is found but has multiple entries
    for inst in VscodeLaunch:
        to_dict: MagicMock = MagicMock(side_effect=lambda wk, inst=inst: dict_side_effect(inst, wk))
        inst.to_dict = to_dict
        jd = _get_data_copy()
        jd["launch"][LAUNCH_TEST_SETTING].append({"name": inst.task_name})
        jd["launch"][LAUNCH_TEST_SETTING].append({"name": inst.task_name})
        tasks_found: list[dict[str, str]] = [
            d for d in jd["launch"][LAUNCH_TEST_SETTING] if d["name"] == inst.task_name
        ]
        assert len(tasks_found) == 2
        result = inst.add_launch_config(jd, substituter, working_path)
        tasks_found = [d for d in result["launch"][LAUNCH_TEST_SETTING] if d["name"] == inst.task_name]
        assert tasks_found
        assert len(tasks_found) == 1
        substituter.assert_called_once()
        assert tasks_found[0]["name"] == inst.task_name
        substituter.reset_mock()
