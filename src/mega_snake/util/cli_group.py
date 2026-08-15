"""Custom Click group helpers for aliases and documentation discovery."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import click
from importlib.resources import files
from rich_click import RichGroup
from rich_click.rich_help_formatter import RichHelpFormatter

from mega_snake.constants import APP_NAME, DOCS_DIR, DOCS_FILE_SUFFIX, MODULE_NAME, RESOURCES_DIR

# Attribute set on a callback by @cli_metadata, holding every metadata keyword it was given.
ATTR_METADATA = "flags"
# Metadata keys, which double as the attribute names resolved onto the command object.
ATTR_ALIAS = "aliases"
ATTR_DOCS = "docs_fragment"
ATTR_GROUP = "docs_group"
# Metadata key holding the initialization flags read by the CLI entry point (hence the double
# nesting: `@cli_metadata(flags={"skip"})` produces `callback.flags == {"flags": {"skip"}}`).
META_FLAGS = "flags"
DEFAULT_GROUP_KEY = "commands"


@dataclass(frozen=True)
class DocumentedCommand:
    """Normalized documentation metadata for one real CLI command.

    Parameters:
        name: The public command name.
        command: The click command object.
        aliases: The hidden aliases registered for the command.
        group: The resolved documentation group title.
        fragment_name: The resolved fragment file stem.
        fragment_path: The resolved fragment path on disk.

    Raises:
        None

    Returns:
        None
    """

    name: str
    command: click.Command
    aliases: tuple[str, ...]
    group: str
    fragment_name: str
    fragment_path: Path


class CliGroup(RichGroup):
    """Custom Click Group that supports command aliases."""

    @staticmethod
    def _derive_group_title(group_name: str) -> str:
        """Convert an internal group key into a display title.

        Parameters:
            group_name: The raw group name or module segment.

        Raises:
            None

        Returns:
            str: A human-readable group title.
        """
        return group_name.replace("_", " ").replace("-", " ").title()

    @classmethod
    def _derive_group_name_from_callback(cls, callback: Any) -> str:
        """Resolve a documentation group title from a callback module path.

        Parameters:
            callback: The callback whose module path should be inspected.

        Raises:
            None

        Returns:
            str: A human-readable group title derived from the callback module path.
        """
        module_name: str = getattr(callback, "__module__", DEFAULT_GROUP_KEY)
        module_parts: list[str] = module_name.split(".")
        group_key: str = module_parts[1] if len(module_parts) > 1 else module_parts[0]
        return cls._derive_group_title(group_key)

    def __add_alias_commands(self, cmd: click.Command, aliases: Optional[list[str]] = None) -> None:
        """Register hidden alias commands for the given real command.

        Parameters:
            cmd: The public command that owns the aliases.
            aliases: The alias names to register.

        Raises:
            None

        Returns:
            None
        """
        if aliases and isinstance(aliases, list):
            for alias in aliases:
                alias_cmd = click.Command(
                    name=alias,
                    callback=cmd.callback,
                    hidden=True,
                    params=cmd.params,
                    help=f"Alias for '{cmd.name}'. Please see '{APP_NAME} {cmd.name} --help' for more information.",
                    short_help=f"Alias for '{cmd.name}'.",
                    epilog=cmd.epilog,
                )
                super().add_command(alias_cmd, alias)

    def add_command(
        self,
        cmd: click.Command,
        name: Optional[str] = None,
        aliases: Optional[Iterable[str]] = None,
        panel: Optional[str] = None,
    ) -> None:
        """Resolve documentation metadata onto the command object then
        register a command after resolving its documentation metadata.

        An explicitly declared group title (through ``@cli_metadata(docs_group=...)`` or an
        attribute already set on the command) is used verbatim, since whoever wrote it chose how it
        should read. Only a title *derived* from the module path is reformatted into a display
        title, because there the raw value is an identifier such as ``remote_branches``.

        Parameters:
            cmd: The command to register.
            name: Optional explicit command name override.
            aliases: Optional aliases forwarded to rich-click.
            panel: Optional rich-click panel forwarded unchanged.

        Raises:
            None

        Returns:
            None
        """
        # Read custom metadata previously attached to a callback
        metadata = getattr(cmd.callback, ATTR_METADATA, {})
        fragment_name: str = getattr(cmd, ATTR_DOCS, "") or metadata.get(ATTR_DOCS) or cmd.name or ""
        explicit_group: str = getattr(cmd, ATTR_GROUP, "") or metadata.get(ATTR_GROUP) or ""
        setattr(cmd, ATTR_DOCS, fragment_name)
        setattr(cmd, ATTR_GROUP, explicit_group or self._derive_group_name_from_callback(cmd.callback))
        super().add_command(cmd, name, aliases=aliases, panel=panel)

    def add_command_with_alias(self, cmd: click.Command, aliases: Optional[list[str]] = None) -> None:
        """Register a command and its hidden aliases.

        Parameters:
            cmd: The public command to register.
            aliases: The aliases that should resolve to the same callback.

        Raises:
            None

        Returns:
            None
        """
        if aliases and isinstance(aliases, list):
            setattr(cmd, ATTR_ALIAS, aliases)
            self.add_command(cmd)
            self.__add_alias_commands(cmd, aliases)
        else:
            self.add_command(cmd, cmd.name)

    def command(self, *args, **kwargs) -> Any:
        """Support alias registration through the group decorator.

        Parameters:
            *args: Positional arguments forwarded to click.
            **kwargs: Keyword arguments forwarded to click.

        Raises:
            click.UsageError: If aliases are declared without an explicit command name.

        Returns:
            Any: The wrapped click decorator.
        """

        def decorator(f: Any) -> Any:
            aliases = kwargs.pop(ATTR_ALIAS, None)
            if aliases and isinstance(aliases, list):
                name = kwargs.pop("name", None)
                if not name:
                    raise click.UsageError("`name` command argument is required when using aliases.")
                base_command = super(CliGroup, self).command(name, *args, **kwargs)(f)  # pylint: disable=R1725
                setattr(base_command, ATTR_ALIAS, aliases)
                self.__add_alias_commands(base_command, aliases)
            else:
                super(CliGroup, self).command(*args, **kwargs)(f)  # pylint: disable=R1725

        return decorator

    def iter_documented_commands(self) -> Iterator[DocumentedCommand]:
        """Yield one normalized entry per real command in deterministic order.

        Parameters:
            None

        Raises:
            None

        Returns:
            Iterator[DocumentedCommand]: All non-hidden commands with resolved docs metadata.
        """
        # Resolve the packaged docs fragment directory
        docs_dir: Path = Path(str(files(MODULE_NAME).joinpath(RESOURCES_DIR, DOCS_DIR)))
        entries: list[DocumentedCommand] = []
        for name, command in self.commands.items():
            if command.hidden:
                continue
            fragment_name: str = getattr(command, ATTR_DOCS, command.name or name)
            fragment_file: str = (
                fragment_name if fragment_name.endswith(DOCS_FILE_SUFFIX) else f"{fragment_name}{DOCS_FILE_SUFFIX}"
            )
            group_name: str = getattr(command, ATTR_GROUP, self._derive_group_name_from_callback(command.callback))
            entries.append(
                DocumentedCommand(
                    name=name,
                    command=command,
                    aliases=tuple(getattr(command, ATTR_ALIAS, [])),
                    group=group_name,
                    fragment_name=fragment_name.removesuffix(DOCS_FILE_SUFFIX),
                    fragment_path=docs_dir / fragment_file,
                )
            )
        yield from sorted(entries, key=lambda entry: (entry.group.casefold(), entry.name))

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Render command names with aliases without mutating the registry.

        Note: rich-click renders the group help through its own ``rich_format_help`` pipeline, so
        this override is only reached by plain-Click rendering paths (a ``click.HelpFormatter``,
        or a future version that restores the classic pipeline). It is kept non-destructive on
        purpose: the previous implementation rewrote ``self.commands`` keys while rendering, which
        broke every later lookup by name.

        Parameters:
            ctx: The active click context.
            formatter: The help formatter used by click/rich-click.

        Raises:
            None

        Returns:
            None
        """
        if isinstance(formatter, RichHelpFormatter):
            formatter.config.text_markup = "rich"

        commands: list[tuple[str, click.Command]] = []
        for subcommand in self.list_commands(ctx):
            command = self.get_command(ctx, subcommand)
            if command is None or command.hidden:
                continue
            aliases: list[str] = getattr(command, ATTR_ALIAS, [])
            display_name: str = subcommand if not aliases else f"{subcommand} | {' | '.join(aliases)}"
            commands.append((display_name, command))

        if not commands:
            return

        limit = formatter.width - 6 - max(len(command_name) for command_name, _command in commands)
        rows = [(command_name, command.get_short_help_str(limit)) for command_name, command in commands]
        with formatter.section("Commands"):
            formatter.write_dl(rows)
