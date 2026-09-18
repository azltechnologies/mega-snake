"""Tests for the `comment-killer` command group and how it is registered.

The group is the crew's only interface, so what is pinned here is the contract the agents key on:
one JSON document on stdout, a hook that refuses by exit status, and a group that keeps its
subcommands and its light-weight initialization after `__main__` wraps it.
"""

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from mega_snake import __main__ as app_main
from mega_snake.comment_killer import commands, module
from mega_snake.comment_killer.constants import (
    GUARD_GIT_STATE,
    GUARD_KINGPIN,
    GUARD_COMMAND,
    GUARD_TRAPPER,
    HOOK_BLOCK_CODE,
    MISSION_DIR_NAME,
    SPOTTER_AGENT,
    STAGE_BRIEF,
    STATUS_ERROR,
    STATUS_LAUNCH,
    STATUS_WRITE,
)
from mega_snake.comment_killer.guards import KINGPIN_REFUSAL, evaluate, shell_refusal
from mega_snake.comment_killer.mission import NO_MISSION_MESSAGE
from mega_snake.constants import KINGPIN_AGENT, SHELL_ENV_VARIABLE, SHELL_OPT, TRAPPER_AGENT
from mega_snake.util.cli_group import ATTR_ALIAS, ATTR_GROUP, ATTR_METADATA, META_CONTEXT_COMMAND, META_FLAGS
from mega_snake.util.formatting import VALIDATION_ERROR_CODE, InternalStateError

COMMENT: str = "the retry policy swallows a 401 and calls it a success"
EXPECTED_SUBCOMMANDS: set[str] = {"start", "next", "status"}


def run(args: list[str], stdin: str = "") -> Any:
    """Invoke the group the way a shell would.

    Parameters:
        args: The command line, without the group's own name.
        stdin: What the caller pipes in, for the hook guard.

    Raises:
        None

    Returns:
        Any: The click result.
    """
    return CliRunner().invoke(commands.comment_killer, args, input=stdin, standalone_mode=False)


def run_guard(args: list[str], stdin: str = "") -> Any:
    """Invoke the registered hook guard through the root CLI, the way the runtime does.

    Through the root, not the bare command: the verdict becomes a status in the module ending and in
    `post_command`, so invoking `commands.guard` alone would exit 0 whatever it decided.

    Parameters:
        args: The command line, without the guard's own name.
        stdin: The hook payload.

    Raises:
        None

    Returns:
        Any: The click result.
    """
    return CliRunner().invoke(app_main.cli, [GUARD_COMMAND, *args], input=stdin)


@pytest.fixture(name="supported_shell", autouse=True)
def fixture_supported_shell(monkeypatch: pytest.MonkeyPatch) -> str:
    """Provision a supported shell explicitly, since the guard blocks every call without one.

    Parameters:
        monkeypatch: The pytest monkeypatch fixture.

    Raises:
        None

    Returns:
        str: The shell provisioned.
    """
    monkeypatch.setenv(SHELL_ENV_VARIABLE, SHELL_OPT[-1])
    return SHELL_OPT[-1]


def working_path_at(path: Path) -> Any:
    """Point the state machine at a working path, for both the command that creates it and the ones that read it.

    Parameters:
        path: The working path.

    Raises:
        None

    Returns:
        Any: The combined patch context.
    """
    return patch.multiple(
        "mega_snake.comment_killer.mission",
        ensure_working_path=MagicMock(return_value=str(path)),
        get_property=MagicMock(return_value=str(path)),
    )


def test_a_mission_runs_through_the_group(tmp_path: Path) -> None:
    """start, next and status speak one JSON document on stdout, and nothing else."""
    with working_path_at(tmp_path):
        opened = run(["start"])
        mission = json.loads(opened.output)["mission"]
        (tmp_path / MISSION_DIR_NAME / mission / "01_brief.md").write_text(COMMENT, encoding="utf-8")
        advanced = run(["next", "--mission", mission])
        reported = run(["status", "--mission", mission])
        given = run(["start", COMMENT])

    assert opened.exit_code == 0
    assert json.loads(opened.output)["status"] == STATUS_WRITE
    assert json.loads(advanced.output)["subagent_type"] == SPOTTER_AGENT
    assert json.loads(reported.output) == json.loads(advanced.output), "status moved the mission"
    assert given.exit_code == 0
    assert json.loads(given.output)["subagent_type"] == SPOTTER_AGENT, "start with a comment did not skip the brief"


