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


def test_field_ids_fall_back_to_the_historic_ids_with_a_warning(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """When neither name exists, the historic ids keep the command working and say so.

    The warning is asserted, not just implied by the name: it is the only thing telling the user
    that `storyPoints` and `sprint` are about to come out null on this tenant.
    """
    assert jira_workspace.exists()
    client, _ = make_client([FakeResponse([{"id": "customfield_1", "name": "Flagged"}])])
    capsys.readouterr()

    assert FieldIds.resolve(client) == FieldIds(
        story_points=HISTORIC_STORY_POINTS_FIELD, sprint=HISTORIC_SPRINT_FIELD
    )
    warnings = capsys.readouterr().err
    assert HISTORIC_STORY_POINTS_FIELD in warnings
    assert HISTORIC_SPRINT_FIELD in warnings


def test_a_fallback_field_id_is_never_cached(jira_workspace: Path, capsys: pytest.CaptureFixture) -> None:
    """Caching a guess would silence the warning from the second run on, and never be undone.

    The fallback ids are the very defect the by-name resolution exists to fix. Persisting one as if
    it had been resolved makes the next run take the cache branch, skip the field endpoint, and
    project null *without saying anything*. `jira-issues --refresh` would not rescue that either: it
    re-queries the instance, but a run that falls back writes nothing, so the stale entry survives
    the refresh and answers again on the run after it. The only way out would be unsetting a key the
    user has no reason to suspect, precisely because the warning stopped. So: nothing is stored, and
    the second run warns again.
    """
    assert jira_workspace.exists()
    client, session = make_client(
        [
            FakeResponse([{"id": "customfield_1", "name": "Flagged"}]),
            FakeResponse([{"id": "customfield_1", "name": "Flagged"}]),
        ]
    )

    FieldIds.resolve(client)
    stored = Store.get_instance().items(SCOPE_REPO)
    capsys.readouterr()
    second = FieldIds.resolve(client)

    assert JIRA_STORY_POINTS_FIELD_KEY not in stored
    assert JIRA_SPRINT_FIELD_KEY not in stored
    assert second == FieldIds(story_points=HISTORIC_STORY_POINTS_FIELD, sprint=HISTORIC_SPRINT_FIELD)
    assert len(session.calls) == 2, "a fallback must not be answered from the cache"
    assert HISTORIC_STORY_POINTS_FIELD in capsys.readouterr().err, "the warning must keep firing"


def test_a_duplicated_field_name_resolves_to_the_first_and_is_never_cached(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """Two fields may share a display name, and then the choice between them is a guess.

    Common after a Server-to-Cloud migration, or on an instance holding both a company-managed and a
    team-managed project: a leftover text field ends up named `Sprint` next to the real Jira Software
    one. Two properties are pinned together because either one alone still lets the defect through:

    - **first wins**, which is what the docstring promises -- a dict comprehension over the field
      list keeps the *last* entry instead, so the leftover would outrank the real field;
    - **the guess is not cached**, so the warning keeps firing. Cached, it would be answered from the
      store on every later run with no warning at all, which is strictly worse than the fallback case
      because nothing would ever hint that the projection is wrong.

    The three ids are mutually distinct and none of them is the historic fallback, so no
    implementation that ignores the ordering, or that falls back, can pass by coincidence.
    """
    assert jira_workspace.exists()
    duplicated = [
        {"id": SPRINT_FIELD, "name": "Sprint"},
        {"id": "customfield_11500", "name": "sprint"},
        {"id": STORY_POINTS_FIELD, "name": "Story Points"},
    ]
    client, session = make_client([FakeResponse(duplicated), FakeResponse(duplicated)])

    first = FieldIds.resolve(client)
    stored = Store.get_instance().items(SCOPE_REPO)
    warning = capsys.readouterr().err
    second = FieldIds.resolve(client)

    assert first.sprint == SPRINT_FIELD, "the first declaration must win, not the last"
    assert first.sprint != "customfield_11500"
    assert first.sprint != HISTORIC_SPRINT_FIELD, "an ambiguous match is still a match, not a fallback"
    assert JIRA_SPRINT_FIELD_KEY not in stored, "a guess between two fields must not be cached"
    assert stored[JIRA_STORY_POINTS_FIELD_KEY] == STORY_POINTS_FIELD, "the unambiguous half is cached"
    assert "customfield_11500" in warning and SPRINT_FIELD in warning, "the warning must name both candidates"
    assert JIRA_SPRINT_FIELD_KEY in warning, "the warning must name the key that pins the right id"
    assert second == first
    assert len(session.calls) == 2, "an ambiguous match must not be answered from the cache"
    assert SPRINT_FIELD in capsys.readouterr().err, "the warning must keep firing on every run"


def test_the_field_that_did_resolve_is_still_cached(jira_workspace: Path) -> None:
    """The half that matched is real, so it is cached; only the guess is withheld."""
    assert jira_workspace.exists()
    client, _ = make_client([FakeResponse([{"id": SPRINT_FIELD, "name": "Sprint"}])])

    FieldIds.resolve(client)
    stored = Store.get_instance().items(SCOPE_REPO)

    assert stored[JIRA_SPRINT_FIELD_KEY] == SPRINT_FIELD
    assert JIRA_STORY_POINTS_FIELD_KEY not in stored


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


def test_an_unambiguous_alternative_name_beats_an_ambiguous_preferred_one(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """The order of `candidate_names` ranks likelihood, not trustworthiness.

    `Story Points` comes first because it is the usual name, but a migration can leave two fields
    carrying it while `Story point estimate` is declared exactly once -- and then the second name is
    the only id actually known, so guessing between the duplicates would be choosing a coin flip over
    a certainty. Being a real match, it is also cached, which the ambiguous guess never is.

    All three ids differ from each other and from the historic fallback, so neither an
    implementation that stops at the first name with any match nor one that falls back can pass by
    coincidence.
    """
    assert jira_workspace.exists()
    fields = [
        {"id": "customfield_20001", "name": "Story Points"},
        {"id": "customfield_20002", "name": "story points"},
        {"id": STORY_POINTS_FIELD, "name": "Story point estimate"},
        {"id": SPRINT_FIELD, "name": "Sprint"},
    ]
    client, _ = make_client([FakeResponse(fields)])

    resolved = FieldIds.resolve(client)

    warning = capsys.readouterr().err
    assert resolved.story_points == STORY_POINTS_FIELD, "the unambiguous name must win"
    assert resolved.story_points != "customfield_20001", "the first duplicate must not be guessed at"
    assert resolved.story_points != HISTORIC_STORY_POINTS_FIELD, "an alternative name is a match, not a fallback"
    assert Store.get_instance().items(SCOPE_REPO)[JIRA_STORY_POINTS_FIELD_KEY] == STORY_POINTS_FIELD
    assert warning == "", "a certainty was available, so there is nothing to warn about"


def test_a_refresh_that_resolves_nothing_drops_the_stale_cached_id(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """`--refresh` means the cache is not to be trusted, and that has to include not confirming it.

    A field renamed on the Jira side stops matching, so the run falls back and writes nothing. If the
    stale entry survived that, the *next* run would take the cache branch and answer with it again --
    and silently, because the cache branch never reaches the warning, so the one run that did warn
    would be the only one, with nothing changed by it.

    The negative half matters as much: the id that still resolves is written, not dropped along with
    the other, so a partial rename does not cost the half that is still correct.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_STORY_POINTS_FIELD_KEY, "customfield_30001")
    store.set(JIRA_SPRINT_FIELD_KEY, "customfield_30002")
    client, _ = make_client([FakeResponse([{"id": SPRINT_FIELD, "name": "Sprint"}])])

    resolved = FieldIds.resolve(client, refresh=True)

    stored = Store.get_instance().items(SCOPE_REPO)
    assert resolved.story_points == HISTORIC_STORY_POINTS_FIELD, "nothing matched, so the fallback answers"
    assert JIRA_STORY_POINTS_FIELD_KEY not in stored, "the id the refresh could not confirm must be gone"
    assert stored[JIRA_SPRINT_FIELD_KEY] == SPRINT_FIELD, "the half that did resolve is written, not dropped"
    assert stored[JIRA_SPRINT_FIELD_KEY] != "customfield_30002"
    assert HISTORIC_STORY_POINTS_FIELD in capsys.readouterr().err


def test_a_run_without_refresh_leaves_an_unconfirmed_cached_id_alone(jira_workspace: Path) -> None:
    """The negative of the drop: only a refresh is allowed to delete, never an ordinary run.

    An ordinary run reaches the field endpoint solely because *one* of the two ids was missing from
    the cache. Dropping the other one there would turn a half-warm cache into a cold one on every
    run, and would delete an id the user may have pinned by hand with `mgsnake config set` -- which
    is the documented remedy for the ambiguous case, so it must survive a run that cannot confirm it.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_STORY_POINTS_FIELD_KEY, "customfield_30001")
    client, _ = make_client([FakeResponse([{"id": SPRINT_FIELD, "name": "Sprint"}])])

    FieldIds.resolve(client)

    stored = Store.get_instance().items(SCOPE_REPO)
    assert stored[JIRA_STORY_POINTS_FIELD_KEY] == "customfield_30001", "a pinned id must survive a normal run"
    assert stored[JIRA_SPRINT_FIELD_KEY] == SPRINT_FIELD
