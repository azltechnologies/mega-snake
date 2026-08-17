"""Tests pinning the contract between the CLI and the shell init scripts.

`reload-config` and `load-env` do no work of their own: they report a request through their exit
status, and the `mgsnake` shell function defined in `config_setup.sh` / `config_setup.ps1` carries it
out in the user's own session. That split means the two halves are written in different languages, in
different files, and nothing at import time makes them agree -- so every fact they share is pinned
here. Each of these tests fails when one half is changed without the other, which is the only failure
mode this design has.
"""

import re
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest
from click.testing import CliRunner

from mega_snake.constants import (
    LOAD_ENV_COMMAND,
    LOAD_ENV_EXIT_CODE,
    LOAD_ENV_HELPER,
    MODULE_NAME,
    RELOAD_CONFIG_COMMAND,
    RELOAD_ENVIRONMENT_EXIT_CODE,
)
from mega_snake.light_weight import module as light_weight_module
from mega_snake.light_weight import shell_init


def _script(name: str) -> str:
    """Read one of the packaged shell init scripts.

    Parameters:
        name: File name of the script, e.g. ``config_setup.sh``.

    Raises:
        None

    Returns:
        str: The script's full text.
    """
    return files(MODULE_NAME).joinpath(name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("command", "expected_code"),
    [
        pytest.param(shell_init.reload_config, RELOAD_ENVIRONMENT_EXIT_CODE, id="reload-config"),
        pytest.param(shell_init.load_env, LOAD_ENV_EXIT_CODE, id="load-env"),
    ],
)
def test_shell_backed_commands_exit_with_their_signal(command, expected_code: int) -> None:
    """Each command's whole purpose is its status, so the exact number is the behaviour under test.

    Asserting it is not 0 as well: a command that returned success would be reported as having
    worked while the shell did nothing, which is precisely the silent failure this design risks.
    """
    result = CliRunner().invoke(command, [])

    assert result.exit_code == expected_code, f"expected {expected_code}, got {result.exit_code}"
    assert result.exit_code != 0, "a successful status would leave the shell with nothing to do"


def test_the_two_signals_are_distinct() -> None:
    """A shared number would make the wrapper unable to tell the two requests apart."""
    assert RELOAD_ENVIRONMENT_EXIT_CODE != LOAD_ENV_EXIT_CODE


@pytest.mark.parametrize("script_name", ["config_setup.sh", "config_setup.ps1"])
def test_scripts_hard_code_the_current_exit_codes(script_name: str) -> None:
    """Both scripts branch on the literal numbers, so a change in Python has to reach them.

    The assertion is on the assignment line rather than on the bare number: the digits alone appear
    in comments and would keep a stale script passing.
    """
    script = _script(script_name)

    assert re.search(rf"ReloadExitCode\s*=\s*{RELOAD_ENVIRONMENT_EXIT_CODE}\b|RELOAD_EXIT_CODE={RELOAD_ENVIRONMENT_EXIT_CODE}\b", script), (
        f"{script_name} does not assign {RELOAD_ENVIRONMENT_EXIT_CODE} as the reload status"
    )
    assert re.search(rf"LoadEnvExitCode\s*=\s*{LOAD_ENV_EXIT_CODE}\b|LOAD_ENV_EXIT_CODE={LOAD_ENV_EXIT_CODE}\b", script), (
        f"{script_name} does not assign {LOAD_ENV_EXIT_CODE} as the load-env status"
    )


@pytest.mark.parametrize("script_name", ["config_setup.sh", "config_setup.ps1"])
def test_scripts_locate_load_env_by_its_registered_name(script_name: str) -> None:
    """The wrapper finds the command's arguments by scanning for this exact name.

    A renamed command would still exit 30, so the wrapper would still fire -- and then fail to find
    the name in the arguments and silently load the wrong file. Nothing else would report it.

    Anchored on the assignment the wrapper reads, not on the name appearing anywhere: it also shows
    up as the display prefix of the `msg -p` call inside the helper, so a bare `in` check would keep
    passing after the variable itself was deleted.
    """
    script = _script(script_name)

    assert re.search(
        rf'LoadEnvCommand\s*=\s*"{LOAD_ENV_COMMAND}"|LOAD_ENV_COMMAND="{LOAD_ENV_COMMAND}"', script
    ), f"{script_name} must bind the registered name {LOAD_ENV_COMMAND!r} to the variable the wrapper scans for"


@pytest.mark.parametrize("script_name", ["config_setup.sh", "config_setup.ps1"])
def test_scripts_define_the_helper_the_generated_config_file_calls(script_name: str) -> None:
    """`init-local-config` writes a call to LOAD_ENV_HELPER, so the scripts must define that name."""
    script = _script(script_name)

    assert f"function {LOAD_ENV_HELPER}" in script or f"{LOAD_ENV_HELPER}()" in script, (
        f"{script_name} does not define {LOAD_ENV_HELPER}, which the generated local config file calls"
    )


