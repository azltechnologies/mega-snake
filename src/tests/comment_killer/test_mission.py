"""Tests for the comment-killer mission state machine.

Every decision the crew's orchestrator is not allowed to improvise lives in `mission.py`, so these
tests are written against what a wrong answer would cost: a stage skipped over an empty handoff, a
verdict read from a report that states both or neither, two missions sharing state, a folder that a
later command cannot find.
"""

import json
from pathlib import Path
from typing import Callable, Iterator
from unittest.mock import MagicMock, patch

import pytest

from mega_snake.comment_killer import mission
from mega_snake.comment_killer.constants import (
    ALREADY_RESOLVED,
    FILE_NAMES,
    MISSION_DIR_NAME,
    SPOTTER_AGENT,
    SPOTTER_BRIEF_FILE,
    SPOTTER_MODEL,
    STAGE_BRIEF,
    STAGE_HITMAN,
    STAGE_SPOTTER,
    STAGE_TRAPPER,
    STAGES,
    STATE_FILE,
    STATUS_DONE,
    STATUS_LAUNCH,
    STATUS_MISSING,
    STATUS_WRITE,
    STILL_VALID,
)
from mega_snake.constants import HITMAN_AGENT, TRAPPER_AGENT
from mega_snake.util.formatting import ValidationError

COMMENT: str = "to_dict() mutates the enum member instead of composing a value"
OTHER_COMMENT: str = "the retry policy swallows a 401 and calls it a success"


@pytest.fixture(name="working_path")
def fixture_working_path(tmp_path: Path) -> Iterator[Path]:
    """Point the crew at a throwaway working path.

    Parameters:
        tmp_path: Pytest's per-test directory.

    Raises:
        None

    Returns:
        Iterator[Path]: The working path the missions are created under.
    """
    with (
        patch("mega_snake.comment_killer.mission.ensure_working_path", return_value=str(tmp_path)),
        patch("mega_snake.comment_killer.mission.get_property", return_value=str(tmp_path)),
    ):
        yield tmp_path


def folder_of(working_path: Path, mission_id: str) -> Path:
    """Locate the folder of a mission from its id, the way the state machine does.

    Parameters:
        working_path: The working path the missions live under.
        mission_id: The id an action carries.

    Raises:
        None

    Returns:
        Path: The mission folder.
    """
    return working_path / MISSION_DIR_NAME / mission_id


def open_mission(working_path: Path, comment: str = COMMENT) -> Path:
    """Open a mission the way the kingpin does, and leave it waiting on the brief's `next`.

    `start` is called without the comment and the brief is then written to the path the action
    names, so every test below starts from the same stage the orchestrator's own flow reaches.

    Parameters:
        working_path: The working path the missions live under.
        comment: The code review comment to write as the brief.

    Raises:
        None

    Returns:
        Path: The mission folder.
    """
    action = mission.start()
    Path(action["path"]).write_text(comment, encoding="utf-8")
    return folder_of(working_path, action["mission"])


def test_start_writes_the_brief_and_hands_over_the_spotter_brief(working_path: Path) -> None:
    """A mission opens with the comment on disk and the spotter's brief beside it."""
    action = mission.start(COMMENT)
    folder = folder_of(working_path, action["mission"])

    assert folder.is_dir(), f"no mission folder named {action['mission']!r}"
    assert action["mission"] == folder.name
    assert action["mission"] != str(folder), "the action handed out a path instead of an id"
    assert (folder / FILE_NAMES[STAGE_BRIEF]).read_text(encoding="utf-8") == COMMENT
    assert (folder / SPOTTER_BRIEF_FILE).read_text(encoding="utf-8").strip(), "the spotter's brief came out empty"
    assert (folder / STATE_FILE).is_file(), "the mission did not record which stage it is on"


