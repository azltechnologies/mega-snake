"""Tests for the raw-issue projection and the dynamic custom field resolution."""

import json
from pathlib import Path

import pytest

from mega_snake.constants import (
    JIRA_SPRINT_FIELD_CACHE_KEY,
    JIRA_SPRINT_FIELD_KEY,
    JIRA_STORY_POINTS_FIELD_CACHE_KEY,
    JIRA_STORY_POINTS_FIELD_KEY,
)
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
# Distinct from every id any fixture below declares and from both historic fallbacks, so a pin can
# only be returned by code that actually read the pin key.
PINNED_FIELD = "customfield_77777"
AMBIGUOUS_SPRINT_FIELDS = [
    {"id": "cf_A", "name": "Sprint"},
    {"id": "cf_B", "name": "sprint"},
    {"id": STORY_POINTS_FIELD, "name": "Story Points"},
]
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

    assert JIRA_STORY_POINTS_FIELD_CACHE_KEY not in stored
    assert JIRA_SPRINT_FIELD_CACHE_KEY not in stored
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
    assert JIRA_SPRINT_FIELD_CACHE_KEY not in stored, "a guess between two fields must not be cached"
    assert stored[JIRA_STORY_POINTS_FIELD_CACHE_KEY] == STORY_POINTS_FIELD, "the unambiguous half is cached"
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

    assert stored[JIRA_SPRINT_FIELD_CACHE_KEY] == SPRINT_FIELD
    assert JIRA_STORY_POINTS_FIELD_CACHE_KEY not in stored


def test_field_ids_are_cached_in_the_repository_scope(jira_workspace: Path) -> None:
    """Resolving them once per clone is enough; the second call makes no request at all."""
    assert jira_workspace.exists()
    client, session = make_client(
        [FakeResponse([{"id": STORY_POINTS_FIELD, "name": "Story Points"}, {"id": SPRINT_FIELD, "name": "Sprint"}])]
    )

    FieldIds.resolve(client)
    stored = Store.get_instance().items(SCOPE_REPO)
    second = FieldIds.resolve(client)

    assert stored[JIRA_STORY_POINTS_FIELD_CACHE_KEY] == STORY_POINTS_FIELD
    assert stored[JIRA_SPRINT_FIELD_CACHE_KEY] == SPRINT_FIELD
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
    assert Store.get_instance().items(SCOPE_REPO)[JIRA_STORY_POINTS_FIELD_CACHE_KEY] == STORY_POINTS_FIELD
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
    store.set(JIRA_STORY_POINTS_FIELD_CACHE_KEY, "customfield_30001")
    store.set(JIRA_SPRINT_FIELD_CACHE_KEY, "customfield_30002")
    client, _ = make_client([FakeResponse([{"id": SPRINT_FIELD, "name": "Sprint"}])])

    resolved = FieldIds.resolve(client, refresh=True)

    stored = Store.get_instance().items(SCOPE_REPO)
    assert resolved.story_points == HISTORIC_STORY_POINTS_FIELD, "nothing matched, so the fallback answers"
    assert JIRA_STORY_POINTS_FIELD_CACHE_KEY not in stored, "the id the refresh could not confirm must be gone"
    assert stored[JIRA_SPRINT_FIELD_CACHE_KEY] == SPRINT_FIELD, "the half that did resolve is written, not dropped"
    assert stored[JIRA_SPRINT_FIELD_CACHE_KEY] != "customfield_30002"
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
    store.set(JIRA_STORY_POINTS_FIELD_CACHE_KEY, "customfield_30001")
    client, _ = make_client([FakeResponse([{"id": SPRINT_FIELD, "name": "Sprint"}])])

    FieldIds.resolve(client)

    stored = Store.get_instance().items(SCOPE_REPO)
    assert stored[JIRA_STORY_POINTS_FIELD_CACHE_KEY] == "customfield_30001", "a pinned id must survive a normal run"
    assert stored[JIRA_SPRINT_FIELD_CACHE_KEY] == SPRINT_FIELD


