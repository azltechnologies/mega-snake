"""
This module contains utility functions for common operations.
"""

import json
import re
import subprocess
import time
from typing import Any, Callable, Optional
import inspect
import click
from colorama import init, Fore, Back, Style
from jsoncomment import JsonComment
from codename_snake.util.formatting import ws_advice, ws_warning

# Initialize colopiprama
init(autoreset=True)


def load_json_with_comments(file_path: str) -> dict:
    """Load a JSON file with comments.

    Args:
        file_path (str): Path to the JSON file

    Returns:
        dict: JSON data
    """
    with open(file_path, "r", encoding="utf-8") as file:
        json_str = file.read()
        if not json_str:
            return {}
        parser = JsonComment(json)
        return parser.loads(json_str)


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


def get_command_return_code(command: str) -> int:
    """
    Gets the return code of the given command.
    """
    result = subprocess.run(command, shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode


def get_input_or_default(prompt: str, default: Any) -> str:
    """
    Get user input or return default value

    Args:
        prompt: str
        default: str
    """
    user_input = input(f"{prompt} (default: {default})\n")
    if user_input.strip() == "":
        return default
    try:
        return type(default)(user_input)
    except (ValueError, TypeError):
        ws_warning(f"Invalid input. Value must be of type {type(default).__name__}. Using default value: {default}")
        return default


def get_validated_input(p_prompt: str, valid_values: list[str]) -> str:
    """
    Get user input and validate against allowed values

    Args:
        prompt: str
        valid_values: set[str]
    """
    instructions: str = f"Please enter one of:\n {' | '.join(valid_values)}"
    warn: str = f"Invalid input. {instructions}"
    tries: int = 0
    prompt = p_prompt
    while True:
        user_input = input(f"\n{prompt}\n").lower() if tries > 0 else input(f"\n{prompt}\n{instructions}\n").lower()
        # convert to lowercase all the values in valid_values
        valid_values = [value.lower() for value in valid_values]
        if user_input in valid_values:
            return user_input
        prompt = f"{Back.BLACK}{Fore.YELLOW}{p_prompt}\ttry again\t—\t{Fore.RED}{3 - tries} attempts left\n{instructions}\n{Style.RESET_ALL}"
        ws_warning(warn)
        tries += 1
        if tries > 3:
            raise KeyError(f"Too many invalid inputs for '{p_prompt} —— {instructions}'. Exiting.")


def get_remote() -> Optional[str]:
    """
    Gets the remote of the repository.

    Returns:
        str
    """
    result: str = run_operation("git remote", "Getting remotes").stdout.strip()
    if not result:
        return None
    remotes: list[str] = result.split("\n")
    if len(remotes) == 1:
        return remotes[0]
    options: list[str] = [str(i) for i in range(0, len(remotes))]
    prompt: str = "Multiple remotes found in the current repository; Please select one of the following:\n"
    for index, remote in enumerate(remotes):
        prompt += f"\t{index}: {remote}\n"
    remote_index = int(get_validated_input(prompt, options))
    return remotes[remote_index]


def get_remote_url() -> Optional[str]:
    """
    Gets the remote URL of the repository.
    """
    remote = get_remote()
    if not remote:
        return None
    return re.sub(r"\.git$", "", run_operation(f"git remote get-url {remote}", "Getting remote URL").stdout.strip())


def get_main_branch() -> str:
    """
    Gets the main branch of the repository.

    Returns:
        str
    """
    remote: Optional[str] = get_remote()
    if not remote:
        return run_operation("git symbolic-ref --short HEAD", "Getting current local branch").stdout.strip()
    result = run_operation(f"git remote show {remote}", "Getting main branch").stdout.strip()
    if not result:
        raise LookupError(f"No main branch found in the current repository for remote {remote}")
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

        command_signature = inspect.signature(click.Command.__init__).parameters

        comm = click.Command(**{k: getattr(command, k) for k, _p in command_signature.items() if k != "self"})
        comm.callback = wrapper  # Override the callback with our wrapper
        if aliases := getattr(command, "aliases", []):
            setattr(comm, "aliases", aliases)
        return comm

    return decorator