def test_start_without_a_comment_asks_the_orchestrator_to_write_it(working_path: Path) -> None:
    """With no comment at hand the first action is to write the brief, not to launch anyone."""
    action = mission.start()

    assert action["status"] == STATUS_WRITE
    assert action["path"] == str(folder_of(working_path, action["mission"]) / FILE_NAMES[STAGE_BRIEF])
    assert not Path(action["path"]).exists(), "the brief must be the orchestrator's to write"


def test_start_with_a_comment_files_it_and_launches_the_spotter(working_path: Path) -> None:
    """A comment given to `start` is the brief: the first action launches the spotter, not a rewrite of the brief."""
    action = mission.start(COMMENT)
    folder = folder_of(working_path, action["mission"])

    assert action["status"] == STATUS_LAUNCH
    assert action["status"] != STATUS_WRITE, "asked to write a brief that was already filed"
    assert action["subagent_type"] == SPOTTER_AGENT
    assert (folder / FILE_NAMES[STAGE_BRIEF]).read_text(encoding="utf-8") == COMMENT
    assert json.loads((folder / STATE_FILE).read_text(encoding="utf-8"))["stage"] == STAGE_SPOTTER
    assert mission.status(action["mission"]) == action, "the action start printed is not the one the mission waits on"


@pytest.mark.parametrize("blank", ["", "   ", "\n\t \n"], ids=repr)
def test_start_with_a_blank_comment_asks_for_the_brief_and_writes_nothing(working_path: Path, blank: str) -> None:
    """A blank comment is no comment: the mission waits on the brief, and no empty brief is filed."""
    action = mission.start(blank)
    folder = folder_of(working_path, action["mission"])

    assert action["status"] == STATUS_WRITE, repr(blank)
    assert not (folder / FILE_NAMES[STAGE_BRIEF]).exists(), f"{blank!r} was filed as a brief"
    assert json.loads((folder / STATE_FILE).read_text(encoding="utf-8"))["stage"] == STAGE_BRIEF


def test_a_stage_that_produced_nothing_does_not_advance(working_path: Path) -> None:
    """An empty handoff holds the mission where it is, and says what is pending.

    Handing a henchman an empty file is the failure this guards: it starts guessing, and comes back
    with something plausible and wrong.
    """
    folder = open_mission(working_path)
    mission.advance()  # brief -> spotter

    action = mission.advance()

    assert action["status"] == STATUS_MISSING
    assert action["path"] == str(folder / FILE_NAMES[STAGE_SPOTTER])
    assert action["pending"]["subagent_type"] == SPOTTER_AGENT
    assert json.loads((folder / STATE_FILE).read_text(encoding="utf-8"))["stage"] == STAGE_SPOTTER


def test_a_blank_report_counts_as_nothing_produced(working_path: Path) -> None:
    """A file holding only whitespace is not a report, however much the file system disagrees."""
    folder = open_mission(working_path)
    mission.advance()
    (folder / FILE_NAMES[STAGE_SPOTTER]).write_text("   \n\t\n", encoding="utf-8")

    assert mission.advance()["status"] == STATUS_MISSING


def test_the_whole_run_walks_spotter_then_trapper_then_hitman(working_path: Path) -> None:
    """Each stage launches its own agent, and the mission ends on the hitman's own report."""
    folder = open_mission(working_path)

    spotter = mission.advance()
    (folder / FILE_NAMES[STAGE_SPOTTER]).write_text(f"# {STILL_VALID}\n\nthe map", encoding="utf-8")
    trapper = mission.advance()
    (folder / FILE_NAMES[STAGE_TRAPPER]).write_text("the trap", encoding="utf-8")
    hitman = mission.advance()
    (folder / FILE_NAMES[STAGE_HITMAN]).write_text("the hit", encoding="utf-8")
    done = mission.advance()

    assert (spotter["status"], spotter["subagent_type"], spotter["model"]) == (
        STATUS_LAUNCH,
        SPOTTER_AGENT,
        SPOTTER_MODEL,
    )
    assert (trapper["status"], trapper["subagent_type"]) == (STATUS_LAUNCH, TRAPPER_AGENT)
    assert "model" not in trapper, "only the built-in agent is launched with an explicit model"
    assert (hitman["status"], hitman["subagent_type"]) == (STATUS_LAUNCH, HITMAN_AGENT)
    assert done["status"] == STATUS_DONE
    assert done["outcome"] == "hit executed"
    assert done["summary_from"] == str(folder / FILE_NAMES[STAGE_HITMAN])


