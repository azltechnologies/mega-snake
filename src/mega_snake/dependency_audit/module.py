"""Contains the dependency-audit command group: scans dependencies and files GitHub issues for findings."""

from typing import Optional

import click

from mega_snake.util.util import cli_metadata, wrapper_decorator
from mega_snake.util.cli_group import CliGroup
from mega_snake.util.formatting import ws_info, ws_success
from mega_snake.dependency_audit.scanner import scan_dependencies, Vulnerability, SUPPORTED_ECOSYSTEMS
from mega_snake.dependency_audit.issue_manager import report_vulnerabilities


@click.group(cls=CliGroup)
def main() -> None:
    """dependency audit related commands"""


@cli_metadata(flags={"skip"})
def wrapper(_ctx: click.Context, *_args, **_kwargs) -> None:
    """Wrapper for the dependency_audit command.

    Parameters:
        _ctx: The click context.

    Raises:
        None

    Returns:
        None
    """


# Export the decorated wrapper for use in other modules
add_wrapper = wrapper_decorator(wrapper)


@click.command(
    name="scan-dependencies",
    short_help="Scans dependencies for vulnerabilities and files GitHub issues for new findings.",
    help="""Scans the project's locked dependencies for known vulnerabilities against the OSV
    advisory database, then files a GitHub issue for each new finding (package, installed
    version, recommended version, severity and advisory link), skipping findings that were
    already reported. The ecosystem (Python/uv, Java/Gradle/Maven, Node, or a generic
    OSV-Scanner audit) is auto-detected from the project's lockfiles, or can be forced with
    `--ecosystem`.""",
    epilog=f"""
    usage: mgsnake scan-dependencies [OPTIONS]\n
    OPTIONS:\n
        --dry-run: scan and print findings without creating GitHub issues.\n
        --ecosystem: force the ecosystem/auditor instead of auto-detecting it.
            One of: {", ".join(SUPPORTED_ECOSYSTEMS)}.
    """,
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Scan and print findings without creating GitHub issues.",
)
@click.option(
    "--ecosystem",
    type=click.Choice(SUPPORTED_ECOSYSTEMS),
    default=None,
    help="Force the ecosystem/auditor instead of auto-detecting it from the project's lockfiles.",
)
def scan_dependencies_command(dry_run: bool, ecosystem: Optional[str]) -> None:
    """Scan the project's dependencies and report vulnerabilities as GitHub issues.

    Parameters:
        dry_run: When True, findings are printed but no GitHub issues are created.
        ecosystem: When given, overrides ecosystem auto-detection with this value.

    Raises:
        None

    Returns:
        None
    """
    ws_info("Scanning project dependencies for known vulnerabilities...")
    vulnerabilities: list[Vulnerability] = scan_dependencies(ecosystem=ecosystem)
    if not vulnerabilities:
        ws_success("No known vulnerabilities found.")
        return
    if dry_run:
        for vulnerability in vulnerabilities:
            ws_info(f"{vulnerability.package}=={vulnerability.installed_version} - {vulnerability.vulnerability_id}")
        return
    created: int = report_vulnerabilities(vulnerabilities)
    ws_success(f"Dependency audit complete. {created} new issue(s) created out of {len(vulnerabilities)} finding(s).")


main.add_command_with_alias(scan_dependencies_command, ["sdep", "audit"])
