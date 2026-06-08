"""Commands to configure Maven tooling for pom.xml-based projects."""

import json
import os
import re
import shutil
from typing import Any, Optional

import click
import jq

from mega_snake.config_environment.models.tools_version import OS, OS_MAP, ToolVersion, set_version_local_config
from mega_snake.config_environment.util import get_local_file, update_workspace
from mega_snake.util.formatting import ws_info, ws_success, ws_warning
from mega_snake.util.props import get_property
from mega_snake.util.util import load_json_with_comments, run_operation

MAVEN_ENV_VAR = "M2_HOME"
ENV_VARIABLE = f"terminal.integrated.env.{OS_MAP[OS]}"
MAVEN_HOME_QUERY = f'.settings["{ENV_VARIABLE}"].{MAVEN_ENV_VAR}'
MAVEN_EXEC_QUERY = '.settings["maven.executable.path"]'


@click.command(
    name="set-maven",
    short_help="Sets Maven home and executable in workspace and local shell config",
    help="Detects Maven installation (or uses --maven-home) and sets Maven paths for VS Code and local shell config.",
    epilog="""usage: mgsnake set-maven [OPTIONS]\n
    OPTIONS:\n
        -m | --maven-home: Optional[str] - Explicit Maven home path (for example /opt/apache-maven-3.9.8)\n
    """,
)
@click.option("--maven-home", "-m", type=click.STRING, default=None, help="Explicit Maven home directory")
def set_maven_version(maven_home: Optional[str]) -> None:
    """Configure Maven paths for the current workspace."""
    workspace_file: str = get_property("workspace_file")
    working_path: str = get_property("working_path")
    local_file = get_local_file()
    shell = get_property("shell")
    _execute_set_maven(workspace_file, working_path, local_file, shell, maven_home)


@click.command(
    name="maven-project-setup",
    short_help="Creates recommended VS Code tasks for Maven projects",
    help="Creates or updates .vscode/tasks.json with common Maven development tasks when pom.xml is present.",
    epilog="""usage: mgsnake maven-project-setup [OPTIONS]\n
    OPTIONS:\n
        -o | --override: bool - Replace existing .vscode/tasks.json content\n
    """,
)
@click.option("--override", "-o", is_flag=True, help="Replace existing .vscode/tasks.json")
def maven_project_setup(override: bool) -> None:
    """Create VS Code Maven task definitions for local development."""
    pom_path = os.path.join(os.getcwd(), "pom.xml")
    if not os.path.exists(pom_path):
        raise FileNotFoundError("pom.xml file not found in the current directory.")
    vscode_path = os.path.join(os.getcwd(), ".vscode")
    os.makedirs(vscode_path, exist_ok=True)
    tasks_path = os.path.join(vscode_path, "tasks.json")
    if os.path.exists(tasks_path) and not override:
        ws_info(f"VS Code Maven task file already exists at {tasks_path}. Use --override to replace it.")
        return
    tasks = {
        "version": "2.0.0",
        "tasks": [
            {"label": "maven: clean install", "type": "shell", "command": "mvn clean install"},
            {"label": "maven: test", "type": "shell", "command": "mvn test"},
            {"label": "maven: verify", "type": "shell", "command": "mvn verify"},
            {"label": "maven: dependency tree", "type": "shell", "command": "mvn dependency:tree"},
            {"label": "maven: spring boot run", "type": "shell", "command": "mvn spring-boot:run"},
        ],
    }
    with open(tasks_path, "w", encoding="utf-8") as file:
        json.dump(tasks, file, indent=2)
    ws_success(f"Maven VS Code tasks file generated at {tasks_path}")


def _execute_set_maven(
    workspace_file: str, working_path: str, local_file: str, shell: str, maven_home: Optional[str]
) -> None:
    """Resolve and apply Maven paths for workspace and local shell config."""
    resolved_maven_home = maven_home if maven_home else _detect_maven_home()
    if not resolved_maven_home:
        ws_warning("Unable to detect Maven home. Use --maven-home to provide it explicitly.")
        return
    if not os.path.isdir(resolved_maven_home):
        raise NotADirectoryError(f"Maven home is not a valid directory: {resolved_maven_home}")
    mvn_executable = "mvn.cmd" if OS == "Windows" else "mvn"
    executable_path = os.path.join(resolved_maven_home, "bin", mvn_executable).replace("\\", "/")
    json_data: Any = load_json_with_comments(workspace_file)
    json_data = jq.compile(f"{MAVEN_HOME_QUERY} = {json.dumps(resolved_maven_home)}").input(json_data).first()
    json_data = jq.compile(f"{MAVEN_EXEC_QUERY} = {json.dumps(executable_path)}").input(json_data).first()
    temp_file = f"{working_path}/maven_settings.json"
    update_workspace(json_data, temp_file, workspace_file)
    version = ToolVersion(version="detected", _path=resolved_maven_home, default=True)
    set_version_local_config(version, local_file, shell, MAVEN_ENV_VAR)
    ws_success(f"Maven home set to {resolved_maven_home}")


def _detect_maven_home() -> Optional[str]:
    """Detect Maven home from `mvn -v` output or from PATH."""
    if not (mvn_path := shutil.which("mvn")):
        return None
    output = run_operation("mvn -v", "Getting Maven details", check=False).stdout.strip()
    if output:
        if match := re.search(r"^Maven home:\s*(.+)$", output, re.MULTILINE):
            return match.group(1).strip().replace("\\", "/")
    return os.path.dirname(os.path.dirname(mvn_path)).replace("\\", "/")