def test_every_file_a_henchman_writes_is_named_in_its_own_prompt(working_path: Path) -> None:
    """A henchman that writes its own report is handed that report's path.

    Both of them are told never to guess a mission path, so a report whose path lives only in the
    orchestrator's instructions is a report nobody writes: the mission then waits on a file that
    will never appear, and `next` answers `missing` forever.
    """
    folder = open_mission(working_path)
    mission.advance()
    (folder / FILE_NAMES[STAGE_SPOTTER]).write_text(f"# {STILL_VALID}\n", encoding="utf-8")
    trapper = mission.advance()
    (folder / FILE_NAMES[STAGE_TRAPPER]).write_text("the trap", encoding="utf-8")
    hitman = mission.advance()

    trapper_lines = trapper["prompt"].splitlines()
    hitman_lines = hitman["prompt"].splitlines()

    assert f"Trap file: {folder / FILE_NAMES[STAGE_TRAPPER]}" in trapper_lines, "the trapper is never told where its trap goes"
    assert f"Hit file: {folder / FILE_NAMES[STAGE_HITMAN]}" in hitman_lines, "the hitman is never told where its report goes"
    assert f"Hit file: {folder / FILE_NAMES[STAGE_HITMAN]}" not in trapper_lines, "the trapper was handed the hitman's file"


def test_an_already_resolved_verdict_ends_the_mission_before_the_trapper(working_path: Path) -> None:
    """A target that is already dead is not worth a trap or a hit."""
    folder = open_mission(working_path)
    mission.advance()
    (folder / FILE_NAMES[STAGE_SPOTTER]).write_text(f"## {ALREADY_RESOLVED} in 4fac93c\n", encoding="utf-8")

    done = mission.advance()

    assert done["status"] == STATUS_DONE
    assert done["outcome"] == "already resolved"
    assert done["summary_from"] == str(folder / FILE_NAMES[STAGE_SPOTTER])
    assert not (folder / FILE_NAMES[STAGE_TRAPPER]).exists()


def test_the_mission_stays_done_once_it_is_done(working_path: Path) -> None:
    """Running `next` past the end repeats the outcome instead of walking off the stage list."""
    folder = open_mission(working_path)
    mission.advance()
    (folder / FILE_NAMES[STAGE_SPOTTER]).write_text(f"{ALREADY_RESOLVED}\n", encoding="utf-8")
    mission.advance()

    assert mission.advance()["status"] == STATUS_DONE
    assert mission.status()["status"] == STATUS_DONE


@pytest.mark.parametrize(
    "report, expected",
    [
        (f"# {STILL_VALID}\n\nstuff", STILL_VALID),
        (f"**{ALREADY_RESOLVED}** in commit abc123", ALREADY_RESOLVED),
        (f"still   valid", STILL_VALID),
        (f"{STILL_VALID} ... {ALREADY_RESOLVED}", None),
        ("the comment describes something that may or may not still apply", None),
        ("\n".join(["padding"] * 40 + [STILL_VALID]), None),
    ],
)
def test_the_verdict_is_read_from_the_top_and_must_be_unambiguous(report: str, expected: str) -> None:
    """One verdict, stated near the top, or none at all.

    A report that states both, neither, or states one only after pages of prose is not a verdict the
    crew may act on: choosing for it is how a mission proceeds against a bug that was fixed weeks
    ago, or stops against one that is still live.
    """
    assert mission.verdict(report) == expected, f"wrong verdict for: {report[:40]!r}"


