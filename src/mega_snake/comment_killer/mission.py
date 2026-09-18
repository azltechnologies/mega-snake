"""The deterministic state machine the comment-killer kingpin relays.

The kingpin is a messenger: it runs one command, does exactly what the printed JSON says (write a
file, launch a subagent), and runs the next one. Every decision that would otherwise live in a
prompt -- the paths, the file names, the order of the stages, whether a handoff file came back
empty, whether the target is already dead -- is taken here, in code, so no model can improvise it.
"""

import json
import re
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any, Final, Optional

from mega_snake.comment_killer.constants import (
    ALREADY_RESOLVED,
    BRIEF_RESOURCE,
    CREW_DIR,
    FILE_NAMES,
    MISSION_DIR_NAME,
    MISSION_ID_PATTERN,
    SPOTTER_AGENT,
    SPOTTER_BRIEF_FILE,
    SPOTTER_MODEL,
    STATE_FILE,
    STAGE_BRIEF,
    STAGE_DONE,
    STAGE_HITMAN,
    STAGE_SPOTTER,
    STAGE_TRAPPER,
    STAGES,
    STATUS_DONE,
    STATUS_LAUNCH,
    STATUS_MISSING,
    STATUS_WRITE,
    STILL_VALID,
    VERDICT_SCAN_LINES,
)
from mega_snake.constants import APP_NAME, HITMAN_AGENT, MODULE_NAME, RESOURCES_DIR, TRAPPER_AGENT
from mega_snake.util.formatting import ValidationError
from mega_snake.util.props import get_property
from mega_snake.util.util import ensure_working_path

STILL_VALID_PATTERN = re.compile(rf"\b{STILL_VALID.replace(' ', r'\s+')}\b", re.IGNORECASE)
ALREADY_RESOLVED_PATTERN = re.compile(rf"\b{ALREADY_RESOLVED.replace(' ', r'\s+')}\b", re.IGNORECASE)

NO_MISSION_MESSAGE: str = "No mission in progress. Run `mgsnake comment-killer start` first."
# What every state this machine writes carries, and what every action built from one reads back.
STATE_FIELDS: Final[tuple[str, ...]] = ("stage", "outcome", "summary_from")
RESTART_HINT: str = "Delete the mission folder and start the mission again."
AMBIGUOUS_VERDICT_MESSAGE: str = (
    "The spotter's report does not state exactly one of STILL VALID or ALREADY RESOLVED near its "
    "top. Show this to the user and stop."
)


def _state_path(folder: Path) -> Path:
    """Locate the state file of one mission.

    It is a dotted file so that the mission folder reads as what the user came for -- the brief,
    the map, the trap and the hit report -- with the machinery out of the way.

    Parameters:
        folder: The mission folder.

    Raises:
        None

    Returns:
        Path: The JSON file holding the mission's stage.
    """
    return folder / STATE_FILE


def _read_state(folder: Path) -> dict[str, Any]:
    """Read the state of a mission, and refuse anything the machine could not act on.

    The file sits in the user's working path, beside the brief and the map, so it arrives
    hand-edited, truncated by a Ctrl-C or simply curious-fingered. Parsing is not enough: every
    caller reads `state["stage"]` and the two fields the final action reports, so a `{}` or a `[]`
    that parses cleanly would surface as a `KeyError` or a `TypeError` -- statuses that tell the
    user mgsnake is defective over a file mgsnake did not write. The shape is checked here instead,
    the way `Store._load` (§4.4) checks its own, and a broken state is reported rather than guessed:
    a mission is cheap to start again, and inferring the stage from the files on disk is precisely
    the improvisation this state machine exists to prevent.

    Parameters:
        folder: The mission folder.

    Raises:
        ValidationError: If the mission's state file is missing, unreadable, or not a state this
            machine could have written.

    Returns:
        dict[str, Any]: The mission state.
    """
    path = _state_path(folder)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"Could not read the mission state at '{path}': {error}") from error
    if not isinstance(state, dict):
        raise ValidationError(
            f"The mission state at '{path}' is a {type(state).__name__}, not an object. {RESTART_HINT}"
        )
    missing = [field for field in STATE_FIELDS if field not in state]
    if missing:
        raise ValidationError(f"The mission state at '{path}' is missing {', '.join(missing)}. {RESTART_HINT}")
    if state["stage"] not in STAGES:
        raise ValidationError(
            f"The mission state at '{path}' is on stage '{state['stage']}', which is not one of "
            f"{', '.join(STAGES)}. {RESTART_HINT}"
        )
    return state


