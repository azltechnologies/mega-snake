""" Test the config_environment module """

import click
import pytest
from click.testing import CliRunner
from mega_snake.config_environment import module
from mega_snake.constants import RELOAD_ENVIRONMENT_EXIT_CODE
from mega_snake.util.cli_group import ATTR_METADATA, META_RELOADS_ENV

# Commands whose whole purpose is to rewrite one of the two local environment files, so the shell
# has to re-source them afterwards. Listed here as the expectation the source must satisfy: the
# wrapper reads the metadata, so a test reading the same metadata would prove nothing.
RELOADING_COMMANDS: tuple[str, ...] = ("set-java", "set-gradle", "set-maven", "init-local-config", "working-env")
# Commands in the same module that touch neither file. They used to emit the signal purely because
# of where they live, which made every run of them re-source the environment for no reason.
NON_RELOADING_COMMANDS: tuple[str, ...] = ("maven-project-setup", "graphql-schema")


def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main, ["--help"])
    assert result.exit_code == 0
    assert "Configuration related commands" in result.output


def _invoke_wrapper(command_name: str) -> dict:
    """Run the module wrapper for a registered command and return the resulting context object.

    Parameters:
        command_name: The registered name of the command to wrap.

    Raises:
        AssertionError: If the command is not registered in the module group.

    Returns:
        dict: The context object the wrapper wrote into.
    """
    command = module.main.commands.get(command_name)
    assert command is not None, f"'{command_name}' is not registered in the config_environment group"
    wrapped: click.Command = module.add_wrapper(command)
    ctx = click.Context(wrapped)
    ctx.obj = {}
    with ctx.scope():
        module.wrapper(ctx)
    return ctx.obj


@pytest.mark.parametrize("command_name", RELOADING_COMMANDS)
def test_wrapper_requests_a_reload_for_commands_that_rewrite_the_environment(command_name: str) -> None:
    """Every command that rewrites a local environment file must request the reload signal.

    The exact number is the contract: config_setup.sh and config_setup.ps1 compare against 29, so
    any other non-zero status would be reported to the user as a failure and no reload would run.
    """
    exit_code = _invoke_wrapper(command_name).get("exit_code", 0)
    assert exit_code == RELOAD_ENVIRONMENT_EXIT_CODE, (
        f"'{command_name}' asked for exit code {exit_code}, expected {RELOAD_ENVIRONMENT_EXIT_CODE}"
    )


@pytest.mark.parametrize("command_name", NON_RELOADING_COMMANDS)
def test_wrapper_stays_silent_for_commands_that_leave_the_environment_alone(command_name: str) -> None:
    """A command that touches neither environment file must exit cleanly, with no signal at all."""
    exit_code = _invoke_wrapper(command_name).get("exit_code", 0)
    assert exit_code == 0, f"'{command_name}' asked for exit code {exit_code}, expected 0"
    assert exit_code != RELOAD_ENVIRONMENT_EXIT_CODE, f"'{command_name}' must not request a shell reload"


def test_every_command_in_the_module_is_classified() -> None:
    """The two lists above must together cover every command in the group.

    Without this, a command added later would be silently absent from both lists and its reload
    behaviour would go untested — which is how the signal came to be attached to the module instead
    of to the commands that need it.
    """
    registered = {command.name for command in module.main.commands.values() if not command.hidden}
    classified = set(RELOADING_COMMANDS) | set(NON_RELOADING_COMMANDS)
    assert registered == classified, f"unclassified commands: {sorted(registered ^ classified)}"


@pytest.mark.parametrize("command_name", RELOADING_COMMANDS)
def test_reload_metadata_survives_the_command_wrapping(command_name: str) -> None:
    """The marker must reach the wrapping callback, which is where the wrapper reads it from.

    ``wrapper_decorator`` rebuilds the command from ``click.Command.__init__``'s signature, so a
    marker that is not explicitly propagated disappears at registration time and the signal dies
    with it, silently.
    """
    command = module.main.commands[command_name]
    wrapped: click.Command = module.add_wrapper(command)
    metadata = getattr(wrapped.callback, ATTR_METADATA, {})
    assert metadata.get(META_RELOADS_ENV) is True, f"'{command_name}' lost its reload marker when wrapped"