def test_an_ambiguous_verdict_stops_the_mission(working_path: Path) -> None:
    """The ambiguity is reported, and the mission does not move."""
    folder = open_mission(working_path)
    mission.advance()
    (folder / FILE_NAMES[STAGE_SPOTTER]).write_text("it is unclear\n", encoding="utf-8")

    with pytest.raises(ValidationError) as error:
        mission.advance()

    assert str(folder / FILE_NAMES[STAGE_SPOTTER]) in str(error.value)
    assert json.loads((folder / STATE_FILE).read_text(encoding="utf-8"))["stage"] == STAGE_SPOTTER


def test_two_missions_advance_independently(working_path: Path) -> None:
    """Two crews, two comments, no shared state: each action names the mission it belongs to."""
    first = open_mission(working_path, COMMENT)
    second = open_mission(working_path, OTHER_COMMENT)

    first_action = mission.advance(first.name)
    mission.advance(second.name)  # brief -> spotter, for the second crew only
    (second / FILE_NAMES[STAGE_SPOTTER]).write_text(f"{STILL_VALID}\n", encoding="utf-8")
    mission.advance(second.name)
    second_action = mission.status(second.name)

    assert first != second
    assert first_action["mission"] == first.name
    assert first_action["subagent_type"] == SPOTTER_AGENT, "the first mission moved with the second one"
    assert second_action["subagent_type"] == TRAPPER_AGENT
    assert (first / FILE_NAMES[STAGE_BRIEF]).read_text(encoding="utf-8") == COMMENT
    assert (second / FILE_NAMES[STAGE_BRIEF]).read_text(encoding="utf-8") == OTHER_COMMENT


def test_without_a_mission_the_newest_one_is_used(working_path: Path) -> None:
    """Typing the command by hand should not mean typing a timestamp."""
    open_mission(working_path, COMMENT)
    newest = open_mission(working_path, OTHER_COMMENT)

    assert mission.status()["mission"] == newest.name


def test_a_folder_that_is_not_a_mission_is_refused(working_path: Path) -> None:
    """A folder under the missions root without the crew's own state file is not a mission."""
    stranger = folder_of(working_path, "not-a-mission")
    stranger.mkdir(parents=True)

    with pytest.raises(ValidationError) as error:
        mission.status(stranger.name)

    assert str(error.value) == (
        f"There is no comment-killer mission 'not-a-mission' under '{working_path / MISSION_DIR_NAME}'."
    )


@pytest.mark.parametrize(
    "given",
    ["/tmp/comment_killer/2026-09-16_01-00-34", "../2026-09-16_01-00-34", "2026-09-16 01-00-34", "a/b", "x;ls"],
    ids=repr,
)
def test_a_mission_is_named_by_its_id_never_by_a_path(working_path: Path, given: str) -> None:
    """A path, a traversal or anything a shell would split is refused before the file system is touched."""
    real = open_mission(working_path)

    with pytest.raises(ValidationError) as error:
        mission.advance(given)

    assert str(error.value) == (
        f"'{given}' is not a mission id. Pass the `mission` field of the last action as it is, "
        "a name such as 2026-09-16_01-00-34, never a path."
    )
    assert json.loads((real / STATE_FILE).read_text(encoding="utf-8"))["stage"] == STAGE_BRIEF, "a mission moved"


def test_a_mission_under_a_path_with_spaces_runs_by_its_id(tmp_path: Path) -> None:
    """The working path is the user's, and may hold spaces: the id is what keeps that out of every command."""
    spaced = tmp_path / "My Projects" / "app repo"
    spaced.mkdir(parents=True)
    with (
        patch("mega_snake.comment_killer.mission.ensure_working_path", return_value=str(spaced)),
        patch("mega_snake.comment_killer.mission.get_property", return_value=str(spaced)),
    ):
        opened = mission.start()
        Path(opened["path"]).write_text(COMMENT, encoding="utf-8")
        advanced = mission.advance(opened["mission"])

    assert " " not in opened["mission"], opened["mission"]
    assert advanced["status"] == STATUS_LAUNCH
    assert advanced["subagent_type"] == SPOTTER_AGENT
    assert f"Brief file: {spaced / MISSION_DIR_NAME / opened['mission'] / FILE_NAMES[STAGE_BRIEF]}" in (
        advanced["prompt"].splitlines()
    )


