"""Project raw Jira issues into the compact schema the Jira skills consume.

This is the Python replacement for the single enormous `jq` filter in `jira_board_issues.sh`, and it
is the most contract-sensitive piece of the migration: the shape produced here is what every Jira
skill and every documented `jq` recipe reads. Two details are easy to get wrong and both are pinned
by tests:

- **`jq` turns `null` into a dict of nulls.** ``null | {id, key}`` yields ``{"id": null, "key": null}``
  and *not* ``null``. ``_pick`` reproduces that exactly, because the documented recipes detect orphan
  stories with ``parent.key == null`` -- returning ``None`` for the whole ``parent`` would silently
  break them.
- **`.attachment[]` and `.comment.comments[]` had no `?`.** When either field came back null (a
  permission, or an issue type without them) `jq` aborted the entire run. Both are treated as empty
  here.

The two custom field ids are resolved by *name* instead of being hardcoded: ``customfield_10016`` and
``customfield_10020`` are allocated per Jira instance, so on any other tenant the shell version
silently projected ``null`` for story points and sprints.
"""

from dataclasses import dataclass
from typing import Optional

from mega_snake.constants import JIRA_SPRINT_FIELD_KEY, JIRA_STORY_POINTS_FIELD_KEY
from mega_snake.jira_api.client import JiraClient
from mega_snake.util.formatting import ws_warning
from mega_snake.util.store import SCOPE_REPO, Store

FIELD_PATH: str = "/rest/api/3/field"

# The ids this project's Jira instance happens to use, kept only as a last resort so the command
# still produces the historical output when the field endpoint is unreachable or the names differ.
HISTORIC_STORY_POINTS_FIELD: str = "customfield_10016"
HISTORIC_SPRINT_FIELD: str = "customfield_10020"

STORY_POINTS_FIELD_NAMES: tuple[str, ...] = ("Story Points", "Story point estimate")
SPRINT_FIELD_NAMES: tuple[str, ...] = ("Sprint",)

PERSON_KEYS: tuple[str, ...] = ("accountId", "displayName", "emailAddress", "timeZone")
ISSUE_TYPE_KEYS: tuple[str, ...] = ("name", "subtask", "entityId", "hierarchyLevel")
ATTACHMENT_KEYS: tuple[str, ...] = ("id", "filename", "mimeType", "size")
COMMENT_KEYS: tuple[str, ...] = ("id", "created", "updated", "jsdPublic", "body")
SPRINT_KEYS: tuple[str, ...] = ("id", "name", "state", "startDate", "endDate", "completeDate")

ACTIVE_SPRINT_KEY: str = "activeSprint"

UNRESOLVED_FIELD_MESSAGE: str = (
    "Could not find the '{names}' custom field in this Jira instance. Falling back to '{fallback}', "
    "which may not exist here and would project null."
)

AMBIGUOUS_FIELD_MESSAGE: str = (
    "This Jira instance declares {count} custom fields named '{name}' ({ids}). Using the first one, "
    "'{chosen}', which is a guess: if the projected value is wrong, pin the right id with "
    "'mgsnake config set {key} <id>'."
)


