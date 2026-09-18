"""Tests for the guards the crew's agents run their tool calls through.

A guard that lets the wrong call through is invisible until it has already happened -- a rewritten
git state, a trapper that "just fixed" the production code, an orchestrator off investigating on its
own -- so each rule is tested from both sides: the call it must refuse, and the call it must not.
"""

import json
import re
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest

from mega_snake.comment_killer import guards
from mega_snake.comment_killer.constants import (
    GUARD_OPT,
    GUARD_GIT_STATE,
    GUARD_KINGPIN,
    GUARD_TRAPPER,
    SPOTTER_AGENT,
    STATE_FILE,
    TEST_PATTERN_KEY,
)
from mega_snake.constants import HITMAN_AGENT, KINGPIN_AGENT, SHELL_ENV_VARIABLE, SHELL_OPT, TRAPPER_AGENT

CUSTOM_PATTERN: str = r"verification/|_should\.py$"
BROKEN_PATTERN: str = "([unclosed"


def payload(agent: str, **tool_input: str) -> dict[str, Any]:
    """Build a hook payload the way the runtime sends one.

    The cast to the runtime's shape lives here so a test can express a payload the schema would
    normally forbid -- a call with no command, a tool call naming no file at all.

    Parameters:
        agent: The `agent_type` the runtime reports.
        tool_input: The fields of the tool call under inspection.

    Raises:
        None

    Returns:
        dict[str, Any]: The payload.
    """
    return {"agent_type": agent, "hook_event_name": "PreToolUse", "tool_input": dict(tool_input)}


@pytest.fixture(name="supported_shell", autouse=True)
def fixture_supported_shell(monkeypatch: pytest.MonkeyPatch) -> str:
    """Provision a supported shell, so the rules below are judged on their own.

    Set explicitly rather than inherited: a developer's terminal exports the variable and a CI runner
    may not, and the environment check runs before every rule. The last supported shell is used so a
    guard that only accepted the first one would not pass by accident.

    Parameters:
        monkeypatch: The pytest monkeypatch fixture.

    Raises:
        None

    Returns:
        str: The shell provisioned.
    """
    monkeypatch.setenv(SHELL_ENV_VARIABLE, SHELL_OPT[-1])
    return SHELL_OPT[-1]


@pytest.fixture(name="no_custom_pattern")
def fixture_no_custom_pattern() -> Any:
    """Answer the store with no custom test pattern, the way a fresh project reads.

    Parameters:
        None

    Raises:
        None

    Returns:
        Any: The patched store accessor.
    """
    with patch("mega_snake.comment_killer.guards.Store") as store:
        store.get_instance.return_value.get.return_value = None
        yield store


@pytest.mark.parametrize(
    "command, refused",
    [
        ("git stash && uv run mypy src", "stash"),
        ("uv run mypy src; git stash pop", "stash"),
        ("git -C /repo add .", "add"),
        ("git commit -m 'wip'", "commit"),
        ("(cd sub; git reset --hard)", "reset"),
        ("git checkout -- src", "checkout"),
        ("git branch -D feature", "branch"),
        ("git worktree remove ../wt", "worktree"),
        ("git update-ref refs/heads/main abc123", "update-ref"),
        ("git for-each-ref --format='%(refname)' refs/heads", None),
        ("git diff src", None),
        ("git show HEAD:src/app.py", None),
        ("git log --oneline -5", None),
        ("grep -rn 'git stash' docs", None),
        ("uv run pytest -q", None),
    ],
)
def test_the_git_state_guard_refuses_only_what_rewrites_history(command: str, refused: Optional[str]) -> None:
    """Reading git is the job; rewriting the user's index, stash, branch or history never is."""
    result = guards.evaluate(GUARD_GIT_STATE, payload(HITMAN_AGENT, command=command))

    if refused is None:
        assert result is None, f"refused a read-only command: {command}"
    else:
        assert result is not None, f"let a state-changing command through: {command}"
        assert refused in result, f"the refusal does not name `git {refused}`: {result}"


