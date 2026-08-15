"""
This module contains utility functions for common operations.
"""

import json
import os
import re
import subprocess
import platform
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional
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

NO_REMOTE_MESSAGE = "No remote repository found. Please add a remote repository to the current repository."
GIT_EXCLUDE_FILE = os.path.join(".git", "info", "exclude")

# Caches the resolved remote for the lifetime of the process. Resolving it is not free: it spawns a
# `git remote` subprocess and, when the repository has more than one remote, it prompts the user to
# pick one. Several call sites need the remote during a single command run (pre-flight wrappers, the
# commands themselves, get_main_branch), so without this cache the user would be prompted repeatedly
# for the very same answer.
_remote_cache: dict[str, Optional[str]] = {}

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


def run_operation(cwd: str, description: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """
    Runs the given command and retries on failure up to 3 times.

    Args:
        cwd: str
        description: str

    Returns:
        subprocess.CompletedProcess[str]
    """
    num_retries = 3
    ws_advice(f"Running operation: {description} ñnCommand: {cwd}")
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
                [shell, flag, cwd], shell=False, check=check, capture_output=True, text=True, errors="replace"
            )
            ws_advice(f"{description} successfully on attempt {attempt}!")
            ws_advice(f"stdout: {result.stdout}")
            break  # Exit the loop on successful push
        except subprocess.CalledProcessError as error:
            ws_warning(f"{description} failed on attempt {attempt}. Error: {error.stdout}")
            ws_warning(f"Error details: {error.stderr}")
            if attempt == num_retries:
                raise subprocess.SubprocessError(
                    (
                        f"{description} failed after {num_retries} attempts.\n"
                        f"Error: {error.stderr}\n"
                        f"Commnad: {cwd}, Shell: {shell}"
                    )
                ) from error
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
        prompt = (
            f"{Back.BLACK}{Fore.YELLOW}{p_prompt}\ttry again\t—\t{Fore.RED}{3 - tries} "
            f"attempts left\n{instructions}\n{Style.RESET_ALL}"
        )
        ws_warning(warn)
        tries += 1
        if tries > 3:
            raise KeyError(f"Too many invalid inputs for '{p_prompt} —— {instructions}'. Exiting.")


def reset_remote_cache() -> None:
    """Clear the cached remote so the next call to get_remote resolves it again.

    Parameters:
        None

    Raises:
        None

    Returns:
        None
    """
    _remote_cache.clear()


def get_remote() -> Optional[str]:
    """Get the remote of the repository, resolving it only once per process.

    The result (including ``None``) is cached, so repeated calls within the same command run reuse
    the first answer instead of spawning another ``git remote`` or prompting the user again when the
    repository has multiple remotes. If ``git remote`` fails altogether (e.g. the current directory
    is not a git repository), the failure is reported as a warning and treated as "no remote", so
    callers get the same friendly handling as a repository without remotes.

    Parameters:
        None

    Raises:
        None

    Returns:
        Optional[str]: The remote name, or None when there is no remote available.
    """
    if "remote" in _remote_cache:
        return _remote_cache["remote"]
    try:
        result: str = run_operation("git remote", "Getting remotes").stdout.strip()
    except subprocess.SubprocessError as error:
        ws_warning(f"{NO_REMOTE_MESSAGE} Unable to get the remotes: {error}")
        _remote_cache["remote"] = None
        return None
    if not result:
        _remote_cache["remote"] = None
        return None
    remotes: list[str] = result.split("\n")
    if len(remotes) == 1:
        _remote_cache["remote"] = remotes[0]
        return remotes[0]
    options: list[str] = [str(i) for i in range(0, len(remotes))]
    prompt: str = "Multiple remotes found in the current repository; Please select one of the following:\n"
    for index, remote in enumerate(remotes):
        prompt += f"\t{index}: {remote}\n"
    remote_index = int(get_validated_input(prompt, options))
    _remote_cache["remote"] = remotes[remote_index]
    return remotes[remote_index]


def require_remote() -> str:
    """Get the remote of the repository, failing with a friendly error when there is none.

    This is the single entry point for commands that cannot work without a remote, so they all
    share the same message and the same (cached) resolution.

    A repository without a remote is not a misuse of the CLI — the user broke no contract — so this
    raises an environment error rather than a ClickException: the exit status then says "the
    environment is not set up", which is a different thing for a script to react to than "you called
    this wrong".

    Parameters:
        None

    Raises:
        EnvironmentError: If the repository has no remote configured.

    Returns:
        str: The remote name.
    """
    remote: Optional[str] = get_remote()
    if not remote:
        raise EnvironmentError(NO_REMOTE_MESSAGE)
    return remote


def get_remote_url() -> Optional[str]:
    """
    Gets the remote URL of the repository.
    """
    remote = get_remote()
    if not remote:
        return None
    return re.sub(r"\.git$", "", run_operation(f"git remote get-url {remote}", "Getting remote URL").stdout.strip())


def get_main_branch(remote: Optional[str] = None) -> str:
    """
    Gets the main branch of the repository.

    Returns:
        str
    """
    if remote is None:
        remote = get_remote()
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
    Gets the current commit of the repository.

    Returns:
        str
    """
    result = run_operation("git rev-parse HEAD", "Getting current branch").stdout.strip()
    return result


def exclude_from_git(entries: list[tuple[str, str]]) -> None:
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

    preserved_attrs: tuple[str, ...] = (ATTR_ALIAS, ATTR_DOCS, ATTR_GROUP)

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