def test_a_pin_is_honoured_even_when_the_other_field_forces_a_lookup(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """The regression test for the pin that sat on disk unread.

    The ambiguity warning tells the user to run `mgsnake config set jira.field.sprint <id>`. While
    both ids were answered together (`if cached_story_points and cached_sprint`), doing exactly that
    changed nothing: story points were not cached yet, so the all-or-nothing branch was skipped, the
    field endpoint was queried, and `_match` guessed at the ambiguous name again -- with the pin
    sitting in the state file, never read. The documented remedy was inert.

    `cf_A` is what the guess would return and it is asserted absent, so a resolver that reaches
    `_match` for a pinned field cannot pass. The warning is asserted empty for the same reason: a pin
    settles the question, so there is nothing left to warn about.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_SPRINT_FIELD_KEY, PINNED_FIELD)
    client, _ = make_client([FakeResponse(AMBIGUOUS_SPRINT_FIELDS)])

    resolved = FieldIds.resolve(client)

    assert resolved.sprint == PINNED_FIELD, "the pin must answer, not the guess"
    assert resolved.sprint != "cf_A", "cf_A is what _match would have guessed"
    assert resolved.story_points == STORY_POINTS_FIELD, "the unpinned field still resolves normally"
    assert capsys.readouterr().err == "", "a pinned field is settled, so nothing is ambiguous"


def test_a_pin_is_never_overwritten_by_a_clean_match(jira_workspace: Path) -> None:
    """Nothing in the codebase writes the pin key, so a clean resolution cannot silently replace it.

    Before the split, `store.set` wrote the resolved id straight onto the key the user had pinned, so
    a pin lasted exactly until the next run whose lookup happened to succeed -- and it disappeared
    without a message, since overwriting a cache entry is not worth reporting and the code could not
    tell the two apart. The cache entry below is asserted to exist *separately*, which is the whole
    point: both facts are recorded, and neither destroys the other.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_SPRINT_FIELD_KEY, PINNED_FIELD)
    client, _ = make_client([FakeResponse([{"id": "cf_9001", "name": "Sprint"}])])

    resolved = FieldIds.resolve(client)

    stored = store.items(SCOPE_REPO)
    assert resolved.sprint == PINNED_FIELD
    assert stored[JIRA_SPRINT_FIELD_KEY] == PINNED_FIELD, "the pin survives untouched"
    assert stored[JIRA_SPRINT_FIELD_KEY] != "cf_9001"
    assert JIRA_SPRINT_FIELD_CACHE_KEY not in stored, "a pinned field is never looked up, so nothing is cached"


def test_refresh_honours_a_pin_and_only_drops_the_cache(jira_workspace: Path) -> None:
    """`--refresh` distrusts what the tool worked out, never what the user decided.

    A pin is not a stale guess to be revisited: the user wrote it precisely because the automatic
    resolution was wrong, so a flag that deleted it would make the documented remedy last exactly one
    run. The cached entry beside it is dropped in the same call, which is the behaviour `--refresh`
    exists for -- both halves are asserted here so neither can regress into the other.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_SPRINT_FIELD_KEY, PINNED_FIELD)
    store.set(JIRA_STORY_POINTS_FIELD_CACHE_KEY, "cf_STALE")
    client, _ = make_client([FakeResponse([{"id": "cf_only", "name": "Flagged"}])])

    resolved = FieldIds.resolve(client, refresh=True)

    stored = store.items(SCOPE_REPO)
    assert resolved.sprint == PINNED_FIELD, "the pin answers even under --refresh"
    assert stored[JIRA_SPRINT_FIELD_KEY] == PINNED_FIELD, "the pin is still on disk"
    assert JIRA_STORY_POINTS_FIELD_CACHE_KEY not in stored, "the unconfirmed cache entry is dropped"
    assert resolved.story_points == HISTORIC_STORY_POINTS_FIELD, "nothing matched, so the fallback answers"


def test_refresh_drops_a_pinned_fields_own_stale_cache_without_any_http_call(jira_workspace: Path) -> None:
    """Regression test: a pinned field's `.cached` sibling used to survive `--refresh` untouched.

    `_cache` is only reached from the branch that actually looks a field up, and a pinned field short
    -circuits before that with `continue` -- so with *both* fields pinned, `--refresh` never queried
    the field endpoint and never dropped anything, contradicting both `_cache`'s own docstring ("The
    drop is the other half of what `--refresh` promises") and the fragment's documented behaviour. The
    stale entry would then resurface the moment the pin was removed, answering with exactly the guess
    `--refresh` was asked to distrust.

    All three consequences are asserted together, as the CR comment asks: the pins survive untouched,
    both stale `.cached` entries are gone, and not a single HTTP call was made -- a pinned field must
    never reach the field endpoint, refresh or not.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_SPRINT_FIELD_KEY, PINNED_FIELD)
    store.set(JIRA_SPRINT_FIELD_CACHE_KEY, "cf_STALE_SPRINT")
    store.set(JIRA_STORY_POINTS_FIELD_KEY, STORY_POINTS_FIELD)
    store.set(JIRA_STORY_POINTS_FIELD_CACHE_KEY, "cf_STALE_STORY_POINTS")
    client, session = make_client([])

    resolved = FieldIds.resolve(client, refresh=True)

    stored = store.items(SCOPE_REPO)
    assert resolved == FieldIds(story_points=STORY_POINTS_FIELD, sprint=PINNED_FIELD)
    assert stored[JIRA_SPRINT_FIELD_KEY] == PINNED_FIELD, "the pin is still on disk"
    assert stored[JIRA_STORY_POINTS_FIELD_KEY] == STORY_POINTS_FIELD, "the other pin is still on disk"
    assert JIRA_SPRINT_FIELD_CACHE_KEY not in stored, "the stale cache behind the sprint pin is dropped"
    assert JIRA_STORY_POINTS_FIELD_CACHE_KEY not in stored, "the stale cache behind the other pin is dropped"
    assert session.calls == [], "a pinned field must never reach the field endpoint, even under --refresh"