def test_status_without_a_mission_reports_instead_of_crashing(tmp_path: Path) -> None:
    """A user who has not started anything gets a message, not a traceback."""
    with working_path_at(tmp_path):
        result = run(["status"])

    assert result.exception is None, "a refusal of the state machine escaped as an exception"
    assert json.loads(result.stdout) == {"status": STATUS_ERROR, "message": NO_MISSION_MESSAGE}
    assert result.stderr == "", "the refusal travels in the action alone, never on stderr too"
    assert result.return_value == result.stdout.rstrip("\n"), "the command did not return the action it printed"


@pytest.mark.parametrize("subcommand", ["next", "status"])
def test_a_malformed_mission_id_is_reported_as_an_error_action(tmp_path: Path, subcommand: str) -> None:
    """The whole message reaches the orchestrator, inside the action it already knows how to read."""
    with working_path_at(tmp_path):
        result = run([subcommand, "--mission", "../elsewhere"])

    action = json.loads(result.stdout)
    assert action["status"] == STATUS_ERROR, subcommand
    assert action["message"] == (
        "'../elsewhere' is not a mission id. Pass the `mission` field of the last action as it is, "
        "a name such as 2026-09-16_01-00-34, never a path."
    )
    assert set(action) == {"status", "message"}, f"{subcommand} added fields to the error action"


def test_the_guard_lets_an_allowed_call_through_silently() -> None:
    """A guard that says nothing and exits zero is what an allowed tool call looks like."""
    payload = json.dumps({"agent_type": KINGPIN_AGENT, "tool_input": {"command": "mgsnake comment-killer next"}})

    result = run_guard([GUARD_KINGPIN], stdin=payload)

    assert result.exit_code == 0
    assert result.exit_code != HOOK_BLOCK_CODE
    assert result.output == "", "a guard must not write anything when it allows a call"


@pytest.mark.parametrize(
    "guard, payload, expected",
    [
        (
            GUARD_KINGPIN,
            {"agent_type": KINGPIN_AGENT, "tool_input": {"command": "ls -la"}},
            "comment-killer",
        ),
        (
            GUARD_GIT_STATE,
            {"agent_type": KINGPIN_AGENT, "tool_input": {"command": "git stash"}},
            "git stash",
        ),
        (
            GUARD_TRAPPER,
            {"agent_type": TRAPPER_AGENT, "tool_input": {"file_path": "src/app/main.py"}},
            "not a test file",
        ),
    ],
)
def test_a_refused_call_exits_with_the_blocking_status(guard: str, payload: dict, expected: str) -> None:
    """The runtime reads the status to block the call and the message to tell the agent why.

    Any other non-zero status is a hook error rather than a refusal, so the number is the contract.
    """
    with patch("mega_snake.comment_killer.guards.Store") as store:
        store.get_instance.return_value.get.return_value = None
        result = run_guard([guard], stdin=json.dumps(payload))

    assert result.exit_code == HOOK_BLOCK_CODE, f"{guard} refused with the wrong status"
    assert expected in result.output


def test_a_payload_that_is_not_json_is_reported() -> None:
    """A hook that sends something else is a defect worth naming, not a silent allow."""
    result = run_guard([GUARD_KINGPIN], stdin="{not json")

    assert result.exit_code == VALIDATION_ERROR_CODE
    assert result.exit_code != HOOK_BLOCK_CODE, "a broken payload must not read as a refused call"
    assert "JSON" in result.output


def test_a_payload_that_does_not_say_who_is_calling_is_refused() -> None:
    """A rule that cannot identify the caller enforces nothing, so it refuses instead of allowing.

    Nothing on stdin reads as an empty payload, which is the shape a runtime change would produce
    too: letting it through would leave every guard silently inert, at exit 0.
    """
    result = run_guard([GUARD_KINGPIN], stdin="")

    assert result.exit_code == HOOK_BLOCK_CODE
    assert "agent_type" in result.stderr