def _write_state(folder: Path, state: dict[str, Any]) -> None:
    """Persist the state of a mission.

    Parameters:
        folder: The mission folder.
        state: The state to store.

    Raises:
        None

    Returns:
        None
    """
    _state_path(folder).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _missions_root() -> Path:
    """Locate the directory missions live under, without creating anything.

    Only ``start`` may offer to create the working path: every other command reads missions that
    must already exist, so a missing folder simply means there are none.

    Parameters:
        None

    Raises:
        None

    Returns:
        Path: The missions directory, which may not exist.
    """
    return Path(get_property("working_path")) / MISSION_DIR_NAME


def resolve_folder(mission: Optional[str] = None) -> Path:
    """Resolve which mission a command is talking about.

    A mission keeps its whole state inside its own folder, so two crews can work two comments at
    the same time without sharing anything: the orchestrator is handed the mission id when the
    mission opens and passes it back on every call. The id is the folder's own name, never a path,
    so nothing the user's working path contains -- a space, a quote -- ever travels through a shell.
    The newest mission is used only as a convenience for a human typing the command by hand.

    Parameters:
        mission: The mission id, when the caller names one.

    Raises:
        ValidationError: If the id is malformed or names no mission, or no mission exists at all.

    Returns:
        Path: The mission folder.
    """
    root = _missions_root()
    if mission:
        if not re.fullmatch(MISSION_ID_PATTERN, mission):
            raise ValidationError(
                f"'{mission}' is not a mission id. Pass the `mission` field of the last action as it is, "
                "a name such as 2026-09-16_01-00-34, never a path."
            )
        folder = root / mission
        if not _state_path(folder).is_file():
            raise ValidationError(f"There is no comment-killer mission '{mission}' under '{root}'.")
        return folder
    missions = sorted((path for path in root.glob("*") if _state_path(path).is_file()), reverse=True)
    if not missions:
        raise ValidationError(NO_MISSION_MESSAGE)
    return missions[0]


def stage_file(folder: Path, stage: str) -> Path:
    """Build the path of the file a stage produces.

    Parameters:
        folder: The mission folder.
        stage: One of the stages in ``FILE_NAMES``.

    Raises:
        None

    Returns:
        Path: The file that stage writes.
    """
    return folder / FILE_NAMES[stage]


def _written(path: Path) -> Optional[str]:
    """Read a handoff file, treating a missing or blank one as not written.

    Parameters:
        path: The file to read.

    Raises:
        None

    Returns:
        Optional[str]: Its content, or None when the file is missing or blank.
    """
    if not path.is_file():
        return None
    content = path.read_text(encoding="utf-8")
    return content if content.strip() else None


def verdict(report: str) -> Optional[str]:
    """Read the spotter's verdict from the top of its report.

    Parameters:
        report: The spotter's report.

    Raises:
        None

    Returns:
        Optional[str]: ``STILL VALID``, ``ALREADY RESOLVED``, or None when the top of the report
        states both or neither.
    """
    head = "\n".join(report.splitlines()[:VERDICT_SCAN_LINES])
    valid, resolved = bool(STILL_VALID_PATTERN.search(head)), bool(ALREADY_RESOLVED_PATTERN.search(head))
    if valid == resolved:
        return None
    return STILL_VALID if valid else ALREADY_RESOLVED


