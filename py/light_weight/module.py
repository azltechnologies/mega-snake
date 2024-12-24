"""Contains the main command group for the light_weight module."""

import click
from py.util.util import cli_metadata
from py.light_weight.echo import echo
from py.light_weight.create_release import create_release
from py.light_weight.jks_expired_certs import expired_certs
from py.util.util import wrapper_decorator


@click.group()
def main() -> None:
    """light weight commands"""


@cli_metadata(flags={"skip"})
def wrapper(_ctx, *_args, **_kwargs) -> None:
    """Wrapper for the light_weight command."""


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)

main.add_command(echo)
main.add_command(create_release)
main.add_command(expired_certs)
