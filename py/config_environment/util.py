""" This module contains utility functions for the configuration environment. """

from py.util.props import AppProperties


def get_local_file() -> str:
    """
    Returns the local configuration file path.

    Returns:
        str: The local configuration file path.
    """
    props_inst: AppProperties = AppProperties.get_instance()
    shell = props_inst.retrieve_property("shell")
    local_file: str = props_inst.retrieve_property("local_config_file")
    match shell:
        case "bash" | "zsh":
            local_file = f"{local_file}.sh"
        case "powershell":
            local_file = f"{local_file}.ps1"
        case _:
            raise NotImplementedError(f"Shell type not supported: {shell}")
    return local_file
