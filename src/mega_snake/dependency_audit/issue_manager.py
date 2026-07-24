"""
This module creates GitHub issues for detected dependency vulnerabilities.

It relies on the `gh` CLI (same "shell wrapper" pattern used by `create-release`)
to search for existing issues and avoid filing duplicates for findings that were
already reported.
"""

import json
from mega_snake.dependency_audit.scanner import Vulnerability
from mega_snake.util.util import run_operation
from mega_snake.util.formatting import ws_info, ws_success

ISSUE_LABELS: str = "dependencies,security"


def build_issue_title(vulnerability: Vulnerability) -> str:
    """Build the deterministic issue title used both for creation and duplicate detection.

    Parameters:
        vulnerability: The vulnerability to build a title for.

    Raises:
        None

    Returns:
        str: The issue title.
    """
    return f"[Security] {vulnerability.package}=={vulnerability.installed_version} - {vulnerability.vulnerability_id}"


def build_issue_body(vulnerability: Vulnerability) -> str:
    """Build the issue body describing the vulnerability finding.

    Parameters:
        vulnerability: The vulnerability to describe.

    Raises:
        None

    Returns:
        str: The issue body containing package, versions, severity, aliases and advisory link.
    """
    aliases: str = ", ".join(vulnerability.aliases) if vulnerability.aliases else "N/A"
    description: str = vulnerability.description or "No description provided by the advisory."
    return (
        f"**Package:** {vulnerability.package}\n"
        f"**Installed version:** {vulnerability.installed_version}\n"
        f"**Recommended version:** {vulnerability.recommended_version}\n"
        f"**Severity:** {vulnerability.severity}\n"
        f"**Aliases:** {aliases}\n"
        f"**Advisory:** {vulnerability.advisory_url}\n\n"
        f"{description}\n\n"
        "_This issue was created automatically by the dependency audit scan._"
    )


def issue_exists(title: str) -> bool:
    """Check whether an issue with the exact given title already exists, to avoid duplicates.

    Both open and closed issues are considered so a re-appearing vulnerability that was
    previously fixed and closed does not get reported again by mistake.

    Parameters:
        title: The exact issue title to search for.

    Raises:
        None

    Returns:
        bool: True if a matching issue already exists, False otherwise.
    """
    escaped_title: str = title.replace('"', '\\"')
    cwd: str = f'gh issue list --search "\\"{escaped_title}\\" in:title" --state all --json title 2>&1'
    result = run_operation(cwd, f"Check for existing issue: {title}", check=False)
    try:
        issues: list[dict] = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        ws_info(f"Could not determine if an issue already exists for '{title}'. Assuming it does not.")
        return False
    return any(issue.get("title") == title for issue in issues)


def create_issue(vulnerability: Vulnerability) -> bool:
    """Create a GitHub issue for the given vulnerability if one does not already exist.

    Parameters:
        vulnerability: The vulnerability to file an issue for.

    Raises:
        subprocess.SubprocessError: If `gh issue create` fails after all retries.

    Returns:
        bool: True if a new issue was created, False if skipped because it already exists.
    """
    title: str = build_issue_title(vulnerability)
    if issue_exists(title):
        ws_info(f"Issue already exists for '{title}'. Skipping.")
        return False
    body: str = build_issue_body(vulnerability)
    cwd: str = f'gh issue create --title "{title}" --body "{body}" --label "{ISSUE_LABELS}" 2>&1'
    run_operation(cwd, f"Create issue for {title}")
    ws_success(f"Created issue for '{title}'")
    return True


def report_vulnerabilities(vulnerabilities: list[Vulnerability]) -> int:
    """Create GitHub issues for each vulnerability found, skipping already reported ones.

    Parameters:
        vulnerabilities: The vulnerabilities to report.

    Raises:
        None

    Returns:
        int: The number of new issues created.
    """
    created: int = 0
    for vulnerability in vulnerabilities:
        if create_issue(vulnerability):
            created += 1
    return created
