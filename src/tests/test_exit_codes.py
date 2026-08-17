"""End-to-end tests for the exit codes the CLI reports to the shell.

Every assertion here compares an **exact** status, and most are paired with a negative assertion
against 1. That pairing is the point of this file: the whole error-handling design was dead for a
long time precisely because everything silently collapsed to 1, and no test ever looked at a real
exit code — the only test covering the reload signal asserted on a hand-built context object and
never on the CLI running, so it stayed green while the signal never reached a shell.

Two levels are used deliberately:

* ``CliRunner`` for anything decided inside the click group (the reload signal, a ClickException's
  own ``exit_code``). It runs the real registry and the real result callback.
* ``subprocess`` for anything decided *outside* it — the translation in ``main()`` and the
  ``sys.excepthook`` that delivers it. Neither runs under ``CliRunner``, which catches exceptions
  and reports 1 for all of them, so an in-process test there would assert nothing at all.
"""

import importlib
import inspect
import os
import pkgutil
import subprocess
import sys
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from mega_snake import __main__ as app_main
from mega_snake.config_environment.models.tools_version import VersionSetException
from mega_snake.constants import MODULE_NAME, RELOAD_ENVIRONMENT_EXIT_CODE
from mega_snake.util import formatting
from mega_snake.util.formatting import (
    ERROR_CODES,
    INTERNAL_ERROR_CODE,
    USER_DECLINED_ERROR_CODE,
    VALIDATION_ERROR_CODE,
    UserDeclinedError,
    ValidationError,
    WorkspaceError,
    resolve_error_code,
)

# The exit code Click uses for a plain user error. Every reclassified failure has to differ from it,
# so it is named here and asserted against explicitly rather than written as a bare literal.
CLICK_EXCEPTION_EXIT_CODE = 1
# Click's own code for a malformed invocation (unknown option, missing argument).
USAGE_ERROR_EXIT_CODE = 2

# The exact table ERROR_CODES is meant to encode, written out independently of the source dict.
# A duplicate key (IOError and EnvironmentError are both OSError, which is how 105 became
# unreachable) silently overwrites an entry without changing the dict's length, so comparing
# lengths would not catch it — comparing every (type, code) pair does.
EXPECTED_ERROR_CODES: tuple[tuple[type[BaseException], int], ...] = (
    (RuntimeError, 101),
    (FileNotFoundError, 102),
    (ValueError, 103),
    (NotImplementedError, 104),
    (NotADirectoryError, 106),
    (LookupError, 107),
    (IndexError, 108),
    (KeyError, 109),
    (PermissionError, 110),
    (subprocess.SubprocessError, 111),
    (EnvironmentError, 112),
    (VersionSetException, 115),
)

# Exceptions that legitimately have no ERROR_CODES entry, with the reason.
UNMAPPED_BY_DESIGN: dict[str, str] = {
    "WorkspaceError": "the carrier itself: its status is resolved from the exception it wraps",
}

# Raised inside the driver below to reach a WorkspaceError whose cause is not in ERROR_CODES.
UNMAPPED_EXCEPTION_NAME = "unmapped"

# Runs main() with the click group replaced by a raiser, which is the only way to reach the
# translation in main() and the except hook without a command that fails on purpose. It runs in its
# own process so the *process* exit status is what gets asserted.
_CRASH_DRIVER = """
import subprocess, sys
from unittest.mock import patch
from mega_snake.__main__ import main
from mega_snake.config_environment.models.tools_version import VersionSetException


class Unmapped(Exception):
    pass


CAUSES = {
    "RuntimeError": RuntimeError("boom"),
    "FileNotFoundError": FileNotFoundError("boom"),
    "ValueError": ValueError("boom"),
    "NotImplementedError": NotImplementedError("boom"),
    "NotADirectoryError": NotADirectoryError("boom"),
    "LookupError": LookupError("boom"),
    "IndexError": IndexError("boom"),
    "KeyError": KeyError("boom"),
    "PermissionError": PermissionError("boom"),
    "SubprocessError": subprocess.SubprocessError("boom"),
    "EnvironmentError": EnvironmentError("boom"),
    "VersionSetException": VersionSetException("boom"),
    "CalledProcessError": subprocess.CalledProcessError(1, "git"),
    "%(unmapped)s": Unmapped("boom"),
}

with patch("mega_snake.util.cli_group.CliGroup.main", side_effect=CAUSES[sys.argv[1]]):
    main()
""" % {"unmapped": UNMAPPED_EXCEPTION_NAME}