@dataclass(frozen=True)
class FieldIds:
    """Instance-specific custom field ids, resolved by name."""

    story_points: str
    sprint: str

    @staticmethod
    def _match(fields: list[dict], candidate_names: tuple[str, ...], fallback: str, key: str) -> tuple[str, bool]:
        """Find the id of the first field matching one of the candidate names.

        Whether the id may be cached is returned alongside it, and it is True only for an
        *unambiguous* match. Two situations must not be cached, for the same reason: the fallback,
        and a name declared by more than one field. Either one warns on the first run, and storing
        the guess would make every later run take the cache branch, skip the field endpoint, and
        project the wrong value *without warning* -- the very defect the by-name resolution exists
        to fix, only moved inside the cache. Keeping the guess out of the store means the warning
        keeps firing until a human resolves it.

        Duplicate display names are ordinary on instances that went through a Server-to-Cloud
        migration, or that hold both a company-managed and a team-managed project. Two rules follow
        from that. **An unambiguous candidate is preferred over an ambiguous one**, whatever the
        order of ``candidate_names``, because that order ranks how likely a name is to be the right
        field and not how trustworthy the answer is. And when every candidate is ambiguous, **the
        first declaration wins**: a dict comprehension over ``fields`` would have kept the *last*
        entry instead, which is how the leftover field of a migration silently outranks the real
        Jira Software one.

        Parameters:
            fields: The entries returned by the field endpoint.
            candidate_names: The display names to look for, in order of preference.
            fallback: The id to use when no field matches.
            key: The store key to name in the ambiguity warning, so the user can pin the right id.

        Raises:
            None

        Returns:
            tuple[str, bool]: The field id, and True only when it was resolved unambiguously.
        """
        by_name: dict[str, list[str]] = {}
        for field in fields:
            name: str = str(field.get("name", "")).casefold()
            field_id: str = str(field.get("id", ""))
            if name and field_id:
                by_name.setdefault(name, []).append(field_id)
        candidates: list[tuple[str, list[str]]] = [
            (candidate, by_name.get(candidate.casefold(), [])) for candidate in candidate_names
        ]
        # An unambiguous match on a less-preferred name beats a guess on the preferred one. The
        # order of `candidate_names` ranks how likely a name is to be the right field, not how
        # trustworthy the answer is: `Story Points` duplicated by a migration and `Story point
        # estimate` declared exactly once means the second one is the only id we actually know.
        for _, matches in candidates:
            if len(matches) == 1:
                return matches[0], True
        for candidate, matches in candidates:
            if len(matches) > 1:
                ws_warning(
                    AMBIGUOUS_FIELD_MESSAGE.format(
                        count=len(matches), name=candidate, ids=", ".join(matches), chosen=matches[0], key=key
                    )
                )
                return matches[0], False
        ws_warning(UNRESOLVED_FIELD_MESSAGE.format(names=", ".join(candidate_names), fallback=fallback))
        return fallback, False

    @staticmethod
    def resolve(client: JiraClient, refresh: bool = False) -> "FieldIds":
        """Resolve the custom field ids, caching them in the repository scope.

        Parameters:
            client: The Jira client used to list the instance's fields.
            refresh: When True, ignore the cached ids and query the instance again.

        Raises:
            click.ClickException: If the field endpoint fails.

        Returns:
            FieldIds: The resolved ids.
        """
        store: Store = Store.get_instance()
        if not refresh:
            cached_story_points: Optional[str] = store.get(JIRA_STORY_POINTS_FIELD_KEY)
            cached_sprint: Optional[str] = store.get(JIRA_SPRINT_FIELD_KEY)
            if cached_story_points and cached_sprint:
                return FieldIds(story_points=cached_story_points, sprint=cached_sprint)
        fields: list[dict] = client.get_list(FIELD_PATH)
        story_points, story_points_matched = FieldIds._match(
            fields, STORY_POINTS_FIELD_NAMES, HISTORIC_STORY_POINTS_FIELD, JIRA_STORY_POINTS_FIELD_KEY
        )
        sprint, sprint_matched = FieldIds._match(
            fields, SPRINT_FIELD_NAMES, HISTORIC_SPRINT_FIELD, JIRA_SPRINT_FIELD_KEY
        )
        # Only an unambiguous match is cached. Persisting a fallback -- or a guess between two
        # fields sharing a display name -- would make the next run take the cache branch above, skip
        # the field endpoint, and use the wrong id *without any warning at all*, which is strictly
        # worse than the uncached guess: there, the warning keeps firing until a human acts on it.
        # `jira-issues --refresh` is the escape hatch for an id that matched once and later changed,
        # and it is symmetric: what a refresh cannot confirm is dropped rather than left behind.
        if store.has_scope(SCOPE_REPO):
            FieldIds._store(store, JIRA_STORY_POINTS_FIELD_KEY, story_points, story_points_matched, refresh)
            FieldIds._store(store, JIRA_SPRINT_FIELD_KEY, sprint, sprint_matched, refresh)
        return FieldIds(story_points=story_points, sprint=sprint)

    @staticmethod
    def _store(store: Store, key: str, field_id: str, matched: bool, refresh: bool) -> None:
        """Persist a resolved id, or drop the cached one that a refresh failed to confirm.

        The drop is what makes ``--refresh`` mean what it says. Without it, a run that resolves
        nothing writes nothing, so the entry the user asked to distrust survives the refresh and
        answers again -- silently, since the cache branch never reaches the warning -- and the only
        way out would be unsetting a key the user has no reason to suspect.

        Parameters:
            store: The store to write to. Its repository scope is known to exist.
            key: The store key for this field.
            field_id: The id that was resolved, real or guessed.
            matched: Whether the id was resolved unambiguously, and may therefore be cached.
            refresh: Whether this run was asked to distrust the cache.

        Raises:
            None

        Returns:
            None
        """
        if matched:
            store.set(key, field_id, SCOPE_REPO)
        elif refresh:
            store.unset(key, SCOPE_REPO)


