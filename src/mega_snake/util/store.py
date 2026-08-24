"""Persistent key/value state that survives across command invocations.

The repository already had three configuration layers and none of them is writable state:
``config.properties`` ships inside the wheel (read-only, replaced on every install), ``AppProperties``
is a per-process singleton that ``_check_forbidden_execution`` deliberately keeps immutable, and the
local config/env files are a shell prelude the CLI writes once and never reads back. This module is
the missing piece: a small layered store the CLI both writes and reads.

Two scopes exist:

- ``global`` -- ``~/.config/mgsnake/state.json`` (``%APPDATA%\\mgsnake\\state.json`` on Windows), for
  settings that follow the user across repositories.
- ``repo`` -- ``<git-dir>/mgsnake/state.json``, for settings that belong to one clone. Living inside
  ``.git`` means the file is never committed (no ``.gitignore`` and no ``.git/info/exclude`` entry
  needed), is per-clone, and dies with the clone. ``workspace_temp`` would have been the obvious
  alternative but it is explicitly disposable -- ``diff-tree`` wipes its subfolder on every run --
  and state that evaporates is not state.

Resolution order for a read is ``env var > repo > global > default``, so every environment variable
based workflow that predates the store keeps working unchanged and migrating to it can be gradual.

**Secrets never go in.** ``set`` rejects any key that looks like a credential: a plaintext JSON file
inside ``.git`` is worse than an environment variable precisely because it persists and is forgotten.
The store keeps identifiers (domain, project key, board id, custom field ids), never credentials.

**No subprocess, on purpose.** The repo scope is resolved by walking up the filesystem instead of
shelling out to ``git rev-parse --git-dir`` through ``run_operation``: that helper reads
``get_property("shell")``, which requires the ``AppProperties`` singleton, and the store has to work
for ``no_init`` commands where that singleton is never built. ``exclude_from_git`` already inspects
``.git`` directly, so filesystem-level git detection is the established precedent here.
"""

import json
import os
import platform
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Optional

import click

from mega_snake.constants import APP_NAME
from mega_snake.util.formatting import UserDeclinedError, ValidationError, ws_success, ws_warning
from mega_snake.util.util import write_json_atomically

SCOPE_GLOBAL: str = "global"
SCOPE_REPO: str = "repo"
SCOPE_ALL: str = "all"
SCOPES: tuple[str, ...] = (SCOPE_GLOBAL, SCOPE_REPO)

STORE_FILE_NAME: str = "state.json"
GIT_DIR_NAME: str = ".git"
# A `.git` *file* (worktrees, submodules) points at the real git directory with this prefix.
GIT_FILE_PREFIX: str = "gitdir:"

# Any key matching this is refused outright: the store is for identifiers, not credentials.
SECRET_KEY_PATTERN: str = r"(?i)(token|secret|password|passwd|credential|api[_.-]?key)"
# Dotted namespace, lowercase: keeps the file from degenerating into a junk drawer of flat keys.
KEY_PATTERN: str = r"^[a-z0-9]+(\.[a-z0-9_]+)+$"

SECRET_KEY_MESSAGE: str = (
    "Refusing to store '{key}': it looks like a credential. Secrets belong in environment "
    "variables only, never in a plaintext state file. Export it from your shell instead."
)
INVALID_KEY_MESSAGE: str = (
    "Invalid setting name '{key}'. Names must be lowercase and dotted, e.g. 'jira.project_key' (pattern: {pattern})."
)
UNKNOWN_SCOPE_MESSAGE: str = "Unknown scope '{scope}'. Expected one of: {scopes}."
NO_REPO_SCOPE_MESSAGE: str = (
    "The 'repo' scope needs a git repository, and none was found from the current directory. "
    "Run the command inside a clone, or use --global."
)
UNREADABLE_STORE_MESSAGE: str = (
    "The {scope} state file at {path} could not be read ({error}). Check its permissions; its contents "
    "may well be intact, so nothing is offered to reset it."
)
CORRUPT_STORE_MESSAGE: str = "The {scope} state file at {path} is not valid JSON ({error})."
NOT_AN_OBJECT_MESSAGE: str = "The {scope} state file at {path} does not contain a JSON object (found {type})."
RECOVERY_PROMPT: str = "{reason} Back it up and start a new empty {scope} state file now?"
RECOVERY_SUCCESS_MESSAGE: str = "Backed up the corrupt {scope} state file to {backup} and started a new one at {path}."
BROKEN_SCOPE_WARNING: str = "Ignoring the {scope} settings for the rest of this run: {reason}"
MISSING_SETTING_MESSAGE: str = (
    "Missing required setting '{key}'. Set it with: {app} config set {key} <value> (or export {env_var})."
)


