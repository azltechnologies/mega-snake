"""Tests for Maven setup commands."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from click.testing import CliRunner
import pytest

from mega_snake.config_environment.maven_setup import maven_project_setup, set_maven_version, _detect_maven_home


def test_set_maven_command_uses_properties() -> None:
    """set-maven should resolve runtime properties and delegate execution."""
    with patch("mega_snake.config_environment.maven_setup.get_property") as get_property, patch(
        "mega_snake.config_environment.maven_setup.get_local_file", return_value="/tmp/local.sh"
    ), patch("mega_snake.config_environment.maven_setup._execute_set_maven") as execute_set_maven:
        get_property.side_effect = ["/tmp/workspace.code-workspace", "/tmp/workspace_temp", "bash"]
        runner = CliRunner()
        result = runner.invoke(set_maven_version, ["--maven-home", "/opt/maven"])
        assert result.exit_code == 0
        execute_set_maven.assert_called_once_with(
            "/tmp/workspace.code-workspace", "/tmp/workspace_temp", "/tmp/local.sh", "bash", "/opt/maven"
        )


def test_maven_project_setup_creates_vscode_tasks() -> None:
    """maven-project-setup should create a VS Code tasks file when pom.xml exists."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pom.xml").write_text("<project/>", encoding="utf-8")
        result = runner.invoke(maven_project_setup)
        assert result.exit_code == 0
        tasks_file = Path(".vscode/tasks.json")
        assert tasks_file.exists()
        contents = tasks_file.read_text(encoding="utf-8")
        assert '"label": "maven: clean install"' in contents
        assert '"command": "mvn spring-boot:run"' in contents


def test_maven_project_setup_requires_pom_file() -> None:
    """maven-project-setup should fail when pom.xml is missing."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(maven_project_setup)
        assert result.exit_code != 0
        assert isinstance(result.exception, FileNotFoundError)


def test_detect_maven_home_prefers_mvn_output() -> None:
    """Maven home should be parsed from mvn -v output when available."""
    with patch("mega_snake.config_environment.maven_setup.shutil.which", return_value="/usr/bin/mvn"), patch(
        "mega_snake.config_environment.maven_setup.run_operation",
        return_value=SimpleNamespace(stdout="Apache Maven 3.9.8\nMaven home: /opt/apache-maven-3.9.8\n"),
    ):
        assert _detect_maven_home() == "/opt/apache-maven-3.9.8"


def test_detect_maven_home_falls_back_to_binary_path() -> None:
    """Maven home should fall back to the binary path when mvn output lacks Maven home."""
    with patch("mega_snake.config_environment.maven_setup.shutil.which", return_value="/usr/local/bin/mvn"), patch(
        "mega_snake.config_environment.maven_setup.run_operation", return_value=SimpleNamespace(stdout="")
    ):
        assert _detect_maven_home() == "/usr/local"