def test_refresh_drops_a_pinned_fields_stale_cache_while_the_other_field_is_still_looked_up(
    jira_workspace: Path,
) -> None:
    """The mixed case from the CR comment's own repro: only `sprint` is pinned.

    Story points still has to be looked up (one HTTP call), and that lookup must not be the thing
    that happens to drop the sprint's stale cache -- it is a different key entirely. This pins the
    call count at exactly one, so a fix that accidentally makes the pinned field reach the endpoint
    too (instead of being dropped directly in `resolve`) would be caught here.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_SPRINT_FIELD_KEY, PINNED_FIELD)
    store.set(JIRA_SPRINT_FIELD_CACHE_KEY, "cf_STALE_SPRINT")
    client, session = make_client([FakeResponse([{"id": STORY_POINTS_FIELD, "name": "Story Points"}])])

    resolved = FieldIds.resolve(client, refresh=True)

    stored = store.items(SCOPE_REPO)
    assert resolved == FieldIds(story_points=STORY_POINTS_FIELD, sprint=PINNED_FIELD)
    assert stored[JIRA_SPRINT_FIELD_KEY] == PINNED_FIELD, "the pin is still on disk"
    assert JIRA_SPRINT_FIELD_CACHE_KEY not in stored, "the stale cache behind the pin is dropped"
    assert stored[JIRA_STORY_POINTS_FIELD_CACHE_KEY] == STORY_POINTS_FIELD, "the looked-up field is still cached"
    assert len(session.calls) == 1, "only the unpinned field may reach the endpoint"


def _write_legacy_state(repo: Path, values: dict) -> None:
    """Write a repo state file the way the pre-pin code left it: no version marker.

    Deliberately not built with `store.set`, which stamps the marker on its first write -- doing so
    would produce a *current* file and quietly make every migration test assert nothing. The whole
    point of a legacy fixture is the absence of that marker.
    """
    state_file = repo / ".git" / "mgsnake" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(values), encoding="utf-8")
    Store.reset_instance()


def test_a_legacy_bare_cache_is_migrated_to_the_cache_key(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """Regression test for the migration `_migrate_legacy_cache` performs.

    Before the pin/cache split, `resolve` wrote the id it worked out onto the bare key itself, which
    is what a clone that ran an earlier commit of this branch still has on disk -- an unmarked file,
    since the marker did not exist then. Reading that leftover as a pin would freeze
    `jira-issues --refresh` on the stale id forever, in silence, so the first `resolve()` must
    relocate it onto the `.cached` key where a fresh lookup or `--refresh` can still reach it.
    """
    _write_legacy_state(jira_workspace, {JIRA_SPRINT_FIELD_KEY: SPRINT_FIELD})
    client, _ = make_client([FakeResponse([{"id": STORY_POINTS_FIELD, "name": "Story Points"}])])

    resolved = FieldIds.resolve(client)

    stored = Store.get_instance().items(SCOPE_REPO)
    assert resolved.sprint == SPRINT_FIELD, "the migrated value still answers the same run"
    assert resolved.story_points == STORY_POINTS_FIELD
    assert JIRA_SPRINT_FIELD_KEY not in stored, "the bare key must not survive as a fake pin"
    assert stored[JIRA_SPRINT_FIELD_CACHE_KEY] == SPRINT_FIELD, "the value is preserved, only relocated"
    assert "Moved" in capsys.readouterr().err


def test_a_pin_written_by_config_set_is_never_migrated(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """The regression that a shape-based migration could not avoid, and the reason for the marker.

    An ambiguous field is never cached, by design -- so the pin the ambiguity warning tells the user
    to create is a bare key with **no** `.cached` sibling, which is byte-for-byte the shape a legacy
    cache has. A migration keyed on that shape relocated the pin on the very next run and
    `--refresh` then discarded it, leaving the user back on the historic fallback: the original
    defect, rebuilt inside its own fix.

    `Store.set` stamps the version marker, so a pin made the documented way is stamped before the
    migration ever looks. Asserted on the store *and* on the resolved value, and with the info
    message asserted absent -- a migration that ran and happened to leave the value reachable would
    still be a bug.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_SPRINT_FIELD_KEY, PINNED_FIELD)
    capsys.readouterr()
    client, _ = make_client([FakeResponse(AMBIGUOUS_SPRINT_FIELDS)])

    resolved = FieldIds.resolve(client)

    stored = store.items(SCOPE_REPO)
    assert stored[JIRA_SPRINT_FIELD_KEY] == PINNED_FIELD, "the pin must stay a pin"
    assert JIRA_SPRINT_FIELD_CACHE_KEY not in stored, "the pin must not be relocated to the cache key"
    assert resolved.sprint == PINNED_FIELD
    assert resolved.sprint != "cf_A", "cf_A is what the ambiguous guess would have returned"
    assert "Moved" not in capsys.readouterr().err, "nothing was migrated, so nothing is reported"


