"""The `config` command group: read and write the persistent CLI state.

Every subcommand is a thin shell over :class:`mega_snake.util.store.Store`; the interesting rules
(scope resolution, secret rejection, atomic writes) live there.

The whole group runs with ``no_init``. ``config get`` and ``config export`` are meant to be consumed
with command substitution (``$(mgsnake config get jira.project_key)``,
``eval "$(mgsnake config export --shell bash)"``), so they must answer before the environment they
help configure exists, exactly like ``shell-path``. A Click group carries a single set of
initialization flags for all of its subcommands, so that requirement decides the whole group -- which
costs nothing, because the store is deliberately independent of ``AppProperties``.
"""

import os
from typing import Optional

import click

from mega_snake.constants import SHELL_OPT
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.formatting import ws_info, ws_success, ws_warning
from mega_snake.util.store import SCOPE_ALL, SCOPE_GLOBAL, SCOPE_REPO, Store, env_var_name
from mega_snake.util.util import cli_metadata

LIST_SCOPES: tuple[str, ...] = (SCOPE_REPO, SCOPE_GLOBAL, SCOPE_ALL)
POSIX_SHELLS: tuple[str, ...] = ("bash", "zsh")
DEFAULT_EXPORT_SHELL: str = "bash"


def _scope_of(global_scope: bool) -> str:
    """Translate the ``--global`` flag into a store scope.

    Parameters:
        global_scope: Whether the user asked for the user-wide scope.

    Raises:
        None

    Returns:
        str: ``global`` when the flag is set, ``repo`` otherwise.
    """
    return SCOPE_GLOBAL if global_scope else SCOPE_REPO


def _format_export(shell: str, key: str, value: str) -> str:
    """Render one setting as a shell statement that exports its environment variable.

    Parameters:
        shell: The target shell, one of ``SHELL_OPT``.
        key: The dotted setting name.
        value: The stored value.

    Raises:
        None

    Returns:
        str: A single line ready to be evaluated by the given shell.
    """
    variable: str = env_var_name(key)
    if shell in POSIX_SHELLS:
        # A POSIX single-quoted string cannot contain a single quote, so close it, escape the quote,
        # and reopen: foo'bar becomes 'foo'\''bar'.
        posix_value: str = value.replace("'", "'\\''")
        return f"export {variable}='{posix_value}'"
    # PowerShell escapes a single quote inside a single-quoted string by doubling it.
    powershell_value: str = value.replace("'", "''")
    return f"$env:{variable} = '{powershell_value}'"


@click.group(
    name="config",
    cls=CliGroup,
    short_help="Reads and writes the settings mgsnake remembers between runs.",
    help="""Reads and writes the persistent settings mgsnake remembers between runs, in two scopes:
    `repo` (stored inside the current clone's git directory) and `global` (stored in the user's
    config directory). Reads resolve through `environment variable > repo > global`, so an exported
    variable always wins and existing environment-based workflows keep working. Credential-shaped
    names are refused: secrets stay in environment variables only.""",
)
@cli_metadata(flags={"no_init"}, docs_group="Configuration")
def config() -> None:
    """Group entry point for the persistent state commands.

    Parameters:
        None

    Raises:
        None

    Returns:
        None
    """


@config.command(
    name="get",
    short_help="Prints the resolved value of a setting.",
    help="Prints to stdout the resolved value of a setting, following the "
    "`environment variable > repo > global` precedence chain. Nothing else is written to stdout, "
    "so the output can be captured with command substitution. Exits with status 1 when the setting "
    "is defined nowhere.",
    epilog="""
    Args:\n
        key: str - dotted name of the setting to read, e.g. jira.project_key.
    """,
)
@click.argument("key")
def config_get(key: str) -> None:
    """Print the resolved value of one setting.

    Parameters:
        key: The dotted setting name.

    Raises:
        click.ClickException: If the setting is defined nowhere, or an explicit-scope call elsewhere
            in the process already reported a scope's state file as unusable. This command itself
            never prompts to recover one, even from an interactive terminal: its stdout is a data
            channel (`$(mgsnake config get ...)`), and a broken scope is skipped with a warning on
            stderr instead -- see ``Store.get``.

    Returns:
        None
    """
    click.echo(Store.get_instance().require(key))


@config.command(
    name="set",
    short_help="Stores a setting in the repo (default) or global scope.",
    help="Stores a setting so later runs can resolve it without being told again. Writes to the "
    "current clone's scope by default, or to the user-wide scope with `--global`. The write is "
    "atomic, so an interrupted run can never leave a corrupt state file behind.",
    epilog="""
    Args:\n
        key: str - dotted name of the setting, e.g. jira.project_key.\n
        value: str - value to store.
    """,
)
@click.argument("key")
@click.argument("value")
@click.option(
    "--global",
    "global_scope",
    is_flag=True,
    default=False,
    help="Store the setting for every repository of this user instead of only the current clone.",
)
def config_set(key: str, value: str, global_scope: bool) -> None:
    """Persist one setting in the requested scope.

    Parameters:
        key: The dotted setting name.
        value: The value to store.
        global_scope: Whether to write to the user-wide scope instead of the current clone.

    Raises:
        click.ClickException: If the key looks like a credential, is malformed, the repo scope is
            requested outside a repository, or the target scope's state file is unusable and could
            not be recovered -- an interactive terminal is offered a backup-and-reset prompt first.

    Returns:
        None
    """
    scope: str = _scope_of(global_scope)
    Store.get_instance().set(key, value, scope)
    ws_success(f"Set {key} = {value} ({scope} scope)")


