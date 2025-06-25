"""gcloud module for the CLI."""

import click
from codename_snake.gcloud.parse_instances_deployment_id import bq_instances_by_deployment_id
from codename_snake.gcloud.parse_json_logs import parse_json_logs
from codename_snake.gcloud.sign import gcloud_login_env, gcloud_logout
from codename_snake.util.formatting import ws_advice
from codename_snake.util.util import wrapper_decorator, get_command_return_code
from codename_snake.util.cli_group import CliGroup


@click.group(cls=CliGroup)
def main() -> None:
    """gcloud related commands"""


def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    """Wrapper for the gcloud command."""
    # checking if gcloud is installed
    exit_status: int = get_command_return_code("gcloud --version")
    if exit_status == 0:
        ws_advice("gcloud is installed and the version command ran successfully.")
    else:
        raise RuntimeError("There was an error running the gcloud version command.")


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)

main.add_command(bq_instances_by_deployment_id)
main.add_command(parse_json_logs)
main.add_command_with_alias(gcloud_login_env, ["gl"])
main.add_command_with_alias(gcloud_logout, ["lg"])