def test_an_unknown_guard_name_fails_as_a_usage_error_not_as_a_refusal() -> None:
    """A typo in an agent's hook must read as a broken invocation, not as a rule that refused the call.

    Click's usage status and `HOOK_BLOCK_CODE` are the same number, so the status alone cannot tell
    the two apart: what distinguishes them is the reason written to stderr, and a guard's reason
    always starts with `Blocked:`. The consequence is worth knowing, since the number is shared: the
    runtime blocks the call, handing the agent Click's usage text instead of a rule.
    """
    payload = json.dumps({"agent_type": KINGPIN_AGENT, "tool_input": {"command": "ls -la"}})

    result = run_guard(["nonexistent"], stdin=payload)

    assert result.exit_code == 2, "an unknown guard should be a usage error"
    assert "Invalid value" in result.output, result.output
    assert "Blocked:" not in result.output, "a bad guard name was reported as a rule refusing the call"


def test_the_group_keeps_its_subcommands_after_registration() -> None:
    """A rebuilt group that loses `commands` stops resolving, with nothing to see until it is run."""
    registered = app_main.cli.commands["comment-killer"]

    assert isinstance(registered, click.Group)
    assert set(registered.commands) == EXPECTED_SUBCOMMANDS


@pytest.mark.parametrize(
    "name, flags, hidden",
    [
        ("comment-killer", {"skip"}, False),
        ("ck", {"skip"}, True),
        (GUARD_COMMAND, {"no_init"}, True),
    ],
)
def test_each_command_keeps_its_own_initialization_level(name: str, flags: set[str], hidden: bool) -> None:
    """The module wrapper declares no flags, so every level comes from the command's own callback.

    The group's `skip` sits on a group callback rather than on a command's, which is the case the
    other modules never exercised: it has to survive the wrapper rebuild all the same, or the whole
    group silently drops to full initialization. The guard's `no_init` is what lets a hook answer in
    an environment where nothing of mgsnake's has been set up.
    """
    registered = app_main.cli.commands[name]

    assert getattr(registered.callback, ATTR_METADATA, {}).get(META_FLAGS) == flags, f"{name} lost its level"
    assert registered.hidden is hidden, f"{name} has the wrong visibility"
    assert getattr(registered, ATTR_GROUP) == "Comment Killer", f"{name} left its documentation group"


def test_the_group_keeps_its_alias() -> None:
    """`ck` is the name a tired human types; it stays attached to the group."""
    assert getattr(app_main.cli.commands["comment-killer"], ATTR_ALIAS) == ["ck"]


def test_the_guard_is_not_one_of_the_group_subcommands() -> None:
    """The guard needs a different initialization level, and a group carries only one."""
    assert "guard" not in app_main.cli.commands["comment-killer"].commands


def test_the_module_exposes_its_own_group() -> None:
    """The module's group is the one its registration wraps."""
    result = CliRunner().invoke(module.main, ["--help"])

    assert result.exit_code == 0
    assert "comment-killer related commands" in result.output


def test_the_alias_resolves_to_the_same_group() -> None:
    """`ck` is the form a hook and a tired human type; it has to reach the same commands."""
    assert set(app_main.cli.commands["ck"].commands) == EXPECTED_SUBCOMMANDS


def test_a_missing_shell_blocks_the_call_through_the_registered_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment refusal travels the same road as a rule's: stderr for the agent, 2 for the runtime."""
    monkeypatch.delenv(SHELL_ENV_VARIABLE, raising=False)
    payload = json.dumps({"agent_type": KINGPIN_AGENT, "tool_input": {"command": "mgsnake comment-killer next"}})

    result = run_guard([GUARD_KINGPIN], stdin=payload)

    assert result.exit_code == HOOK_BLOCK_CODE
    assert result.stdout == "", "a refusal belongs on stderr, where the runtime reads it"
    expected = shell_refusal()
    assert expected is not None
    # ws_error colours the console, so the escape sequences are stripped before comparing lines.
    written = re.sub(r"\x1b\[[0-9;]*m", "", result.stderr).splitlines()
    assert written[: len(expected.splitlines())] == expected.splitlines()
    assert KINGPIN_REFUSAL not in result.stderr, "the rule ran although the environment already blocked"


