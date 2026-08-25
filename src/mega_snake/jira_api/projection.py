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

from mega_snake.constants import (
    JIRA_SPRINT_FIELD_CACHE_KEY,
    JIRA_SPRINT_FIELD_KEY,
    JIRA_STORY_POINTS_FIELD_CACHE_KEY,
    JIRA_STORY_POINTS_FIELD_KEY,
)
from mega_snake.jira_api.client import JiraClient
from mega_snake.util.formatting import ValidationError, ws_info, ws_warning
from mega_snake.util.store import SCOPE_REPO, Store

FIELD_PATH: str = "/rest/api/3/field"

# The ids this project's Jira instance happens to use, kept only as a last resort so the command
# still produces the historical output when the field endpoint is unreachable or the names differ.
HISTORIC_STORY_POINTS_FIELD: str = "customfield_10016"
HISTORIC_SPRINT_FIELD: str = "customfield_10020"

STORY_POINTS_FIELD_NAMES: tuple[str, ...] = ("Story Points", "Story point estimate")
SPRINT_FIELD_NAMES: tuple[str, ...] = ("Sprint",)


@dataclass(frozen=True)
class _FieldSpec:
    """Everything needed to resolve one custom field id, so the two are handled by one code path.

    Keeping the pin key and the cache key side by side is what makes the asymmetry between them
    impossible to forget: ``pin_key`` is read and never written, ``cache_key`` is read, written and
    deleted, and no other combination is legal.
    """

    pin_key: str
    cache_key: str
    names: tuple[str, ...]
    fallback: str


STORY_POINTS_SPEC: _FieldSpec = _FieldSpec(
    pin_key=JIRA_STORY_POINTS_FIELD_KEY,
    cache_key=JIRA_STORY_POINTS_FIELD_CACHE_KEY,
    names=STORY_POINTS_FIELD_NAMES,
    fallback=HISTORIC_STORY_POINTS_FIELD,
)
SPRINT_SPEC: _FieldSpec = _FieldSpec(
    pin_key=JIRA_SPRINT_FIELD_KEY,
    cache_key=JIRA_SPRINT_FIELD_CACHE_KEY,
    names=SPRINT_FIELD_NAMES,
    fallback=HISTORIC_SPRINT_FIELD,
)
FIELD_SPECS: tuple[_FieldSpec, ...] = (STORY_POINTS_SPEC, SPRINT_SPEC)

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

