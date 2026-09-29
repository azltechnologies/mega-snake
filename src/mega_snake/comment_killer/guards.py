"""The hook guards the crew's agents run their own tool calls through.

A hook declared on an agent is inherited by every subagent it spawns, so each guard decides by the
``agent_type`` the runtime reports rather than by the shape of the command: the kingpin is held to
its own state machine, the trapper is held to test files, and nobody rewrites the user's git state.

They live in the CLI, not as scripts in the user's repository, so the crew ships and versions as one
piece and a user's checkout gains no Python it did not ask for.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from mega_snake.comment_killer.constants import (
    GUARD_GIT_STATE,
    GUARD_KINGPIN,
    GUARD_TRAPPER,
    MISSION_ID_PATTERN,
    STATE_FILE,
    TEST_PATTERN_KEY,
)
from mega_snake.constants import APP_NAME, KINGPIN_AGENT, SHELL_ENV_VARIABLE, SHELL_OPT, TRAPPER_AGENT
from mega_snake.util.formatting import ws_warning
from mega_snake.util.store import Store

# `git` in command position -- the start of the command, or right after a separator, so a quoted
# "git stash" inside a grep pattern is left alone -- followed by a subcommand that rewrites the
# index, the stash, the branch or the history. The judgement is on the subcommand alone, never on its
# flags: `branch` and `worktree` are refused whole, so their read-only forms (`git branch --list`)
# are refused too, and the refusal names what to read instead. A rule that had to tell `-d` from
# `--list` would be one more flag away from being wrong in the direction that costs the user work.
GIT_STATE_CHANGE = re.compile(
    r"(?:^|[;&|(\n]|\$\()\s*git\b(?:\s+-[Cc]\s+\S+|\s+--?[\w-]+(?:=\S+)?)*\s+"
    r"(stash|add|commit|checkout|switch|reset|restore|rebase|merge|cherry-pick|revert|rm|mv|push|pull"
    r"|am|apply|clean|tag|branch|worktree|update-ref)\b"
)

# The only command the kingpin may run: its own state machine, optionally naming the mission it is
# driving by its id -- never by a path, which could hold spaces, quotes or anything else a shell
# reads. Nothing else -- no second command chained on with `&&`, no substitution, no redirection:
# an orchestrator that can append to its own command can do anything the crew was built to stop it
# doing. A path in front is allowed, but only one that ends in `/`, so the binary is `mgsnake` itself
# and not any name that merely ends in it.
KINGPIN_COMMAND = re.compile(
    r"(?:[\w./-]*/)?mgsnake\s+(comment-killer|ck)\s+(start|next|status)"
    rf"(\s+(-m|--mission)(\s+|=){MISSION_ID_PATTERN})?\s*"
)

# How test files are named or filed across the stacks a user's repository may be written in.
TEST_PATH = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__|testing)(/|$)"
    r"|(^|/)test_[^/]+$"
    r"|[._-](test|tests|spec|specs)\.[^/]+$"
    r"|Tests?\.[^/]+$"
    r"|(^|/)conftest\.py$",
    re.IGNORECASE,
)

GIT_STATE_REFUSAL: str = (
    "Blocked: `git {subcommand}` changes the git state, and the user keeps their own work in there. "
    "Read the original code with `git diff` or `git show HEAD:<path>`, and list refs with "
    "`git for-each-ref` or `git log`, instead. Do not retry this command in another form."
)
UNKNOWN_AGENT_REFUSAL: str = (
    "Blocked: this hook payload does not say which agent is calling (`agent_type` is missing), so "
    "the crew's rules cannot be applied to it. Stop and show this to the user: the guard refuses "
    "rather than letting the call through, because a rule that cannot identify the caller protects "
    "nobody."
)
KINGPIN_REFUSAL: str = (
    "Blocked: you only run `mgsnake comment-killer start|next|status`, on its own. The crew does the digging, not you."
)
TRAPPER_REFUSAL: str = (
    "Blocked: `{target}` is not a test file. You set the trap; the hitman does the fixing. Write the "
    "scenario that fails and hand it over -- do not touch production code, not even a one-liner. (If "
    f"this project files its tests somewhere the crew does not recognise, the user can teach it with "
    f"`mgsnake config set {TEST_PATTERN_KEY} '<regex>'`.)"
)
# The block the user adds to `.claude/settings.local.json`, indented to read as a quoted snippet.
SHELL_SETTINGS_SNIPPET: str = "\n".join(
    f"  {line}" for line in json.dumps({"env": {SHELL_ENV_VARIABLE: SHELL_OPT[0]}}, indent=2).splitlines()
)
SHELL_REFUSAL: str = (
    "Blocked: the comment-killer crew cannot run, because {problem}, and every `"
    + APP_NAME
    + "` command the crew needs refuses to start without it. Stop the mission and show this message to "
    "the user verbatim. The user has to add the variable, with the shell they use (one of: "
    + ", ".join(SHELL_OPT)
    + '), to the "env" block of `.claude/settings.local.json`:\n\n{snippet}\n\n'
    "and then restart the Claude Code session, so the new environment reaches the crew."
)
INVALID_PATTERN_WARNING: str = (
    f"The custom test pattern in '{TEST_PATTERN_KEY}' is not a valid regular expression and is being "
    "ignored: {error}. The crew falls back to the conventions it ships with."
)


def _command(payload: dict[str, Any]) -> str:
    """Read the shell command a hook payload carries.

    Parameters:
        payload: The hook input.

    Raises:
        None

    Returns:
        str: The command, or an empty string when the call is not a shell call.
    """
    return str(payload.get("tool_input", {}).get("command", "")).strip()


def _target(payload: dict[str, Any]) -> str:
    """Read the file a hook payload's tool call writes to.

    Parameters:
        payload: The hook input.

    Raises:
        None

    Returns:
        str: The file path, or an empty string when the call names none.
    """
    tool_input = payload.get("tool_input", {})
    return str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")


def _git_state(payload: dict[str, Any]) -> Optional[str]:
    """Refuse a shell command that changes the git state.

    Parameters:
        payload: The hook input.

    Raises:
        None

    Returns:
        Optional[str]: The refusal to hand back to the agent, or None to let the call through.
    """
    match = GIT_STATE_CHANGE.search(_command(payload))
    return GIT_STATE_REFUSAL.format(subcommand=match.group(1)) if match else None


def _kingpin(payload: dict[str, Any]) -> Optional[str]:
    """Hold the kingpin to its own state machine.

    A payload that does not name its agent is refused rather than allowed: the rule exists to hold
    one agent to one command list, and a rule that cannot tell who is calling enforces nothing. An
    allowed call is the runtime's default when a hook errors, so failing open here would be a guard
    that stops guarding without a word -- the exact failure the crew's hooks exist to avoid.

    Parameters:
        payload: The hook input.

    Raises:
        None

    Returns:
        Optional[str]: The refusal to hand back to the agent, or None to let the call through.
    """
    if not payload.get("agent_type"):
        return UNKNOWN_AGENT_REFUSAL
    if payload["agent_type"] != KINGPIN_AGENT:
        return None
    return None if KINGPIN_COMMAND.fullmatch(_command(payload)) else KINGPIN_REFUSAL


def test_path_patterns() -> tuple[re.Pattern[str], ...]:
    """Build the patterns that decide whether a path is one of the project's test files.

    The shipped conventions cover the stacks the crew is likely to land in, and never all of them:
    a project is free to file its tests under `verification/` or name them `*_should.py`. So the
    user may add their own through `ck.test_pattern`, and it is **added** to the defaults rather
    than replacing them -- a partial pattern must not cost a project the conventions it does
    follow. An unusable pattern warns and is ignored, because a typo in a setting must never be
    what stops a mission.

    The two are compiled and matched separately, never joined into one expression: a pattern that
    compiles on its own can stop compiling once concatenated (an inline flag such as `(?i)` is only
    valid at the start), and the user's pattern keeps exactly the flags the user wrote.

    Parameters:
        None

    Raises:
        None

    Returns:
        tuple[re.Pattern[str], ...]: The shipped conventions, followed by the user's pattern when it compiles.
    """
    custom: Optional[str] = Store.get_instance().get(TEST_PATTERN_KEY)
    if not custom:
        return (TEST_PATH,)
    try:
        return (TEST_PATH, re.compile(custom))
    except re.error as error:
        ws_warning(INVALID_PATTERN_WARNING.format(error=error))
        return (TEST_PATH,)


def _trapper(payload: dict[str, Any]) -> Optional[str]:
    """Hold the trapper to the project's test files.

    The trap is the specification the hitman implements against, so a trapper that "just fixes" the
    production code while it is there destroys the point: the tests would be written against a fix
    that already exists, and nobody would ever see them fail for the real reason.

    Parameters:
        payload: The hook input.

    Raises:
        None

    Returns:
        Optional[str]: The refusal to hand back to the agent, or None to let the call through.
    """
    if not payload.get("agent_type"):
        return UNKNOWN_AGENT_REFUSAL
    if payload["agent_type"] != TRAPPER_AGENT:
        return None
    target = _target(payload)
    if not target:
        return TRAPPER_REFUSAL.format(target=target)
    path = Path(target)
    # Its own trap report lives in the mission folder, which is neither production code nor a test.
    if (path.parent / STATE_FILE).is_file():
        return None
    if any(pattern.search(path.as_posix()) for pattern in test_path_patterns()):
        return None
    return TRAPPER_REFUSAL.format(target=target)


GUARDS: dict[str, Any] = {
    GUARD_GIT_STATE: _git_state,
    GUARD_KINGPIN: _kingpin,
    GUARD_TRAPPER: _trapper,
}


def shell_refusal() -> Optional[str]:
    """Refuse every call while the shell variable the crew's own commands need is unusable.

    The guard itself is ``no_init`` and runs without the variable, but ``comment-killer`` is not: a
    session that never had it provisioned would see every state-machine command fail with 112, and a
    henchman would carry on regardless. Blocking here, before any rule, is what turns that into one
    message telling the user how to fix it.

    Parameters:
        None

    Raises:
        None

    Returns:
        Optional[str]: The refusal naming the problem, or None when the variable holds a supported shell.
    """
    shell: Optional[str] = os.environ.get(SHELL_ENV_VARIABLE)
    if not shell:
        return SHELL_REFUSAL.format(problem=f"`{SHELL_ENV_VARIABLE}` is not set", snippet=SHELL_SETTINGS_SNIPPET)
    if shell not in SHELL_OPT:
        return SHELL_REFUSAL.format(
            problem=f"`{SHELL_ENV_VARIABLE}` is `{shell}`, which {APP_NAME} does not support",
            snippet=SHELL_SETTINGS_SNIPPET,
        )
    return None


def evaluate(guard: str, payload: dict[str, Any]) -> Optional[str]:
    """Run one guard against a hook payload, after checking the environment the crew needs.

    Parameters:
        guard: The guard's name, one of ``GUARD_OPT``.
        payload: The hook input, as the runtime sent it on stdin.

    Raises:
        None

    Returns:
        Optional[str]: The refusal to hand back to the agent, or None to let the call through.
    """
    return shell_refusal() or GUARDS[guard](payload)