@pytest.mark.parametrize(
    "command, allowed",
    [
        ("mgsnake comment-killer next", True),
        ("mgsnake comment-killer next --mission 2026-09-16_01-00-34", True),
        ("mgsnake comment-killer next --mission=2026-09-16_01-00-34_2", True),
        ("mgsnake ck status -m 2026-09-16_01-00-34", True),
        ("mgsnake ck status", True),
        ("/usr/local/bin/mgsnake comment-killer start", True),
        ("./mgsnake ck next", True),
        ("evilmgsnake comment-killer start", False),
        ("my-mgsnake ck next", False),
        ("/usr/bin/evilmgsnake ck next", False),
        ("mgsnake comment-killer next --mission /tmp/x", False),
        ("mgsnake comment-killer next --mission=/tmp/x", False),
        ("mgsnake comment-killer next --mission ../x", False),
        ('mgsnake comment-killer next --mission "2026-09-16 01-00-34"', False),
        ("mgsnake comment-killer next --mission '2026-09-16_01-00-34'", False),
        ("mgsnake comment-killer next && ls", False),
        ("mgsnake comment-killer next; rm -rf src", False),
        ("mgsnake comment-killer next --mission $(cat /tmp/evil)", False),
        ("mgsnake comment-killer next > /tmp/out", False),
        ("mgsnake comment-killer-guard kingpin", False),
        ("ls -la", False),
        ("grep -rn to_dict src", False),
        ("", False),
    ],
)
def test_the_kingpin_runs_its_own_state_machine_and_nothing_else(command: str, allowed: bool) -> None:
    """The orchestrator relays a state machine; every other command is somebody else's job."""
    result = guards.evaluate(GUARD_KINGPIN, payload(KINGPIN_AGENT, command=command))

    assert (result is None) is allowed, f"wrong verdict for: {command!r}"


def test_the_kingpin_guard_leaves_every_other_agent_alone() -> None:
    """Hooks are inherited by the subagents the orchestrator spawns, so the guard asks who is calling.

    Deciding by the shape of the command instead is what once blocked the spotter from running
    `git log` at all: the rule was written for the orchestrator and reached the whole crew.
    """
    for agent in (SPOTTER_AGENT, TRAPPER_AGENT, HITMAN_AGENT):
        assert guards.evaluate(GUARD_KINGPIN, payload(agent, command="grep -rn to_dict src")) is None, agent


@pytest.mark.parametrize(
    "target, allowed",
    [
        ("src/tests/config_environment/test_java_set.py", True),
        ("tests/unit/foo_spec.rb", True),
        ("app/src/test/java/com/x/FooTest.java", True),
        ("src/components/Button.test.tsx", True),
        ("spec/models/user_spec.rb", True),
        ("src/tests/conftest.py", True),
        ("src/mega_snake/config_environment/models/vscode_task.py", False),
        ("src/components/Button.tsx", False),
        (".github/copilot-instructions.md", False),
        ("", False),
    ],
)
def test_the_trapper_writes_tests_and_nothing_else(target: str, allowed: bool, no_custom_pattern: Any) -> None:
    """The trap is the specification; a trapper that fixes the code writes its tests against its own fix."""
    result = guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path=target))

    assert (result is None) is allowed, f"wrong verdict for: {target!r}"
    if not allowed:
        assert TEST_PATTERN_KEY in result, "the refusal does not say how to teach the crew a new convention"


def test_the_trapper_may_write_its_own_report_into_the_mission(tmp_path: Path, no_custom_pattern: Any) -> None:
    """Its trap report is neither production code nor a test, and it is the trapper's to file."""
    (tmp_path / STATE_FILE).write_text("{}", encoding="utf-8")

    assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path=str(tmp_path / "03_trap.md"))) is None


def test_the_git_state_refusal_names_the_read_only_way_to_get_the_same_information() -> None:
    """A refusal that only says no leaves the agent stuck, or looking for another spelling of the same call.

    `branch` and `worktree` are refused whole, read-only forms included, so the way out has to be in
    the message: this is the one refusal an agent is most likely to hit while doing its job right.
    """
    result = guards.evaluate(GUARD_GIT_STATE, payload(HITMAN_AGENT, command="git branch -D feature"))

    assert result == (
        "Blocked: `git branch` changes the git state, and the user keeps their own work in there. "
        "Read the original code with `git diff` or `git show HEAD:<path>`, and list refs with "
        "`git for-each-ref` or `git log`, instead. Do not retry this command in another form."
    )


@pytest.mark.parametrize("guard", [GUARD_KINGPIN, GUARD_TRAPPER])
@pytest.mark.parametrize(
    "agent_payload",
    [{}, {"agent_type": None}, {"agent_type": ""}, {"hook_event_name": "PreToolUse"}],
    ids=["no-field", "null", "empty", "other-fields-only"],
)
def test_an_agent_rule_refuses_a_payload_that_does_not_say_who_is_calling(guard: str, agent_payload: dict) -> None:
    """A rule keyed on `agent_type` cannot enforce anything without it, so it refuses rather than allows.

    The runtime reads anything but 2 as a hook error and lets the call through, so failing open here
    would turn a renamed or re-nested field into two guards that quietly stop existing.
    """
    call = {**agent_payload, "tool_input": {"command": "ls -la", "file_path": "src/app/main.py"}}

    result = guards.evaluate(guard, call)

    assert result == guards.UNKNOWN_AGENT_REFUSAL, f"{guard} with {agent_payload}"