def env_var_name(key: str) -> str:
    """Derive the environment variable that overrides a given setting.

    Parameters:
        key: The dotted setting name, e.g. ``jira.project_key``.

    Raises:
        None

    Returns:
        str: The matching environment variable name, e.g. ``JIRA_PROJECT_KEY``.
    """
    return key.replace(".", "_").upper()


def _global_store_dir() -> Path:
    """Resolve the directory holding the user-wide state file.

    Parameters:
        None

    Raises:
        None

    Returns:
        Path: ``%APPDATA%/mgsnake`` on Windows, ``$XDG_CONFIG_HOME/mgsnake`` (or ``~/.config/mgsnake``)
            everywhere else.
    """
    if platform.system() == "Windows":
        base: str = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def find_git_dir(start: Optional[Path] = None) -> Optional[Path]:
    """Find the git directory owning the given path, walking up the filesystem.

    Both forms are handled: a real ``.git`` directory, and the ``.git`` *file* that worktrees and
    submodules leave behind pointing at the actual git directory.

    Parameters:
        start: The directory to start the search from. Defaults to the current working directory.

    Raises:
        None

    Returns:
        Optional[Path]: The resolved git directory, or None when the path is not inside a repository.
    """
    current: Path = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate: Path = directory / GIT_DIR_NAME
        if candidate.is_dir():
            return candidate
        if candidate.is_file():
            content: str = candidate.read_text(encoding="utf-8").strip()
            if content.startswith(GIT_FILE_PREFIX):
                target: str = content.removeprefix(GIT_FILE_PREFIX).strip()
                return (directory / target).resolve()
    return None


def _validate_key_format(key: str) -> None:
    """Reject malformed setting names, regardless of what the key is used for.

    Parameters:
        key: The setting name to validate.

    Raises:
        click.ClickException: If the key does not follow ``KEY_PATTERN``.

    Returns:
        None
    """
    if not re.match(KEY_PATTERN, key):
        raise click.ClickException(INVALID_KEY_MESSAGE.format(key=key, pattern=KEY_PATTERN))


def _validate_key(key: str) -> None:
    """Reject credential-shaped and malformed setting names before anything is written.

    Only used by ``set``: ``unset`` must still be able to remove a credential-shaped key that ended
    up in the file some other way (a manual edit, an older bug), so it validates the format only.

    Parameters:
        key: The setting name to validate.

    Raises:
        click.ClickException: If the key looks like a secret, or does not follow ``KEY_PATTERN``.

    Returns:
        None
    """
    if re.search(SECRET_KEY_PATTERN, key):
        raise click.ClickException(SECRET_KEY_MESSAGE.format(key=key))
    _validate_key_format(key)