def test_the_guard_is_registered_as_a_context_command() -> None:
    """The registered guard is wrapped by the context decorator, which is what can turn its verdict into a status."""
    registered = app_main.cli.commands[GUARD_COMMAND]

    assert getattr(registered.callback, ATTR_METADATA, {}).get(META_CONTEXT_COMMAND) is True
    assert registered.callback is not commands.guard.callback, "the guard was registered without its wrapper"


@pytest.mark.parametrize(
    "result, expected",
    [
        (True, {"exit_code": HOOK_BLOCK_CODE}),
        (False, {}),
        (json.dumps({"status": STATUS_ERROR, "message": "no such mission"}), {"exit_code": VALIDATION_ERROR_CODE}),
        (json.dumps({"status": STATUS_LAUNCH, "message": "error"}), {}),
        (json.dumps({"status": STATUS_WRITE}), {}),
    ],
    ids=["guard-refused", "guard-allowed", "error-action", "launch-mentioning-error", "write-action"],
)
def test_the_module_ending_sets_a_status_only_for_a_refusal_or_an_error_action(result: object, expected: dict) -> None:
    """Each command's result keeps its own meaning; anything that is not a refusal leaves the context untouched.

    The two refusals use different numbers on purpose: 2 is what a hook blocks with, 113 is what a
    validation reports, and crossing them would turn a crew error into a blocked tool call or back.
    """
    ctx = click.Context(app_main.cli, obj={})

    module.ending(ctx, result)

    assert ctx.obj == expected, f"wrong status for {result!r}"


@pytest.mark.parametrize("result", [None, 0, 1.5], ids=repr)
def test_the_module_ending_refuses_a_result_neither_command_returns(result: object) -> None:
    """A primitive of another type means a command changed its contract without its ending."""
    ctx = click.Context(app_main.cli, obj={})

    with pytest.raises(InternalStateError) as raised:
        module.ending(ctx, result)

    assert str(raised.value) == (
        f"The comment-killer ending received {type(result).__name__}; it only reads a guard's bool "
        "or an action's JSON text."
    )
    assert ctx.obj == {}


@pytest.mark.parametrize("name", ["comment-killer", "ck", GUARD_COMMAND])
def test_every_command_of_the_module_is_registered_as_a_context_command(name: str) -> None:
    """The group, its alias and the guard all reach the ending, which is what makes their statuses real."""
    registered = app_main.cli.commands[name]

    assert getattr(registered.callback, ATTR_METADATA, {}).get(META_CONTEXT_COMMAND) is True, name


def test_every_command_the_state_machine_hands_the_kingpin_passes_the_kingpin_guard(tmp_path: Path) -> None:
    """The guard and the state machine must agree on what a mission id looks like.

    Every `next --mission <id>` an action tells the kingpin to run -- in `then`, and in the message of a
    `missing` action -- is checked against the guard, across a whole mission, under a working path with
    a space in it. A guard stricter than the ids it is handed stops the crew on its first `next`.
    """
    spaced = tmp_path / "my repo"
    commands_handed: list[str] = []
    with working_path_at(spaced):
        action = json.loads(run(["start"]).output)
        mission = action["mission"]
        folder = spaced / MISSION_DIR_NAME / mission
        folder.joinpath("01_brief.md").write_text(COMMENT, encoding="utf-8")
        commands_handed.append(action["then"])
        for report, content in [("02_map.md", "# STILL VALID\n"), ("03_trap.md", "trap"), ("04_hit.md", "hit")]:
            action = json.loads(run(["next", "--mission", mission]).output)
            commands_handed.append(action["then"])
            missing = json.loads(run(["next", "--mission", mission]).output)
            commands_handed.append(missing["message"])
            folder.joinpath(report).write_text(content, encoding="utf-8")

    resumes = [re.search(r"mgsnake comment-killer next --mission \S+", text) for text in commands_handed]
    assert all(resumes), f"an action gave no whole resume command: {commands_handed}"
    for found in resumes:
        command = found.group(0).rstrip("`")  # type: ignore[union-attr]
        assert evaluate(GUARD_KINGPIN, {"agent_type": KINGPIN_AGENT, "tool_input": {"command": command}}) is None, (
            f"the kingpin guard refuses a command the state machine handed out: {command}"
        )