def _pick(source: Optional[dict], *keys: str) -> dict:
    """Project selected keys out of a mapping, mirroring `jq`'s object construction.

    A missing source yields a mapping of nulls rather than ``None``, which is what
    ``null | {id, key}`` does in `jq` and what the documented recipes rely on.

    Parameters:
        source: The mapping to read from, possibly None.
        *keys: The keys to project.

    Raises:
        None

    Returns:
        dict: One entry per requested key, with None for anything missing.
    """
    values: dict = source or {}
    return {key: values.get(key) for key in keys}


def _person(source: Optional[dict]) -> dict:
    """Project a Jira user object down to the fields the schema exposes.

    Parameters:
        source: The raw user object, possibly None.

    Raises:
        None

    Returns:
        dict: The projected user.
    """
    return _pick(source, *PERSON_KEYS)


def _project_attachment(attachment: dict) -> dict:
    """Project one attachment entry.

    Parameters:
        attachment: The raw attachment object.

    Raises:
        None

    Returns:
        dict: The projected attachment, with ``content`` renamed to ``contentUrl``.
    """
    return {
        **_pick(attachment, *ATTACHMENT_KEYS),
        "contentUrl": attachment.get("content"),
        "author": _person(attachment.get("author")),
    }


def _project_comment(comment: dict) -> dict:
    """Project one comment entry.

    Parameters:
        comment: The raw comment object.

    Raises:
        None

    Returns:
        dict: The projected comment.
    """
    return {
        **_pick(comment, *COMMENT_KEYS),
        "author": _person(comment.get("author")),
        "updateAuthor": _person(comment.get("updateAuthor")),
    }


def _project_status(status: Optional[dict]) -> dict:
    """Project the status object together with its nested category.

    Parameters:
        status: The raw status object, possibly None.

    Raises:
        None

    Returns:
        dict: The projected status.
    """
    return {
        **_pick(status, "id", "name"),
        "statusCategory": _pick((status or {}).get("statusCategory"), "id", "key", "name"),
    }


def project_issue(raw: dict, field_ids: FieldIds) -> dict:
    """Project a raw Jira issue into the compact schema consumed by the skills.

    Parameters:
        raw: One entry of the ``issues`` array returned by the search endpoint.
        field_ids: The instance-specific custom field ids.

    Raises:
        None

    Returns:
        dict: The projected issue, with the same keys and order the `jq` filter produced.
    """
    fields: dict = raw.get("fields") or {}
    attachments: list[dict] = fields.get("attachment") or []
    comment: dict = fields.get("comment") or {}
    comments: list[dict] = comment.get("comments") or []
    sprints: list[dict] = fields.get(field_ids.sprint) or []
    return {
        "id": raw.get("id"),
        "link": raw.get("self"),
        "key": raw.get("key"),
        "fields": {
            "summary": fields.get("summary"),
            "statuscategorychangedate": fields.get("statuscategorychangedate"),
            "created": fields.get("created"),
            "resolutiondate": fields.get("resolutiondate"),
            "lastViewed": fields.get("lastViewed"),
            "updated": fields.get("updated"),
            "description": fields.get("description"),
            "issuetype": _pick(fields.get("issuetype"), *ISSUE_TYPE_KEYS),
            "parent": _pick(fields.get("parent"), "id", "key"),
            "project": _pick(fields.get("project"), "id", "key", "name"),
            "status": _project_status(fields.get("status")),
            "workratio": fields.get("workratio"),
            "issuerestriction": fields.get("issuerestriction"),
            "priority": _pick(fields.get("priority"), "id", "name"),
            "labels": fields.get("labels"),
            "storyPoints": fields.get(field_ids.story_points),
            "assignee": _person(fields.get("assignee")),
            "creator": _person(fields.get("creator")),
            "reporter": _person(fields.get("reporter")),
            "votes": _pick(fields.get("votes"), "votes", "hasVoted"),
            "attachment": [_project_attachment(attachment) for attachment in attachments],
            "attachmentsCount": len(attachments),
            "comment": [_project_comment(entry) for entry in comments],
            "commentCount": comment.get("total"),
            "sprint": [_pick(sprint, *SPRINT_KEYS) for sprint in sprints],
        },
    }
