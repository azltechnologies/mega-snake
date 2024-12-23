""" This module contains the echo function that prints messages to the console and logs them into the workspace configuration log file. """

from typing import Optional, Callable
import click
from py.constants import MSG_OPT


@click.command(
    name="msg",
    short_help="Prints message to the console and logs it.",
    help="Prints a message to the console in a custom format and logs it into the workspace configuration log file.",
    epilog="""
    usage: set_env msg <message> [OPTIONS]   <type>\n
    OPTIONS:\n
        epilog: an optional ending message as a second argument\n
        type:
            usage: [-t | --type] <type>\n
            allowed values:\n
                S | I | W | E | A | T
                    S - Success
                    I - Information -- default
                    W - Warning
                    E - Error
                    A - Advice -- use for Debugging
                    T - Tip
    """,
)
@click.argument("message", type=click.STRING)
@click.argument("epilog", type=click.STRING, required=False, default=None)
@click.option(
    "--type-msg",
    "-t",
    type=click.Choice(list(MSG_OPT.keys()), False),
    help="""The type of message to be printed:\n
        'S' - Success\n
        'I' - Information -- default\n
        'W' - Warning\n
        'E' - Error\n
        'A' - Advice -- use for Debugging\n
        'T' - Tip\n
     """,
    default="I",
)
def echo(message: str, epilog: Optional[str], type_msg: str) -> None:  # previously echo
    """
    Prints a message to the console and logs it into the workspace configuration log file.

    Args:
        message (str): The message to be printed.
        epilog (Optional[str]): An optional ending message as a second argument.
        type (str): The type of message to be printed.

    Returns:
        None
    """
    fun_dict: dict[str, Callable] = MSG_OPT
    valid_filters: set[str] = set(fun_dict.keys())
    if type_msg not in valid_filters:
        raise ValueError(f"Invalid message type: {type_msg}; message type value must be one of:\n {' | '.join(valid_filters)}")
    msg: str = f"{message}\n{epilog}" if epilog else message
    if type_msg == "A":
        fun_dict[type_msg](msg, True)
    if type_msg == "T":
        fun_dict[type_msg](message, epilog)
    else:
        fun_dict[type_msg](msg)