def _package_env(**overrides: Optional[str]) -> dict[str, str]:
    """Build a subprocess environment that can import mega_snake, with the given overrides.

    Parameters:
        overrides: Variables to set, or to remove when the value is None.

    Raises:
        None

    Returns:
        dict[str, str]: The environment for the child process.
    """
    env = dict(os.environ)
    # The package lives under src/, which is on the path of the test session but not necessarily of
    # a child started from a temporary directory.
    package_root = str(Path(importlib.import_module(MODULE_NAME).__file__).parent.parent)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_root, env.get("PYTHONPATH")]))
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _run_cli(*args: str, cwd: Optional[Path] = None, stdin: str = "", **env_overrides: Optional[str]):
    """Run the CLI in a child process and return the completed process.

    Parameters:
        args: The command line arguments passed after ``python -m mega_snake``.
        cwd: Directory to run in; defaults to the current one.
        stdin: Text fed to the process' standard input.
        env_overrides: Environment variables to set, or to remove when the value is None.

    Raises:
        None

    Returns:
        subprocess.CompletedProcess[str]: The finished child process.
    """
    return subprocess.run(
        [sys.executable, "-m", MODULE_NAME, *args],
        cwd=str(cwd) if cwd else None,
        env=_package_env(**env_overrides),
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(name="git_workspace")
def fixture_git_workspace(tmp_path: Path) -> Path:
    """Create a throwaway git repository with a commit and a working path folder.

    The commands exercised through it (``diff-tree``) need a repository and a scratch folder that
    already exists, so nothing prompts.

    Parameters:
        tmp_path: pytest's temporary directory.

    Raises:
        None

    Returns:
        Path: The repository root.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "workspace_temp").mkdir()
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    git = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com"]
    subprocess.run([*git, "init", "-q"], cwd=repo, check=True, capture_output=True)
    subprocess.run([*git, "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run([*git, "commit", "-qm", "initial"], cwd=repo, check=True, capture_output=True)
    return repo


# --------------------------------------------------------------------------------------------
# 0 — success
# --------------------------------------------------------------------------------------------


def test_a_successful_command_exits_zero() -> None:
    """A command that does its job must report success, and must not emit the reload signal."""
    result = _run_cli("man", "diff-tree", MEGA_SNAKE_SHELL="bash")

    assert result.returncode == 0, f"'man diff-tree' exited {result.returncode}\n{result.stderr}"
    assert result.returncode != RELOAD_ENVIRONMENT_EXIT_CODE, "a read-only command must not ask for a shell reload"


# --------------------------------------------------------------------------------------------
# 1 — the user invoked the command incorrectly (click.ClickException)
# --------------------------------------------------------------------------------------------


def test_an_unknown_command_name_exits_one() -> None:
    """`man <unknown>` is a genuine invocation error, so it keeps Click's status."""
    result = _run_cli("man", "definitely-not-a-command", MEGA_SNAKE_SHELL="bash")

    assert result.returncode == CLICK_EXCEPTION_EXIT_CODE, f"exited {result.returncode}\n{result.stderr}"


def test_mutually_exclusive_diff_tree_flags_exit_one(git_workspace: Path) -> None:
    """--target-hash with a scope that reads the working tree is misuse, and stays a 1."""
    result = _run_cli("dt", "-t", "HEAD", "-s", "u", cwd=git_workspace, MEGA_SNAKE_SHELL="bash")

    assert result.returncode == CLICK_EXCEPTION_EXIT_CODE, f"exited {result.returncode}\n{result.stderr}"
    assert result.returncode != VALIDATION_ERROR_CODE, "misuse must not be reported as a validation failure"


# --------------------------------------------------------------------------------------------
# 2 — programming error in command registration / malformed invocation (click.UsageError)
# --------------------------------------------------------------------------------------------


def test_an_unknown_option_exits_two() -> None:
    """Click's own usage error keeps its status: nothing in this design may shadow it."""
    result = _run_cli("--definitely-not-an-option", MEGA_SNAKE_SHELL="bash")

    assert result.returncode == USAGE_ERROR_EXIT_CODE, f"exited {result.returncode}\n{result.stderr}"
    assert result.returncode != CLICK_EXCEPTION_EXIT_CODE, "a usage error is not a plain ClickException"


# --------------------------------------------------------------------------------------------
# 29 — success + the shell must reload its local environment files
# --------------------------------------------------------------------------------------------


def test_a_command_that_rewrites_the_environment_emits_the_reload_signal() -> None:
    """`init-local-config` must leave the process with 29 so the shell wrapper re-sources the files.

    This goes through the real group: the command, its module wrapper and ``post_command``. The
    previous test for this asserted on a hand-built context object, which is why a signal that never
    reached a process could stay "covered" indefinitely.
    """
    runner = CliRunner()
    with patch.dict(os.environ, {"MEGA_SNAKE_SHELL": "bash"}), patch(
        "mega_snake.__main__.init_app_properties"
    ), patch("mega_snake.config_environment.local_config.execute"):
        result = runner.invoke(app_main.cli, ["init-local-config"])

    assert result.exit_code == RELOAD_ENVIRONMENT_EXIT_CODE, (
        f"'init-local-config' exited {result.exit_code}, expected {RELOAD_ENVIRONMENT_EXIT_CODE}"
    )
    assert result.exit_code != 0, "a plain success would leave the shell with a stale environment"


def test_a_command_that_leaves_the_environment_alone_does_not_emit_the_signal(tmp_path: Path) -> None:
    """`graphql-schema` writes no environment file, so it must exit 0 and trigger no reload."""
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "a.graphql").write_text("type Query { a: String }\n", encoding="utf-8")

    runner = CliRunner()
    with patch.dict(os.environ, {"MEGA_SNAKE_SHELL": "bash"}), patch(
        "mega_snake.__main__.init_app_properties"
    ), patch(
        "mega_snake.config_environment.graphql_schema.get_property",
        return_value=str(tmp_path / "schema.graphql"),
    ), patch("mega_snake.config_environment.graphql_schema._create_schema"):
        result = runner.invoke(app_main.cli, ["graphql-schema", str(schema_dir)])

    assert result.exit_code == 0, f"'graphql-schema' exited {result.exit_code}: {result.output}"
    assert result.exit_code != RELOAD_ENVIRONMENT_EXIT_CODE, (
        "graphql-schema touches neither local environment file, so it must not force a reload"
    )


