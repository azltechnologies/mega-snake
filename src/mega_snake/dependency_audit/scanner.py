"""
This module scans a project's locked dependencies for known vulnerabilities.

It supports multiple ecosystems through a small `DependencyAuditor` protocol:
- `PipAuditAuditor` exports `uv.lock` to a requirements file and runs `pip-audit`
  against it (Python/uv projects).
- `OsvScannerAuditor` runs `osv-scanner` against the project tree, covering
  Java/Gradle/Maven, Node, and any other ecosystem OSV-Scanner supports.

Both auditors normalize their tool-specific output into a shared list of
`Vulnerability` objects. `detect_ecosystem` inspects the project root for marker
files (`uv.lock`, `build.gradle(.kts)`/`pom.xml`, `package-lock.json`) to pick the
right auditor automatically, with a manual override available via `get_auditor`.
"""

import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol
from mega_snake.util.util import run_operation
from mega_snake.util.formatting import ws_info, ws_warning

REQUIREMENTS_EXPORT_PATH: str = "workspace_temp/dependency-audit-requirements.txt"

ECOSYSTEM_PYTHON: str = "python"
ECOSYSTEM_JAVA: str = "java"
ECOSYSTEM_NODE: str = "node"
ECOSYSTEM_OSV: str = "osv"

SUPPORTED_ECOSYSTEMS: tuple[str, ...] = (ECOSYSTEM_PYTHON, ECOSYSTEM_JAVA, ECOSYSTEM_NODE, ECOSYSTEM_OSV)

# Marker files used to auto-detect a project's ecosystem, checked in order.
# The generic "osv" ecosystem has no marker: it is the fallback when nothing matches.
ECOSYSTEM_MARKERS: dict[str, tuple[str, ...]] = {
    ECOSYSTEM_PYTHON: ("uv.lock",),
    ECOSYSTEM_JAVA: ("build.gradle", "build.gradle.kts", "pom.xml"),
    ECOSYSTEM_NODE: ("package-lock.json",),
}


@dataclass
class Vulnerability:
    """Represents a single known vulnerability affecting an installed package."""

    package: str
    installed_version: str
    vulnerability_id: str
    fix_versions: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def recommended_version(self) -> str:
        """Return the earliest known fixed version for this vulnerability.

        Parameters:
            None

        Raises:
            None

        Returns:
            str: The recommended version, or "unknown" if no fix is published yet.
        """
        return self.fix_versions[0] if self.fix_versions else "unknown"

    @property
    def advisory_url(self) -> str:
        """Return a link to the OSV advisory for this vulnerability.

        Parameters:
            None

        Raises:
            None

        Returns:
            str: The URL of the OSV advisory page.
        """
        return f"https://osv.dev/vulnerability/{self.vulnerability_id}"

    @property
    def severity(self) -> str:
        """Return the best-effort severity label for this vulnerability.

        pip-audit does not always expose a normalized severity score, so this
        returns a human-readable hint pointing at the advisory when a CVE
        alias is present.

        Parameters:
            None

        Raises:
            None

        Returns:
            str: A severity label, or "unknown" when nothing can be inferred.
        """
        if any(alias.upper().startswith("CVE-") for alias in self.aliases):
            return "See advisory (CVE-tracked)"
        return "unknown"


class DependencyAuditor(Protocol):
    """Protocol implemented by every ecosystem-specific dependency auditor."""

    def scan(self) -> list[Vulnerability]:
        """Run the audit and return the vulnerabilities found.

        Parameters:
            None

        Raises:
            None

        Returns:
            list[Vulnerability]: The vulnerabilities found by this auditor.
        """
        ...  # pragma: no cover - structural typing only


def export_requirements(output_path: str = REQUIREMENTS_EXPORT_PATH) -> str:
    """Export the locked dependencies from `uv.lock` to a requirements file for auditing.

    Parameters:
        output_path: Destination path for the exported requirements file.

    Raises:
        subprocess.SubprocessError: If `uv export` fails after all retries.

    Returns:
        str: The path to the exported requirements file.
    """
    cwd: str = f"uv export --no-hashes --format requirements-txt -o {output_path} 2>&1"
    run_operation(cwd, "Export locked dependencies for audit")
    return output_path


