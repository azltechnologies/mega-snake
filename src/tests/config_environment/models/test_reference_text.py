"""Test for reference_text"""

from types import SimpleNamespace
from mega_snake.config_environment.models.reference_text import INPUT_CALL_PATTERN, reference_text

PROBE_PATH = "workspace_temp"


def test_reference_text_reaches_env() -> None:
    """The `env` field is scanned like every other field: no real VscodeLaunch member has an `env`
    entry that matches `${input:...}`, so nothing would notice if this branch stopped being read.
    """
    member = SimpleNamespace(
        args=[],
        extra_args={},
        watcher=None,
        env={"SOME_VAR": "${input:todayTimestamp}"},
    )
    assert INPUT_CALL_PATTERN.findall(reference_text(member, PROBE_PATH)) == ["todayTimestamp"]


def test_reference_text_tolerates_a_member_without_command_or_env() -> None:
    """VscodeLaunch has no `command`; VscodeTask has no `env` -- both must flatten without raising."""
    launch_like = SimpleNamespace(args=["${input:from_args}"], extra_args={}, watcher=None)
    assert reference_text(launch_like, PROBE_PATH) == "${input:from_args}"

    task_like = SimpleNamespace(command="${input:from_command}", args=[], extra_args={}, watcher=None)
    assert reference_text(task_like, PROBE_PATH) == "${input:from_command}"


def test_reference_text_reaches_problem_matcher() -> None:
    """`problem_matcher` is emitted verbatim by `to_dict`, so it is a reference site like any other.

    No task ships a non-empty one today, which is exactly why the field has to be pinned here: the
    whole-graph invariant in `test_stack_references.py` reads the same flattened text, so a blind
    spot in this function is a blind spot in that test too.
    """
    member = SimpleNamespace(
        command=None,
        args=[],
        extra_args={},
        watcher=None,
        problem_matcher=[{"fileLocation": "${input:selectBuildTask}"}],
    )
    assert INPUT_CALL_PATTERN.findall(reference_text(member, PROBE_PATH)) == ["selectBuildTask"]
