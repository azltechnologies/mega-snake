"""Test the module.py file in the dependency_audit directory"""

from unittest.mock import patch
from click.testing import CliRunner
from mega_snake.dependency_audit import module
from mega_snake.dependency_audit.scanner import Vulnerability


def test_main_group() -> None:
    """Test the main command group"""
    runner = CliRunner()
    result = runner.invoke(module.main, ["--help"])
    assert result.exit_code == 0
    assert "dependency audit related commands" in result.output


def test_scan_dependencies_command_no_findings() -> None:
    """When no vulnerabilities are found, no issues should be created."""
    with patch("mega_snake.dependency_audit.module.scan_dependencies", return_value=[]), patch(
        "mega_snake.dependency_audit.module.report_vulnerabilities"
    ) as report_mock:
        module.scan_dependencies_command.callback(False)
    report_mock.assert_not_called()


def test_scan_dependencies_command_dry_run() -> None:
    """Dry-run mode should print findings without creating any issues."""
    vulnerability = Vulnerability(package="pkg", installed_version="1.0.0", vulnerability_id="PYSEC-1")
    with patch("mega_snake.dependency_audit.module.scan_dependencies", return_value=[vulnerability]), patch(
        "mega_snake.dependency_audit.module.report_vulnerabilities"
    ) as report_mock:
        module.scan_dependencies_command.callback(True)
    report_mock.assert_not_called()


def test_scan_dependencies_command_creates_issues() -> None:
    """Non dry-run mode should report vulnerabilities and create issues."""
    vulnerability = Vulnerability(package="pkg", installed_version="1.0.0", vulnerability_id="PYSEC-1")
    with patch("mega_snake.dependency_audit.module.scan_dependencies", return_value=[vulnerability]), patch(
        "mega_snake.dependency_audit.module.report_vulnerabilities", return_value=1
    ) as report_mock:
        module.scan_dependencies_command.callback(False)
    report_mock.assert_called_once_with([vulnerability])
