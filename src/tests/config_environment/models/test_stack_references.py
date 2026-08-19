"""Invariants over the references the workspace artifacts make to each other.

The stack tagging is a graph, not a set of independent labels: a task redirects into a `LogWatcher`,
depends on other tasks by label, and calls a `VscodeInput` through `${input:<id>}`; a launch depends
on tasks and carries a watcher of its own. Every one of those referents is filtered by *its own*
stack, so a member tagged with a stack that does not activate its referent produces a workspace with
a dangling reference — a `dependsOn` naming a task that was never written, or a redirect into a
watcher that was filtered out. VS Code reports that only when the developer runs the entry.

These tests walk the whole universe instead of sampling the tags that happen to exist today.
"""

import json
import re
from typing import Optional, Union

from mega_snake.config_environment.create_working_env import DEFAULT_PROPS
from mega_snake.config_environment.models.project_stack import ProjectStack, expand, resolve_stacks
from mega_snake.config_environment.models.vscode_input import VscodeInput
from mega_snake.config_environment.models.vscode_launch import REMOTE_DEBUG_PORT_QUERY, VscodeLaunch
from mega_snake.config_environment.models.vscode_task import VscodeTask

INPUT_CALL_PATTERN = re.compile(r"\$\{input:([^}]+)\}")
CONFIG_REF_PATTERN = re.compile(r"\$\{config:([^}]+)\}")

# Any path works: only the `${input:...}` the redirect interpolates is of interest, never the
# folder it is anchored to.
WATCHER_PROBE_PATH = "workspace_temp"

# Which stack writes each `.settings` key of DEFAULT_PROPS. `_update_input_props` filters that map by
# stack exactly like every artifact enum, so a `${config:…}` reference is a graph edge like any other
# -- it just points at a setting instead of at a task or a watcher.
PROP_OWNER: dict[str, ProjectStack] = {key: stack for stack, props in DEFAULT_PROPS.items() for key in props}


def _activated_by(stack: ProjectStack) -> set[ProjectStack]:
    """Resolve everything a workspace gets when the given stack is the only one that is active.

    An opt-in stack cannot be named on `--stack` -- `resolve_stacks` refuses the key outright -- so
    its entry point is the marker file, which activates the stack and everything it implies. The set
    is the same either way; only the door differs.
    """
    if stack is ProjectStack.COMMON:
        return {ProjectStack.COMMON}
    if stack.opt_in:
        return {ProjectStack.COMMON, *expand(stack)}
    return resolve_stacks([stack.key])


def _reference_text(member: Union[VscodeTask, VscodeLaunch]) -> str:
    """Join every field of a member that VS Code interpolates references out of.

    `extra_args` is included, and that is the point: `to_dict` emits it verbatim, so the Windows
    overrides on the Gradle build tasks (`{"windows": {"command": …, "args": …}}`) and a launch's
    `port`/`program` entries are as much a reference site as `command` is. Scanning only `command`
    and `args` left them outside the walk this module claims to be exhaustive.

    Parameters:
        member: The task or launch configuration to flatten.

    Returns:
        str: Every interpolatable field, joined; JSON for the nested ones so no value is lost.
    """
    parts: list[str] = [getattr(member, "command", None) or "", *getattr(member, "args", [])]
    for nested in (getattr(member, "extra_args", None), getattr(member, "env", None)):
        if nested:
            parts.append(json.dumps(nested))
    # The redirect a watcher builds is rendered, not stored. `add_logger_args` appends it to
    # `member.args` -- but it does so by mutating the enum member in place, from inside `to_dict()`,
    # so in a fresh process `args` does not contain it and the walk sees nothing. Calling `to_dict`
    # here would find it at the price of leaving that mutation behind for every later test in the
    # session; asking the watcher for the same string costs nothing and is order-independent.
    if getattr(member, "watcher", None):
        parts.append(member.watcher.get_pattern_date(WATCHER_PROBE_PATH))
    return " ".join(parts)


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
        for input_id in INPUT_CALL_PATTERN.findall(_reference_text(task)):
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


def test_launch_input_calls_stay_inside_their_own_stacks() -> None:
    """A launch configuration never calls an input its own stack does not activate."""
    inputs_by_id: dict[str, VscodeInput] = {member.input_id: member for member in VscodeInput}
    for launch in VscodeLaunch:
        active: set[ProjectStack] = _activated_by(launch.stack)
        for input_id in INPUT_CALL_PATTERN.findall(_reference_text(launch)):
            assert input_id in inputs_by_id, (
                f"{launch.name} calls '${{input:{input_id}}}', which no VscodeInput declares"
            )
            referenced: VscodeInput = inputs_by_id[input_id]
            assert referenced.stack in active, (
                f"{launch.name} ({launch.stack}) calls '${{input:{input_id}}}' ({referenced.stack}), "
                f"which is not written for its stack"
            )


