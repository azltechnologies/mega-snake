"""Test for VscodeLaunch model"""

from pathlib import Path
from typing import Generator, Union
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

# What the patched `_logger_args` returns in `test_to_dict`. Deliberately non-empty: an empty stub is
# what an implementation that never calls the builder would also produce, so it could not tell a
# composed `args` from one that forgot the redirect.
LOGGER_ARGS_STUB: list[str] = [">", "'stub.log'", "2>&1"]
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


def test_logger_args_renders_the_redirect_without_touching_the_member() -> None:
    """`_logger_args` returns the redirect but never writes it back onto the enum member.

    `self` is an enum member, i.e. a process-wide singleton, so a builder that appended to
    `self.args` would permanently mutate it for every other caller. This pins that `_logger_args`
    is a pure function of its argument: it returns the redirect, and `member.args` is unchanged
    before and after the call, for members with and without a watcher.
    """
    for member in VscodeLaunch:
        args_before = list(member.args)
        if member.watcher:
            mock = MagicMock()
            mock.return_value = "mocked log path"
            with patch.object(member.watcher, "get_pattern_date", mock):
                result = member._logger_args("path/to/working")  # pylint: disable=protected-access
                mock.assert_called_once_with("path/to/working")
            assert result == "mocked log path".split(" ")
        else:
            result = member._logger_args("path/to/working")  # pylint: disable=protected-access
            assert result == []
        assert member.args == args_before, f"{member.name}.args was mutated by _logger_args"


def test_to_dict_emits_the_redirect_once_however_often_it_is_called() -> None:
    """Calling `to_dict()` twice on the same member must not carry the first redirect into the second.

    `to_dict` used to call `add_logger_args`, which appended the redirect onto the enum member's
    own `args` list -- a process-wide singleton -- so a second call appended it a second time. The
    two calls use different working paths, so a redirect left behind by the first one is a distinct
    value in the second emission, and each emission is compared by equality against the declared
    args followed by the redirect of its own call -- joined into one string for `debugpy`.
    """
    first_path, second_path = "path/to/first", "path/to/second"
    watched = [t for t in VscodeLaunch if t.watcher]
    assert watched, "no launch configuration has a watcher, so this test walks nothing"
    assert any(t.task_type == "debugpy" for t in watched), "the joined-args branch is not walked"
    for member in watched:
        declared_args: list[str] = list(member.args)
        first_redirect: list[str] = member.watcher.get_pattern_date(first_path).split(" ")
        second_redirect: list[str] = member.watcher.get_pattern_date(second_path).split(" ")
        first_expected: list[str] = [*declared_args, *first_redirect]
        second_expected: list[str] = [*declared_args, *second_redirect]
        if member.task_type == "debugpy":
            first_expected_value: Union[str, list[str]] = " ".join(first_expected)
            second_expected_value: Union[str, list[str]] = " ".join(second_expected)
        else:
            first_expected_value, second_expected_value = first_expected, second_expected

        first_args = member.to_dict(first_path)["args"]
        second_args = member.to_dict(second_path)["args"]

        assert first_args == first_expected_value, f"{member.name} emitted {first_args}"
        assert second_args == second_expected_value, f"{member.name} emitted {second_args}"
        assert first_redirect[1] not in second_args, f"{member.name} kept the first call's redirect"
        assert member.args == declared_args, f"{member.name}.args was mutated by to_dict()"


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
        mock = MagicMock(return_value=list(LOGGER_ARGS_STUB))
        # `fake_launch` is a bare SimpleNamespace, so it has no `_logger_args` of its own to
        # save and restore -- `create=True` lets patch.object add it for the block and delete it
        # again on exit, instead of leaving it stuck on the object for later tests to trip over.
        with patch.object(member, "_logger_args", mock, create=True):
            result = member.to_dict(param)
            mock.assert_called_once_with(param)
        assert result["name"] == member.task_name
        assert result["type"] == member.task_type
        assert result["request"] == member.request
        if member.env:
            assert result["env"] == member.env
        # `args` is composed: the member's own args followed by the redirect, never `member.args` alone
        expected_args: list[str] = [*member.args, *LOGGER_ARGS_STUB]
        if member.task_type == "debugpy":
            assert result["args"] == " ".join(expected_args), f"{member.name} did not compose its args"
        else:
            assert result["args"] == expected_args, f"{member.name} did not compose its args"
        for key, value in member.extra_args.items():
            assert result[key] == value
        # the stack only decides whether the configuration is written, it is not part of it
        assert "stack" not in result


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
        jd = _get_data_copy()
        tasks_found: list[dict[str, str]] = [
            d for d in jd["launch"][LAUNCH_TEST_SETTING] if d["name"] == inst.task_name
        ]
        assert not tasks_found
        # Patched for the call only: `inst` is an enum member, so assigning `inst.to_dict` would
        # leave the mock on the singleton for every test that runs afterwards.
        with patch.object(inst, "to_dict", to_dict):
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
        jd = _get_data_copy()
        jd["launch"][LAUNCH_TEST_SETTING].append({"name": inst.task_name})
        jd["launch"][LAUNCH_TEST_SETTING].append({"name": inst.task_name})
        tasks_found: list[dict[str, str]] = [
            d for d in jd["launch"][LAUNCH_TEST_SETTING] if d["name"] == inst.task_name
        ]
        assert len(tasks_found) == 2
        with patch.object(inst, "to_dict", to_dict):
            result = inst.add_launch_config(jd, substituter, working_path)
        tasks_found = [d for d in result["launch"][LAUNCH_TEST_SETTING] if d["name"] == inst.task_name]
        assert tasks_found
        assert len(tasks_found) == 1
        substituter.assert_called_once()
        assert tasks_found[0]["name"] == inst.task_name
        substituter.reset_mock()
