"""logins to gcloud and sets the project"""

import os
from typing import Optional
import click
from py.constants import GCLOUD_LOGGIN_OPT
from py.util.formatting import ws_info, ws_success, ws_tip, Color
from py.util.util import run_operation, cli_metadata, get_command_return_code


@click.command(
    name="gcloudLogin",
    short_help="Logs into gcloud — [supports skip mode]",
    help="Logs into gcloud and sets the project — [supports skip mode]",
    epilog="""
             usage: set_env Login [OPTIONS] [project]\n
                args:\n
                    project: Optional[str] - project name\n
                    type-login: str - login type\n
                        allowed values:\n
                            'A' - Application Default\n
                            'U' - User Account\n
                            'B' - Both\n
             """,
)
@click.argument("type-login", type=click.Choice(list(GCLOUD_LOGGIN_OPT.keys()), False), required=True)
@click.argument("project", type=click.STRING, required=False, default=None)
@cli_metadata(flags={"skip"})
def gcloud_login_env(project: Optional[str], type_login: str) -> None:
    """
    Logs into the gcloud account.

    Returns:
        None
    """
    valid_filters: set[str] = set(GCLOUD_LOGGIN_OPT.keys())
    if type_login not in valid_filters:
        raise ValueError(f"Invalid loggin type: {type_login}; logging type value must be one of:\n {' | '.join(valid_filters)}")
    gcloud_login(type_login, project)


@click.command(
    name="gcloudLogout",
    short_help="Logs out of gcloud — [supports skip mode]",
    help="Logs out of gcloud — [supports skip mode]",
    epilog="usage: set_env Logout",
)
@cli_metadata(flags={"skip"})
def gcloud_logout() -> None:
    """
    Logs out of gcloud
    """
    exit_code:int =os.system("gcloud auth revoke")
    if exit_code == 0:
        ws_success("gcloud account is now logged out.")
    exit_code = os.system("gcloud auth application-default revoke")
    if exit_code == 0:
        ws_success("gcloud application-default credentials are now revoked.")


def gcloud_login(type_login: str, project: Optional[str]) -> None:
    """
    Logs into the gcloud account and sets the project.

    Args:
        type_login: str
        project: str

    Returns:
        None
    """
    if type_login.lower() != "u":
        user_login()
    if type_login.lower() != "a":
        app_login()
    if project:
        project_set(project)


def user_login() -> None:
    """
    gcloud user login

    Returns:
        None
    """
    exit_status: int = get_command_return_code("gcloud auth application-default print-access-token")
    if exit_status == 0:
        ws_info("gcloud application-default credentials were already set.")
    else:
        exit_status = os.system("gcloud auth application-default login")
        if exit_status != 0:
            raise RuntimeError("There was an error running the gcloud auth application-default login command.")
        ws_success("gcloud application-default credentials are now set.")


def app_login() -> None:
    """
    gcloud app login

    Returns:
        None
    """
    exit_status = get_command_return_code("gcloud auth print-access-token")
    if exit_status == 0:
        ws_info("gcloud account was already set.")
    else:
        exit_status = os.system("gcloud auth login")
        if exit_status != 0:
            raise RuntimeError("There was an error running the gcloud auth login command.")
        ws_success("gcloud account is now set.")


def project_set(project: str) -> None:
    """
    Sets the project in the gcloud configuration.

    Args:
        project: str
    """
    current_project: str = run_operation("gcloud config get-value project", "Getting current project").stdout.strip()
    if project.strip() != current_project:
        dict_color: dict[Color, str] = {Color.RED: "current_project: ", Color.GREEN: current_project}
        ws_tip(dict_color)
        exit_status = os.system(f"gcloud config set project {project}")
        if exit_status != 0:
            raise RuntimeError(f"There was an error running the gcloud config set project {project} command.")
        new_project: str = run_operation("gcloud config get-value project", "Getting new project").stdout.strip()
        if new_project != project:
            raise RuntimeError("gcloud: The project was not set to the specified project.")
        ws_success(f"Project is now set to {project}")
    else:
        ws_info("Project was already set to the specified project.")