@pytest.mark.parametrize("script_name", ["config_setup.sh", "config_setup.ps1"])
def test_scripts_no_longer_define_the_old_public_helpers(script_name: str) -> None:
    """The helpers are private now; the CLI commands are the public interface.

    Pinned because the rename is the whole point: leaving a public `mgsnake_reload` behind would give
    every action two names, one of them undocumented and invisible to `--help`. `mgsnake_reload_all`
    is gone outright -- it loaded the `.env` of whatever directory the user happened to be in, on top
    of the one the config file had already loaded by absolute path.
    """
    script = _script(script_name)

    # Anchored at the start of a line: a bare `in` check matches `__mgsnake_reload()` too, so it
    # would pass for the renamed private helper and prove nothing.
    for retired in ("mgsnake_reload_all", "mgsnake_reload", "mgsnake_load_env"):
        pattern = rf"^(?:function\s+)?{retired}\s*(?:\(\)|\{{)"
        assert not re.search(pattern, script, re.MULTILINE), (
            f"{script_name} still defines the retired public helper {retired!r}"
        )


def test_shell_backed_commands_have_no_aliases() -> None:
    """An alias would be invoked fine and then leave the wrapper unable to find the arguments.

    The wrapper scans "$@" for the registered name, so `mgsnake le foo.env` would exit 30, match
    nothing, and load `.env` instead of `foo.env` -- a wrong result with no error.
    """
    for name in (RELOAD_CONFIG_COMMAND, LOAD_ENV_COMMAND):
        command = light_weight_module.main.commands[name]
        aliases = getattr(command, "aliases", [])
        assert not aliases, f"{name} must not have aliases, found: {aliases}"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available on this platform")
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        pytest.param(f"{LOAD_ENV_COMMAND} foo.env", "foo.env", id="plain-invocation"),
        pytest.param(f"--log-level DEBUG {LOAD_ENV_COMMAND} foo.env", "foo.env", id="after-a-global-option"),
        pytest.param(f"{LOAD_ENV_COMMAND}", "", id="no-argument-yields-nothing"),
        pytest.param(f"--log-level DEBUG {LOAD_ENV_COMMAND}", "", id="global-option-and-no-argument"),
    ],
)
def test_bash_argument_slicing_returns_only_the_commands_own_arguments(argv: str, expected: str) -> None:
    """The slicing helper is the mechanism that makes stdout unnecessary, so it is tested for real.

    Run through bash rather than asserted as text: the point is what the shell actually computes.
    The `--log-level DEBUG` rows are the ones that fail if the helper ever forwards the raw "$@",
    which is the naive implementation this design exists to avoid.
    """
    script = _script("config_setup.sh")
    # Take the helper alone: sourcing the whole file would require the mgsnake executable on PATH.
    match = re.search(r"^__mgsnake_args_after\(\) \{.*?^\}", script, re.MULTILINE | re.DOTALL)
    assert match, "the argument-slicing helper is no longer defined under its expected name"

    program = f'{match.group(0)}\n__mgsnake_args_after "{LOAD_ENV_COMMAND}" {argv}\n'
    result = subprocess.run(
        ["bash", "-c", program], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected, (
        f"for `mgsnake {argv}` the shell should forward {expected!r}, got {result.stdout.strip()!r}"
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available on this platform")
@pytest.mark.parametrize(
    ("stub_status", "argv", "expected_status", "expected_marker"),
    [
        pytest.param(RELOAD_ENVIRONMENT_EXIT_CODE, "set-java", 0, "reloaded", id="reload-signal-is-served"),
        pytest.param(LOAD_ENV_EXIT_CODE, f"{LOAD_ENV_COMMAND} foo.env", 0, "loaded:foo.env", id="load-env-signal-is-served"),
        pytest.param(0, "diff-tree", 0, "", id="success-passes-through"),
        pytest.param(3, "diff-tree", 3, "", id="a-real-failure-passes-through"),
        pytest.param(1, "diff-tree", 1, "", id="a-misuse-status-passes-through"),
    ],
)
def test_bash_wrapper_reports_success_once_it_has_served_the_signal(
    tmp_path: Path, stub_status: int, argv: str, expected_status: int, expected_marker: str
) -> None:
    """A served signal must not reach the caller, and every other status must reach it unchanged.

    The signal is a request. Once the wrapper has carried it out there is nothing left to report, so
    propagating it would make `mgsnake set-java && echo ok` never print and abort any `set -e`
    script on its happy path. Both halves are asserted here: the exact caller-visible status *and*
    the marker proving the dispatch actually ran -- a wrapper that returned 0 without dispatching
    would satisfy the status assertion alone.
    """
    script = _script("config_setup.sh")
    wrapper = re.search(r"^mgsnake\(\) \{.*?^\}", script, re.MULTILINE | re.DOTALL)
    slicing = re.search(r"^__mgsnake_args_after\(\) \{.*?^\}", script, re.MULTILINE | re.DOTALL)
    assert wrapper, "the mgsnake wrapper function is no longer defined under its expected name"
    assert slicing, "the argument-slicing helper is no longer defined under its expected name"

    # Stands in for the real executable: `command mgsnake` resolves through PATH, never the function.
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "mgsnake"
    stub.write_text(f"#!/usr/bin/env bash\nexit {stub_status}\n", encoding="utf-8")
    stub.chmod(0o755)

    program = (
        f'export PATH="{stub_dir}:$PATH"\n'
        f"{slicing.group(0)}\n"
        f"{wrapper.group(0)}\n"
        f"MEGA_SNAKE_RELOAD_EXIT_CODE={RELOAD_ENVIRONMENT_EXIT_CODE}\n"
        f"MEGA_SNAKE_LOAD_ENV_EXIT_CODE={LOAD_ENV_EXIT_CODE}\n"
        f'MEGA_SNAKE_LOAD_ENV_COMMAND="{LOAD_ENV_COMMAND}"\n'
        '__mgsnake_reload() { printf "reloaded"; }\n'
        '__mgsnake_load_env() { printf "loaded:%s" "$1"; }\n'
        f"mgsnake {argv}\n"
        'printf "|%s" "$?"\n'
    )
    result = subprocess.run(["bash", "-c", program], capture_output=True, text=True, check=False)

    marker, _, status = result.stdout.partition("|")
    assert status == str(expected_status), (
        f"`mgsnake {argv}` (executable exited {stub_status}) should leave the caller with "
        f"{expected_status}, got {status!r}"
    )
    assert marker == expected_marker, (
        f"`mgsnake {argv}` should have dispatched {expected_marker!r}, got {marker!r}"
    )


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh is not available on this platform")
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        pytest.param(f'"{LOAD_ENV_COMMAND}","foo.env"', "foo.env", id="plain-invocation"),
        pytest.param(f'"--log-level","DEBUG","{LOAD_ENV_COMMAND}","other.env"', "other.env", id="after-a-global-option"),
        pytest.param(f'"{LOAD_ENV_COMMAND}"', "", id="no-argument-yields-nothing"),
        pytest.param(f'"--log-level","DEBUG","{LOAD_ENV_COMMAND}"', "", id="global-option-and-no-argument"),
        pytest.param('"set-java"', "", id="a-different-command-matches-nothing"),
    ],
)
def test_pwsh_argument_slicing_returns_only_the_commands_own_argument(argv: str, expected: str) -> None:
    """The PowerShell half of the slicing, exercised in a real pwsh.

    Written after the bash-only version of this test passed while the PowerShell one was broken: a
    range yielding a single item was unwrapped to a bare string, so the caller indexed into it and
    loaded `f` instead of `foo.env`. Asserting the exact value (not merely "something came back") is
    what catches that class of failure.
    """
    script = _script("config_setup.ps1")
    match = re.search(r"^function __mgsnake_args_after.*?^\}", script, re.MULTILINE | re.DOTALL)
    assert match, "the argument-slicing helper is no longer defined under its expected name"

    dispatch = re.search(r"^function mgsnake \{.*?^\}", script, re.MULTILINE | re.DOTALL)
    assert dispatch, "the mgsnake wrapper function is no longer defined under its expected name"

    # The whole dispatch is exercised, not just the slicing helper: the value this returns was
    # already correct when the bug existed, and what broke was the *call site* indexing into it.
    # Stubbing __mgsnake_load_env and echoing the -Path it receives is what makes that observable.
    program = (
        f"{match.group(0)}\n"
        f"{dispatch.group(0)}\n"
        f"$global:MegaSnakeReloadExitCode = {RELOAD_ENVIRONMENT_EXIT_CODE}\n"
        f"$global:MegaSnakeLoadEnvExitCode = {LOAD_ENV_EXIT_CODE}\n"
        f'$global:MegaSnakeLoadEnvCommand = "{LOAD_ENV_COMMAND}"\n'
        # Stands in for the real executable: always asks for the load-env dispatch.
        f'$stub = Join-Path ([System.IO.Path]::GetTempPath()) "mgsnake_stub.ps1"\n'
        f'Set-Content -Path $stub -Value "exit {LOAD_ENV_EXIT_CODE}"\n'
        f'$global:MegaSnakeExe = $stub\n'
        'function __mgsnake_load_env { param([string]$Path = "") Write-Output "[$Path]" }\n'
        # Space-separated, not an array literal: `mgsnake @("a","b")` would pass one array argument,
        # so $args would hold a single element and the slicing would have nothing to find.
        f"mgsnake {argv.replace(',', ' ')}\n"
    )
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", program], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"[{expected}]", (
        f"for `mgsnake {argv}` the helper should receive {expected!r}, got {result.stdout.strip()!r}"
    )


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh is not available on this platform")
@pytest.mark.parametrize(
    ("stub_status", "argv", "expected_status", "expected_marker"),
    [
        pytest.param(RELOAD_ENVIRONMENT_EXIT_CODE, '"set-java"', 0, "reloaded", id="reload-signal-is-served"),
        pytest.param(LOAD_ENV_EXIT_CODE, f'"{LOAD_ENV_COMMAND}" "foo.env"', 0, "loaded:foo.env", id="load-env-signal-is-served"),
        pytest.param(0, '"diff-tree"', 0, "", id="success-passes-through"),
        pytest.param(3, '"diff-tree"', 3, "", id="a-real-failure-passes-through"),
        pytest.param(1, '"diff-tree"', 1, "", id="a-misuse-status-passes-through"),
    ],
)
def test_pwsh_wrapper_reports_success_once_it_has_served_the_signal(
    tmp_path: Path, stub_status: int, argv: str, expected_status: int, expected_marker: str
) -> None:
    """The PowerShell half of the same contract: a served signal must not reach `$LASTEXITCODE`.

    Asserted through the status the caller actually reads, and paired with the dispatch marker so a
    wrapper that reported 0 without doing the work would still fail.
    """
    script = _script("config_setup.ps1")
    slicing = re.search(r"^function __mgsnake_args_after.*?^\}", script, re.MULTILINE | re.DOTALL)
    dispatch = re.search(r"^function mgsnake \{.*?^\}", script, re.MULTILINE | re.DOTALL)
    assert slicing, "the argument-slicing helper is no longer defined under its expected name"
    assert dispatch, "the mgsnake wrapper function is no longer defined under its expected name"

    stub = tmp_path / "mgsnake_stub.ps1"
    stub.write_text(f"exit {stub_status}\n", encoding="utf-8")

    program = (
        f"{slicing.group(0)}\n"
        f"{dispatch.group(0)}\n"
        f"$global:MegaSnakeReloadExitCode = {RELOAD_ENVIRONMENT_EXIT_CODE}\n"
        f"$global:MegaSnakeLoadEnvExitCode = {LOAD_ENV_EXIT_CODE}\n"
        f'$global:MegaSnakeLoadEnvCommand = "{LOAD_ENV_COMMAND}"\n'
        f'$global:MegaSnakeExe = "{stub.as_posix()}"\n'
        'function __mgsnake_reload { [Console]::Write("reloaded") }\n'
        'function __mgsnake_load_env { param([string]$Path = "") [Console]::Write("loaded:$Path") }\n'
        f"mgsnake {argv}\n"
        '[Console]::Write("|$LASTEXITCODE")\n'
    )
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", program], capture_output=True, text=True, check=False
    )

    marker, _, status = result.stdout.partition("|")
    assert status == str(expected_status), (
        f"`mgsnake {argv}` (executable exited {stub_status}) should leave $LASTEXITCODE at "
        f"{expected_status}, got {status!r} ({result.stderr})"
    )
    assert marker == expected_marker, (
        f"`mgsnake {argv}` should have dispatched {expected_marker!r}, got {marker!r}"
    )


