"""Tests for the raw-issue projection and the dynamic custom field resolution."""

import json
from pathlib import Path

import pytest

from mega_snake.constants import JIRA_SPRINT_FIELD_KEY, JIRA_STORY_POINTS_FIELD_KEY
from mega_snake.jira_api.projection import (
    HISTORIC_SPRINT_FIELD,
    HISTORIC_STORY_POINTS_FIELD,
    FieldIds,
    _pick,
    project_issue,
)
from mega_snake.util.store import SCOPE_REPO, Store

from tests.jira_api.jira_doubles import FakeResponse, make_client

RESOURCES = Path(__file__).resolve().parents[1] / "resources" / "jira"
STORY_POINTS_FIELD = "customfield_99999"
SPRINT_FIELD = "customfield_88888"
FIELD_IDS = FieldIds(story_points=STORY_POINTS_FIELD, sprint=SPRINT_FIELD)

EXPECTED_FIELD_KEYS = {
    "summary",
    "statuscategorychangedate",
    "created",
    "resolutiondate",
    "lastViewed",
    "updated",
    "description",
    "issuetype",
    "parent",
    "project",
    "status",
    "workratio",
    "issuerestriction",
    "priority",
    "labels",
    "storyPoints",
    "assignee",
    "creator",
    "reporter",
    "votes",
    "attachment",
    "attachmentsCount",
    "comment",
    "commentCount",
    "sprint",
}


def _load(name: str) -> list[dict]:
    """Read one of the Jira fixtures."""
    return json.loads((RESOURCES / name).read_text(encoding="utf-8"))


RAW_ISSUES = _load("board_issues_raw.json")
EXPECTED_ISSUES = _load("board_issues_projected.json")


@pytest.mark.parametrize(
    ("raw", "expected"), list(zip(RAW_ISSUES, EXPECTED_ISSUES)), ids=[issue["key"] for issue in RAW_ISSUES]
)
def test_projection_matches_the_reference_schema(raw: dict, expected: dict) -> None:
    """Every issue of the fixture is compared in full, field by field, against the expected output.

    Sampling one field would let a regression in any other one through, and this projection is the
    schema every Jira skill and every documented `jq` recipe reads.
    """
    assert project_issue(raw, FIELD_IDS) == expected


def test_projection_keys_are_exactly_the_documented_schema() -> None:
    """Set equality catches a field that went missing *and* one that was added by accident."""
    projected = project_issue(RAW_ISSUES[0], FIELD_IDS)

    assert set(projected["fields"].keys()) == EXPECTED_FIELD_KEYS
    assert list(projected.keys()) == ["id", "link", "key", "fields"]


def test_null_parent_becomes_dict_of_nulls_not_none() -> None:
    """`jq` renders `null | {id, key}` as a mapping of nulls, and the recipes depend on it.

    The documented way to find orphan stories is `.fields.parent.key == null`, which throws the
    moment `parent` itself becomes null.
    """
    projected = project_issue({"fields": {"parent": None}}, FIELD_IDS)

    assert projected["fields"]["parent"] is not None
    assert projected["fields"]["parent"] == {"id": None, "key": None}


@pytest.mark.parametrize("attachment", [None, [], "absent"])
@pytest.mark.parametrize("comment", [None, {}, "absent"])
def test_null_attachment_and_comment_do_not_raise(attachment, comment) -> None:
    """`.attachment[]` and `.comment.comments[]` had no `?`, so a null field aborted the whole run."""
    fields: dict = {}
    if attachment != "absent":
        fields["attachment"] = attachment
    if comment != "absent":
        fields["comment"] = comment

    projected = project_issue({"fields": fields}, FIELD_IDS)

    assert projected["fields"]["attachment"] == []
    assert projected["fields"]["attachmentsCount"] == 0
    assert projected["fields"]["comment"] == []