# --------------------------------------------------------------------------------------------
# 100–115 — errors, by exception type
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cause_name", "expected_code"),
    [
        ("RuntimeError", 101),
        ("FileNotFoundError", 102),
        ("ValueError", 103),
        ("NotImplementedError", 104),
        ("NotADirectoryError", 106),
        ("LookupError", 107),
        ("IndexError", 108),
        ("KeyError", 109),
        ("PermissionError", 110),
        ("SubprocessError", 111),
        ("EnvironmentError", 112),
        ("VersionSetException", 115),
        # Not listed in ERROR_CODES: it must inherit SubprocessError's code through the MRO instead
        # of falling to the generic one.
        ("CalledProcessError", 111),
        (UNMAPPED_EXCEPTION_NAME, INTERNAL_ERROR_CODE),
    ],
)
def test_an_unhandled_exception_reaches_the_shell_as_its_registered_code(cause_name: str, expected_code: int) -> None:
    """Each exception type must leave the *process* with its own status, delivered by the hook.

    Run in a child process on purpose: the translation lives in ``main()`` and the delivery in
    ``sys.excepthook``, and neither runs under CliRunner. The assertion that the status is not 1 is
    the half that matters — 1 is what every one of these produced before, and what any future
    regression in main() would silently produce again.
    """
    result = subprocess.run(
        [sys.executable, "-c", _CRASH_DRIVER, cause_name],
        env=_package_env(MEGA_SNAKE_SHELL="bash"),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == expected_code, (
        f"{cause_name} exited {result.returncode}, expected {expected_code}\n{result.stderr}"
    )
    assert result.returncode != CLICK_EXCEPTION_EXIT_CODE, f"{cause_name} collapsed back to the generic exit code 1"


def test_a_missing_shell_variable_exits_with_the_environment_error_code() -> None:
    """`MEGA_SNAKE_SHELL` unset is an environment failure (112), not a bad invocation (1)."""
    result = _run_cli("diff-tree", MEGA_SNAKE_SHELL=None)

    assert result.returncode == 112, f"exited {result.returncode}\n{result.stderr}"
    assert result.returncode != CLICK_EXCEPTION_EXIT_CODE, "an unset environment variable is not user misuse"


def test_an_unsupported_shell_exits_with_the_value_error_code() -> None:
    """An unsupported shell is a bad value (103), which must survive as such."""
    result = _run_cli("diff-tree", MEGA_SNAKE_SHELL="fish")

    assert result.returncode == 103, f"exited {result.returncode}\n{result.stderr}"
    assert result.returncode != CLICK_EXCEPTION_EXIT_CODE, "a rejected value must not collapse to 1"


def test_an_invalid_commit_hash_exits_with_the_value_error_code(git_workspace: Path) -> None:
    """`mgsnake dt -o <typo>` raises ValueError deep in the command: it must reach the shell as 103."""
    result = _run_cli("dt", "-o", "doesnotexist", cwd=git_workspace, MEGA_SNAKE_SHELL="bash")

    assert result.returncode == 103, f"exited {result.returncode}\n{result.stderr}"
    assert result.returncode != CLICK_EXCEPTION_EXIT_CODE, "a typo'd revision must not be reported as exit 1"


# --------------------------------------------------------------------------------------------
# 113 / 114 — the two ClickException subclasses
# --------------------------------------------------------------------------------------------


def test_stale_generated_docs_exit_with_the_validation_code(tmp_path: Path) -> None:
    """`generate-docs --check` on a stale file reports 113, not the generic ClickException code."""
    stale = tmp_path / "COMMANDS.md"
    stale.write_text("stale\n", encoding="utf-8")

    result = _run_cli("generate-docs", "--check", "--output", str(stale), MEGA_SNAKE_SHELL="bash")

    assert result.returncode == VALIDATION_ERROR_CODE, f"exited {result.returncode}\n{result.stderr}"
    assert result.returncode != CLICK_EXCEPTION_EXIT_CODE, "stale content is not an invocation error"


def test_declining_to_create_the_working_path_exits_with_the_declined_code(tmp_path: Path) -> None:
    """Answering "n" to the working-path prompt reports 114, not the generic ClickException code."""
    repo = tmp_path / "no-workspace"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)

    result = _run_cli("dt", cwd=repo, stdin="n\n", MEGA_SNAKE_SHELL="bash")

    assert result.returncode == USER_DECLINED_ERROR_CODE, f"exited {result.returncode}\n{result.stderr}"
    assert result.returncode != CLICK_EXCEPTION_EXIT_CODE, "declining a prompt is not an invocation error"


