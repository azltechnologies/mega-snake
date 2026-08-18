"""Custom Click group helpers for aliases and documentation discovery."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import click
from importlib.resources import files
from rich_click import RichGroup

from mega_snake.constants import APP_NAME, DOCS_DIR, DOCS_FILE_SUFFIX, MODULE_NAME, RESOURCES_DIR

# Attribute set on a callback by @cli_metadata, holding every metadata keyword it was given.
# Deliberately distinct from META_FLAGS below: this is the *container* attribute name, not a key
# inside it. Keeping the two apart avoids the confusing "callback.flags == {'flags': ...}" shape
# that resulted from both once sharing the string "flags".
ATTR_METADATA = "_cli_metadata"
# Metadata keys, which double as the attribute names resolved onto the command object.
ATTR_ALIAS = "aliases"
ATTR_DOCS = "docs_fragment"
ATTR_GROUP = "docs_group"
# Metadata key holding the initialization flags read by the CLI entry point, e.g.
# `@cli_metadata(flags={"skip"})` produces `getattr(callback, ATTR_METADATA) == {"flags": {"skip"}}`.
META_FLAGS = "flags"
# Metadata key marking a command that rewrites one of the local environment files, so the shell has
# to re-source them once it finishes. Declared per command rather than per module: sitting in
# config_environment is not what makes a command change the environment, touching those files is.
META_RELOADS_ENV = "reloads_environment"
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

    def __resolve_origin(self, cmd: click.Command) -> str:
        """Describe where a command came from, for use in diagnostics.

        Parameters:
            cmd: The command whose origin should be described.

        Raises:
            None

        Returns:
            str: The command's documentation group, resolved from its module path when unset.
        """
        return getattr(cmd, ATTR_GROUP, "") or self._derive_group_name_from_callback(cmd.callback)

    def __reject_duplicate(self, name: str, cmd: click.Command, label: str) -> None:
        """Fail loudly when a name is already taken in this group.

        Click's registry is a plain dict, so a second registration under an existing name silently
        replaces the first one: the shadowed command becomes unreachable while every test that
        exercises it directly keeps passing. Refusing the registration turns that into an immediate,
        located failure instead of dead code that nobody notices.

        Parameters:
            name: The name (or alias) about to be registered.
            cmd: The command being registered under that name.
            label: How to describe the name in the error message ("Command" or "Alias").

        Raises:
            click.UsageError: If the name is already registered in this group.

        Returns:
            None
        """
        existing: Optional[click.Command] = self.commands.get(name)
        if existing is None:
            return
        raise click.UsageError(
            f"{label} '{name}' is already registered by '{self.__resolve_origin(existing)}' "
            f"and cannot be reused by '{self.__resolve_origin(cmd)}'. "
            "Rename one of them or drop the duplicate registration."
        )

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
                # An alias belongs to the same documentation group as the command it points at, so
                # a later collision against it reports the owning command instead of this module.
                setattr(alias_cmd, ATTR_GROUP, self.__resolve_origin(cmd))
                self.__reject_duplicate(alias, cmd, "Alias")
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
            click.UsageError: If the resolved name is already registered in this group.

        Returns:
            None
        """
        # Read custom metadata previously attached to a callback
        metadata = getattr(cmd.callback, ATTR_METADATA, {})
        fragment_name: str = getattr(cmd, ATTR_DOCS, "") or metadata.get(ATTR_DOCS) or cmd.name or ""
        explicit_group: str = getattr(cmd, ATTR_GROUP, "") or metadata.get(ATTR_GROUP) or ""
        setattr(cmd, ATTR_DOCS, fragment_name)
        setattr(cmd, ATTR_GROUP, explicit_group or self._derive_group_name_from_callback(cmd.callback))
        self.__reject_duplicate(name or cmd.name or "", cmd, "Command")
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
                base_command = super(CliGroup, self).command(name, *args, **kwargs)(f)
                setattr(base_command, ATTR_ALIAS, aliases)
                self.__add_alias_commands(base_command, aliases)
            else:
                super(CliGroup, self).command(*args, **kwargs)(f)

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