def parse_pip_audit_output(raw_output: str) -> list[Vulnerability]:
    """Parse the raw JSON produced by `pip-audit` into `Vulnerability` objects.

    Parameters:
        raw_output: The raw stdout content produced by `pip-audit --format json`.

    Raises:
        None

    Returns:
        list[Vulnerability]: One entry per (package, vulnerability) pair found. Empty if
            the output is empty or cannot be parsed as JSON.
    """
    vulnerabilities: list[Vulnerability] = []
    if not raw_output or not raw_output.strip():
        return vulnerabilities
    try:
        data: dict = json.loads(raw_output)
    except json.JSONDecodeError:
        ws_warning("Could not parse pip-audit output as JSON. Skipping vulnerability scan results.")
        return vulnerabilities
    dependencies: list[dict] = data.get("dependencies", [])
    for dependency in dependencies:
        package: str = dependency.get("name", "unknown")
        installed_version: str = dependency.get("version", "unknown")
        for vuln in dependency.get("vulns", []):
            vulnerabilities.append(
                Vulnerability(
                    package=package,
                    installed_version=installed_version,
                    vulnerability_id=vuln.get("id", "UNKNOWN"),
                    fix_versions=vuln.get("fix_versions", []),
                    aliases=vuln.get("aliases", []),
                    description=vuln.get("description", ""),
                )
            )
    ws_info(f"Found {len(vulnerabilities)} vulnerabilities across {len(dependencies)} dependencies.")
    return vulnerabilities


def run_pip_audit(requirements_path: str) -> list[Vulnerability]:
    """Run `pip-audit` against the given requirements file and parse its results.

    `pip-audit` exits with a non-zero status code when vulnerabilities are found,
    so the underlying command is executed without raising on failure.

    Parameters:
        requirements_path: Path to the requirements file to audit.

    Raises:
        None

    Returns:
        list[Vulnerability]: The vulnerabilities found in the given requirements file.
    """
    cwd: str = f"pip-audit -r {shlex.quote(requirements_path)} --format json --progress-spinner off"
    result = run_operation(cwd, "Audit dependencies with pip-audit", check=False)
    return parse_pip_audit_output(result.stdout)


def _extract_osv_fix_versions(vulnerability: dict) -> list[str]:
    """Extract the fixed versions referenced by an OSV-Scanner vulnerability entry.

    Parameters:
        vulnerability: A single vulnerability entry from OSV-Scanner's JSON output,
            following the OSV schema (`affected[].ranges[].events[].fixed`).

    Raises:
        None

    Returns:
        list[str]: The fixed versions found, in the order they appear.
    """
    fix_versions: list[str] = []
    for affected in vulnerability.get("affected", []):
        for value_range in affected.get("ranges", []):
            for event in value_range.get("events", []):
                fixed: Optional[str] = event.get("fixed")
                if fixed:
                    fix_versions.append(fixed)
    return fix_versions


def parse_osv_scanner_output(raw_output: str) -> list[Vulnerability]:
    """Parse the raw JSON produced by `osv-scanner` into `Vulnerability` objects.

    Parameters:
        raw_output: The raw stdout content produced by `osv-scanner --format json`.

    Raises:
        None

    Returns:
        list[Vulnerability]: One entry per (package, vulnerability) pair found. Empty if
            the output is empty or cannot be parsed as JSON.
    """
    vulnerabilities: list[Vulnerability] = []
    if not raw_output or not raw_output.strip():
        return vulnerabilities
    try:
        data: dict = json.loads(raw_output)
    except json.JSONDecodeError:
        ws_warning("Could not parse osv-scanner output as JSON. Skipping vulnerability scan results.")
        return vulnerabilities
    results: list[dict] = data.get("results", [])
    for result in results:
        for package_entry in result.get("packages", []):
            package_info: dict = package_entry.get("package", {})
            package: str = package_info.get("name", "unknown")
            installed_version: str = package_info.get("version", "unknown")
            for vuln in package_entry.get("vulnerabilities", []):
                vulnerabilities.append(
                    Vulnerability(
                        package=package,
                        installed_version=installed_version,
                        vulnerability_id=vuln.get("id", "UNKNOWN"),
                        fix_versions=_extract_osv_fix_versions(vuln),
                        aliases=vuln.get("aliases", []),
                        description=vuln.get("summary") or vuln.get("details", ""),
                    )
                )
    ws_info(f"Found {len(vulnerabilities)} vulnerabilities via osv-scanner.")
    return vulnerabilities


