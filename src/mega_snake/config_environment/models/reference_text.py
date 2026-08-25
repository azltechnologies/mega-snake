"""Flattening of the text a VS Code task or launch configuration interpolates references out of.

Both the workspace generator and its invariant tests need the same view of a task or launch
configuration: every field VS Code substitutes `${input:...}`/`${config:...}` references into,
joined into one string. Production narrows that string down to the input ids it calls;
`test_stack_references.py` applies different patterns over the same text to also check
`${config:...}` references. Keeping the flattening itself in one place is what keeps those two
readings honest about what "every interpolatable field" means.
"""

import json
import re
from typing import Union

from mega_snake.config_environment.models.vscode_launch import VscodeLaunch
from mega_snake.config_environment.models.vscode_task import VscodeTask

# Every `${input:<id>}` a task or a launch configuration interpolates.
INPUT_CALL_PATTERN = re.compile(r"\$\{input:([^}]+)\}")


def reference_text(member: Union[VscodeTask, VscodeLaunch], working_path: str) -> str:
    """Join every field of a member that VS Code interpolates references out of.

    The fields are the ones `to_dict` emits, and that is the rule for extending this function: a
    value VS Code never receives cannot interpolate anything, and a value it does receive is a
    reference site no matter how nested it is. `extra_args` is included for exactly that reason --
    the Windows overrides on the Gradle build tasks (`{"windows": {"command": ..., "args": ...}}`)
    and a launch's `port`/`program` entries are as much a reference site as `command` is -- and so
    is `problem_matcher`, which is `Any`-typed, unvalidated and copied verbatim into
    `result["problemMatcher"]`. `VscodeLaunch.depends_on` is deliberately absent: `to_dict` does not
    emit it, so nothing in the workspace file ever interpolates it. Should that change, it belongs
    here in the same commit.

    The watcher redirect is asked of the watcher rather than read back from `args`: `add_logger_args`
    only appends it while `to_dict` runs, which happens after inputs are written, so in a fresh
    process `args` does not contain it yet.

    Parameters:
        member: The task or launch configuration to flatten.
        working_path: Path the watcher redirect, if any, is anchored to. Callers that only care
            about which `${input:...}`/`${config:...}` id the redirect interpolates -- never the
            folder it is anchored to -- may pass any string.

    Raises:
        None

    Returns:
        str: Every field `to_dict` emits, joined; JSON for the nested ones so no value is lost.
    """
    # Falsy entries are dropped rather than joined: a member without a `command` (every
    # `VscodeLaunch`) used to contribute an empty string, and `" ".join` turned that into a leading
    # space on the whole flattened text.
    parts: list[str] = [part for part in (getattr(member, "command", None), *member.args) if part]
    for nested in (member.extra_args, getattr(member, "env", None), getattr(member, "problem_matcher", None)):
        if nested:
            parts.append(json.dumps(nested))
    if member.watcher:
        parts.append(member.watcher.get_pattern_date(working_path))
    return " ".join(parts)
