"""Tests for the `mgsnake config` command group."""

from pathlib import Path
import re

from click.testing import CliRunner
import pytest

from mega_snake import __main__ as app_main
from mega_snake.state.config_cmd import _format_export, config
from mega_snake.util.store import SCOPE_GLOBAL, SCOPE_REPO, STORE_FILE_NAME, Store, env_var_name

APP_DIR_NAME = "mgsnake"
DOMAIN_KEY = "jira.domain"
PROJECT_KEY = "jira.project_key"
BOARD_ID_KEY = "jira.board_id"


@pytest.fixture(name="workspace")
def workspace_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated home and git repository with a fresh store."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "home" / "AppData"))
    for key in (DOMAIN_KEY, PROJECT_KEY, BOARD_ID_KEY):
        monkeypatch.delenv(env_var_name(key), raising=False)
    monkeypatch.chdir(repo)
    Store.reset_instance()
    yield repo
    Store.reset_instance()


def test_get_writes_only_the_value_to_stdout(workspace: Path) -> None:
    """`config get` is consumed with command substitution, so its stdout is the value and nothing else.

    Asserted by equality: a containment check would pass even with a banner printed above the value.
    """
    assert workspace.exists()
    Store.get_instance().set(PROJECT_KEY, "TAROTAPP")

    result = CliRunner().invoke(config, ["get", PROJECT_KEY])

    assert result.exit_code == 0
    assert result.stdout == "TAROTAPP\n"


def _plain(output: str) -> str:
    """Strip the rich-click error box so a message can be matched across its wrapped lines."""
    return " ".join(re.sub(r"\x1b\[[0-9;]*m", "", output).replace("│", " ").split())


def test_get_fails_with_status_one_when_the_setting_is_missing(workspace: Path) -> None:
    """An unset setting is an error, not an empty string a script would silently use."""
    assert workspace.exists()

    result = CliRunner().invoke(config, ["get", PROJECT_KEY])

    assert result.exit_code == 1
    assert f"mgsnake config set {PROJECT_KEY} <value>" in _plain(result.output)


