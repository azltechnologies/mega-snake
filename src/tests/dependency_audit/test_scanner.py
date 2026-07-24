"""Tests for mega_snake.dependency_audit.scanner"""

import json
from typing import Generator
from unittest.mock import patch, MagicMock
import pytest
from mega_snake.dependency_audit.scanner import (
    Vulnerability,
    export_requirements,
    parse_pip_audit_output,
    run_pip_audit,
    scan_dependencies,
)


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock, None, None]:
    """Mock run_operation"""
    with patch("mega_snake.dependency_audit.scanner.run_operation") as mock:
        yield mock


def test_vulnerability_recommended_version_defaults_to_unknown() -> None:
    """When no fix_versions are provided, recommended_version should be 'unknown'."""
    vulnerability = Vulnerability(package="pkg", installed_version="1.0.0", vulnerability_id="PYSEC-1")
    assert vulnerability.recommended_version == "unknown"
    assert vulnerability.severity == "unknown"


def test_vulnerability_recommended_version_and_severity_with_data() -> None:
    """When fix_versions/aliases are provided they should be reflected."""
    vulnerability = Vulnerability(
        package="pkg",
        installed_version="1.0.0",
        vulnerability_id="PYSEC-1",
        fix_versions=["1.0.1", "1.0.2"],
        aliases=["CVE-2024-0001"],
    )
    assert vulnerability.recommended_version == "1.0.1"
    assert vulnerability.severity == "See advisory (CVE-tracked)"
    assert vulnerability.advisory_url == "https://osv.dev/vulnerability/PYSEC-1"


def test_export_requirements(run_operation: MagicMock) -> None:
    """Test export_requirements"""
    path = export_requirements("out/requirements.txt")
    run_operation.assert_called_once()
    assert "uv export" in run_operation.call_args[0][0]
    assert "out/requirements.txt" in run_operation.call_args[0][0]
    assert path == "out/requirements.txt"


def test_parse_pip_audit_output_empty() -> None:
    """Empty or blank output should return an empty list."""
    assert not parse_pip_audit_output("")
    assert not parse_pip_audit_output("   ")


def test_parse_pip_audit_output_invalid_json() -> None:
    """Invalid JSON should be handled gracefully and return an empty list."""
    assert not parse_pip_audit_output("not-json")


def test_parse_pip_audit_output_parses_vulnerabilities() -> None:
    """Valid pip-audit JSON output should be parsed into Vulnerability objects."""
    raw_output = json.dumps(
        {
            "dependencies": [
                {
                    "name": "example",
                    "version": "1.0.0",
                    "vulns": [
                        {
                            "id": "PYSEC-2024-1",
                            "fix_versions": ["1.0.1"],
                            "aliases": ["CVE-2024-0001"],
                            "description": "An example vulnerability.",
                        }
                    ],
                },
                {"name": "safe-package", "version": "2.0.0", "vulns": []},
            ]
        }
    )
    vulnerabilities = parse_pip_audit_output(raw_output)
    assert len(vulnerabilities) == 1
    vulnerability = vulnerabilities[0]
    assert vulnerability.package == "example"
    assert vulnerability.installed_version == "1.0.0"
    assert vulnerability.vulnerability_id == "PYSEC-2024-1"
    assert vulnerability.fix_versions == ["1.0.1"]
    assert vulnerability.aliases == ["CVE-2024-0001"]
    assert vulnerability.description == "An example vulnerability."


def test_run_pip_audit(run_operation: MagicMock) -> None:
    """Test run_pip_audit parses the result of run_operation."""
    run_operation.return_value = MagicMock(stdout=json.dumps({"dependencies": []}))
    vulnerabilities = run_pip_audit("requirements.txt")
    run_operation.assert_called_once()
    command = run_operation.call_args[0][0]
    assert "pip-audit -r requirements.txt" in command
    # stderr must NOT be merged into stdout: pip-audit prints its human-readable summary
    # to stderr, which would corrupt the JSON we parse from stdout.
    assert "2>&1" not in command
    assert run_operation.call_args.kwargs.get("check") is False
    assert not vulnerabilities


def test_scan_dependencies_runs_full_pipeline() -> None:
    """scan_dependencies should export requirements and then run pip-audit against them."""
    with patch(
        "mega_snake.dependency_audit.scanner.export_requirements", return_value="requirements.txt"
    ) as export_mock, patch(
        "mega_snake.dependency_audit.scanner.run_pip_audit", return_value=[]
    ) as audit_mock:
        result = scan_dependencies()
    export_mock.assert_called_once()
    audit_mock.assert_called_once_with("requirements.txt")
    assert result == []