LEGACY_CACHE_MIGRATED_MESSAGE: str = (
    "Moved '{pin_key}' to '{cache_key}': an earlier version of this command wrote it as a cache, not "
    "a pin. Re-run with --refresh if you want the id re-resolved from this Jira instance."
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
        """Resolve the custom field ids, honouring user pins and caching what it works out itself.

        Three sources answer, in this order: the **pin** (``jira.field.sprint``), which only the user
        ever writes and which nothing here overwrites, deletes or second-guesses; the **cache**
        (``jira.field.sprint.cached``), which only this method writes; and a fresh lookup by name.

        Each field is resolved independently. That is not a tidiness preference: while the two were
        answered together, a pin was read only if the *other* field also happened to be cached, so
        pinning the ambiguous field -- the one case the warning tells you to pin -- left the pin
        sitting on disk, unread, while the guess kept being used.

        Before any of that, ``_migrate_legacy_cache`` moves a bare key that an earlier version of
        this module wrote as a cache back onto its ``.cached`` sibling, so a leftover from that code
        is not mistaken for a pin (see its docstring).

        Parameters:
            client: The Jira client used to list the instance's fields.
            refresh: When True, ignore the cached ids and query the instance again. Pins are still
                honoured: a pin is a decision the user made, not a cached guess to be revisited. A
                pinned field's own ``.cached`` entry, if any, is still dropped: it is a leftover
                guess the pin has already overridden, and leaving it behind would let it answer
                again the moment the pin is removed -- which is exactly the stale value ``--refresh``
                was asked to distrust.

        Raises:
            click.ClickException: If the field endpoint fails.

        Returns:
            FieldIds: The resolved ids.
        """
        store: Store = Store.get_instance()
        FieldIds._migrate_legacy_cache(store)
        known: dict[str, str] = {}
        for spec in FIELD_SPECS:
            pin: Optional[str] = store.get(spec.pin_key)
            if pin:
                known[spec.pin_key] = pin
                # A pinned field never reaches `_cache` below (the loop skips it with `continue`),
                # so without this its stale `.cached` entry survives `--refresh` untouched -- and
                # resurfaces the moment the pin is removed, answering with exactly the guess
                # `--refresh` was asked to distrust. This is the pinned half of the same promise
                # `_cache` keeps for the resolved half.
                if refresh and store.has_scope(SCOPE_REPO):
                    store.unset(spec.cache_key, SCOPE_REPO)
                continue
            if not refresh:
                cached: Optional[str] = store.get(spec.cache_key)
                if cached:
                    known[spec.pin_key] = cached
        if len(known) < len(FIELD_SPECS):
            fields: list[dict] = client.get_list(FIELD_PATH)
            for spec in FIELD_SPECS:
                if spec.pin_key in known:
                    continue
                field_id, matched = FieldIds._match(fields, spec.names, spec.fallback, spec.pin_key)
                known[spec.pin_key] = field_id
                FieldIds._cache(store, spec, field_id, matched, refresh)
        return FieldIds(story_points=known[STORY_POINTS_SPEC.pin_key], sprint=known[SPRINT_SPEC.pin_key])

    @staticmethod
    def _migrate_legacy_cache(store: Store) -> None:
        """One-time migration for bare keys an earlier version of this module wrote as a cache.

        Before the pin/cache split, ``resolve`` cached the id it worked out under the bare key itself
        (``store.set(JIRA_SPRINT_FIELD_KEY, ...)``), which is what a clone that ran an earlier commit
        of this branch still has on disk. The bare key now means a user pin, so an untouched leftover
        reads back as a deliberate pin and ``--refresh`` returns the same stale id forever, silently.

        **The trigger is the store's version marker, not the shape of the data**, and that
        distinction is the whole correctness argument. A legacy cache and a pin written today are the
        same key holding the same kind of value, so "bare key present, ``.cached`` absent" does not
        identify a leftover -- it is exactly what the documented pin workflow produces, because an
        ambiguous field is never cached. Keyed on shape, this migration relocated the pin the
        ambiguity warning had just told the user to create, and ``--refresh`` then discarded it: the
        original defect, rebuilt inside its own fix. ``Store.set`` stamps the marker on the first
        write, so any pin made through ``config set`` is stamped before this ever sees it.

        The shape check is kept as a second guard: a bare key coexisting with its ``.cached`` sibling
        cannot be a legacy leftover, since the older code wrote only one of the two.

        Parameters:
            store: The store to read from and migrate in.

        Raises:
            None

        Returns:
            None
        """
        if not store.has_scope(SCOPE_REPO):
            return
        try:
            if store.is_current_layout(SCOPE_REPO):
                return
            repo_values: dict[str, str] = store.items(SCOPE_REPO)
        except ValidationError:
            # An unusable repo file is reported (and degraded) by the reads that follow in
            # `resolve`; migrating is simply not possible, and turning a condition the store handles
            # gracefully into a hard failure here would be a regression of its own.
            return
        for spec in FIELD_SPECS:
            legacy_value: Optional[str] = repo_values.get(spec.pin_key)
            if legacy_value is None or spec.cache_key in repo_values:
                continue
            store.set(spec.cache_key, legacy_value, SCOPE_REPO)
            store.unset(spec.pin_key, SCOPE_REPO)
            ws_info(LEGACY_CACHE_MIGRATED_MESSAGE.format(pin_key=spec.pin_key, cache_key=spec.cache_key))

    @staticmethod
    def _cache(store: Store, spec: "_FieldSpec", field_id: str, matched: bool, refresh: bool) -> None:
        """Write, keep or drop the cached id -- never the pin, which is not ours to touch.

        Only an unambiguous match is cached. Persisting a fallback, or a guess between two fields
        sharing a display name, would make the next run read it back, skip the field endpoint and use
        the wrong id *without any warning at all* -- strictly worse than the uncached guess, where
        the warning keeps firing until a human acts on it.

        The drop is the other half of what ``--refresh`` promises for a field this method actually
        looks up. Without it a run that resolves nothing writes nothing, so the entry the user asked
        to distrust survives the refresh and answers again on the run after it, silently, since the
        cache path never reaches the warning. It is confined to ``refresh`` because an ordinary run
        reaches the field endpoint merely because the *other* id was missing, and evicting a good
        entry there would make every run cold.

        A pinned field never reaches this method at all -- ``resolve`` skips it with ``continue``
        before the lookup -- so its own ``.cached`` entry is dropped directly in ``resolve``, under
        the same ``refresh`` condition. Both halves exist for the identical reason: an entry
        ``--refresh`` was asked to distrust must not survive it.

        Parameters:
            store: The store to write to.
            spec: The field being resolved, carrying the cache key to write.
            field_id: The id that was resolved, real or guessed.
            matched: Whether the id was resolved unambiguously, and may therefore be cached.
            refresh: Whether this run was asked to distrust the cache.

        Raises:
            None

        Returns:
            None
        """
        if not store.has_scope(SCOPE_REPO):
            return
        if matched:
            store.set(spec.cache_key, field_id, SCOPE_REPO)
        elif refresh:
            store.unset(spec.cache_key, SCOPE_REPO)


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