def test_config_runs_through_the_cli_without_the_shell_environment(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The group is `no_init`, so it answers before MEGA_SNAKE_SHELL exists.

    This is the whole reason the flag is on the group: the entry point would otherwise raise
    EnvironmentError before the command ever ran.
    """
    assert workspace.exists()
    monkeypatch.delenv("MEGA_SNAKE_SHELL", raising=False)
    Store.get_instance().set(PROJECT_KEY, "TAROTAPP")

    result = CliRunner().invoke(app_main.cli, ["config", "get", PROJECT_KEY])

    assert result.exit_code == 0
    assert result.stdout == "TAROTAPP\n"


def test_set_writes_to_the_repository_scope_by_default(workspace: Path) -> None:
    """Most settings belong to one clone, so that is the default target."""
    result = CliRunner().invoke(config, ["set", PROJECT_KEY, "TAROTAPP"])

    assert result.exit_code == 0
    assert (workspace / ".git" / APP_DIR_NAME / STORE_FILE_NAME).is_file()
    assert Store.get_instance().items(SCOPE_REPO) == {PROJECT_KEY: "TAROTAPP"}


def test_set_global_writes_to_the_user_scope_only(workspace: Path) -> None:
    """`--global` targets the user-wide file and leaves the repository one untouched."""
    result = CliRunner().invoke(config, ["set", DOMAIN_KEY, "azltech.atlassian.net", "--global"])

    assert result.exit_code == 0
    assert Store.get_instance().items(SCOPE_GLOBAL) == {DOMAIN_KEY: "azltech.atlassian.net"}
    assert Store.get_instance().items(SCOPE_REPO) == {}
    assert not (workspace / ".git" / APP_DIR_NAME / STORE_FILE_NAME).exists()


def test_set_refuses_a_credential_shaped_key(workspace: Path) -> None:
    """The CLI surfaces the store's refusal as a clean failure, not a traceback."""
    assert workspace.exists()

    result = CliRunner().invoke(config, ["set", "jira.api_token", "secret-value"])

    assert result.exit_code == 1
    assert "secret-value" not in result.output


def test_unset_removes_the_setting(workspace: Path) -> None:
    """Removing a setting reports success and the value stops resolving."""
    assert workspace.exists()
    Store.get_instance().set(PROJECT_KEY, "TAROTAPP")

    result = CliRunner().invoke(config, ["unset", PROJECT_KEY])

    assert result.exit_code == 0
    assert Store.get_instance().get(PROJECT_KEY) is None


def test_unset_warns_when_there_was_nothing_to_remove(workspace: Path) -> None:
    """An absent setting is reported, not silently treated as a successful removal."""
    assert workspace.exists()

    result = CliRunner().invoke(config, ["unset", PROJECT_KEY])

    assert result.exit_code == 0
    assert "nothing to remove" in result.output


def test_list_prints_one_key_value_pair_per_line(workspace: Path) -> None:
    """The listing is greppable, and merges both scopes by default."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "azltech.atlassian.net", SCOPE_GLOBAL)
    store.set(PROJECT_KEY, "TAROTAPP", SCOPE_REPO)

    result = CliRunner().invoke(config, ["list"])

    assert result.exit_code == 0
    assert f"{DOMAIN_KEY}=azltech.atlassian.net" in result.output
    assert f"{PROJECT_KEY}=TAROTAPP" in result.output


def test_list_honours_the_scope_filter(workspace: Path) -> None:
    """Asking for one scope must not show the other one's settings."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "azltech.atlassian.net", SCOPE_GLOBAL)
    store.set(PROJECT_KEY, "TAROTAPP", SCOPE_REPO)

    result = CliRunner().invoke(config, ["list", "--scope", SCOPE_REPO])

    assert result.exit_code == 0
    assert f"{PROJECT_KEY}=TAROTAPP" in result.output
    assert DOMAIN_KEY not in result.output


def test_list_reports_an_empty_scope(workspace: Path) -> None:
    """An empty store says so instead of printing nothing at all."""
    assert workspace.exists()

    result = CliRunner().invoke(config, ["list"])

    assert result.exit_code == 0
    assert "No settings stored" in result.output


def test_export_emits_evaluable_statements(workspace: Path) -> None:
    """`config export` is read with eval, so its stdout is statements and nothing else."""
    assert workspace.exists()
    store = Store.get_instance()
    store.set(PROJECT_KEY, "TAROTAPP", SCOPE_GLOBAL)
    store.set(DOMAIN_KEY, "azltech.atlassian.net", SCOPE_GLOBAL)

    result = CliRunner().invoke(config, ["export", "--shell", "bash"])

    assert result.exit_code == 0
    assert result.stdout == (
        "export JIRA_DOMAIN='azltech.atlassian.net'\nexport JIRA_PROJECT_KEY='TAROTAPP'\n"
    )


def test_export_leaves_the_repository_scope_out_by_default(workspace: Path) -> None:
    """An exported variable outranks every scope, so a per-clone setting must not reach the profile.

    `config export` is documented as something to `eval` from the shell profile, which runs in
    whatever directory the terminal opened in. Promoting this clone's `jira.board_id` and
    `jira.project_key` into the environment would make *every other* clone resolve them from here:
    `mgsnake jira-issues` in repo B would silently download repo A's board.
    """
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "azltech.atlassian.net", SCOPE_GLOBAL)
    store.set(BOARD_ID_KEY, "17")
    store.set(PROJECT_KEY, "TAROTAPP")

    default_scope = CliRunner().invoke(config, ["export", "--shell", "bash"])
    every_scope = CliRunner().invoke(config, ["export", "--shell", "bash", "--scope", "all"])

    assert default_scope.stdout == "export JIRA_DOMAIN='azltech.atlassian.net'\n"
    assert "JIRA_BOARD_ID" not in default_scope.stdout
    assert "JIRA_PROJECT_KEY" not in default_scope.stdout
    # --scope all is still reachable for anyone who wants exactly that; it is only the default that
    # changed, because the default is the one a profile ends up using.
    assert "export JIRA_BOARD_ID='17'" in every_scope.stdout


@pytest.mark.parametrize(
    ("shell", "value", "expected"),
    [
        ("bash", "TAROTAPP", "export JIRA_PROJECT_KEY='TAROTAPP'"),
        ("zsh", "TAROTAPP", "export JIRA_PROJECT_KEY='TAROTAPP'"),
        ("bash", "it's", "export JIRA_PROJECT_KEY='it'\\''s'"),
        ("pwsh", "TAROTAPP", "$env:JIRA_PROJECT_KEY = 'TAROTAPP'"),
        ("powershell", "it's", "$env:JIRA_PROJECT_KEY = 'it''s'"),
    ],
)
def test_format_export_quotes_per_shell(shell: str, value: str, expected: str) -> None:
    """A value containing a quote must survive the shell that evaluates it."""
    assert _format_export(shell, PROJECT_KEY, value) == expected


