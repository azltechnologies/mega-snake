"""Tests for mega_snake.dependency_audit.scanner"""

import json
from typing import Generator
from unittest.mock import patch, MagicMock
import pytest
from mega_snake.dependency_audit.scanner import (
    ECOSYSTEM_JAVA,
    ECOSYSTEM_NODE,
    ECOSYSTEM_OSV,
    ECOSYSTEM_PYTHON,
    OsvScannerAuditor,
    PipAuditAuditor,
    Vulnerability,
    detect_ecosystem,
    export_requirements,
    get_auditor,
    parse_osv_scanner_output,
    parse_pip_audit_output,
    run_osv_scanner,
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


def test_parse_osv_scanner_output_empty() -> None:
    """Empty or blank output should return an empty list."""
    assert not parse_osv_scanner_output("")
    assert not parse_osv_scanner_output("   ")


def test_parse_osv_scanner_output_invalid_json() -> None:
    """Invalid JSON should be handled gracefully and return an empty list."""
    assert not parse_osv_scanner_output("not-json")


def test_parse_osv_scanner_output_parses_vulnerabilities() -> None:
    """Valid osv-scanner JSON output should be parsed into Vulnerability objects."""
    raw_output = json.dumps(
        {
            "results": [
                {
                    "source": {"path": "build.gradle.kts", "type": "lockfile"},
                    "packages": [
                        {
                            "package": {"name": "com.example:example", "version": "1.0.0", "ecosystem": "Maven"},
                            "vulnerabilities": [
                                {
                                    "id": "GHSA-xxxx-yyyy-zzzz",
                                    "aliases": ["CVE-2024-0002"],
                                    "summary": "An example vulnerability.",
                                    "affected": [
                                        {
                                            "ranges": [
                                                {
                                                    "type": "ECOSYSTEM",
                                                    "events": [{"introduced": "0"}, {"fixed": "1.0.1"}],
                                                }
                                            ]
                                        }
                                    ],
                                }
                            ],
                        },
                        {
                            "package": {"name": "safe-package", "version": "2.0.0", "ecosystem": "Maven"},
                            "vulnerabilities": [],
                        },
                    ],
                }
            ]
        }
    )
    vulnerabilities = parse_osv_scanner_output(raw_output)
    assert len(vulnerabilities) == 1
    vulnerability = vulnerabilities[0]
    assert vulnerability.package == "com.example:example"
    assert vulnerability.installed_version == "1.0.0"
    assert vulnerability.vulnerability_id == "GHSA-xxxx-yyyy-zzzz"
    assert vulnerability.fix_versions == ["1.0.1"]
    assert vulnerability.aliases == ["CVE-2024-0002"]
    assert vulnerability.description == "An example vulnerability."


def test_parse_osv_scanner_output_falls_back_to_details() -> None:
    """When no summary is present, the description should fall back to details."""
    raw_output = json.dumps(
        {
            "results": [
                {
                    "packages": [
                        {
                            "package": {"name": "pkg", "version": "1.0.0"},
                            "vulnerabilities": [{"id": "OSV-1", "details": "Detailed description."}],
                        }
                    ]
                }
            ]
        }
    )
    vulnerabilities = parse_osv_scanner_output(raw_output)
    assert vulnerabilities[0].description == "Detailed description."
    assert vulnerabilities[0].fix_versions == []


def test_run_osv_scanner(run_operation: MagicMock) -> None:
    """Test run_osv_scanner parses the result of run_operation."""
    run_operation.return_value = MagicMock(stdout=json.dumps({"results": []}))
    vulnerabilities = run_osv_scanner("some/target")
    run_operation.assert_called_once()
    command = run_operation.call_args[0][0]
    assert "osv-scanner --format json --recursive some/target" in command
    assert run_operation.call_args.kwargs.get("check") is False
    assert not vulnerabilities


def test_pip_audit_auditor_scan() -> None:
    """PipAuditAuditor.scan should export requirements and then run pip-audit against them."""
    with patch(
        "mega_snake.dependency_audit.scanner.export_requirements", return_value="requirements.txt"
    ) as export_mock, patch(
        "mega_snake.dependency_audit.scanner.run_pip_audit", return_value=[]
    ) as audit_mock:
        result = PipAuditAuditor().scan()
    export_mock.assert_called_once()
    audit_mock.assert_called_once_with("requirements.txt")
    assert result == []


def test_osv_scanner_auditor_scan() -> None:
    """OsvScannerAuditor.scan should delegate to run_osv_scanner with its target."""
    with patch("mega_snake.dependency_audit.scanner.run_osv_scanner", return_value=[]) as scan_mock:
        result = OsvScannerAuditor(target="some/target").scan()
    scan_mock.assert_called_once_with("some/target")
    assert result == []


def test_detect_ecosystem_python(tmp_path) -> None:
    """A project with a uv.lock file should be detected as Python."""
    (tmp_path / "uv.lock").write_text("")
    assert detect_ecosystem(str(tmp_path)) == ECOSYSTEM_PYTHON


@pytest.mark.parametrize("marker", ["build.gradle", "build.gradle.kts", "pom.xml"])
def test_detect_ecosystem_java(tmp_path, marker: str) -> None:
    """A project with a Gradle or Maven build file should be detected as Java."""
    (tmp_path / marker).write_text("")
    assert detect_ecosystem(str(tmp_path)) == ECOSYSTEM_JAVA


def test_detect_ecosystem_node(tmp_path) -> None:
    """A project with a package-lock.json file should be detected as Node."""
    (tmp_path / "package-lock.json").write_text("")
    assert detect_ecosystem(str(tmp_path)) == ECOSYSTEM_NODE


def test_detect_ecosystem_falls_back_to_osv(tmp_path) -> None:
    """A project with none of the known markers should fall back to the generic osv ecosystem."""
    assert detect_ecosystem(str(tmp_path)) == ECOSYSTEM_OSV


def test_get_auditor_uses_detection_when_no_override(tmp_path) -> None:
    """get_auditor should auto-detect the ecosystem when no override is given."""
    (tmp_path / "uv.lock").write_text("")
    auditor = get_auditor(project_root=str(tmp_path))
    assert isinstance(auditor, PipAuditAuditor)


def test_get_auditor_returns_osv_scanner_for_non_python_ecosystems(tmp_path) -> None:
    """get_auditor should return OsvScannerAuditor for java/node/osv ecosystems."""
    auditor = get_auditor(ecosystem=ECOSYSTEM_JAVA, project_root=str(tmp_path))
    assert isinstance(auditor, OsvScannerAuditor)
    assert auditor.target == str(tmp_path)


def test_get_auditor_rejects_unsupported_ecosystem(tmp_path) -> None:
    """get_auditor should raise ValueError for an unknown ecosystem override."""
    with pytest.raises(ValueError):
        get_auditor(ecosystem="ruby", project_root=str(tmp_path))


def test_scan_dependencies_runs_pip_audit_auditor_for_python() -> None:
    """scan_dependencies should dispatch to PipAuditAuditor when ecosystem is python."""
    with patch(
        "mega_snake.dependency_audit.scanner.export_requirements", return_value="requirements.txt"
    ) as export_mock, patch(
        "mega_snake.dependency_audit.scanner.run_pip_audit", return_value=[]
    ) as audit_mock:
        result = scan_dependencies(ecosystem=ECOSYSTEM_PYTHON)
    export_mock.assert_called_once()
    audit_mock.assert_called_once_with("requirements.txt")
    assert result == []


def test_scan_dependencies_runs_osv_scanner_auditor_for_java() -> None:
    """scan_dependencies should dispatch to OsvScannerAuditor when ecosystem is java."""
    with patch("mega_snake.dependency_audit.scanner.run_osv_scanner", return_value=[]) as scan_mock:
        result = scan_dependencies(ecosystem=ECOSYSTEM_JAVA, project_root="some/target")
    scan_mock.assert_called_once_with("some/target")
    assert result == []
