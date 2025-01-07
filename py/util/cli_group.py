"""Custom Click Group that supports command aliases."""

from typing import Any
from rich_click import RichGroup
import click


class CliGroup(RichGroup):
    """Custom Click Group that supports command aliases."""

    def add_command_with_alias(self, cmd: click.Command, aliases: list[str] | None = None) -> None:
        """Adds the ability to add `aliases` to commands."""
        if aliases and isinstance(aliases, list):
            super().add_command(cmd)
            for alias in aliases:
                alias_cmd = click.Command(
                    name=alias,
                    callback=cmd.callback,
                    hidden=True,
                    short_help=f"Alias for '{cmd.name}'.\n\n{cmd.help}",
                    params=cmd.params,
                    help=cmd.help,
                    epilog=cmd.epilog,
                )
                super().add_command(alias_cmd, alias)
        else:
            super().add_command(cmd, cmd.name)

    def command(self, *args, **kwargs) -> Any:
        """Adds the ability to add `aliases` to commands."""

        def decorator(f) -> Any:
            aliases = kwargs.pop("aliases", None)
            if aliases and isinstance(aliases, list):
                name = kwargs.pop("name", None)
                if not name:
                    raise click.UsageError("`name` command argument is required when using aliases.")

                base_command = super().command(name, *args, **kwargs)(f)

                for alias in aliases:
                    cmd = super().command(alias, hidden=True, *args, **kwargs)(f)
                    cmd.help = f"Alias for '{name}'.\n\n{cmd.help}"
                    cmd.params = base_command.params

            else:
                cmd = super().command(*args, **kwargs)(f)

            return cmd

        return decorator
