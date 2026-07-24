"""
This module scans the project's locked dependencies for known vulnerabilities.

It exports the `uv.lock` file to a `requirements.txt` file and runs `pip-audit`
against it, parsing the JSON output into a list of `Vulnerability` objects.
"""

import json
from dataclasses import dataclass, field
from mega_snake.util.util import run_operation
from mega_snake.util.formatting import ws_info, ws_warning

REQUIREMENTS_EXPORT_PATH: str = "workspace_temp/dependency-audit-requirements.txt"


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
    cwd: str = f"pip-audit -r {requirements_path} --format json --progress-spinner off 2>&1"
    result = run_operation(cwd, "Audit dependencies with pip-audit", check=False)
    return parse_pip_audit_output(result.stdout)


def scan_dependencies() -> list[Vulnerability]:
    """Run the full dependency audit pipeline: export, audit, and parse.

    Parameters:
        None

    Raises:
        subprocess.SubprocessError: If exporting the locked dependencies fails.

    Returns:
        list[Vulnerability]: The vulnerabilities found in the project's locked dependencies.
    """
    requirements_path: str = export_requirements()
    return run_pip_audit(requirements_path)