def test_the_input_reference_walk_actually_sees_something() -> None:
    """The two input walks above are only meaningful while they really traverse something.

    `test_launch_input_calls_stay_inside_their_own_stacks` shipped green over an **empty loop**: no
    launch configuration carries a `${input:...}` in `command`/`args`/`extra_args`/`env` at import
    time, and the one edge that exists -- the watcher redirect -- reached `args` only because
    `add_logger_args` mutates the enum member in place from inside `to_dict()`. A test whose
    docstring promises an invariant while its body distinguishes no behaviour is the failure the
    sibling config guard was written to prevent, and it was reproduced here one test later.

    So both walks are pinned by the field they must reach, not merely by being non-empty: a count
    stays satisfied by whichever reference happens to survive a refactor.
    """
    def calls(member: Union[VscodeTask, VscodeLaunch]) -> list[str]:
        return INPUT_CALL_PATTERN.findall(_reference_text(member))

    task_refs: dict[str, list[str]] = {member.name: calls(member) for member in VscodeTask if calls(member)}
    launch_refs: dict[str, list[str]] = {member.name: calls(member) for member in VscodeLaunch if calls(member)}
    assert task_refs, "no VscodeTask calls an input; the task invariant walks nothing"
    assert launch_refs, "no VscodeLaunch calls an input; the launch invariant walks nothing"

    # `command` -- RUN_JAVA_DEBUG names its input there and nowhere else
    assert VscodeInput.SELECT_BUILD.input_id in task_refs.get(VscodeTask.RUN_JAVA_DEBUG.name, []), (
        f"RUN_JAVA_DEBUG no longer contributes its ${{input:...}} from `command`: {task_refs}"
    )
    # the rendered watcher redirect -- the field whose absence made the launch walk vacuous, and the
    # only source of an input reference for any launch configuration
    for owner in (VscodeLaunch.DEBUG_PYTHON_FILE.name, VscodeTask.GRADLE_BUILD.name):
        refs: dict[str, list[str]] = launch_refs if owner in launch_refs else task_refs
        assert VscodeInput.TODAY_TIMESTAMP.input_id in refs.get(owner, []), (
            f"{owner} no longer contributes the redirect's ${{input:...}}; _reference_text stopped "
            f"reading the watcher redirect: tasks={task_refs} launches={launch_refs}"
        )


def test_config_references_stay_inside_their_own_stacks() -> None:
    """A member never reads a workspace setting its own stack does not write.

    `${config:mgsnake.java.remoteDebug.port}` resolves to nothing unless `DEFAULT_PROPS[JAVA]` was
    written, and that map is stack-filtered like everything else. Both sides are `JAVA` today, so
    this walks a graph that is already consistent -- retag either side and the workspace gets a
    silent empty interpolation instead of a port number.

    Keys outside `DEFAULT_PROPS` are out of scope by construction: `java.import.gradle.home` and
    `maven.executable.path` are written by `set-gradle`/`set-maven`, which run unconditionally.
    """
    for member in (*VscodeTask, *VscodeLaunch):
        active: set[ProjectStack] = _activated_by(member.stack)
        for key in CONFIG_REF_PATTERN.findall(_reference_text(member)):
            owner: Optional[ProjectStack] = PROP_OWNER.get(key)
            if owner is None:
                continue
            assert owner in active, (
                f"{member.name} ({member.stack}) reads '${{config:{key}}}', written by "
                f"DEFAULT_PROPS[{owner}], which is not active for its stack"
            )


def test_the_config_reference_walk_actually_sees_something() -> None:
    """The walk above is only meaningful while some member really does read a DEFAULT_PROPS key.

    Without this, deleting every `${config:…}` reference -- or breaking `_reference_text` -- would
    leave `test_config_references_stay_inside_their_own_stacks` passing over an empty loop, which is
    the shape of a test that verifies nothing.
    """
    referenced: set[str] = set()
    for member in (*VscodeTask, *VscodeLaunch):
        referenced.update(key for key in CONFIG_REF_PATTERN.findall(_reference_text(member)) if key in PROP_OWNER)
    assert referenced, "no member reads a DEFAULT_PROPS setting; the config-reference invariant walks nothing"
    # DEBUG_JAVA reads the port from `extra_args` and from nowhere else, so it is the one member that
    # proves `_reference_text` reaches in there -- the precise gap this walk was extended to close.
    assert REMOTE_DEBUG_PORT_QUERY in CONFIG_REF_PATTERN.findall(_reference_text(VscodeLaunch.DEBUG_JAVA)), (
        "DEBUG_JAVA's `${config:…}` port lives in extra_args; _reference_text no longer reads that field"
    )