@pytest.mark.parametrize("call", [mission.advance, mission.status], ids=["next", "status"])
def test_only_start_may_offer_to_create_the_working_path(tmp_path: Path, call: MagicMock) -> None:
    """Without the folder there are no missions: `next` and `status` say so, and never prompt or create it."""
    absent = tmp_path / "workspace_temp"
    prompt = MagicMock(side_effect=AssertionError("prompted for the working path"))
    with (
        patch("mega_snake.comment_killer.mission.ensure_working_path", prompt),
        patch("mega_snake.comment_killer.mission.get_property", return_value=str(absent)),
    ):
        with pytest.raises(ValidationError) as error:
            call()

    assert str(error.value) == mission.NO_MISSION_MESSAGE
    prompt.assert_not_called()
    assert not absent.exists(), "the working path was created by a command that only reads missions"


def test_asking_for_a_mission_when_none_was_started(working_path: Path) -> None:
    """The first thing a new user does wrong gets an answer that says what to run."""
    with pytest.raises(ValidationError) as error:
        mission.advance()

    assert "start" in str(error.value)


def test_an_unreadable_state_file_is_reported_not_guessed(working_path: Path) -> None:
    """A corrupt state file stops the mission instead of resetting it to a stage of our choosing."""
    folder = open_mission(working_path)
    (folder / STATE_FILE).write_text("{not json", encoding="utf-8")

    with pytest.raises(ValidationError) as error:
        mission.status(folder.name)

    assert STATE_FILE in str(error.value)


@pytest.mark.parametrize(
    "stored, expected_reason",
    [
        ("[]", "is a list, not an object."),
        ('"brief"', "is a str, not an object."),
        ("{}", "is missing stage, outcome, summary_from."),
        ('{"stage": "spotter"}', "is missing outcome, summary_from."),
        ('{"stage": "nonsense", "outcome": null, "summary_from": null}', "is on stage 'nonsense', which is not one of"),
    ],
    ids=["list", "string", "empty-object", "half-written", "unknown-stage"],
)
@pytest.mark.parametrize("call", [mission.advance, mission.status], ids=["next", "status"])
def test_a_state_this_machine_never_wrote_is_reported_as_the_users_file(
    working_path: Path, call: Callable[[str], dict], stored: str, expected_reason: str
) -> None:
    """A hand-edited state file is the user's, so it is reported -- never read as a bug, never guessed.

    Each of these parses cleanly and then breaks somewhere else: `{}` and a half-written object reach
    a `KeyError` on the field the action reports, and a list reaches a `TypeError`. Both surface as
    statuses that accuse mgsnake of being defective over a file it did not write.
    """
    folder = open_mission(working_path)
    (folder / STATE_FILE).write_text(stored, encoding="utf-8")

    with pytest.raises(ValidationError) as error:
        call(folder.name)

    message = str(error.value)
    assert str(folder / STATE_FILE) in message, message
    assert expected_reason in message, message
    assert message.endswith("Delete the mission folder and start the mission again."), message


def test_a_state_this_machine_wrote_is_accepted_at_every_stage(working_path: Path) -> None:
    """The check must admit every stage the machine itself reaches, or it would refuse its own files.

    The universe is walked rather than sampled: a check written against a list of stages someone
    remembers is one stage away from stopping a mission mid-run.
    """
    folder = open_mission(working_path)
    for stage in STAGES:
        (folder / STATE_FILE).write_text(
            json.dumps({"stage": stage, "outcome": None, "summary_from": None}), encoding="utf-8"
        )

        assert mission.status(folder.name)["mission"] == folder.name, f"the machine refused its own '{stage}' state"