def _copy_spotter_brief(folder: Path) -> Path:
    """Place the spotter's brief inside the mission folder.

    The brief ships with the package and is copied per mission rather than installed into the
    user's repository: it is instructions for one agent on one job, not a file anybody maintains.

    Parameters:
        folder: The mission folder.

    Raises:
        None

    Returns:
        Path: The brief, ready to be pointed at.
    """
    source = resources.files(MODULE_NAME).joinpath(RESOURCES_DIR, CREW_DIR, BRIEF_RESOURCE)
    destination = folder / SPOTTER_BRIEF_FILE
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def _reserve_folder(root: Path) -> Path:
    """Create a folder no other mission is using.

    The timestamp names the mission for a human reading the working path, and a second mission
    opened inside the same second gets a suffix rather than the same folder: two crews are expected
    to run at once, and sharing a folder would mean one overwriting the other's brief.

    Parameters:
        root: The directory missions live under.

    Raises:
        None

    Returns:
        Path: The freshly created, exclusively owned mission folder.
    """
    stamp = f"{datetime.now():%Y-%m-%d_%H-%M-%S}"
    attempt = 0
    while True:
        suffix = "" if attempt == 0 else f"_{attempt + 1}"
        folder = root / f"{stamp}{suffix}"
        try:
            folder.mkdir(parents=True)
            return folder
        except FileExistsError:
            attempt += 1


def start(comment: Optional[str] = None) -> dict[str, Any]:
    """Open a mission, and move it past the brief when the comment came with the call.

    A comment given here is the brief, so the mission advances through the same validation as a
    brief the kingpin writes, and the first action is the spotter's launch rather than a request to
    write a file that already exists. A blank comment is no comment: nothing is written, and the
    first action asks for the brief.

    Parameters:
        comment: The code review comment, when the caller already has it; the kingpin writes it
            itself when this is None.

    Raises:
        UserDeclinedError: If the working path is missing and the user declines to create it.

    Returns:
        dict[str, Any]: The first action: the spotter's launch with a comment, the brief to write without one.
    """
    root = Path(ensure_working_path()) / MISSION_DIR_NAME
    folder = _reserve_folder(root)
    _copy_spotter_brief(folder)
    state: dict[str, Any] = {"stage": STAGE_BRIEF, "outcome": None, "summary_from": None}
    _write_state(folder, state)
    if comment and comment.strip():
        stage_file(folder, STAGE_BRIEF).write_text(comment, encoding="utf-8")
        return advance(folder.name)
    return action_for(folder, state)


def _resume_command(folder: Path) -> str:
    """Build the command that carries the mission on, exactly as the orchestrator must type it.

    Every action tells the orchestrator what to run next, and its guard accepts only the whole
    invocation: a bare `next --mission <id>` is neither a command the shell knows nor one the guard
    lets through, so the two would disagree the moment the orchestrator took an action literally.

    Parameters:
        folder: The mission folder.

    Raises:
        None

    Returns:
        str: The `next` invocation for this mission.
    """
    return f"{APP_NAME} comment-killer next --mission {folder.name}"


