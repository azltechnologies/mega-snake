"""Tests for the persistent key/value store backing `mgsnake config`."""

import json
from pathlib import Path
from unittest.mock import patch

import click
import pytest

from mega_snake.util.formatting import UserDeclinedError, ValidationError
from mega_snake.util.store import (
    SCOPE_GLOBAL,
    SCOPE_REPO,
    STORE_FILE_NAME,
    Store,
    env_var_name,
    find_git_dir,
)

APP_DIR_NAME = "mgsnake"
DOMAIN_KEY = "jira.domain"
PROJECT_KEY = "jira.project_key"


@pytest.fixture(name="workspace")
def workspace_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated home and git repository with a fresh store.

    The known store-key environment variables are already stripped by the autouse
    `_isolated_environment` fixture in the root `conftest.py`; this fixture only sets up what is
    specific to this test module (the isolated home directory and the git repository).
    """
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    monkeypatch.chdir(repo)
    Store.reset_instance()
    yield repo
    Store.reset_instance()


def test_env_var_name_maps_dots_to_underscores() -> None:
    """A dotted setting maps to the screaming-snake-case variable that overrides it."""
    assert env_var_name("jira.field.story_points") == "JIRA_FIELD_STORY_POINTS"


def test_repo_store_path_lives_inside_git_dir(workspace: Path) -> None:
    """The repository state file must sit under .git/mgsnake, not next to it.

    Compared by full equality: a containment check would accept `.git/state.json` just as happily,
    and that is a different file with a different lifetime.
    """
    assert Store.get_instance().scope_path(SCOPE_REPO) == workspace / ".git" / APP_DIR_NAME / STORE_FILE_NAME


def test_global_store_path_lives_in_the_user_config_dir(workspace: Path, tmp_path: Path) -> None:
    """The global state file follows XDG, so it survives across repositories."""
    assert workspace.exists()
    expected = tmp_path / "home" / ".config" / APP_DIR_NAME / STORE_FILE_NAME
    assert Store.get_instance().scope_path(SCOPE_GLOBAL) == expected


def test_global_store_path_follows_appdata_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows has no XDG directory, so the user scope lives under %APPDATA%."""
    monkeypatch.setattr("mega_snake.util.store.platform.system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    Store.reset_instance()

    assert Store.get_instance().scope_path(SCOPE_GLOBAL) == tmp_path / "Roaming" / APP_DIR_NAME / STORE_FILE_NAME
    Store.reset_instance()


def test_global_store_path_falls_back_to_the_home_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With neither XDG_CONFIG_HOME nor APPDATA set, the home directory is the last resort."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("mega_snake.util.store.Path.home", lambda: tmp_path / "home")
    Store.reset_instance()

    assert Store.get_instance().scope_path(SCOPE_GLOBAL) == (
        tmp_path / "home" / ".config" / APP_DIR_NAME / STORE_FILE_NAME
    )
    Store.reset_instance()


def test_get_prefers_env_var_over_repo_scope(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An exported variable wins, which is what keeps the pre-store workflows working."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "stored.atlassian.net", SCOPE_REPO)
    monkeypatch.setenv(env_var_name(DOMAIN_KEY), "exported.atlassian.net")

    assert store.get(DOMAIN_KEY) == "exported.atlassian.net"


def test_get_uses_the_repo_scope_once_the_env_var_is_gone(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative of the precedence test: without the variable, the stored value wins."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "stored.atlassian.net", SCOPE_REPO)
    monkeypatch.delenv(env_var_name(DOMAIN_KEY), raising=False)

    assert store.get(DOMAIN_KEY) == "stored.atlassian.net"


def test_get_prefers_repo_scope_over_global_scope(workspace: Path) -> None:
    """A per-clone value overrides the user-wide one."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "global.atlassian.net", SCOPE_GLOBAL)
    store.set(DOMAIN_KEY, "repo.atlassian.net", SCOPE_REPO)

    assert store.get(DOMAIN_KEY) == "repo.atlassian.net"


def test_get_falls_back_to_global_when_repo_scope_has_no_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside a repository the repo scope simply does not exist; reads must not fail."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    monkeypatch.delenv(env_var_name(DOMAIN_KEY), raising=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    Store.reset_instance()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "global.atlassian.net", SCOPE_GLOBAL)

    assert store.has_scope(SCOPE_REPO) is False
    assert store.get(DOMAIN_KEY) == "global.atlassian.net"
    Store.reset_instance()


def test_set_in_the_repo_scope_fails_outside_a_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Writing to a scope that does not exist must say so instead of writing somewhere else."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    Store.reset_instance()

    with pytest.raises(click.ClickException) as error:
        Store.get_instance().set(DOMAIN_KEY, "x.atlassian.net", SCOPE_REPO)

    assert "--global" in str(error.value)
    Store.reset_instance()


def test_get_returns_the_default_when_nothing_defines_the_setting(workspace: Path) -> None:
    """An unset setting falls through to the caller's default."""
    assert workspace.exists()

    assert Store.get_instance().get("jira.unknown_setting", "fallback") == "fallback"


@pytest.mark.parametrize(
    "key",
    [
        "jira.token",
        "jira.api_token",
        "jira.secret",
        "jira.password",
        "jira.passwd",
        "jira.credential",
        "jira.api_key",
        "jira.apiKey",
        "jira.API-KEY",
        "github.access_token",
    ],
)
def test_set_rejects_every_secret_shaped_key(workspace: Path, key: str) -> None:
    """Credentials belong in the environment; the store refuses to persist them.

    The assertion covers both halves: the rejection, and the fact that nothing reached the disk --
    a store that raised *after* writing would leak the secret anyway.
    """
    assert workspace.exists()
    store = Store.get_instance()

    with pytest.raises(click.ClickException) as error:
        store.set(key, "super-secret")

    assert "credential" in str(error.value)
    assert not (store.scope_path(SCOPE_REPO) or Path("missing")).exists()


@pytest.mark.parametrize("key", ["jira", "", "Jira.Domain", "a..b", "jira.", ".domain", "jira.Domain"])
def test_set_rejects_keys_without_a_lowercase_namespace(workspace: Path, key: str) -> None:
    """Names must be dotted and lowercase, so the state file stays navigable."""
    assert workspace.exists()
    store = Store.get_instance()

    with pytest.raises(click.ClickException) as error:
        store.set(key, "value")

    assert "Invalid setting name" in str(error.value)


def test_set_is_atomic_when_interrupted(workspace: Path) -> None:
    """A write that dies half way must leave the previous file byte for byte as it was."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "first.atlassian.net")
    path = store.scope_path(SCOPE_REPO)
    assert path is not None
    original_bytes = path.read_bytes()

    with patch("json.dump", side_effect=RuntimeError("interrupted")):
        with pytest.raises(RuntimeError):
            store.set(DOMAIN_KEY, "second.atlassian.net")

    assert path.read_bytes() == original_bytes
    assert sorted(entry.name for entry in path.parent.iterdir()) == [STORE_FILE_NAME]


def _corrupt_repo_state_file(workspace: Path, content: bytes = b'{"jira.domain": ') -> Path:
    """Write unusable content into the repo scope's state file and return its path."""
    path = workspace / ".git" / APP_DIR_NAME / STORE_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_explicit_scope_access_raises_when_the_state_file_is_corrupt(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`items(scope=...)` asked about one exact scope must not lie about its unusable content.

    A truncated state file must not crash with a raw JSONDecodeError either -- the message names
    the path instead.
    """
    path = _corrupt_repo_state_file(workspace)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: False)
    Store.reset_instance()

    with pytest.raises(ValidationError) as error:
        Store.get_instance().items(scope=SCOPE_REPO)

    assert str(path) in str(error.value)
    assert error.value.exit_code == 113


def test_set_raises_when_the_target_scope_holds_non_object_json(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A state file holding a JSON array (or any non-object) must not crash with a raw TypeError."""
    path = _corrupt_repo_state_file(workspace, b"[]")
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: False)
    Store.reset_instance()

    with pytest.raises(ValidationError) as error:
        Store.get_instance().set(DOMAIN_KEY, "x.atlassian.net", SCOPE_REPO)

    assert str(path) in str(error.value)
    assert error.value.exit_code == 113


def test_get_degrades_to_the_other_scope_when_one_is_corrupt(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A broken `repo` file must not block a setting that only lives in the healthy `global` one."""
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "global.atlassian.net", SCOPE_GLOBAL)
    path = _corrupt_repo_state_file(workspace)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: False)
    Store.reset_instance()

    assert Store.get_instance().get(DOMAIN_KEY) == "global.atlassian.net"
    assert str(path) in capsys.readouterr().err


def test_get_warns_about_a_broken_scope_only_once_per_process(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Repeated lookups against the same broken scope must not spam the same warning per key."""
    path = _corrupt_repo_state_file(workspace)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: False)
    Store.reset_instance()
    store = Store.get_instance()

    store.get(DOMAIN_KEY)
    store.get(PROJECT_KEY)

    assert capsys.readouterr().err.count(str(path)) == 1


def _failing_confirm(*_args: object, **_kwargs: object) -> bool:
    """A `click.confirm` stand-in that fails the test the moment it is called.

    Used to prove a call site never even asks -- a mock that just returns a canned answer cannot
    tell "never asked" apart from "asked and happened to get that answer".
    """
    pytest.fail("this call site must never prompt")


def test_get_never_prompts_even_on_an_interactive_terminal(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`get` is read with `$(...)`; a prompt on a corrupt scope would corrupt the captured value.

    A `True` `isatty()` is deliberately still in place: the guard that matters is `get` never opting
    into the prompt in the first place, not the terminal happening to be non-interactive.
    """
    corrupted_bytes = b'{"jira.domain": '
    path = _corrupt_repo_state_file(workspace, corrupted_bytes)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mega_snake.util.store.click.confirm", _failing_confirm)
    Store.reset_instance()

    assert Store.get_instance().get(DOMAIN_KEY) is None
    assert path.read_bytes() == corrupted_bytes  # untouched, let alone moved or reset


def test_export_never_prompts_even_on_an_interactive_terminal(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`config export` is `eval`'d from a shell profile; a prompt there would hang every new terminal.

    Exercised the way `config_export` actually calls the store: `items(scope, interactive=False)`
    (its default), never opting in.
    """
    corrupted_bytes = _corrupt_repo_state_file(workspace).read_bytes()
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mega_snake.util.store.click.confirm", _failing_confirm)
    Store.reset_instance()

    with pytest.raises(ValidationError) as error:
        Store.get_instance().items(scope=SCOPE_REPO)

    assert error.value.exit_code == 113
    path = workspace / ".git" / APP_DIR_NAME / STORE_FILE_NAME
    assert path.read_bytes() == corrupted_bytes


def test_set_still_prompts_on_an_interactive_terminal(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The positive twin of the two tests above: this is what stops `interactive` from being disabled
    everywhere as a shortcut to make those pass."""
    _corrupt_repo_state_file(workspace)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    prompted: list[bool] = []
    monkeypatch.setattr("mega_snake.util.store.click.confirm", lambda *_a, **_k: prompted.append(True) or True)
    Store.reset_instance()

    Store.get_instance().set(DOMAIN_KEY, "recovered.atlassian.net", SCOPE_REPO)

    assert prompted == [True]


def test_list_still_prompts_on_an_interactive_terminal(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`config list` on an explicit scope opts in too, the same as `set`/`unset`."""
    _corrupt_repo_state_file(workspace)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    prompted: list[bool] = []
    monkeypatch.setattr("mega_snake.util.store.click.confirm", lambda *_a, **_k: prompted.append(True) or True)
    Store.reset_instance()

    Store.get_instance().items(scope=SCOPE_REPO, interactive=True)

    assert prompted == [True]


def test_corrupt_state_file_is_backed_up_and_reset_when_the_user_confirms(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Confirming the recovery prompt (triggered here through `set`, which opts in) must back up the
    broken file and restore functionality."""
    corrupted_bytes = b'{"jira.domain": '
    path = _corrupt_repo_state_file(workspace, corrupted_bytes)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mega_snake.util.store.click.confirm", lambda *_a, **_k: True)
    Store.reset_instance()
    store = Store.get_instance()

    store.set(DOMAIN_KEY, "recovered.atlassian.net", SCOPE_REPO)

    assert path.read_bytes() != corrupted_bytes
    backups = [entry for entry in path.parent.iterdir() if entry.name.startswith(f"{STORE_FILE_NAME}.corrupted-")]
    assert len(backups) == 1
    assert backups[0].read_bytes() == corrupted_bytes
    assert "Backed up" in capsys.readouterr().err
    # The store is actually usable again, not merely non-crashing: the value survived the reset.
    assert store.get(DOMAIN_KEY) == "recovered.atlassian.net"


def test_corrupt_state_file_stays_untouched_when_the_user_declines_recovery(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Declining must leave the broken file exactly as it was -- no backup, no reset."""
    corrupted_bytes = b'{"jira.domain": '
    path = _corrupt_repo_state_file(workspace, corrupted_bytes)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mega_snake.util.store.click.confirm", lambda *_a, **_k: False)
    Store.reset_instance()

    with pytest.raises(UserDeclinedError) as error:
        Store.get_instance().items(scope=SCOPE_REPO, interactive=True)

    assert error.value.exit_code == 114
    assert path.read_bytes() == corrupted_bytes
    assert sorted(entry.name for entry in path.parent.iterdir()) == [STORE_FILE_NAME]


def test_corrupt_state_file_fails_loudly_when_confirmation_cannot_be_asked(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A closed stdin (`click.confirm` raising `Abort`) must fail the same as a non-interactive run.

    A hang while waiting on input the process cannot receive would be worse than the old crash this
    whole mechanism replaces.
    """
    corrupted_bytes = b'{"jira.domain": '
    path = _corrupt_repo_state_file(workspace, corrupted_bytes)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)

    def _abort(*_args: object, **_kwargs: object) -> bool:
        raise click.exceptions.Abort()

    monkeypatch.setattr("mega_snake.util.store.click.confirm", _abort)
    Store.reset_instance()

    with pytest.raises(ValidationError) as error:
        Store.get_instance().items(scope=SCOPE_REPO, interactive=True)

    assert error.value.exit_code == 113
    assert path.read_bytes() == corrupted_bytes


def _unreadable(target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make exactly one path raise `PermissionError` on read, leaving every other path alone.

    A real `chmod(0o000)` is not usable here: it is a no-op on Windows (which this package supports)
    and it is also a no-op for the root user, which is how containers commonly run CI -- the test
    would then pass by reading the file just fine, which is the "a wrong value also makes it pass"
    failure mode. Patching the read is the only form that means the same thing everywhere.
    """
    original = Path.read_text

    def _read(self: Path, *args: object, **kwargs: object) -> str:
        if self == target:
            raise PermissionError(13, "Permission denied", str(target))
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", _read)


def test_explicit_scope_access_raises_when_the_state_file_cannot_be_read(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable state file must fail like an unusable one -- and must never offer to reset it.

    The distinction is the point: a file we cannot *read* very likely holds intact content behind
    wrong permissions, so the backup-and-reset offered for corrupt *content* would destroy
    recoverable state to fix something `chmod` solves. `_failing_confirm` proves the offer is never
    even made, on a fully interactive terminal with the caller opted in -- the exact combination that
    does prompt for a truncated file.
    """
    content = b'{"jira.domain": "intact.atlassian.net"}'
    path = _corrupt_repo_state_file(workspace, content)
    _unreadable(path, monkeypatch)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mega_snake.util.store.click.confirm", _failing_confirm)
    Store.reset_instance()

    with pytest.raises(ValidationError) as error:
        Store.get_instance().items(scope=SCOPE_REPO, interactive=True)

    assert str(path) in str(error.value)
    assert error.value.exit_code == 113
    monkeypatch.undo()
    assert path.read_bytes() == content  # nothing renamed, nothing reset
    assert sorted(entry.name for entry in path.parent.iterdir()) == [STORE_FILE_NAME]


def test_get_degrades_when_a_scope_state_file_cannot_be_read(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An unreadable scope must degrade exactly like a corrupt one, not kill the whole lookup.

    Before this, an unreadable file was the one failure mode that escaped `_load_gracefully` as a raw
    `PermissionError`, so a bad `chmod` on the global state file aborted `config export` -- which is
    `eval`'d from the shell profile on every new terminal.
    """
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "global.atlassian.net", SCOPE_GLOBAL)
    path = _corrupt_repo_state_file(workspace, b'{"jira.domain": "unreadable.atlassian.net"}')
    _unreadable(path, monkeypatch)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: False)
    Store.reset_instance()

    assert Store.get_instance().get(DOMAIN_KEY) == "global.atlassian.net"
    assert str(path) in capsys.readouterr().err


def test_recovery_fails_cleanly_when_the_backup_cannot_be_written(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A filesystem failure mid-recovery must surface as `ValidationError`, not a raw `OSError`.

    Also proves the invariant behind write-before-move: with the failure injected in the *first*
    step (writing the fresh file), the original corrupt content is provably still at `path` --
    nothing was renamed away before the failure.
    """
    corrupted_bytes = b'{"jira.domain": '
    path = _corrupt_repo_state_file(workspace, corrupted_bytes)
    store = Store.get_instance()
    store.set(PROJECT_KEY, "healthy-elsewhere", SCOPE_GLOBAL)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mega_snake.util.store.click.confirm", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "mega_snake.util.store.write_json_atomically",
        lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("disk is read-only")),
    )
    Store.reset_instance()

    with pytest.raises(ValidationError) as error:
        Store.get_instance().set(DOMAIN_KEY, "x.atlassian.net", SCOPE_REPO)

    assert str(path) in str(error.value)
    assert path.read_bytes() == corrupted_bytes  # nothing was renamed away before the write failed
    assert sorted(entry.name for entry in path.parent.iterdir()) == [STORE_FILE_NAME]
    # The healthy global scope is completely unaffected by the repo scope's failed recovery.
    Store.reset_instance()
    assert Store.get_instance().get(PROJECT_KEY) == "healthy-elsewhere"


def test_recovery_failure_message_survives_even_when_the_cleanup_of_the_fresh_file_also_fails(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The best-effort cleanup of the orphaned temporary file must not itself crash the recovery.

    Forces a second, independent failure (the `fresh.unlink` cleanup) on top of the first (the write
    itself), and asserts the original `ValidationError` about the write still surfaces -- the cleanup
    failure is swallowed on purpose, since a dangling temp file is a lesser problem than losing the
    diagnostic about the real one.
    """
    corrupted_bytes = b'{"jira.domain": '
    path = _corrupt_repo_state_file(workspace, corrupted_bytes)
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("mega_snake.util.store.click.confirm", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "mega_snake.util.store.write_json_atomically",
        lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("disk is read-only")),
    )
    monkeypatch.setattr(Path, "unlink", lambda *_a, **_k: (_ for _ in ()).throw(PermissionError("also read-only")))
    Store.reset_instance()

    with pytest.raises(ValidationError) as error:
        Store.get_instance().set(DOMAIN_KEY, "x.atlassian.net", SCOPE_REPO)

    assert "disk is read-only" in str(error.value)
    assert path.read_bytes() == corrupted_bytes


def test_global_scope_corruption_is_recovered_the_same_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The global scope resolves through `_global_store_dir`, a different path than `.git` -- exercise
    it explicitly instead of trusting that the repo-scope tests generalize."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    Store.reset_instance()
    path = tmp_path / "home" / ".config" / APP_DIR_NAME / STORE_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: False)
    Store.reset_instance()

    with pytest.raises(ValidationError) as error:
        Store.get_instance().items(scope=SCOPE_GLOBAL)

    assert str(path) in str(error.value)
    Store.reset_instance()


def test_get_returns_the_default_and_warns_twice_when_both_scopes_are_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Neither scope has an answer, and the diagnosis must name each broken file, not just one of them."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    monkeypatch.delenv(env_var_name(DOMAIN_KEY), raising=False)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    Store.reset_instance()
    repo_path = _corrupt_repo_state_file(repo)
    global_path = tmp_path / "home" / ".config" / APP_DIR_NAME / STORE_FILE_NAME
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text("not json either", encoding="utf-8")
    monkeypatch.setattr("mega_snake.util.store.sys.stdin.isatty", lambda: False)
    Store.reset_instance()

    assert Store.get_instance().get(DOMAIN_KEY, "fallback") == "fallback"
    warnings = capsys.readouterr().err
    assert str(repo_path) in warnings
    assert str(global_path) in warnings
    Store.reset_instance()


def test_unset_removes_a_secret_shaped_key_left_over_from_a_manual_edit(workspace: Path) -> None:
    """`set` never writes a credential-shaped key, but `unset` must still be able to remove one."""
    path = workspace / ".git" / APP_DIR_NAME / STORE_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"jira.api_token": "leaked"}), encoding="utf-8")
    Store.reset_instance()

    assert Store.get_instance().unset("jira.api_token", SCOPE_REPO) is True
    assert Store.get_instance().get("jira.api_token") is None


def test_unset_still_rejects_a_malformed_key(workspace: Path) -> None:
    """Allowing secret-shaped keys through `unset` must not also let malformed ones through."""
    assert workspace.exists()

    with pytest.raises(click.ClickException):
        Store.get_instance().unset("not-dotted", SCOPE_REPO)


def test_require_names_the_command_that_would_define_the_setting(workspace: Path) -> None:
    """The error has to be actionable: it spells out the exact command to run."""
    assert workspace.exists()

    with pytest.raises(click.ClickException) as error:
        Store.get_instance().require(PROJECT_KEY)

    assert f"mgsnake config set {PROJECT_KEY} <value>" in str(error.value)
    assert "JIRA_PROJECT_KEY" in str(error.value)


def test_require_returns_the_resolved_value(workspace: Path) -> None:
    """A configured setting is returned unchanged."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(PROJECT_KEY, "TAROTAPP")

    assert store.require(PROJECT_KEY) == "TAROTAPP"


def test_unset_removes_only_the_requested_scope(workspace: Path) -> None:
    """Unsetting the repository value falls back to the user-wide one, it does not erase it."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "global.atlassian.net", SCOPE_GLOBAL)
    store.set(DOMAIN_KEY, "repo.atlassian.net", SCOPE_REPO)

    assert store.unset(DOMAIN_KEY, SCOPE_REPO) is True
    assert store.get(DOMAIN_KEY) == "global.atlassian.net"


def test_unset_reports_when_there_was_nothing_to_remove(workspace: Path) -> None:
    """Removing an absent setting is a no-op the caller can report on."""
    assert workspace.exists()

    assert Store.get_instance().unset(DOMAIN_KEY, SCOPE_REPO) is False


def test_items_merges_the_scopes_with_the_repository_winning(workspace: Path) -> None:
    """The merged listing mirrors the read precedence between the two scopes."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "global.atlassian.net", SCOPE_GLOBAL)
    store.set(PROJECT_KEY, "TAROTAPP", SCOPE_REPO)
    store.set(DOMAIN_KEY, "repo.atlassian.net", SCOPE_REPO)

    assert store.items() == {DOMAIN_KEY: "repo.atlassian.net", PROJECT_KEY: "TAROTAPP"}
    assert store.items(SCOPE_GLOBAL) == {DOMAIN_KEY: "global.atlassian.net"}


def test_unknown_scope_is_rejected(workspace: Path) -> None:
    """A scope typo must fail loudly rather than resolve to nothing."""
    assert workspace.exists()

    with pytest.raises(click.ClickException) as error:
        Store.get_instance().scope_path("workspace")

    assert "Unknown scope 'workspace'" in str(error.value)


def test_stored_file_is_plain_sorted_json(workspace: Path) -> None:
    """The state file is meant to be readable and diffable by a human."""
    store = Store.get_instance()
    store.set(PROJECT_KEY, "TAROTAPP")
    store.set(DOMAIN_KEY, "repo.atlassian.net")
    path = workspace / ".git" / APP_DIR_NAME / STORE_FILE_NAME

    assert json.loads(path.read_text(encoding="utf-8")) == {
        DOMAIN_KEY: "repo.atlassian.net",
        PROJECT_KEY: "TAROTAPP",
    }
    assert path.read_text(encoding="utf-8").index(f'"{DOMAIN_KEY}"') < path.read_text(encoding="utf-8").index(
        f'"{PROJECT_KEY}"'
    )


def test_find_git_dir_follows_a_gitdir_file(tmp_path: Path) -> None:
    """Worktrees and submodules leave a `.git` file pointing at the real directory."""
    real_git_dir = tmp_path / "real" / "worktrees" / "wt"
    real_git_dir.mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {real_git_dir}\n", encoding="utf-8")

    assert find_git_dir(worktree) == real_git_dir.resolve()


def test_find_git_dir_returns_none_outside_a_repository(tmp_path: Path) -> None:
    """Nothing to find means None, not an exception."""
    outside = tmp_path / "outside"
    outside.mkdir()

    assert find_git_dir(outside) is None


def test_get_instance_is_a_singleton(workspace: Path) -> None:
    """Every call site shares one store, so one read of each file serves the whole run."""
    assert workspace.exists()

    assert Store.get_instance() is Store.get_instance()
