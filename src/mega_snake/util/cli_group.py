"""Custom Click Group that supports command aliases."""

from typing import Any, cast
from rich_click import RichGroup
from rich_click.rich_help_formatter import RichHelpFormatter
from rich_click.rich_context import RichContext
import click
from mega_snake.constants import APP_NAME

ATTR_ALIAS = "aliases"


class CliGroup(RichGroup):
    """Custom Click Group that supports command aliases."""

    def __add_alias_commands(self, cmd: click.Command, aliases: list[str] | None = None) -> None:
        """Adds the ability to add `aliases` to commands."""
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

    def add_command_with_alias(self, cmd: click.Command, aliases: list[str] | None = None) -> None:
        """Adds the ability to add `|` to commands."""
        if aliases and isinstance(aliases, list):
            setattr(cmd, ATTR_ALIAS, aliases)
            super().add_command(cmd)
            self.__add_alias_commands(cmd, aliases)
        else:
            super().add_command(cmd, cmd.name)

    def command(self, *args, **kwargs) -> Any:
        """Adds the ability to add `aliases` to commands."""

        def decorator(f) -> Any:
            aliases = kwargs.pop(ATTR_ALIAS, None)
            if aliases and isinstance(aliases, list):
                name = kwargs.pop("name", None)
                if not name:
                    raise click.UsageError("`name` command argument is required when using aliases.")
                base_command = super(CliGroup, self).command(name, *args, **kwargs)(f)  # pylint: disable=R1725
                self.__add_alias_commands(base_command, aliases)
            else:
                super(CliGroup, self).command(*args, **kwargs)(f)  # pylint: disable=R1725

        return decorator

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Override format_commands to respect the hidden property."""
        fter = cast(RichHelpFormatter, formatter)
        fter.config.text_markup = "rich"
        rows = list(self.commands.items())
        for name, cmd in rows:
            del self.commands[name]
            new_name = f"{name}"
            if not hasattr(cmd, ATTR_ALIAS):
                setattr(cmd, ATTR_ALIAS, [])
            else:
                new_name = f"{name} | "
            list_aliases: list[str] = getattr(cmd, ATTR_ALIAS)
            new_name += " | ".join(list_aliases)
            self.commands[new_name] = cmd
        super().format_commands(cast(RichContext, ctx), fter)