def test_a_legacy_file_is_migrated_only_once(jira_workspace: Path, capsys: pytest.CaptureFixture) -> None:
    """After the first run the scope is marked, so a pin created later is safe.

    This is the half that makes the marker worth its cost: without it the migration has no memory,
    so every run re-evaluates the same shape and a pin written between two runs is indistinguishable
    from the leftover the first run just moved.
    """
    _write_legacy_state(jira_workspace, {JIRA_SPRINT_FIELD_KEY: SPRINT_FIELD})
    client, _ = make_client([FakeResponse([{"id": STORY_POINTS_FIELD, "name": "Story Points"}])])
    FieldIds.resolve(client)
    capsys.readouterr()

    store = Store.get_instance()
    store.unset(JIRA_SPRINT_FIELD_CACHE_KEY, SCOPE_REPO)
    store.set(JIRA_SPRINT_FIELD_KEY, PINNED_FIELD)
    client, _ = make_client([])

    resolved = FieldIds.resolve(client)

    stored = store.items(SCOPE_REPO)
    assert stored[JIRA_SPRINT_FIELD_KEY] == PINNED_FIELD, "the later pin survives the second run"
    assert JIRA_SPRINT_FIELD_CACHE_KEY not in stored
    assert resolved.sprint == PINNED_FIELD
    assert "Moved" not in capsys.readouterr().err, "the migration must not run a second time"


