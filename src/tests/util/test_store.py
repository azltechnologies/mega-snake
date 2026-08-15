"""Tests for the persistent key/value store backing `mgsnake config`."""

import json
from pathlib import Path
from unittest.mock import patch

import click
import pytest

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
    """Provide an isolated home and git repository with a fresh store."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    for key in (DOMAIN_KEY, PROJECT_KEY):
        monkeypatch.delenv(env_var_name(key), raising=False)
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


def test_corrupt_store_raises_click_exception_naming_the_path(workspace: Path) -> None:
    """A truncated state file must not crash every command with a raw JSONDecodeError."""
    path = workspace / ".git" / APP_DIR_NAME / STORE_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"jira.domain": ', encoding="utf-8")
    Store.reset_instance()

    with pytest.raises(click.ClickException) as error:
        Store.get_instance().get(DOMAIN_KEY)

    assert str(path) in str(error.value)


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
