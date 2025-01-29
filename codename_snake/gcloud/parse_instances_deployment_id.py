""" This script is used to parse instances by deployment id and copy the command to clipboard """

import pyperclip
import click
from codename_snake.util.util import run_operation
from codename_snake.util.formatting import ws_advice, ws_success


@click.command(
    name="bqInstancesQuery",
    short_help="Parse instances by deployment id and copy the command to clipboard.",
    help="""Parse instances by deployment id and copy the command to clipboard.\n
    The command is intended to be used in BigQuery to filter instances by deployment id.""",
    epilog="""usage: snake bqInstancesQuery <project> <...deployment_ids...>""",
)
@click.argument("project", type=click.STRING)
@click.argument("deployment_ids", nargs=-1, required=True, type=str)
def bq_instances_by_deployment_id(project: str, deployment_ids: list[str]) -> None:
    """
    Parse instances by deployment id and copy the command to clipboard.
    The command is intended to be used in BigQuery to filter instances by deployment id.

    Args:
        project (str): project id
        deployment_ids (list[str]): list of deployment ids
    """
    arrays = []
    for d_id in deployment_ids:
        instance_list = run_operation(
            f'gcloud compute instances list --project {project} --filter="labels.deployment-id={d_id} AND (status=RUNNING OR status=TERMINATED)" --format="value(id)"',
            "retrieve instances by deployment id",
        ).stdout.strip()
        ws_advice(f"ProjectId: {d_id}")
        instances = instance_list.splitlines()
        arrays.extend(instances)
        ws_advice(f"elements at the moment: {len(arrays)}")
    result: str = '" OR "'.join(arrays)
    result = f'resource.labels.instance_id=("{result}")'
    result = f'resource.type="gce_instance"\n{result}'
    pyperclip.copy(result)
    ws_success("success: Command copied to clipboard")