def test_the_git_state_rule_judges_the_command_whoever_is_calling(no_custom_pattern: Any) -> None:
    """Unlike the other two, this rule never asks who is calling, so a payload without an agent is fine."""
    assert guards.evaluate(GUARD_GIT_STATE, {"tool_input": {"command": "git log --oneline"}}) is None
    assert guards.evaluate(GUARD_GIT_STATE, {"tool_input": {"command": "git stash"}}) is not None


def test_the_trapper_guard_leaves_the_hitman_alone(no_custom_pattern: Any) -> None:
    """The hitman edits production code for a living; the same inherited hook must not stop it."""
    assert guards.evaluate(GUARD_TRAPPER, payload(HITMAN_AGENT, file_path="src/mega_snake/app.py")) is None


def test_a_notebook_is_judged_by_its_path_like_any_other_file(no_custom_pattern: Any) -> None:
    """A notebook edit names its file under another key, and must not slip past because of it."""
    assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, notebook_path="src/analysis.ipynb")) is not None
    assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, notebook_path="tests/analysis.ipynb")) is None


def test_a_custom_pattern_widens_the_conventions_it_ships_with() -> None:
    """A project that files its tests its own way is taught, not blocked -- and keeps the defaults.

    Replacing the shipped conventions with the user's would cost a project every convention it does
    follow the moment it names one it does not.
    """
    with patch("mega_snake.comment_killer.guards.Store") as store:
        store.get_instance.return_value.get.return_value = CUSTOM_PATTERN

        assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="verification/x.py")) is None
        assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="lib/checks_should.py")) is None
        assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="src/tests/test_x.py")) is None
        assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="src/app/main.py")) is not None


def test_an_unusable_custom_pattern_warns_and_is_ignored() -> None:
    """A typo in a setting must not be what stops a mission."""
    with patch("mega_snake.comment_killer.guards.Store") as store, patch(
        "mega_snake.comment_killer.guards.ws_warning"
    ) as warning:
        store.get_instance.return_value.get.return_value = BROKEN_PATTERN

        assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="src/tests/test_x.py")) is None
        assert guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="verification/x.py")) is not None

    assert warning.called, "an ignored setting the user wrote has to be reported"
    assert TEST_PATTERN_KEY in warning.call_args.args[0]


def test_the_shipped_pattern_is_returned_untouched_without_a_setting(no_custom_pattern: Any) -> None:
    """With nothing configured, the guard compiles nothing new and keeps its own pattern."""
    patterns = guards.test_path_patterns()

    assert patterns == (guards.TEST_PATH,)
    assert patterns[0] is guards.TEST_PATH


@pytest.mark.parametrize(
    "custom, target",
    [
        ("(?i)verification/", "VERIFICATION/x.py"),
        ("(?x) verification / ", "verification/x.py"),
        ("^checks/", "checks/x.py"),
    ],
    ids=["inline-ignorecase", "inline-verbose", "anchored"],
)
def test_a_custom_pattern_that_compiles_alone_is_honoured_as_written(custom: str, target: str) -> None:
    """A valid expression is never refused because of how it would combine with the shipped one.

    Joining the two texts turned an inline flag -- valid only at the start of an expression -- into
    an error the guard did not catch, and a crashed guard lets the trapper write anywhere.
    """
    with patch("mega_snake.comment_killer.guards.Store") as store, patch(
        "mega_snake.comment_killer.guards.ws_warning"
    ) as warning:
        store.get_instance.return_value.get.return_value = custom

        allowed = guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path=target))
        shipped = guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="src/tests/test_x.py"))
        production = guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="src/app/main.py"))

    assert allowed is None, f"{custom!r} did not admit {target!r}"
    assert shipped is None, f"{custom!r} cost the shipped conventions"
    assert production is not None, f"{custom!r} let production code through"
    warning.assert_not_called()


def test_a_custom_pattern_keeps_its_own_flags_and_not_the_shipped_ones() -> None:
    """The shipped conventions ignore case; the user's pattern matches exactly as the user wrote it."""
    with patch("mega_snake.comment_killer.guards.Store") as store:
        store.get_instance.return_value.get.return_value = "verification/"
        patterns = guards.test_path_patterns()

    assert [pattern.pattern for pattern in patterns] == [guards.TEST_PATH.pattern, "verification/"]
    assert patterns[0].flags & re.IGNORECASE, "the shipped conventions stopped ignoring case"
    assert not patterns[1].flags & re.IGNORECASE, "the user's pattern inherited a flag it never asked for"
    assert patterns[0].search("SRC/TESTS/TEST_X.PY"), "a path the shipped conventions match stopped matching"


