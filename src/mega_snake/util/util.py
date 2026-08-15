"""
This module contains utility functions for common operations.
"""

import json
import os
import re
from typing import Optional, Tuple, Union
import subprocess
import platform
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
import inspect
import click
from colorama import init, Fore, Back, Style
from jsoncomment import JsonComment
from mega_snake.util.formatting import (
    InternalStateError,
    UserDeclinedError,
    ws_advice,
    ws_info,
    ws_success,
    ws_warning,
)
from mega_snake.util.cli_group import ATTR_ALIAS, ATTR_DOCS, ATTR_GROUP, ATTR_METADATA
from mega_snake.util.props import get_property

OS = platform.system()

GIT_EXCLUDE_FILE = os.path.join(".git", "info", "exclude")

REMOTE_PREFIX = "refs/remotes"
LOCAL_PREFIX = "refs/heads"

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


def write_json_atomically(path: Path, payload: Any, sort_keys: bool = False) -> None:
    """Serialize a JSON payload and put it in place in a single, uninterruptible step.

    The temporary file is created in the destination directory so ``os.replace`` is a rename within
    one filesystem, which is atomic. Anything that fails before the rename leaves the previous file
    byte for byte as it was and removes the temporary file rather than leaking it into the
    directory. ``newline="\\n"`` keeps the bytes identical on Windows.

    Parameters:
        path: The destination file.
        payload: Any JSON-serializable value.
        sort_keys: Whether to sort object keys. Leave it False for payloads whose key order is part
            of a published contract.

    Raises:
        OSError: If the file cannot be created or replaced.
        TypeError: If the payload is not JSON-serializable.

    Returns:
        None
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(  # pylint: disable=consider-using-with
        mode="w",
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
        newline="\n",
    )
    temp_path: Path = Path(handle.name)
    replaced: bool = False
    try:
        with handle:
            json.dump(payload, handle, indent=2, sort_keys=sort_keys, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_path, path)
        replaced = True
    finally:
        if not replaced:
            temp_path.unlink(missing_ok=True)


def _as_text(stream: Optional[Union[str, bytes]]) -> str:
    """Render a captured subprocess stream as text, whatever the exception carried.

    ``CalledProcessError`` carries the decoded strings ``run_operation`` asked for with ``text=True``,
    but ``TimeoutExpired`` carries whatever had been read when the timer fired, which is ``bytes`` or
    ``None``. Both reach the same warning, so the difference is absorbed here instead of at each
    call site.

    Parameters:
        stream: The captured stream, already decoded, still raw, or absent.

    Raises:
        None

    Returns:
        str: The stream as text, or an empty string when there was nothing captured.
    """
    if stream is None:
        return ""
    return stream if isinstance(stream, str) else stream.decode(errors="replace")


def run_operation(
    cwd: str, description: str, check: bool = True, timeout: Optional[float] = None
) -> subprocess.CompletedProcess[str]:
    """Runs the given command and retries on failure up to 3 times.

    Parameters:
        cwd: The shell command to execute.
        description: Human-readable description of the operation, used in log messages.
        check: Whether a non-zero exit code should raise subprocess.CalledProcessError.
        timeout: Maximum number of seconds to wait for the command to finish, or None to wait
            indefinitely.

    A timeout is retried like any other failure. It used to propagate on the first attempt instead,
    because ``subprocess.TimeoutExpired`` is a ``SubprocessError`` but **not** a
    ``CalledProcessError``, so the ``except`` clause never saw it — which meant a single slow network
    call (a cold fetch, a VPN, a credential prompt) aborted the whole command with a raw traceback,
    and the retries that exist precisely for transient failures never ran. The two are caught
    together and reported the same way; only the wording differs, since a timeout has no exit code
    to show.

    Raises:
        subprocess.SubprocessError: If the command still fails — or still times out — after 3
            attempts.

    Returns:
        subprocess.CompletedProcess[str]: The result of the last (successful) attempt.
    """
    num_retries = 3
    ws_advice(
        f"Running operation: {description}; Command: {cwd}; Timeout: {timeout if timeout is not None else 'None'} secs"
    )
    for attempt in range(1, num_retries + 1):
        shell: str = get_property("shell")
        if OS == "Windows" and shell not in ["powershell", "pwsh"]:
            shell = "powershell"
        elif OS != "Darwin" and shell not in ["bash", "zsh"]:
            shell = "zsh"
        elif OS == "Linux" and shell not in ["bash", "zsh"]:
            shell = "bash"
        flag: str = "-Command" if shell in ["powershell", "pwsh"] else "-c"
        try:
            ws_advice(f"Running: {cwd}")
            result = subprocess.run(
                [shell, flag, cwd],
                shell=False,
                check=check,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
            )
            ws_advice(f"{description} successfully on attempt {attempt}!")
            ws_advice(f"stdout: {result.stdout}")
            break  # Exit the loop on successful push
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            timed_out: bool = isinstance(error, subprocess.TimeoutExpired)
            detail: str = (
                f"timed out after {timeout} seconds" if timed_out else f"failed. Error: {_as_text(error.stdout)}"
            )
            ws_warning(f"{description} {detail} on attempt {attempt}.")
            ws_warning(f"Error details: {_as_text(error.stderr)}")
            if attempt == num_retries:
                raise subprocess.SubprocessError(
                    (
                        f"{description} {'timed out' if timed_out else 'failed'} after "
                        f"{num_retries} attempts.\n"
                        f"Error: {_as_text(error.stderr)}\n"
                        f"Commnad: {cwd}, Shell: {shell}"
                    )
                ) from error
            ws_warning(f"Retrying {description} in 2 seconds...")
            time.sleep(2)  # Wait 2 seconds before retrying
    return result


def get_command_return_code(command: str, description: str, timeout: Optional[float] = None) -> int:
    """
    Gets the return code of the given command.
    """
    ws_advice(
        f"Getting return code for command: {command}; Description: {description};"
        f" Timeout: {timeout if timeout is not None else 'None'} secs"
    )
    result = subprocess.run(
        command, shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout
    )
    return result.returncode


def get_typed_validated_input(p_prompt: str, warn: str, valid_values: list[str], fail_msg: Optional[str] = None) -> str:
    """Ask the user for one of the given values, comparing the answer verbatim.

    The answer is matched **case-sensitively**, unlike ``get_validated_input``. The two exist for
    different kinds of value: that one offers single-letter choices the tool itself defines
    (``y``/``n``, ``M``/``U``/``A``), where accepting either case is a convenience; this one offers
    identifiers that come from the system and whose case is meaningful — git branch names, which
    git itself treats as distinct. Lowercasing the answer here made every branch carrying an
    uppercase letter impossible to select, while the warning text told the user the opposite.

    Parameters:
        p_prompt: The question shown to the user.
        warn: Message shown after a rejected answer, explaining what is expected.
        valid_values: The accepted answers, matched exactly as given.
        fail_msg: Extra guidance appended to the error once the attempts run out.

    Raises:
        KeyError: If the user fails to give an accepted value within the allowed attempts.

    Returns:
        str: The accepted value, exactly as the user typed it.
    """
    tries: int = 0
    prompt = p_prompt
    while True:
        user_input = input(f"\n{prompt}\n")
        if user_input in valid_values:
            return user_input
        prompt = (
            f"{Back.BLACK}{Fore.YELLOW}{p_prompt}\ttry again\t—\t{Fore.RED}{3 - tries} attempts left\n{Style.RESET_ALL}"
        )
        ws_warning(warn)
        tries += 1
        if tries > 3:
            raise KeyError(
                f"Too many invalid inputs for '{p_prompt}'. Exiting. {fail_msg if fail_msg is not None else ''}"
            )


def get_input_or_default(p_prompt: str, default: Any) -> str:
    """
    Get user input or return default value

    Args:
        p_prompt: str
        default: str
    """
    user_input = input(f"{p_prompt} (default: {default})\n")
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
        prompt = (
            f"{Back.BLACK}{Fore.YELLOW}{p_prompt}\ttry again\t—\t{Fore.RED}{3 - tries} "
            f"attempts left\n{instructions}\n{Style.RESET_ALL}"
        )
        ws_warning(warn)
        tries += 1
        if tries > 3:
            raise KeyError(f"Too many invalid inputs for '{p_prompt} —— {instructions}'. Exiting.")


def exclude_from_git(entries: list[Tuple[str, str]]) -> None:
    """Add the given entries to the repository's local git exclude file when missing.

    Entries already present are left untouched, so the operation is idempotent. When the current
    directory is not a git repository the exclusions are skipped with a warning instead of failing,
    and a missing exclude file is created rather than crashing with a FileNotFoundError.

    Parameters:
        entries: Pairs of (entry, description); the entry is the literal line written to the git
            exclude file (e.g. ``".vscode/"``) and the description is used in the log messages.

    Raises:
        None

    Returns:
        None
    """
    if not os.path.exists(".git"):
        ws_warning(
            f"Not inside a git repository; skipping git exclusions for: "
            f"{', '.join(description for _, description in entries)}"
        )
        return
    exclude: str = ""
    if os.path.exists(GIT_EXCLUDE_FILE):
        with open(GIT_EXCLUDE_FILE, "r", encoding="utf-8") as file:
            exclude = file.read()
    else:
        os.makedirs(os.path.dirname(GIT_EXCLUDE_FILE), exist_ok=True)
    if exclude and not exclude.endswith("\n"):
        exclude += "\n"
    for entry, description in entries:
        regex = re.compile(rf"^\s*{re.escape(entry.rstrip('/'))}/?\s*$", re.MULTILINE)
        if regex.search(exclude):
            ws_advice(f"{description} already excluded in {GIT_EXCLUDE_FILE}")
            continue
        exclude += f"{entry}\n"
        ws_success(f"Excluded {description} in {GIT_EXCLUDE_FILE}")
    with open(GIT_EXCLUDE_FILE, "w", encoding="utf-8") as file:
        file.write(exclude)


def ensure_working_path(decline_message: Optional[str] = None) -> str:
    """Get the working path, offering to create it (and exclude it from git) when it is missing.

    This is the single implementation shared by every command that writes its output to the working
    path (``workspace_temp`` by default), so they all behave the same way when the folder is not
    there yet instead of crashing with a raw FileNotFoundError.

    Parameters:
        decline_message: Error message used when the user declines to create the folder. Defaults to
            a generic message mentioning the working path.

    Raises:
        InternalStateError: If the working path property is empty or points outside the current
            directory, which would mean the properties were built incorrectly.
        UserDeclinedError: If the working path is missing and the user declines to create it.

    Returns:
        str: The absolute path to the existing working path folder.
    """
    working_path: str = get_property("working_path")
    # Both checks restate what initialization already guaranteed: _check_property refuses an empty
    # value, and __working_path_validator resolves it against the cwd. Failing here means the
    # properties were built wrong, so the user has nothing to act on.
    if not working_path:
        raise InternalStateError("Working path is required but was not found in the properties. This is a bug.")
    if not Path(working_path).resolve().is_relative_to(Path.cwd().resolve()):
        raise InternalStateError("Working path is not in the current directory. This is a bug.")
    if os.path.exists(working_path):
        ws_info(f"Working path found: {working_path}")
        return working_path
    ws_warning("Working path not found in current directory")
    if get_validated_input("Would you like to create a new default working path?", ["y", "n"]) == "n":
        # Declining a prompt is a decision, not a mistake: it gets its own status so a caller can
        # stop retrying instead of reading it as a bad invocation.
        raise UserDeclinedError(
            decline_message or f"Cannot continue without the '{working_path}' folder. Please create it and try again."
        )
    os.makedirs(working_path, exist_ok=True)
    exclude_from_git([(f"{os.path.basename(working_path)}/", f"{os.path.basename(working_path)} folder")])
    ws_success(f"Working path created at {working_path}")
    return working_path


def cli_metadata(**metadata) -> Callable:
    """
    Decorator to add custom metadata to a command
    """

    def decorator(f: Callable) -> Callable:
        if not hasattr(f, ATTR_METADATA):
            setattr(f, ATTR_METADATA, {})
        getattr(f, ATTR_METADATA).update(metadata)
        return f

    return decorator


def _rebuild_command(command: click.Command) -> click.Command:
    """Rebuild a command as the same class, so wrapping it cannot change what it is.

    Wrapping copies the command through ``click.Command.__init__``'s signature, which is the reason
    §2.3 of the contributor guide insists custom attributes be re-applied by hand afterwards. A
    ``click.Group`` carries one more thing that signature does not mention: its ``commands``. Copying
    a group through the plain ``Command`` constructor would silently return a leaf command with no
    subcommands, so ``mgsnake config get`` would stop resolving the moment the group is registered
    through a module wrapper like every other command.

    Parameters:
        command: The command (or group) to copy.

    Raises:
        None

    Returns:
        click.Command: A fresh instance of the same class carrying the same constructor arguments.
    """
    attribute_names: set[str] = {
        name for name in inspect.signature(click.Command.__init__).parameters if name != "self"
    }
    if isinstance(command, click.Group):
        attribute_names.add("commands")
    return type(command)(**{name: getattr(command, name) for name in attribute_names if hasattr(command, name)})


def wrapper_decorator(sub_wrapper: Callable) -> Callable:
    """Decorator to wrap a command with additional logic"""

    preserved_attrs: Tuple[str, ...] = (ATTR_ALIAS, ATTR_DOCS, ATTR_GROUP)

    def apply_command_metadata(target: click.Command, source: Any) -> None:
        """Copy custom documentation metadata from a wrapper or callback onto a command.

        Parameters:
            target: The command that should receive the metadata.
            source: The callback or wrapper that may carry metadata.

        Raises:
            None

        Returns:
            None
        """
        metadata: dict[str, Any] = getattr(source, ATTR_METADATA, {})
        for attr_name in (ATTR_DOCS, ATTR_GROUP):
            if value := metadata.get(attr_name):
                setattr(target, attr_name, value)

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
            if source_flags := getattr(source, ATTR_METADATA, {}):
                if not hasattr(wrapper, ATTR_METADATA):
                    setattr(wrapper, ATTR_METADATA, {})
                getattr(wrapper, ATTR_METADATA).update(source_flags)

        update_flags(sub_wrapper)
        update_flags(command.callback)

        comm = _rebuild_command(command)
        comm.callback = wrapper  # Override the callback with our wrapper
        for attr_name in preserved_attrs:
            if value := getattr(command, attr_name, None):
                setattr(comm, attr_name, value)
        apply_command_metadata(comm, sub_wrapper)
        apply_command_metadata(comm, command.callback)
        return comm

    return decorator