@dataclass
class Store:
    """Layered persistent state: environment variable > repo scope > global scope.

    The instance is a lazily loaded singleton: nothing is read from disk until the first ``get``,
    which is what lets it work identically under the three initialization levels, ``no_init``
    included.

    Parameters:
        None

    Raises:
        None

    Returns:
        None
    """

    _instance: ClassVar[Optional["Store"]] = None

    _paths: dict[str, Optional[Path]] = field(default_factory=dict)
    _values: dict[str, dict[str, str]] = field(default_factory=dict)
    _broken_scopes: set[str] = field(default_factory=set)

    @staticmethod
    def get_instance() -> "Store":
        """Return the process-wide store, creating it on first use.

        Parameters:
            None

        Raises:
            None

        Returns:
            Store: The shared store instance.
        """
        if Store._instance is None:
            Store._instance = Store()
        return Store._instance

    @staticmethod
    def reset_instance() -> None:
        """Drop the cached store so paths and contents are resolved again.

        Both the resolved scope paths and the loaded contents are memoized for the lifetime of the
        instance, so anything that invalidates them (a test using a different temporary home, a
        change of working directory) has to go through here.

        Parameters:
            None

        Raises:
            None

        Returns:
            None
        """
        Store._instance = None

    def scope_path(self, scope: str) -> Optional[Path]:
        """Resolve the state file backing a scope.

        Parameters:
            scope: One of ``SCOPES``.

        Raises:
            click.ClickException: If the scope name is unknown.

        Returns:
            Optional[Path]: The state file path, or None when the repo scope has no repository.
        """
        if scope not in SCOPES:
            raise click.ClickException(UNKNOWN_SCOPE_MESSAGE.format(scope=scope, scopes=", ".join(SCOPES)))
        if scope not in self._paths:
            if scope == SCOPE_GLOBAL:
                self._paths[scope] = _global_store_dir() / STORE_FILE_NAME
            else:
                git_dir: Optional[Path] = find_git_dir()
                self._paths[scope] = git_dir / APP_NAME / STORE_FILE_NAME if git_dir else None
        return self._paths[scope]

    def has_scope(self, scope: str) -> bool:
        """Tell whether a scope is available in the current context.

        Parameters:
            scope: One of ``SCOPES``.

        Raises:
            click.ClickException: If the scope name is unknown.

        Returns:
            bool: True when the scope can be read and written, False for ``repo`` outside a repository.
        """
        return self.scope_path(scope) is not None

    def _require_scope_path(self, scope: str) -> Path:
        """Resolve a scope path, failing with an actionable message when it does not exist.

        Parameters:
            scope: One of ``SCOPES``.

        Raises:
            click.ClickException: If the scope is unknown, or is ``repo`` outside a repository.

        Returns:
            Path: The state file path for the scope.
        """
        path: Optional[Path] = self.scope_path(scope)
        if path is None:
            raise click.ClickException(NO_REPO_SCOPE_MESSAGE)
        return path

    def _load(self, scope: str, interactive: bool = False) -> dict[str, str]:
        """Read (and memoize) the contents of one scope.

        Parameters:
            scope: One of ``SCOPES``.
            interactive: Whether the caller may be offered a backup-and-reset prompt when the state
                file is unusable. Only ``set``/``unset``/an explicit ``list --scope`` pass ``True``;
                ``get`` and ``export`` never do -- see ``_recover_from_corruption``.

        Raises:
            ValidationError: If the state file cannot be read at all (permissions, an I/O error), or
                if it is unusable (invalid JSON, or not a JSON object) and could not be recovered
                automatically: not ``interactive``, no interactive terminal, a closed stdin, or the
                backup-and-reset itself failed.
            UserDeclinedError: If ``interactive`` and the user declined the offered backup-and-reset.

        Returns:
            dict[str, str]: The stored values, empty when the scope has no file yet.
        """
        if scope in self._values:
            return self._values[scope]
        path: Optional[Path] = self.scope_path(scope)
        values: dict[str, str] = {}
        if path is not None and path.is_file():
            try:
                content: str = path.read_text(encoding="utf-8")
            except OSError as error:
                # Deliberately *not* routed through `_recover_from_corruption`: an unreadable file is
                # not a corrupt one. Its contents are very likely fine and only the permissions are
                # wrong, so offering to rename it aside and start over would destroy recoverable
                # state to fix a problem `chmod` solves. Raising `ValidationError` still lets
                # `_load_gracefully` degrade a multi-scope read, which is the half that matters:
                # before this, an unreadable `global` file killed `config export` outright, and that
                # command is `eval`'d from the shell profile on every new terminal.
                raise ValidationError(
                    UNREADABLE_STORE_MESSAGE.format(scope=scope, path=path, error=error)
                ) from error
            try:
                decoded: object = json.loads(content or "{}")
            except json.JSONDecodeError as error:
                values = self._recover_from_corruption(
                    scope, path, CORRUPT_STORE_MESSAGE.format(scope=scope, path=path, error=error), interactive
                )
            else:
                if isinstance(decoded, dict):
                    values = decoded
                else:
                    values = self._recover_from_corruption(
                        scope,
                        path,
                        NOT_AN_OBJECT_MESSAGE.format(scope=scope, path=path, type=type(decoded).__name__),
                        interactive,
                    )
        self._values[scope] = values
        return values

    def _recover_from_corruption(self, scope: str, path: Path, reason: str, interactive: bool) -> dict[str, str]:
        """Offer to back up an unusable state file and start over, or fail with an actionable message.

        An interactive terminal gets a choice **only when the caller says it may be asked**:
        confirming backs up the broken file (never deletes it outright) and replaces it with a fresh,
        empty one, so the run continues instead of dying on state nobody corrupted on purpose. A
        declined confirmation, a non-interactive context (a script, CI, a closed stdin), and a caller
        that did not opt in, all leave the file untouched and fail loudly instead -- silently
        discarding state nobody agreed to lose would be worse than stopping, and matches how the rest
        of the store treats this class of decision (compare ``ensure_working_path``'s offer to create
        the missing working path).

        ``interactive`` exists because ``sys.stdin.isatty()`` alone answers "is a human at the other
        end of this process", not "is this command's stdout a data channel a script depends on".
        ``config get``/``config export`` are read from an interactive shell profile on every new
        terminal (``eval "$(mgsnake config export ...)"``) -- a prompt there would hang the shell
        startup on a corrupt file, which is exactly the situation this whole mechanism exists to
        avoid. Only ``config set``/``unset``/an explicit-scope ``list`` opt in.

        Parameters:
            scope: One of ``SCOPES``. Only used for the prompt and the messages.
            path: The unusable state file.
            reason: Human-readable description of what is wrong with the file, already naming
                ``path``.
            interactive: Whether this call site is allowed to prompt at all.

        Raises:
            UserDeclinedError: If asked and the user declines the backup-and-reset.
            ValidationError: If the file cannot be recovered automatically: not ``interactive``, no
                interactive terminal, a closed stdin (``click.confirm`` raises
                ``click.exceptions.Abort`` on EOF), or the backup-and-reset failed.

        Returns:
            dict[str, str]: An empty mapping, once the file has been backed up and reset.
        """
        if interactive and sys.stdin.isatty():
            try:
                if not click.confirm(RECOVERY_PROMPT.format(reason=reason, scope=scope), err=True):
                    raise UserDeclinedError(reason)
            except click.exceptions.Abort:
                pass
            else:
                return self._backup_and_reset(scope, path)
        raise ValidationError(reason)

    def _backup_and_reset(self, scope: str, path: Path) -> dict[str, str]:
        """Replace an unusable state file with a fresh empty one, without ever losing the original.

        The fresh, empty content is written to a temporary sibling first, and only once that write
        succeeds is the broken original renamed aside (never deleted) and the temporary file swapped
        into place. That ordering keeps the on-disk state always resolvable to exactly one of two
        places -- untouched at ``path``, or moved intact to ``backup`` -- there is no intermediate
        step where a filesystem failure could leave the user's data nowhere at all.

        Parameters:
            scope: One of ``SCOPES``. Only used for the success message.
            path: The unusable state file to replace.

        Raises:
            ValidationError: If any filesystem operation fails, naming wherever the original content
                actually ended up.

        Returns:
            dict[str, str]: An empty mapping, once ``path`` holds a fresh, empty state file.
        """
        stamp: str = f"{datetime.now():%Y%m%dT%H%M%S%f}"
        backup: Path = path.with_name(f"{path.name}.corrupted-{stamp}")
        fresh: Path = path.with_name(f"{path.name}.new-{stamp}")
        try:
            write_json_atomically(fresh, {})
            path.replace(backup)
            fresh.replace(path)
        except OSError as error:
            try:
                fresh.unlink(missing_ok=True)
            except OSError:
                pass
            safe_at: Path = backup if backup.exists() else path
            raise ValidationError(
                f"Could not reset the {scope} state file at {path}: {error}. "
                f"Your original content is safe at {safe_at}."
            ) from error
        ws_success(RECOVERY_SUCCESS_MESSAGE.format(scope=scope, backup=backup, path=path))
        return {}

    def _load_gracefully(self, scope: str) -> dict[str, str]:
        """Load a scope for a multi-scope read, degrading instead of failing when it is unusable.

        Used by ``get`` and the scope-merging branch of ``items``: both read across the two scopes
        looking for an answer, so one broken scope should not block whatever the other scope can
        still provide -- a corrupt ``repo`` file must not stop a setting that only ever lived in
        ``global`` from resolving. ``set``, ``unset`` and a single-scope ``items`` call are explicit
        about the one scope they operate on and must keep failing loudly instead; they call
        ``_load`` directly.

        The failure (and any interactive prompt ``_load`` triggers) happens at most once per scope
        per process: once a scope is marked broken, later calls skip straight to the empty mapping
        instead of re-reading the file or asking again.

        Parameters:
            scope: One of ``SCOPES``.

        Raises:
            None

        Returns:
            dict[str, str]: The scope's stored values, or an empty mapping when the scope is broken.
        """
        if scope in self._broken_scopes:
            return {}
        try:
            return self._load(scope)
        except (ValidationError, UserDeclinedError) as error:
            self._broken_scopes.add(scope)
            ws_warning(BROKEN_SCOPE_WARNING.format(scope=scope, reason=error.message))
            return {}

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Read a setting through the precedence chain.

        Parameters:
            key: The dotted setting name.
            default: Value returned when nothing defines the setting.

        Raises:
            None

        Returns:
            Optional[str]: The resolved value, or ``default``. A scope whose state file is unusable
                is skipped (with a warning on stderr) rather than failing the whole lookup -- see
                ``_load_gracefully``.
        """
        environment_value: Optional[str] = os.environ.get(env_var_name(key))
        if environment_value:
            return environment_value
        for scope in (SCOPE_REPO, SCOPE_GLOBAL):
            values: dict[str, str] = self._load_gracefully(scope)
            if key in values:
                return values[key]
        return default

    def require(self, key: str, env_var: Optional[str] = None) -> str:
        """Read a setting, failing with the exact command that would define it.

        Parameters:
            key: The dotted setting name.
            env_var: The environment variable to mention. Defaults to the derived name.

        Raises:
            click.ClickException: If the setting is defined nowhere.

        Returns:
            str: The resolved value.
        """
        value: Optional[str] = self.get(key)
        if not value:
            raise click.ClickException(
                MISSING_SETTING_MESSAGE.format(key=key, app=APP_NAME, env_var=env_var or env_var_name(key))
            )
        return value

    def set(self, key: str, value: str, scope: str = SCOPE_REPO) -> None:
        """Persist a setting in the given scope.

        Parameters:
            key: The dotted setting name.
            value: The value to store.
            scope: One of ``SCOPES``. Defaults to ``repo``, since most settings belong to one clone.

        Raises:
            click.ClickException: If the key looks like a secret, is malformed, the scope is unknown,
                or the repo scope is requested outside a repository.

        Returns:
            None
        """
        _validate_key(key)
        path: Path = self._require_scope_path(scope)
        values: dict[str, str] = dict(self._load(scope, interactive=True))
        values[key] = value
        write_json_atomically(path, values, sort_keys=True)
        self._values[scope] = values

    def unset(self, key: str, scope: str = SCOPE_REPO) -> bool:
        """Remove a setting from the given scope.

        Unlike ``set``, a credential-shaped key is allowed here: ``set`` never wrote one, but a
        manual edit or an older bug could have, and there must be a way to remove it besides editing
        the state file by hand.

        Parameters:
            key: The dotted setting name.
            scope: One of ``SCOPES``.

        Raises:
            click.ClickException: If the key is malformed, the scope is unknown, or the repo scope is
                requested outside a repository.

        Returns:
            bool: True when the setting was present and removed, False when there was nothing to do.
        """
        _validate_key_format(key)
        path: Path = self._require_scope_path(scope)
        values: dict[str, str] = dict(self._load(scope, interactive=True))
        if key not in values:
            return False
        del values[key]
        write_json_atomically(path, values, sort_keys=True)
        self._values[scope] = values
        return True

    def items(self, scope: Optional[str] = None, interactive: bool = False) -> dict[str, str]:
        """Return the stored settings, without applying the environment override.

        Parameters:
            scope: One of ``SCOPES`` to read a single scope, or None to merge them with ``repo``
                taking precedence.
            interactive: Whether a single-scope call may be offered a backup-and-reset prompt when
                that scope's state file is unusable (``config list`` opts in; ``config export`` never
                does). Ignored when ``scope`` is None: merging both scopes always degrades instead,
                regardless of this flag -- see ``_load_gracefully``.

        Raises:
            click.ClickException: If the scope name is unknown, or -- only when a single ``scope``
                was requested explicitly -- its state file is unusable. Merging both scopes (the
                default) degrades a broken one instead of failing; see ``_load_gracefully``.

        Returns:
            dict[str, str]: The stored settings.
        """
        if scope is not None:
            return dict(self._load(scope, interactive=interactive))
        merged: dict[str, str] = dict(self._load_gracefully(SCOPE_GLOBAL))
        merged.update(self._load_gracefully(SCOPE_REPO))
        return merged