@pytest.mark.parametrize(
    ("exception_type", "expected_code"),
    [(ValidationError, VALIDATION_ERROR_CODE), (UserDeclinedError, USER_DECLINED_ERROR_CODE)],
)
def test_the_click_exception_subclasses_keep_clean_output_and_their_own_code(
    exception_type: type[click.ClickException], expected_code: int
) -> None:
    """Both must remain ClickExceptions — that is what keeps the traceback out of the user's face."""
    error = exception_type("something")

    assert isinstance(error, click.ClickException), f"{exception_type.__name__} must subclass ClickException"
    assert error.exit_code == expected_code, f"{exception_type.__name__} carries {error.exit_code}"
    assert error.exit_code != CLICK_EXCEPTION_EXIT_CODE, (
        f"{exception_type.__name__} must not reuse the generic ClickException code"
    )


# --------------------------------------------------------------------------------------------
# The ERROR_CODES table itself
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("exception_type", "expected_code"), EXPECTED_ERROR_CODES)
def test_error_codes_maps_each_type_to_its_documented_code(
    exception_type: type[BaseException], expected_code: int
) -> None:
    """Each entry must be readable back exactly as written.

    Written as an independent table rather than as a length check: aliases (IOError *is* OSError)
    overwrite an entry without changing the dict's size, so only comparing the values catches it.
    """
    assert ERROR_CODES.get(exception_type) == expected_code, (
        f"{exception_type.__name__} maps to {ERROR_CODES.get(exception_type)}, expected {expected_code}"
    )


