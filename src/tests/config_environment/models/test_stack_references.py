"""Invariants over the references the workspace artifacts make to each other.

The stack tagging is a graph, not a set of independent labels: a task redirects into a `LogWatcher`,
depends on other tasks by label, and calls a `VscodeInput` through `${input:<id>}`; a launch depends
on tasks and carries a watcher of its own. Every one of those referents is filtered by *its own*
stack, so a member tagged with a stack that does not activate its referent produces a workspace with
a dangling reference — a `dependsOn` naming a task that was never written, or a redirect into a
watcher that was filtered out. VS Code reports that only when the developer runs the entry.

These tests walk the whole universe instead of sampling the tags that happen to exist today.
"""

import re

from mega_snake.config_environment.models.log_viewer_watcher import LogWatcher
from mega_snake.config_environment.models.project_stack import ProjectStack, resolve_stacks
from mega_snake.config_environment.models.vscode_input import VscodeInput
from mega_snake.config_environment.models.vscode_launch import VscodeLaunch
from mega_snake.config_environment.models.vscode_task import VscodeTask

INPUT_CALL_PATTERN = re.compile(r"\$\{input:([^}]+)\}")


def _activated_by(stack: ProjectStack) -> set[ProjectStack]:
    """Resolve everything a workspace gets when the given stack is the only one selected."""
    if stack is ProjectStack.COMMON:
        return {ProjectStack.COMMON}
    return resolve_stacks([stack.key])


def _owner_of_label(label: str) -> VscodeTask:
    """Find the task a `dependsOn` entry names.

    Parameters:
        label: The task label as it appears in the workspace file.

    Raises:
        AssertionError: If no task declares that label.

    Returns:
        VscodeTask: The task that owns the label.
    """
    for task in VscodeTask:
        if task.label == label:
            return task
    raise AssertionError(f"dependsOn names '{label}', which no VscodeTask declares")


def test_task_watchers_stay_inside_their_own_stacks() -> None:
    """A task never redirects into a watcher its own stack does not activate."""
    for task in VscodeTask:
        if not task.watcher:
            continue
        active: set[ProjectStack] = _activated_by(task.stack)
        assert task.watcher.stack in active, (
            f"{task.name} ({task.stack}) redirects into {task.watcher.name} ({task.watcher.stack}), "
            f"which is not written for its stack"
        )


def test_task_dependencies_stay_inside_their_own_stacks() -> None:
    """A task never depends on a task its own stack does not activate."""
    for task in VscodeTask:
        active: set[ProjectStack] = _activated_by(task.stack)
        for label in task.extra_args.get("dependsOn", []):
            owner: VscodeTask = _owner_of_label(label)
            assert owner.stack in active, (
                f"{task.name} ({task.stack}) dependsOn '{label}' ({owner.stack}), "
                f"which is not written for its stack"
            )


def test_task_input_calls_stay_inside_their_own_stacks() -> None:
    """A task never calls an input its own stack does not activate."""
    inputs_by_id: dict[str, VscodeInput] = {member.input_id: member for member in VscodeInput}
    for task in VscodeTask:
        active: set[ProjectStack] = _activated_by(task.stack)
        text: str = " ".join([task.command or "", *task.args])
        for input_id in INPUT_CALL_PATTERN.findall(text):
            assert input_id in inputs_by_id, f"{task.name} calls '${{input:{input_id}}}', which no VscodeInput declares"
            referenced: VscodeInput = inputs_by_id[input_id]
            assert referenced.stack in active, (
                f"{task.name} ({task.stack}) calls '${{input:{input_id}}}' ({referenced.stack}), "
                f"which is not written for its stack"
            )


def test_launch_references_stay_inside_their_own_stacks() -> None:
    """A launch configuration never depends on a task, or redirects into a watcher, its stack skips."""
    for launch in VscodeLaunch:
        active: set[ProjectStack] = _activated_by(launch.stack)
        for task in launch.depends_on:
            assert task.stack in active, (
                f"{launch.name} ({launch.stack}) dependsOn {task.name} ({task.stack}), "
                f"which is not written for its stack"
            )
        if launch.watcher:
            assert launch.watcher.stack in active, (
                f"{launch.name} ({launch.stack}) redirects into {launch.watcher.name} "
                f"({launch.watcher.stack}), which is not written for its stack"
            )


def test_watcher_patterns_are_unique_per_stack() -> None:
    """Two watchers never claim the same log pattern, which would make one of them unreachable."""
    seen: dict[str, LogWatcher] = {}
    for watcher in LogWatcher:
        clash = seen.get(watcher.pattern)
        assert clash is None, f"{watcher.name} reuses the pattern of {clash.name if clash else ''}: {watcher.pattern}"
        seen[watcher.pattern] = watcher
