"""Tests for top-level CLI command names and short aliases."""

import pytest

from mega_snake import __main__ as app_main


@pytest.mark.parametrize(
    ("command_name", "aliases"),
    [
        ("working-env", ["cwe", "env"]),
        ("set-java", ["java", "sj"]),
        ("set-gradle", ["gradle", "sg"]),
        ("set-maven", ["maven", "sm"]),
        ("maven-project-setup", ["mps"]),
        ("init-local-config", ["iload", "ilc"]),
        ("graphql-schema", ["graphql", "gql", "cgs"]),
        ("diff-tree", ["dt", "tree"]),
        ("remote-branches-details", ["rbd"]),
        ("remote-branches-cleanup", ["rbc"]),
        ("create-release", ["release", "cr"]),
        ("expired-certs-jks", ["ecj"]),
    ],
)
def test_cli_exposes_kebab_case_names_with_short_aliases(command_name: str, aliases: list[str]) -> None:
    """Commands should expose kebab-case names and hidden short aliases."""
    commands = app_main.cli.commands
    assert command_name in commands
    for alias in aliases:
        assert alias in commands
        assert commands[alias].hidden is True
