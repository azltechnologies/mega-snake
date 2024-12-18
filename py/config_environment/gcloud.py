"""logins to gcloud and sets the project"""

import os
from typing import Optional
from py.util.formatting import ws_info, ws_success, ws_tip
from py.util.util import run_operation


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
    exit_status: int = os.system("gcloud auth application-default print-access-token")
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
    exit_status = os.system("gcloud auth print-access-token")
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
        ws_tip("Current project:", current_project)
        exit_status = os.system(f"gcloud config set project {project}")
        if exit_status != 0:
            raise RuntimeError(f"There was an error running the gcloud config set project {project} command.")
        new_project: str = run_operation("gcloud config get-value project", "Getting new project").stdout.strip()
        if new_project != project:
            raise RuntimeError("gcloud: The project was not set to the specified project.")
        ws_success(f"Project is now set to {project}")
    else:
        ws_info("Project was already set to the specified project.")