@config.command(
    name="unset",
    short_help="Removes a setting from the repo (default) or global scope.",
    help="Removes a setting from one scope. Only the requested scope is touched, so unsetting a "
    "repository value leaves the user-wide one in place and reads fall back to it.",
    epilog="""
    Args:\n
        key: str - dotted name of the setting to remove.
    """,
)
@click.argument("key")
@click.option(
    "--global",
    "global_scope",
    is_flag=True,
    default=False,
    help="Remove the setting from the user-wide scope instead of the current clone.",
)
def config_unset(key: str, global_scope: bool) -> None:
    """Remove one setting from the requested scope.

    Parameters:
        key: The dotted setting name.
        global_scope: Whether to remove from the user-wide scope instead of the current clone.

    Raises:
        click.ClickException: If the key is malformed, the repo scope is requested outside a
            repository, or the target scope's state file is unusable and could not be recovered --
            an interactive terminal is offered a backup-and-reset prompt first.

    Returns:
        None
    """
    scope: str = _scope_of(global_scope)
    if Store.get_instance().unset(key, scope):
        ws_success(f"Removed {key} ({scope} scope)")
        return
    ws_warning(f"{key} was not set in the {scope} scope; nothing to remove.")


@config.command(
    name="list",
    short_help="Lists the stored settings.",
    help="Lists the stored settings as `key=value` lines, one per line. Environment overrides are "
    "not applied here: this shows what is on disk, which is what `set` and `unset` operate on.",
)
@click.option(
    "--scope",
    type=click.Choice(LIST_SCOPES),
    default=SCOPE_ALL,
    show_default=True,
    help="Which scope to list: 'repo' for the current clone, 'global' for the user-wide settings, "
    "or 'all' for both merged with the repository scope taking precedence.",
)
def config_list(scope: str) -> None:
    """List the settings stored in one or both scopes.

    Parameters:
        scope: One of ``repo``, ``global`` or ``all``.

    Raises:
        click.ClickException: If a single scope (``repo`` or ``global``) is requested explicitly and
            its state file is unusable -- an interactive terminal is offered a backup-and-reset
            prompt first. ``all`` merges both scopes and degrades a broken one instead of failing --
            see ``Store._load_gracefully``.

    Returns:
        None
    """
    store: Store = Store.get_instance()
    values: dict[str, str] = store.items(None if scope == SCOPE_ALL else scope, interactive=True)
    if not values:
        ws_info(f"No settings stored in the {scope} scope.")
        return
    for key in sorted(values):
        click.echo(f"{key}={values[key]}")


@config.command(
    name="export",
    short_help="Prints the stored settings as shell export statements.",
    help="Prints the stored settings as export statements for the given shell, so the store can be "
    "the single source of truth and the shell environment merely a cache of it. Meant to be "
    "evaluated from the shell profile, next to the `mgsnake reload-config` command. Only the "
    "user-wide scope is exported by default: an environment variable outranks every scope, so "
    "exporting a per-clone setting from the profile would answer for the wrong repository. Only "
    "the statements are written to stdout.",
)
@click.option(
    "--shell",
    type=click.Choice(SHELL_OPT, False),
    default=None,
    help="Target shell syntax. Defaults to $MEGA_SNAKE_SHELL, then to bash.",
)
@click.option(
    "--scope",
    type=click.Choice(LIST_SCOPES),
    default=SCOPE_GLOBAL,
    show_default=True,
    help="Which scope to export: 'global' for the user-wide settings, 'repo' for the current "
    "clone's, or 'all' for both merged with the repository scope taking precedence. Exporting "
    "anything but 'global' from a shell profile pins one clone's settings onto the whole session.",
)
def config_export(shell: Optional[str], scope: str) -> None:
    """Print the stored settings as shell export statements.

    Parameters:
        shell: The target shell. Defaults to ``$MEGA_SNAKE_SHELL`` and then to bash.
        scope: One of ``repo``, ``global`` or ``all``.

    Raises:
        click.ClickException: If a single scope (``repo`` or ``global``) is requested explicitly and
            its state file is unusable. This never prompts, even from an interactive terminal:
            ``export`` is meant to be ``eval``'d from a shell profile, where a prompt would hang the
            terminal's startup instead of failing it in milliseconds. ``all`` merges both scopes and
            degrades a broken one instead of failing -- see ``Store._load_gracefully``.

    Returns:
        None
    """
    target_shell: str = shell or os.environ.get("MEGA_SNAKE_SHELL") or DEFAULT_EXPORT_SHELL
    values: dict[str, str] = Store.get_instance().items(None if scope == SCOPE_ALL else scope)
    for key in sorted(values):
        click.echo(_format_export(target_shell, key, values[key]))