def test_a_bare_key_is_left_alone_when_a_cache_key_already_exists(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """The second guard: both keys set cannot be a legacy leftover, so it is never touched.

    The older code wrote only the bare key, so a file carrying both -- even an unmarked one -- was
    edited by hand or by a newer run. This guard is redundant with the marker for any clone that
    reached the current code, and is kept for the file a user assembles themselves.
    """
    _write_legacy_state(
        jira_workspace, {JIRA_SPRINT_FIELD_KEY: PINNED_FIELD, JIRA_SPRINT_FIELD_CACHE_KEY: "cf_STALE_CACHE"}
    )
    client, _ = make_client([FakeResponse([{"id": STORY_POINTS_FIELD, "name": "Story Points"}])])

    resolved = FieldIds.resolve(client)

    stored = Store.get_instance().items(SCOPE_REPO)
    assert resolved.sprint == PINNED_FIELD, "the pin still answers, untouched"
    assert stored[JIRA_SPRINT_FIELD_KEY] == PINNED_FIELD
    assert stored[JIRA_SPRINT_FIELD_CACHE_KEY] == "cf_STALE_CACHE", "the cache entry is left exactly as it was"
    assert "Moved" not in capsys.readouterr().err


def test_a_pinned_field_costs_no_http_call_when_both_are_settled(jira_workspace: Path) -> None:
    """A pin is as good as a cache entry for skipping the lookup, asserted by equality against zero.

    Otherwise pinning one field would mean paying for the field endpoint on every single run, which
    is the cost the cache exists to avoid -- and the user would have no way to stop paying it.
    """
    assert jira_workspace.exists()
    store = Store.get_instance()
    store.set(JIRA_SPRINT_FIELD_KEY, PINNED_FIELD)
    store.set(JIRA_STORY_POINTS_FIELD_CACHE_KEY, STORY_POINTS_FIELD)
    client, session = make_client([])

    resolved = FieldIds.resolve(client)

    assert resolved == FieldIds(story_points=STORY_POINTS_FIELD, sprint=PINNED_FIELD)
    assert len(session.calls) == 0


def test_outside_a_repository_nothing_is_cached_and_the_ids_still_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repo scope needs a `.git`, and `jira-issues --output` does not.

    With `-o` naming a destination the command never touches the working path, so it runs perfectly
    well from a directory that is not a clone -- and then there is nowhere to write a per-clone cache.
    Resolution must still work (the ids come from the instance, not from the store), and the write
    must be skipped rather than raising: `Store.set(..., SCOPE_REPO)` outside a repository is a
    `ClickException`, which would turn a legitimate invocation into an error about a scope the user
    never asked for.

    Asserted with a second run that queries the endpoint again — a cache that did not happen has to
    be visible as a cache miss, not merely as the absence of a file nobody looked for.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    monkeypatch.chdir(tmp_path)
    Store.reset_instance()
    fields = [{"id": STORY_POINTS_FIELD, "name": "Story Points"}, {"id": SPRINT_FIELD, "name": "Sprint"}]
    client, session = make_client([FakeResponse(fields), FakeResponse(fields)])

    first = FieldIds.resolve(client)
    second = FieldIds.resolve(client)

    assert first == FieldIds(story_points=STORY_POINTS_FIELD, sprint=SPRINT_FIELD), "resolution still works"
    assert second == first
    assert len(session.calls) == 2, "nothing was cached, so the second run queries again"
    assert Store.get_instance().has_scope(SCOPE_REPO) is False
    Store.reset_instance()


def test_an_unusable_repo_store_does_not_make_the_migration_the_thing_that_fails(
    jira_workspace: Path, capsys: pytest.CaptureFixture
) -> None:
    """The migration reads the repo scope strictly, so it has to degrade like every other reader.

    `is_current_layout` and `items(SCOPE_REPO)` both go through `_load` directly rather than
    `_load_gracefully`, because a single named scope must fail loudly for `set`/`unset`. Running one
    of them unguarded at the top of `resolve` would convert a corrupt state file -- which the store
    is built to degrade around, warning on stderr and carrying on -- into a hard failure of
    `jira-issues`, and from a code path the user never asked to run.

    So: nothing is migrated, the endpoint is still queried, the ids still resolve, and the only thing
    on stderr is the store's own warning plus the ordinary fallback notice. The field names below
    match nothing on purpose, so `_cache` writes nothing and the run completes -- isolating the
    migration's own behaviour from the separate question of writing to a broken scope.
    """
    state_file = jira_workspace / ".git" / "mgsnake" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{not json at all", encoding="utf-8")
    Store.reset_instance()
    client, session = make_client([FakeResponse([{"id": "cf_unrelated", "name": "Flagged"}])])

    resolved = FieldIds.resolve(client)

    errors = capsys.readouterr().err
    assert resolved == FieldIds(story_points=HISTORIC_STORY_POINTS_FIELD, sprint=HISTORIC_SPRINT_FIELD)
    assert len(session.calls) == 1, "the lookup still happened"
    assert "Ignoring the repo settings" in errors, "the store reported the broken scope itself"
    assert "Moved" not in errors, "nothing can be migrated out of a file that cannot be read"
    assert state_file.read_text(encoding="utf-8") == "{not json at all", "the broken file is left untouched"