# ---------------------------------------------------------------------------
# The environment check: every guard blocks while the shell variable is unusable
# ---------------------------------------------------------------------------

# A call every guard lets through on its own merits, so only the environment can refuse it.
ALLOWED_BY_EVERY_RULE: dict[str, Any] = payload(KINGPIN_AGENT, command="mgsnake comment-killer next")


def test_the_call_used_below_is_allowed_by_every_rule() -> None:
    """The environment tests only prove something if the rules themselves would let the call through."""
    for guard in GUARD_OPT:
        assert guards.GUARDS[guard](ALLOWED_BY_EVERY_RULE) is None, f"the {guard} rule refuses the probe call"


@pytest.mark.parametrize("shell", SHELL_OPT)
def test_every_supported_shell_lets_the_rules_decide(shell: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A supported shell adds no refusal of its own, whichever guard runs."""
    monkeypatch.setenv(SHELL_ENV_VARIABLE, shell)

    assert guards.shell_refusal() is None, shell
    for guard in GUARD_OPT:
        assert guards.evaluate(guard, ALLOWED_BY_EVERY_RULE) is None, f"{guard} refused with {shell}"


@pytest.mark.parametrize("guard", GUARD_OPT)
@pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
def test_a_missing_shell_blocks_every_guard_before_its_rule(
    guard: str, value: Optional[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset and empty both read as missing, and the refusal wins over a rule that would allow the call."""
    if value is None:
        monkeypatch.delenv(SHELL_ENV_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(SHELL_ENV_VARIABLE, value)
    expected = guards.SHELL_REFUSAL.format(
        problem=f"`{SHELL_ENV_VARIABLE}` is not set", snippet=guards.SHELL_SETTINGS_SNIPPET
    )

    result = guards.evaluate(guard, ALLOWED_BY_EVERY_RULE)

    assert result == expected, f"{guard} with the variable {value!r}"
    assert result is not None


@pytest.mark.parametrize("shell", ["fish", "Bash", " bash"], ids=repr)
def test_an_unsupported_shell_blocks_naming_the_value(shell: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A value mgsnake does not model is as unusable as none, and the message says which value it read."""
    monkeypatch.setenv(SHELL_ENV_VARIABLE, shell)
    expected = guards.SHELL_REFUSAL.format(
        problem=f"`{SHELL_ENV_VARIABLE}` is `{shell}`, which mgsnake does not support",
        snippet=guards.SHELL_SETTINGS_SNIPPET,
    )

    assert guards.evaluate(GUARD_KINGPIN, ALLOWED_BY_EVERY_RULE) == expected, repr(shell)


def test_the_shell_refusal_tells_the_user_exactly_what_to_add(monkeypatch: pytest.MonkeyPatch) -> None:
    """The message is the whole remedy: the file, the block, the valid values and the restart.

    Written out in full on purpose: comparing against the template would only prove the template
    agrees with itself.
    """
    monkeypatch.delenv(SHELL_ENV_VARIABLE, raising=False)

    assert guards.shell_refusal() == (
        "Blocked: the comment-killer crew cannot run, because `MEGA_SNAKE_SHELL` is not set, and every "
        "`mgsnake` command the crew needs refuses to start without it. Stop the mission and show this "
        "message to the user verbatim. The user has to add the variable, with the shell they use (one of: "
        "bash, zsh, powershell, pwsh), to the \"env\" block of `.claude/settings.local.json`:\n"
        "\n"
        "  {\n"
        '    "env": {\n'
        '      "MEGA_SNAKE_SHELL": "bash"\n'
        "    }\n"
        "  }\n"
        "\n"
        "and then restart the Claude Code session, so the new environment reaches the crew."
    )


def test_the_settings_snippet_is_json_built_from_the_supported_shells() -> None:
    """The snippet a user pastes must parse, and must name a value the CLI accepts."""
    parsed = json.loads(guards.SHELL_SETTINGS_SNIPPET)

    assert parsed == {"env": {SHELL_ENV_VARIABLE: SHELL_OPT[0]}}
    assert parsed["env"][SHELL_ENV_VARIABLE] in SHELL_OPT


def test_a_blocked_environment_never_reads_the_custom_test_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    """The check runs before any rule, so the trapper's rule -- and the store behind it -- is never reached."""
    monkeypatch.delenv(SHELL_ENV_VARIABLE, raising=False)

    with patch("mega_snake.comment_killer.guards.Store") as store:
        result = guards.evaluate(GUARD_TRAPPER, payload(TRAPPER_AGENT, file_path="src/app/main.py"))

    assert result is not None and result.startswith("Blocked: the comment-killer crew cannot run"), result
    store.get_instance.assert_not_called()
