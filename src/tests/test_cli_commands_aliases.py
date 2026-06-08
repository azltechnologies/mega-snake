"""Tests for top-level CLI command names and compatibility aliases."""

import pytest

from mega_snake import __main__ as app_main


@pytest.mark.parametrize(
    ("command_name", "legacy_alias"),
    [
        ("working_env", "createWorkingEnv"),
        ("set_java", "setJava"),
        ("set_gradle", "setGradle"),
        ("init_local_config", "initLocalConfig"),
        ("graphql_schema", "createGraphqlSchema"),
        ("diff_tree", "createDiffTree"),
        ("remote_branches_details", "remoteBranchesDetails"),
        ("remote_branches_cleanup", "remoteBranchesCleanUp"),
        ("create_release", "createRelease"),
        ("expired_certs_jks", "expiredCertsJks"),
    ],
)
def test_cli_exposes_snake_case_names_with_legacy_aliases(command_name: str, legacy_alias: str) -> None:
    """Each renamed command should keep a backwards-compatible legacy alias."""
    commands = app_main.cli.commands
    assert command_name in commands
    assert legacy_alias in commands
    assert commands[legacy_alias].hidden is True