def action_for(folder: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Build the pending action for the stage the mission is waiting on.

    Parameters:
        folder: The mission folder.
        state: The mission state.

    Raises:
        None

    Returns:
        dict[str, Any]: The action to print.
    """
    stage: str = state["stage"]
    brief = str(stage_file(folder, STAGE_BRIEF))
    # The mission id travels in every action: it is what the orchestrator passes back on the next
    # call, and what lets two crews work two comments at once without sharing any state.
    resume = _resume_command(folder)
    if stage == STAGE_BRIEF:
        return {
            "status": STATUS_WRITE,
            "path": brief,
            "content": "the code review comment exactly as the user gave it, with nothing added",
            "mission": folder.name,
            "then": resume,
        }
    if stage == STAGE_SPOTTER:
        return {
            "status": STATUS_LAUNCH,
            "subagent_type": SPOTTER_AGENT,
            "model": SPOTTER_MODEL,
            "description": "Spotter: is the CR comment still valid?",
            "prompt": "\n".join(
                [
                    f"Your full brief for this job is in `{folder / SPOTTER_BRIEF_FILE}`. Read it "
                    "first and follow it exactly.",
                    "",
                    f"Brief file: {brief}",
                ]
            ),
            "mission": folder.name,
            "then": (
                f"write the agent's final response, verbatim, to {stage_file(folder, STAGE_SPOTTER)}, then run {resume}"
            ),
        }
    if stage == STAGE_TRAPPER:
        return {
            "status": STATUS_LAUNCH,
            "subagent_type": TRAPPER_AGENT,
            "description": "Trapper: set the trap",
            "prompt": "\n".join(
                [
                    f"Brief file: {brief}",
                    f"Map file: {stage_file(folder, STAGE_SPOTTER)}",
                    f"Trap file: {stage_file(folder, STAGE_TRAPPER)}",
                ]
            ),
            "mission": folder.name,
            "then": (
                f"the trapper writes its own trap to {stage_file(folder, STAGE_TRAPPER)}; when it returns, run {resume}"
            ),
        }
    if stage == STAGE_HITMAN:
        return {
            "status": STATUS_LAUNCH,
            "subagent_type": HITMAN_AGENT,
            "description": "Hitman: spring the trap",
            "prompt": "\n".join(
                [
                    f"Brief file: {brief}",
                    f"Map file: {stage_file(folder, STAGE_SPOTTER)}",
                    f"Trap file: {stage_file(folder, STAGE_TRAPPER)}",
                    f"Hit file: {stage_file(folder, STAGE_HITMAN)}",
                ]
            ),
            "mission": folder.name,
            "then": f"the hitman writes its own report; when it returns, run {resume}",
        }
    return {
        "status": STATUS_DONE,
        "mission": folder.name,
        "folder": str(folder),
        "summary_from": state["summary_from"],
        "outcome": state["outcome"],
    }


def advance(mission: Optional[str] = None) -> dict[str, Any]:
    """Validate the stage that just finished and return the next action.

    Parameters:
        mission: The mission id, when the caller names one.

    Raises:
        ValidationError: If no mission is in progress, or the spotter's verdict is ambiguous.

    Returns:
        dict[str, Any]: The next action for the kingpin.
    """
    folder = resolve_folder(mission)
    state = _read_state(folder)
    stage: str = state["stage"]
    if stage == STAGE_DONE:
        return action_for(folder, state)
    content = _written(stage_file(folder, stage))
    if content is None:
        return {
            "status": STATUS_MISSING,
            "path": str(stage_file(folder, stage)),
            "mission": folder.name,
            "message": (
                f"The {stage} stage has not produced its file yet, or it came back empty. Do what "
                f"the pending action says, then run `{_resume_command(folder)}` again."
            ),
            "pending": action_for(folder, state),
        }
    if stage == STAGE_SPOTTER:
        found = verdict(content)
        if found is None:
            raise ValidationError(f"{AMBIGUOUS_VERDICT_MESSAGE} Report: '{stage_file(folder, stage)}'.")
        if found == ALREADY_RESOLVED:
            state.update(stage=STAGE_DONE, outcome="already resolved", summary_from=str(stage_file(folder, stage)))
            _write_state(folder, state)
            return action_for(folder, state)
    if stage == STAGE_HITMAN:
        state.update(stage=STAGE_DONE, outcome="hit executed", summary_from=str(stage_file(folder, stage)))
    else:
        state["stage"] = STAGES[STAGES.index(stage) + 1]
    _write_state(folder, state)
    return action_for(folder, state)


def status(mission: Optional[str] = None) -> dict[str, Any]:
    """Return the pending action again, without advancing.

    Parameters:
        mission: The mission id, when the caller names one.

    Raises:
        ValidationError: If no mission is in progress.

    Returns:
        dict[str, Any]: The pending action.
    """
    folder = resolve_folder(mission)
    return action_for(folder, _read_state(folder))
