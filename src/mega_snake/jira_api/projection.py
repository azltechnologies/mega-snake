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


@dataclass(frozen=True)
class FieldIds:
    """Instance-specific custom field ids, resolved by name."""

    story_points: str
    sprint: str

    @staticmethod
    def _match(fields: list[dict], candidate_names: tuple[str, ...], fallback: str) -> tuple[str, bool]:
        """Find the id of the first field matching one of the candidate names.

        Whether the id was actually found is returned alongside it, because the caller must not
        cache a guess: a fallback stored as if it were a resolved id would silence the warning from
        the second run onwards and project ``null`` forever, which is the very defect the by-name
        resolution exists to fix, only moved inside the cache.

        Parameters:
            fields: The entries returned by the field endpoint.
            candidate_names: The display names to look for, in order of preference.
            fallback: The id to use when no field matches.

        Raises:
            None

        Returns:
            tuple[str, bool]: The field id, and True only when it came from a real match.
        """
        by_name: dict[str, str] = {str(field.get("name", "")).casefold(): str(field.get("id", "")) for field in fields}
        for name in candidate_names:
            field_id: Optional[str] = by_name.get(name.casefold())
            if field_id:
                return field_id, True
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
            fields, STORY_POINTS_FIELD_NAMES, HISTORIC_STORY_POINTS_FIELD
        )
        sprint, sprint_matched = FieldIds._match(fields, SPRINT_FIELD_NAMES, HISTORIC_SPRINT_FIELD)
        # Only a real match is cached. Persisting a fallback would make the next run take the cache
        # branch above, skip the field endpoint, and use the wrong id *without warning* -- and there
        # is no flag to undo that, so recovering would mean unsetting a key the user has no reason
        # to suspect, precisely because the warning stopped.
        if store.has_scope(SCOPE_REPO):
            if story_points_matched:
                store.set(JIRA_STORY_POINTS_FIELD_KEY, story_points, SCOPE_REPO)
            if sprint_matched:
                store.set(JIRA_SPRINT_FIELD_KEY, sprint, SCOPE_REPO)
        return FieldIds(story_points=story_points, sprint=sprint)


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