def test_load_env_declares_its_argument_for_documentation() -> None:
    """The argument exists so `--help` and the reference describe it, even though Python ignores it.

    Without the declaration click would reject `mgsnake load-env foo.env` outright, so this is the
    difference between a documented command and a broken one.
    """
    argument_names = [param.name for param in shell_init.load_env.params if isinstance(param, __import__("click").Argument)]

    assert argument_names == ["env_file"], f"expected a single `env_file` argument, found {argument_names}"


def test_generated_local_config_calls_the_private_helper(tmp_path: Path) -> None:
    """The generated file must call the private helper, not the retired public function name."""
    from mega_snake.config_environment import local_config

    env_file = tmp_path / ".mgsnake.env"
    local_file = tmp_path / "local_config.sh"

    def fake_get_property(key: str) -> str:
        return {"local_env_file": str(env_file), "shell": "bash"}[key]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(local_config, "get_property", fake_get_property)
        monkeypatch.setattr(local_config, "get_local_file", lambda: str(local_file))
        local_config.execute(True)

    contents = local_file.read_text(encoding="utf-8")
    assert LOAD_ENV_HELPER in contents, "the generated config file no longer calls the private helper"
    assert "mgsnake_load_env " not in contents.replace(LOAD_ENV_HELPER, ""), (
        "the generated config file still calls the retired public helper name"
    )
