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

    `extra_args` is included, and that is the point: `to_dict` emits it verbatim, so the Windows
    overrides on the Gradle build tasks (`{"windows": {"command": ..., "args": ...}}`) and a
    launch's `port`/`program` entries are as much a reference site as `command` is. Scanning only
    `command` and `args` would leave them outside the walk this function backs.

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
        str: Every interpolatable field, joined; JSON for the nested ones so no value is lost.
    """
    parts: list[str] = [getattr(member, "command", None) or "", *member.args]
    for nested in (member.extra_args, getattr(member, "env", None)):
        if nested:
            parts.append(json.dumps(nested))
    if member.watcher:
        parts.append(member.watcher.get_pattern_date(working_path))
    return " ".join(parts)
