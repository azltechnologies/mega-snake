"""Tests for mega_snake.dependency_audit.issue_manager"""

import json
from typing import Generator
from unittest.mock import patch, MagicMock
import pytest
from mega_snake.dependency_audit.scanner import Vulnerability
from mega_snake.dependency_audit.issue_manager import (
    build_issue_title,
    build_issue_body,
    issue_exists,
    create_issue,
    report_vulnerabilities,
)


@pytest.fixture(name="vulnerability")
def fixture_vulnerability() -> Vulnerability:
    """A sample vulnerability used across tests."""
    return Vulnerability(
        package="example",
        installed_version="1.0.0",
        vulnerability_id="PYSEC-2024-1",
        fix_versions=["1.0.1"],
        aliases=["CVE-2024-0001"],
        description="An example vulnerability.",
    )


@pytest.fixture(name="run_operation")
def fixture_run_operation() -> Generator[MagicMock, None, None]:
    """Mock run_operation"""
    with patch("mega_snake.dependency_audit.issue_manager.run_operation") as mock:
        yield mock


def test_build_issue_title(vulnerability: Vulnerability) -> None:
    """Test build_issue_title"""
    assert build_issue_title(vulnerability) == "[Security] example==1.0.0 - PYSEC-2024-1"


def test_build_issue_body(vulnerability: Vulnerability) -> None:
    """Test build_issue_body"""
    body = build_issue_body(vulnerability)
    assert "**Package:** example" in body
    assert "**Installed version:** 1.0.0" in body
    assert "**Recommended version:** 1.0.1" in body
    assert "**Severity:** See advisory (CVE-tracked)" in body
    assert "**Aliases:** CVE-2024-0001" in body
    assert "https://osv.dev/vulnerability/PYSEC-2024-1" in body
    assert "An example vulnerability." in body


def test_build_issue_body_without_aliases_or_description() -> None:
    """Missing aliases/description should fall back to sensible defaults."""
    vulnerability = Vulnerability(package="pkg", installed_version="1.0.0", vulnerability_id="PYSEC-1")
    body = build_issue_body(vulnerability)
    assert "**Aliases:** N/A" in body
    assert "No description provided by the advisory." in body


def test_issue_exists_true(run_operation: MagicMock) -> None:
    """issue_exists should return True when a matching title is found."""
    run_operation.return_value = MagicMock(stdout=json.dumps([{"title": "[Security] example==1.0.0 - PYSEC-2024-1"}]))
    assert issue_exists("[Security] example==1.0.0 - PYSEC-2024-1") is True
    run_operation.assert_called_once()
    assert "gh issue list" in run_operation.call_args[0][0]


def test_issue_exists_false(run_operation: MagicMock) -> None:
    """issue_exists should return False when no matching title is found."""
    run_operation.return_value = MagicMock(stdout=json.dumps([{"title": "unrelated"}]))
    assert issue_exists("[Security] example==1.0.0 - PYSEC-2024-1") is False


def test_issue_exists_handles_invalid_json(run_operation: MagicMock) -> None:
    """issue_exists should return False when the gh output cannot be parsed."""
    run_operation.return_value = MagicMock(stdout="not-json")
    assert issue_exists("title") is False


def test_create_issue_skips_when_issue_exists(vulnerability: Vulnerability) -> None:
    """create_issue should not call gh issue create when the issue already exists."""
    with patch("mega_snake.dependency_audit.issue_manager.issue_exists", return_value=True), patch(
        "mega_snake.dependency_audit.issue_manager.run_operation"
    ) as run_operation:
        assert create_issue(vulnerability) is False
    run_operation.assert_not_called()


def test_create_issue_creates_new_issue(vulnerability: Vulnerability, run_operation: MagicMock) -> None:
    """create_issue should call gh issue create when no matching issue exists."""
    with patch("mega_snake.dependency_audit.issue_manager.issue_exists", return_value=False):
        assert create_issue(vulnerability) is True
    run_operation.assert_called_once()
    command = run_operation.call_args[0][0]
    assert "gh issue create" in command
    assert "[Security] example==1.0.0 - PYSEC-2024-1" in command
    assert "dependencies,security" in command


def test_report_vulnerabilities_counts_created_issues(vulnerability: Vulnerability) -> None:
    """report_vulnerabilities should return the count of newly created issues."""
    other = Vulnerability(package="other", installed_version="2.0.0", vulnerability_id="PYSEC-2024-2")
    with patch("mega_snake.dependency_audit.issue_manager.create_issue", side_effect=[True, False]) as create_mock:
        created = report_vulnerabilities([vulnerability, other])
    assert created == 1
    assert create_mock.call_count == 2