def test_export_emits_the_global_value_of_a_key_that_both_scopes_define(workspace: Path) -> None:
    """The sibling of the test above: what happens when the *same* key lives in both scopes.

    `export` writes environment variables, and those outrank both scopes, so evaluating this from a
    shell profile makes the global value answer for a clone that deliberately overrode it -- and
    `config set` defaults to the repo scope, so such overrides are the normal thing a user creates.
    This is not a defect `export` can fix (a profile runs in whatever directory the terminal opened
    in, so there is no "current repository" to filter against that would be reproducible); it is
    documented in `config.md` and in the `--scope` help, and pinned here so nobody has to guess
    which of the two a profile ends up using.
    """
    assert workspace.exists()
    store = Store.get_instance()
    store.set(DOMAIN_KEY, "company-a.atlassian.net", SCOPE_GLOBAL)
    store.set(DOMAIN_KEY, "company-b.atlassian.net")

    exported = CliRunner().invoke(config, ["export", "--shell", "bash"])

    assert exported.stdout == "export JIRA_DOMAIN='company-a.atlassian.net'\n"
    assert "company-b.atlassian.net" not in exported.stdout, "the repo override does not reach the profile"
    # And the store itself still resolves the override correctly for anything that reads it in place:
    # it is only the exported copy that inverts the precedence, which is the whole point of the note.
    assert store.get(DOMAIN_KEY) == "company-b.atlassian.net"


def test_export_defaults_to_the_active_shell(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --shell the syntax follows MEGA_SNAKE_SHELL, which the setup script exports."""
    assert workspace.exists()
    Store.get_instance().set(PROJECT_KEY, "TAROTAPP", SCOPE_GLOBAL)
    monkeypatch.setenv("MEGA_SNAKE_SHELL", "pwsh")

    result = CliRunner().invoke(config, ["export"])

    assert result.stdout == "$env:JIRA_PROJECT_KEY = 'TAROTAPP'\n"


@pytest.mark.parametrize(
    "key",
    ["jira.api_token", "jira.secret", "github.password", "app.credential", "jira.apikey"],
    ids=["token", "secret", "password", "credential", "apikey"],
)
def test_get_refuses_a_credential_shaped_key(workspace: Path, monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    """The guard was on the half that never held a secret; the read path is the one that discloses.

    `config set jira.api_token` was refused from the start, so the store genuinely never holds a
    credential -- but `config get`'s *first* precedence layer is the environment, and it validated
    nothing. `mgsnake config get jira.api_token` therefore printed the live token to stdout, where a
    command substitution, a CI log or a screen share picks it up, from a command that reads like
    harmless introspection.

    The token is injected here deliberately, so the test fails if the value is echoed rather than
    passing merely because nothing was set.
    """
    assert workspace.exists()
    monkeypatch.setenv(env_var_name(key), "SUPER-SECRET-VALUE")

    result = CliRunner().invoke(config, ["get", key])

    assert result.exit_code == 1
    assert result.stdout == "", "nothing reaches the data channel"
    assert "SUPER-SECRET-VALUE" not in result.output, "the value must not appear anywhere, stderr included"


@pytest.mark.parametrize("key", ["path", "home", "UPPER.CASE", "jira..domain", "jira.domain "])
def test_get_refuses_a_key_that_is_not_a_setting_name(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    """`config get path` echoed `$PATH`, because any word maps to a variable name.

    A bare word is not a dotted setting name, so the format check the write path always ran is what
    stops the read path from being a general-purpose environment dumper. `PATH` is injected with a
    recognisable value for the same reason as above: an empty environment would make this pass for
    the wrong reason.
    """
    assert workspace.exists()
    monkeypatch.setenv(env_var_name(key.strip()) or "PATH", "/marker/bin")

    result = CliRunner().invoke(config, ["get", key])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "/marker/bin" not in result.output


def test_get_still_answers_a_well_formed_setting_from_the_environment(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative of the two tests above: the guards must not break the command's actual job.

    `config get` exists to be read with `$(...)`, and the environment is a legitimate source -- so a
    well-formed, non-credential key must still resolve from it, with the value alone on stdout.
    """
    assert workspace.exists()
    monkeypatch.setenv(env_var_name(PROJECT_KEY), "FROM-ENV")

    result = CliRunner().invoke(config, ["get", PROJECT_KEY])

    assert result.exit_code == 0
    assert result.stdout == "FROM-ENV\n"