def run_osv_scanner(target: str = ".") -> list[Vulnerability]:
    """Run `osv-scanner` against the given target and parse its results.

    `osv-scanner` exits with a non-zero status code when vulnerabilities are found,
    so the underlying command is executed without raising on failure.

    Parameters:
        target: Path to the project root to scan recursively.

    Raises:
        None

    Returns:
        list[Vulnerability]: The vulnerabilities found under the given target.
    """
    cwd: str = f"osv-scanner --format json --recursive {shlex.quote(target)}"
    result = run_operation(cwd, "Audit dependencies with osv-scanner", check=False)
    return parse_osv_scanner_output(result.stdout)


@dataclass
class PipAuditAuditor:
    """Audits Python/uv projects by exporting `uv.lock` and running `pip-audit`."""

    requirements_output_path: str = REQUIREMENTS_EXPORT_PATH

    def scan(self) -> list[Vulnerability]:
        """Export the locked Python dependencies and audit them with `pip-audit`.

        Parameters:
            None

        Raises:
            subprocess.SubprocessError: If exporting the locked dependencies fails.

        Returns:
            list[Vulnerability]: The vulnerabilities found in the project's locked dependencies.
        """
        requirements_path: str = export_requirements(self.requirements_output_path)
        return run_pip_audit(requirements_path)


@dataclass
class OsvScannerAuditor:
    """Audits any ecosystem supported by OSV-Scanner (Java/Gradle/Maven, Node, ...)."""

    target: str = "."

    def scan(self) -> list[Vulnerability]:
        """Audit the target project tree with `osv-scanner`.

        Parameters:
            None

        Raises:
            None

        Returns:
            list[Vulnerability]: The vulnerabilities found under the target project tree.
        """
        return run_osv_scanner(self.target)


def detect_ecosystem(project_root: str = ".") -> str:
    """Detect a project's ecosystem by looking for well-known lockfile/build markers.

    Parameters:
        project_root: The directory to inspect for ecosystem marker files.

    Raises:
        None

    Returns:
        str: One of `SUPPORTED_ECOSYSTEMS`. Falls back to `ECOSYSTEM_OSV` when no
            known marker file is found, so OSV-Scanner is used as a generic default.
    """
    root: Path = Path(project_root)
    for ecosystem, markers in ECOSYSTEM_MARKERS.items():
        if any((root / marker).exists() for marker in markers):
            return ecosystem
    ws_warning("No ecosystem marker found. Falling back to generic OSV scan (this may be a full recursive scan of the current directory).")
    return ECOSYSTEM_OSV


def get_auditor(ecosystem: Optional[str] = None, project_root: str = ".") -> DependencyAuditor:
    """Resolve the `DependencyAuditor` to use for the given (or detected) ecosystem.

    Parameters:
        ecosystem: An explicit ecosystem override (one of `SUPPORTED_ECOSYSTEMS`). When
            None, the ecosystem is auto-detected from `project_root`.
        project_root: The directory to inspect for ecosystem markers and to scan.

    Raises:
        ValueError: If `ecosystem` is provided but not one of `SUPPORTED_ECOSYSTEMS`.

    Returns:
        DependencyAuditor: `PipAuditAuditor` for the Python ecosystem, `OsvScannerAuditor`
            for every other (Java, Node, or generic OSV) ecosystem.
    """
    resolved: str = ecosystem or detect_ecosystem(project_root)
    if resolved not in SUPPORTED_ECOSYSTEMS:
        raise ValueError(f"Unsupported ecosystem '{resolved}'. Expected one of: {', '.join(SUPPORTED_ECOSYSTEMS)}.")
    if resolved == ECOSYSTEM_PYTHON:
        return PipAuditAuditor()
    return OsvScannerAuditor(target=project_root)


def scan_dependencies(ecosystem: Optional[str] = None, project_root: str = ".") -> list[Vulnerability]:
    """Run the full dependency audit pipeline for the detected or given ecosystem.

    Parameters:
        ecosystem: An explicit ecosystem override (one of `SUPPORTED_ECOSYSTEMS`). When
            None, the ecosystem is auto-detected from `project_root`.
        project_root: The directory to inspect for ecosystem markers and to scan.

    Raises:
        ValueError: If `ecosystem` is provided but not one of `SUPPORTED_ECOSYSTEMS`.
        subprocess.SubprocessError: If the underlying auditor's export/scan step fails.

    Returns:
        list[Vulnerability]: The vulnerabilities found in the project's dependencies.
    """
    auditor: DependencyAuditor = get_auditor(ecosystem, project_root)
    return auditor.scan()