def test_pick_reads_the_requested_keys_only() -> None:
    """The helper projects exactly what was asked for, with None for anything absent."""
    assert _pick({"id": "1", "key": "A-1", "extra": "dropped"}, "id", "key", "missing") == {
        "id": "1",
        "key": "A-1",
        "missing": None,
    }


def test_field_ids_are_resolved_by_name_not_hardcoded(jira_workspace: Path) -> None:
    """`customfield_10016` and `customfield_10020` are allocated per Jira instance.

    The fixture puts story points in `customfield_99999` and also carries a decoy value in
    `customfield_10016`; the projected value must come from the resolved field, and the historic id
    must never be consulted.
    """
    assert jira_workspace.exists()
    client, _ = make_client(
        [
            FakeResponse(
                [
                    {"id": STORY_POINTS_FIELD, "name": "Story Points"},
                    {"id": SPRINT_FIELD, "name": "Sprint"},
                    {"id": HISTORIC_STORY_POINTS_FIELD, "name": "Something else"},
                ]
            )
        ]
    )

    field_ids = FieldIds.resolve(client)

    assert field_ids == FieldIds(story_points=STORY_POINTS_FIELD, sprint=SPRINT_FIELD)
    assert project_issue(RAW_ISSUES[0], field_ids)["fields"]["storyPoints"] == 5
    assert RAW_ISSUES[0]["fields"][HISTORIC_STORY_POINTS_FIELD] == 999, "the decoy must stay unread"


def test_field_ids_accept_the_alternative_story_points_name(jira_workspace: Path) -> None:
    """Team-managed projects call the field "Story point estimate" instead."""
    assert jira_workspace.exists()
    client, _ = make_client(
        [FakeResponse([{"id": "customfield_777", "name": "Story point estimate"}, {"id": "cf_1", "name": "Sprint"}])]
    )

    assert FieldIds.resolve(client).story_points == "customfield_777"


def test_field_ids_fall_back_to_the_historic_ids_with_a_warning(jira_workspace: Path) -> None:
    """When neither name exists, the historic ids keep the command working and say so."""
    assert jira_workspace.exists()
    client, _ = make_client([FakeResponse([{"id": "customfield_1", "name": "Flagged"}])])

    assert FieldIds.resolve(client) == FieldIds(
        story_points=HISTORIC_STORY_POINTS_FIELD, sprint=HISTORIC_SPRINT_FIELD
    )


def test_field_ids_are_cached_in_the_repository_scope(jira_workspace: Path) -> None:
    """Resolving them once per clone is enough; the second call makes no request at all."""
    assert jira_workspace.exists()
    client, session = make_client(
        [FakeResponse([{"id": STORY_POINTS_FIELD, "name": "Story Points"}, {"id": SPRINT_FIELD, "name": "Sprint"}])]
    )

    FieldIds.resolve(client)
    stored = Store.get_instance().items(SCOPE_REPO)
    second = FieldIds.resolve(client)

    assert stored[JIRA_STORY_POINTS_FIELD_KEY] == STORY_POINTS_FIELD
    assert stored[JIRA_SPRINT_FIELD_KEY] == SPRINT_FIELD
    assert second == FieldIds(story_points=STORY_POINTS_FIELD, sprint=SPRINT_FIELD)
    assert len(session.calls) == 1


def test_refresh_re_resolves_the_field_ids(jira_workspace: Path) -> None:
    """The negative of the caching test."""
    assert jira_workspace.exists()
    client, session = make_client(
        [
            FakeResponse([{"id": STORY_POINTS_FIELD, "name": "Story Points"}, {"id": SPRINT_FIELD, "name": "Sprint"}]),
            FakeResponse([{"id": "customfield_1", "name": "Story Points"}, {"id": "customfield_2", "name": "Sprint"}]),
        ]
    )

    FieldIds.resolve(client)
    refreshed = FieldIds.resolve(client, refresh=True)

    assert refreshed == FieldIds(story_points="customfield_1", sprint="customfield_2")
    assert len(session.calls) == 2
