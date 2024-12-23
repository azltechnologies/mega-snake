"""
This module contains utility functions for common operations.
"""

import re
import subprocess
import time
from typing import Callable
import click
from colorama import init, Fore, Back
from py.util.formatting import ws_advice, ws_warning

# Initialize colopiprama
init(autoreset=True)


def run_operation(cwd: str, description: str) -> subprocess.CompletedProcess[str]:
    """
    Runs the given command and retries on failure up to 3 times.

    Args:
        cwd: str
        description: str

    Returns:
        subprocess.CompletedProcess[str]
    """
    num_retries = 3
    ws_advice(f"Running operation: {description}")
    for attempt in range(1, num_retries + 1):
        try:
            ws_advice(f"Running: {cwd}")
            result = subprocess.run(cwd, shell=True, check=True, capture_output=True, text=True)
            ws_advice(f"{description} successfully on attempt {attempt}!")
            ws_advice(f"stdout: {result.stdout}")
            break  # Exit the loop on successful push
        except subprocess.CalledProcessError as error:
            ws_warning(f"{description} failed on attempt {attempt}. Error: {error.stdout}")
            ws_warning(f"Error details: {error.stderr}")
            if attempt == num_retries:
                raise subprocess.SubprocessError(f"{description} failed after {num_retries} attempts. Error: {error.stderr}") from error
            ws_warning(f"Retrying {description} in 2 seconds...")
            time.sleep(2)  # Wait 2 seconds before retrying
    return result


def get_main_branch() -> str:
    """
    Gets the main branch of the repository.

    Returns:
        str
    """
    remotes: list[str] = run_operation("git remote", "Getting remotes").stdout.strip().split("\n")
    if not remotes:
        raise ValueError("No remotes found in the current repository")
    if len(remotes) > 1:
        raise NotImplementedError("Multiple remotes found in the current repository; Operations with multiple remotes are not supported")
    result = run_operation(f"git remote show {remotes[0]}", "Getting main branch").stdout.strip()
    if not result:
        raise LookupError(f"No main branch found in the current repository for remote {remotes[0]}")
    pattern = r"^(\s*HEAD branch:\s*)(\S+)"
    match = re.search(pattern, result, re.MULTILINE)
    if match:
        return match.group(2)
    raise LookupError("No main branch found in the current repository")


def get_current_commit() -> str:
    """
    Gets the current branch of the repository.

    Returns:
        str
    """
    result = run_operation("git rev-parse HEAD", "Getting current branch").stdout.strip()
    return result


def get_validated_input(p_prompt: str, valid_values: list[str]) -> str:
    """
    Get user input and validate against allowed values

    Args:
        prompt: str
        valid_values: set[str]
    """
    warn: str = f"Invalid input. Please enter one of:\n {' | '.join(valid_values)}"
    tries: int = 0
    prompt = p_prompt
    while True:
        user_input = input(f"\n{prompt}\n").lower()
        # convert to lowercase all the values in valid_values
        valid_values = [value.lower() for value in valid_values]
        if user_input in valid_values:
            return user_input
        prompt = f"{Back.BLACK}{Fore.YELLOW}{p_prompt}\ttry again\t—\t{3-tries} attempts left"
        ws_warning(warn)
        tries += 1
        if tries > 3:
            raise KeyError(f"Too many invalid inputs for '{prompt}'. Exiting.")


def cli_metadata(**metadata) -> Callable:
    """
    Decorator to add custom metadata to a command
    """

    def decorator(f: Callable) -> Callable:
        if not hasattr(f, "flags"):
            setattr(f, "flags", {})
        getattr(f, "flags").update(metadata)
        return f

    return decorator


def wrapper_decorator(sub_wrapper: Callable) -> Callable:
    """Decorator to wrap a command with additional logic"""

    def decorator(command) -> click.Command:
        """
        Decorator that can handle both Click Commands and regular functions
        """

        @click.pass_context
        def wrapper(ctx, *args, **kwargs) -> None:
            sub_wrapper(ctx, *args, **kwargs)
            return ctx.invoke(command, *args, **kwargs)

        def update_flags(source) -> None:
            """Update flags from the source object to the wrapper"""
            if source_flags := getattr(source, "flags", {}):
                if not hasattr(wrapper, "flags"):
                    setattr(wrapper, "flags", {})
                getattr(wrapper, "flags").update(source_flags)

        update_flags(sub_wrapper)
        update_flags(command.callback)

        return click.Command(
            name=command.name,
            callback=wrapper,
            params=command.params,
            help=command.help,
            short_help=command.short_help,
            epilog=command.epilog,
        )
    return decorator