def test_error_codes_has_no_aliased_or_extra_entries() -> None:
    """The table must contain exactly the documented entries, each with a distinct code."""
    assert set(ERROR_CODES) == {entry[0] for entry in EXPECTED_ERROR_CODES}, (
        f"unexpected entries: {sorted(t.__name__ for t in set(ERROR_CODES) ^ {e[0] for e in EXPECTED_ERROR_CODES})}"
    )
    codes = list(ERROR_CODES.values())
    assert len(codes) == len(set(codes)), f"two exception types share an exit code: {sorted(codes)}"


def test_error_codes_never_reassigns_the_internal_error_code() -> None:
    """100 means "no mapped type": a registered type using it would make the two indistinguishable."""
    assert INTERNAL_ERROR_CODE not in ERROR_CODES.values(), "100 is reserved for an unmapped cause"


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        # Listed in its own right: it must win over the OSError it derives from (112).
        (FileNotFoundError("x"), 102),
        (PermissionError("x"), 110),
        (NotADirectoryError("x"), 106),
        # Unlisted subclasses: each inherits its nearest listed ancestor.
        (subprocess.CalledProcessError(1, "git"), 111),
        (KeyError("x"), 109),
        (OSError("x"), 112),
        (UnicodeDecodeError("utf-8", b"", 0, 1, "x"), 103),
        # Nothing in the MRO is registered.
        (Exception("x"), INTERNAL_ERROR_CODE),
    ],
)
def test_resolve_error_code_walks_the_mro(exception: BaseException, expected_code: int) -> None:
    """A subclass inherits its nearest registered ancestor's code, and a listed type still wins.

    The old exact ``type(e) in ERROR_CODES`` lookup sent every unlisted subclass to 100, so the
    ``CalledProcessError`` and ``OSError`` rows are the ones that fail without the MRO walk, and the
    ``FileNotFoundError`` row is the one that fails if the walk is done in the wrong order.
    """
    assert resolve_error_code(exception) == expected_code, (
        f"{type(exception).__name__} resolved to {resolve_error_code(exception)}, expected {expected_code}"
    )


def _iter_package_exceptions() -> Iterator[type[BaseException]]:
    """Yield every exception class defined inside the mega_snake package.

    Parameters:
        None

    Raises:
        None

    Returns:
        Iterator[type[BaseException]]: The custom exception classes, without duplicates.
    """
    package = importlib.import_module(MODULE_NAME)
    seen: set[type[BaseException]] = set()
    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{MODULE_NAME}."):
        module = importlib.import_module(module_info.name)
        for _, member in inspect.getmembers(module, inspect.isclass):
            if not issubclass(member, BaseException):
                continue
            if not member.__module__.startswith(f"{MODULE_NAME}."):
                continue
            if member in seen:
                continue
            seen.add(member)
            yield member


def test_every_custom_exception_in_the_package_has_a_registered_exit_code() -> None:
    """Walk the whole package and fail naming any custom exception with no exit code of its own.

    This enforces the registration rule mechanically instead of by convention: a new exception that
    nobody adds to ERROR_CODES would otherwise exit 100, indistinguishable from an internal error,
    and nothing would ever say so. It also proves the discovery works, since a walk that imported
    nothing would pass vacuously.
    """
    unregistered: list[str] = []
    discovered: list[str] = []
    for exception_type in _iter_package_exceptions():
        discovered.append(exception_type.__name__)
        if exception_type.__name__ in UNMAPPED_BY_DESIGN:
            continue
        if exception_type in ERROR_CODES:
            continue
        if issubclass(exception_type, click.ClickException) and exception_type.exit_code != CLICK_EXCEPTION_EXIT_CODE:
            continue
        unregistered.append(f"{exception_type.__module__}.{exception_type.__name__}")

    assert not unregistered, (
        "these custom exceptions have no exit code of their own; register them in ERROR_CODES "
        f"(or give them a ClickException exit_code): {sorted(unregistered)}"
    )
    # Guards against a silently empty walk, which would make the assertion above meaningless.
    for expected in ("WorkspaceError", "ValidationError", "UserDeclinedError", "VersionSetException"):
        assert expected in discovered, f"the package walk did not reach {expected}; the invariant proves nothing"


