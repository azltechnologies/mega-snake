"""Test for VscodeInput"""

from typing import Generator
from types import SimpleNamespace, MethodType
import inspect
from unittest.mock import patch, MagicMock
import pytest
from codename_snake.config_environment.models.vscode_input import VscodeInput

INPUT_TEST_SETTING = "inputTests"
INPUT_TEST_QUERY = f'.launch.["{INPUT_TEST_SETTING}"]'


def dict_side_effect(instance: VscodeInput) -> dict[str, str]:
    """Side effect for jq.compile"""
    command_signature = inspect.signature(VscodeInput.__init__).parameters
    result = {}
    for k in (k for k, _p in command_signature.items() if k != "self" and _p.annotation.__name__ == "str"):
        result[k.replace("input_", "")] = vars(instance)[k]
    return result


@pytest.fixture(name="vscode_task")
def fixture_vscode_task() -> Generator[MagicMock]:
    """Mock VscodeTask"""
    with patch("codename_snake.config_environment.models.vscode_input.VscodeTask") as mock:
        yield mock


def test_to_dict() -> None:
    """Test to_dict"""
    list_input: list[VscodeInput] = list(m for m in VscodeInput)
    fake_input = SimpleNamespace(
        input_id="fake_id",
        input_type="fake_type",
        input_command="fake_command",
        input_args={"fake": "args"},
        input_options=["fake", "options"],
        input_default="fake_default",
        input_description="fake_description",
    )
    fake_input.to_dict = MethodType(VscodeInput.to_dict, fake_input)
    list_input.append(fake_input)
    for member in list_input:
        result = member.to_dict()
        assert result["id"] == member.input_id
        assert result["type"] == member.input_type
        if member.input_command:
            assert result["command"] == member.input_command
        if member.input_args:
            assert result["args"] == member.input_args
        if member.input_options:
            assert result["options"] == member.input_options
        if member.input_default:
            assert result["default"] == member.input_default
        if member.input_description:
            assert result["description"] == member.input_description


def test_get_input_call() -> None:
    """Test get_input_call"""
    for member in VscodeInput:
        result = member.get_input_call()
        assert result == f"${{input:{member.input_id}}}"


def test_add_task_arg() -> None:
    """Test add_task_arg"""
    list_input: list[VscodeInput] = list(m for m in VscodeInput)
    fake_input = SimpleNamespace(
        input_id="fake_id",
        input_type="fake_type",
        input_command="fake_command",
        input_args=None,
        input_options=["fake", "options"],
        input_default="fake_default",
        input_description="fake_description",
    )
    fake_input.add_task_arg = MethodType(VscodeInput.add_task_arg, fake_input)
    list_input.append(fake_input)
    for member in list_input:
        task = MagicMock()
        member.add_task_arg(task)
        assert member.input_args["task"] == task.label


def test_add_tasks_input() -> None:
    """Test add_tasks_input"""

    def _get_data_copy() -> dict[str, str]:
        return {"launch": {INPUT_TEST_SETTING: [{"id": "task1"}, {"id": "task2"}]}}

    # Test when the pattern is found
    for inst in VscodeInput:
        jd = _get_data_copy()
        jd["launch"][INPUT_TEST_SETTING].append({"id": inst.input_id})
        tasks_found: list[dict[str, str]] = [d for d in jd["launch"][INPUT_TEST_SETTING] if d["id"] == inst.input_id]
        assert len(tasks_found) == 1
        result = inst.add_tasks_input(jd, INPUT_TEST_QUERY)
        assert result is None

    # Test when the pattern is not found
    for inst in VscodeInput:
        to_dict: MagicMock = MagicMock(side_effect=lambda inst=inst: dict_side_effect(inst))
        inst.to_dict = to_dict
        jd = _get_data_copy()
        tasks_found: list[dict[str, str]] = [d for d in jd["launch"][INPUT_TEST_SETTING] if d["id"] == inst.input_id]
        assert not tasks_found
        result = inst.add_tasks_input(jd, INPUT_TEST_QUERY)
        tasks_found = [d for d in result["launch"][INPUT_TEST_SETTING] if d["id"] == inst.input_id]
        assert tasks_found
        assert len(tasks_found) == 1
        to_dict.assert_called_once_with()
        assert tasks_found[0]["id"] == inst.input_id

    # Test when the pattern is found but has multiple entries
    for inst in VscodeInput:
        to_dict: MagicMock = MagicMock(side_effect=lambda inst=inst: dict_side_effect(inst))
        inst.to_dict = to_dict
        jd = _get_data_copy()
        jd["launch"][INPUT_TEST_SETTING].append({"id": inst.input_id})
        jd["launch"][INPUT_TEST_SETTING].append({"id": inst.input_id})
        tasks_found: list[dict[str, str]] = [d for d in jd["launch"][INPUT_TEST_SETTING] if d["id"] == inst.input_id]
        assert len(tasks_found) == 2
        result = inst.add_tasks_input(jd, INPUT_TEST_QUERY)
        tasks_found = [d for d in result["launch"][INPUT_TEST_SETTING] if d["id"] == inst.input_id]
        assert tasks_found
        assert len(tasks_found) == 1
        assert tasks_found[0]["id"] == inst.input_id
