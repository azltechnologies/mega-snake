""" Contains multiple functions to configure the environment for development with vscode. """

from typing import Optional
from py.util.formatting import WorkspaceError


def initial_load():
    """
    Initializes the configuration system by creating a local config file if it doesn't exist,
    then loads its contents into the environment.

    Returns:
        None
    """
    pass


def set_gradle_version(version: str): # previously gradleSet
    """
    Sets the gradle version to be used in the project.

    Args:
        version (str): The version of gradle to be used.

    Returns:
        None
    """
    pass


def set_java_version(version: str): # previously javaSet
    """
    Sets the java version to be used in the project.

    Args:
        version (str): The version of java to be used.

    Returns:
        None
    """
    pass


def gcloud_login(type: str): # previously gcloudSet
    """
    Logs into the gcloud account.

    Returns:
        None
    """
    valid_filters: set[str] = {"B", "U", "A"}
    if type not in valid_filters:
        e = ValueError(f"Invalid loggin type: {type}")
        WorkspaceError.ws_error(e, f"logging type value must be one of:\n {' | '.join(valid_filters)}")
        raise e
    pass

def setting_workspace(): # previously untrackGradleProps
    """
    Sets the workspace for the project.

    Returns:
        None
    """
    pass