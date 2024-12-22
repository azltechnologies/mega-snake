"""gcloud module for the CLI."""

import os
import click
from py.gcloud.parse_instances_deployment_id import bq_instances_by_deployment_id
from py.gcloud.parse_json_logs import parse_json_logs
from py.gcloud.sign import gcloud_login_env, gcloud_logout
from py.util.formatting import ws_advice

@click.group()
def gcloud() -> None:
    """gcloud related commands"""


def add_final_steps(command: click.Command) -> click.Command:
    """Adds final steps to a command."""

    @click.pass_context
    def wrapper(ctx, *args, **kwargs) -> None:
        # checking if gcloud is installed
        exit_status: int = os.system("gcloud --version")
        if exit_status == 0:
            ws_advice("gcloud is installed and the version command ran successfully.")
        else:
            raise RuntimeError("There was an error running the gcloud version command.")
        # Execute the original command
        result = ctx.invoke(command, *args, **kwargs)
        return result

    return click.Command(
        name=command.name,
        callback=wrapper,
        params=command.params,
        help=command.help,
    )


gcloud.add_command(bq_instances_by_deployment_id)
gcloud.add_command(parse_json_logs)
gcloud.add_command(gcloud_login_env)
gcloud.add_command(gcloud_logout)