def test_main_re_raises_a_click_exception_instead_of_relabelling_it() -> None:
    """A ClickException must reach Click untouched: it already knows its own status.

    Wrapping it in a WorkspaceError would resolve a *new* code from its type and turn a clean user
    error into an internal one, so this asserts the exception object comes back identical.
    """
    error = ValidationError("stale")
    with patch("mega_snake.util.cli_group.CliGroup.main", side_effect=error):
        with pytest.raises(ValidationError) as excinfo:
            app_main.main()

    assert excinfo.value is error, "the ClickException was replaced instead of propagated"
    assert not isinstance(excinfo.value, WorkspaceError), "a ClickException must not become a WorkspaceError"
    assert excinfo.value.exit_code == VALIDATION_ERROR_CODE


def test_main_wraps_any_other_exception_so_its_code_can_be_resolved() -> None:
    """Anything that is not a ClickException becomes a WorkspaceError carrying its resolved code."""
    with patch("mega_snake.util.cli_group.CliGroup.main", side_effect=ValueError("boom")):
        with pytest.raises(WorkspaceError) as excinfo:
            app_main.main()

    assert excinfo.value.error_code == 103, f"a ValueError produced code {excinfo.value.error_code}, expected 103"
    assert excinfo.value.error_code != CLICK_EXCEPTION_EXIT_CODE


@pytest.mark.parametrize(
    ("error_code", "expect_traceback"),
    [
        # A mapped cause was anticipated and already reported: no traceback, just the status.
        (103, False),
        # An unmapped cause is unexpected, so the traceback is the only diagnostic on the console.
        (INTERNAL_ERROR_CODE, True),
    ],
)
def test_on_crash_exits_with_the_workspace_error_code(error_code: int, expect_traceback: bool) -> None:
    """The hook must exit for *every* WorkspaceError, including the unmapped one.

    It used to return without exiting when the code was 100, which handed the process straight back
    to Python's default handling and its exit status of 1 — so the one code meant to say "internal
    error" was the only one that could never be observed.
    """
    original_hook = sys.excepthook
    try:
        error = WorkspaceError("wrapped", ValueError("boom") if error_code == 103 else Exception("boom"))
        with patch("mega_snake.util.formatting.old_hook") as hook_mock:
            with pytest.raises(SystemExit) as excinfo:
                formatting._on_crash(type(error), error, None)
    finally:
        sys.excepthook = original_hook

    assert excinfo.value.code == error_code, f"the hook exited {excinfo.value.code}, expected {error_code}"
    assert excinfo.value.code != CLICK_EXCEPTION_EXIT_CODE
    assert hook_mock.called is expect_traceback, (
        f"traceback printing was {'skipped' if expect_traceback else 'performed'} for code {error_code}"
    )


def test_on_crash_leaves_unrelated_exceptions_to_the_default_handler() -> None:
    """Anything that is not a WorkspaceError must fall through untouched, without a forced exit."""
    original_hook = sys.excepthook
    try:
        error = ValueError("boom")
        with patch("mega_snake.util.formatting.old_hook") as hook_mock:
            assert formatting._on_crash(ValueError, error, None) is None
    finally:
        sys.excepthook = original_hook

    hook_mock.assert_called_once_with(ValueError, error, None)


def test_workspace_error_resolves_its_code_from_the_cause_over_the_caller_hint() -> None:
    """A registered cause decides the status, so the same failure always reports the same number."""
    registered = WorkspaceError("wrapped", ValueError("boom"), error_code=999)
    unregistered = WorkspaceError("wrapped", Exception("boom"))

    assert registered.error_code == 103, f"a ValueError cause resolved to {registered.error_code}"
    assert unregistered.error_code == INTERNAL_ERROR_CODE, (
        f"an unmapped cause resolved to {unregistered.error_code}"
    )
