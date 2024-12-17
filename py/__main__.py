""" Sets the environment configuration """

from typing import Callable, Optional
import os
import click
from .branch_cleanup.module import main as branch_cleanup
from .config_environment.module import echo as msg, create_graphql_schema as graphql_schema, gcloud_login_env, set_java_version as java, set_gradle_version as gradle
from .constants import MSG_OPT, REMOTE_BRANCHES_OPT, LOGGING_OPT, SHELL_OPT, RELEASE_TYPE_OPT, GCLOUD_LOGGIN_OPT
from .util.formatting import get_traceback
from .util.props import init_app_properties
from .diff_tree.module import main as diff_tree
from .remote_branches.module import main as remote_branches
from .util.formatting import WorkspaceError, ws_advice, ws_success, ws_info, ws_warning
from .create_release.module import main as create_release


def cli_metadata(**metadata) -> Callable:
    """
    Decorator to add custom metadata to a command
    """

    def decorator(f) -> Callable:
        if not hasattr(f, "metadata"):
            f.flags = {}
        f.flags.update(metadata)
        return f

    return decorator


@click.group(
    help="Python CLI tool to prepare the environment for a vscode workspace and ",
    epilog="requires ...",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.option("--log-level", "-l", type=click.Choice(list(LOGGING_OPT), False), default="INFO", help="log level")
@click.option("--shell", type=click.Choice(SHELL_OPT, False), required=True, hidden=True)
@click.option("--skip-initilization", "-s", is_flag=True, help="Skip initialization in those commands that support it")
@click.pass_context
def cli(ctx: click.Context, log_level: str, shell: str, skip_initilization: bool) -> None:
    """cli entry point"""
    try:
        cmd_name = ctx.invoked_subcommand
        if cmd_name:
            ws_advice(f"Invoking subcommand: {cmd_name}")
            if skip_initilization:
                # Access params
                cmd = cli.get_command(ctx, cmd_name)
                if not cmd:
                    raise click.ClickException(f"Command '{cmd_name}' not found")
                # check if the command has cli_metadata
                metadata = getattr(cmd.callback, "flags", {})
                flags: Optional[set[str]] = metadata.get("flags")
                if flags and "skip" in flags:
                    ws_info("'skip' flag detected. Skipping initialization.")
                    return
                ws_warning("'skip' flag detected but not supported by the invoked command. \n Proceeding with initialization.")
        init_app_properties(log_level, shell)
    except Exception as e:
        print(f"Error during initialization: {e}")
        print(get_traceback(e))
        raise SystemExit(e) from e


@cli.result_callback()
@click.pass_context
def post_command(ctx, result, **kwargs) -> None:
    """Post-command execution logic"""
    if ctx.invoked_subcommand:
        ws_advice(f"Command '{ctx.invoked_subcommand}' completed successfully with result: {result} and kwargs: { kwargs}")


@cli.command(
    name="createDiffTree",
    short_help="Creates diff tree and commit list of current changes",
    help="Creates a diff tree of changes and a commit list of the current branch against master or a specified commit hash",
    epilog="the directory tree and commit list are created within $WS_TEMP path.",
)
@click.option("--commit-hash", "-c", type=click.STRING, default=None, help="Commit hash to compare against instead of master")
def create_diff_tree(commit_hash: str) -> None:
    """
    calls the diff_tree module:

    Args:
        commit_hash: str | None
    """
    diff_tree(commit_hash)


@cli.command(
    name="remoteBranchesDetails",
    short_help="Gets details of remote branches",
    help="Creates a detailed list of remote branches filtered by type",
    epilog="the branch details are created within $WS_TEMP path.",
)
@click.option(
    "--filter-by",
    "-f",
    type=click.Choice(REMOTE_BRANCHES_OPT, False),
    help="""filter branches by merge status against main branch:\n
    'M' - merged branches\n
    'U' - unmerged branches\n
    'A' - all branches (default)\n""",
    default="A",
)
def remote_branches_details(filter_by: str) -> None:
    """
    calls the remote_branches module:

    Args:
        filter_by: str | "A"
    """
    remote_branches(filter_by)


@cli.command(
    name="remoteBranchesCleanUp",
    short_help="Helper function for deleting branches merged branches from the remote repository.",
    help="Iterates over the remote branches asking the user which merged branches to delete",
    epilog="Requires user input to delete branches",
)
def remote_branches_clean_up() -> None:
    """
    calls the branch_cleanup module
    """
    branch_cleanup()


@cli.command(
    name="msg",
    short_help="Prints message to the console and logs it.",
    help="Prints a message to the console in a custom format and logs it into the workspace configuration log file.",
    epilog="""
    usage: set_env msg <message> [OPTIONS]   <type>\n
    OPTIONS:\n
        epilog: an optional ending message as a second argument\n
        type:
            usage: [-t | --type] <type>\n
            allowed values:\n
                S | I | W | E | A | T
                    S - Success
                    I - Information -- default
                    W - Warning
                    E - Error
                    A - Advice -- use for Debugging
                    T - Tip
    """,
)
@click.argument("message", type=click.STRING)
@click.argument("epilog", type=click.STRING, required=False, default=None)
@click.option(
    "--type-msg",
    "-t",
    type=click.Choice(list(MSG_OPT.keys()), False),
    help="""The type of message to be printed:\n
        'S' - Success\n
        'I' - Information -- default\n
        'W' - Warning\n
        'E' - Error\n
        'A' - Advice -- use for Debugging\n
        'T' - Tip\n
     """,
    default="I",
)
def echo(message: str, epilog: Optional[str], type_msg: str) -> None:
    """
    Calls the echo function from the config_environment module

    Args:
        message: str
        epilog: str
        type_msg: str
    """
    msg(message, epilog, type_msg)


@cli.command(
    name="createGraphqlSchema",
    short_help="Creates a GraphQL schema file in the working directory.",
    help="Creates a GraphQL schema file in the working directory.",
    epilog="usage: set_env createGraphqlSchema <schema_path>",
)
@click.argument("schema_path", type=click.STRING)
def create_graphql_schema(schema_path: str) -> None:
    """
    Calls the create_graphql_schema function from the config_environment module

    Args:
        schema_path: str
    """
    graphql_schema(schema_path)


@cli.command(
    name="createRelease",
    short_help="Creates a new release on GitHub with the given parameters.",
    help="Creates a new release on GitHub with the given parameters.",
    epilog="""
    usage: set_env createRelease <tag_suffix> <release_type> <release_notes> <release_branch>\n
    Args:\n
        tag_suffix: str - suffix to add to the tag\n
        release_type: int -\n
            1: --prerelease\n
            2: --latest=false\n
            3: --latest\n
        notes: Optional[str] - release notes
    """,
)
@click.argument("tag_suffix", type=click.STRING, required=True)
@click.option(
    "--release-type",
    "-r",
    type=click.Choice(list(RELEASE_TYPE_OPT.keys()), False),
    required=True,
    help="""Release type:\n
        'p' - --prerelease\n
        'r' - --latest=false\n
        'l' - --latest\n""",
)
@click.option("--notes", "-n", type=click.STRING, required=False, default=None)
@click.option("--branch", "-b", type=click.STRING, required=False, default=None)
def create_release_github(tag_suffix: str, release_type: str, notes: Optional[str], branch: Optional[str]) -> None:
    """
    Calls the create_release function from the create_release module

    Args:
        tag_suffix: str
        release_type: str
        notes: Optional[str]
        branch: str
    """
    create_release(tag_suffix, release_type, notes, branch)


@cli.command(
    name="gcloudLogin",
    short_help="Logs into gcloud — [supports skip mode]",
    help="Logs into gcloud and sets the project — [supports skip mode]",
    epilog="""
             usage: set_env Login [OPTIONS] [project]\n
                args:\n
                    project: Optional[str] - project name\n
                    type-login: str - login type\n
                        allowed values:\n
                            'A' - Application Default\n
                            'U' - User Account\n
                            'B' - Both\n
             """,
)
@click.argument("type-login", type=click.Choice(list(GCLOUD_LOGGIN_OPT.keys()), False), required=True)
@click.argument("project", type=click.STRING, required=False, default=None)
@cli_metadata(flags={"skip"})
def gcloud_login_click(project: Optional[str], type_login: str) -> None:
    """
    Calls the gcloud_login function from the config_environment module

    Args:
        project: Optional[str]
        type_login: str
    """
    gcloud_login_env(project, type_login)


@cli.command(
    name="gcloudLogout",
    short_help="Logs out of gcloud — [supports skip mode]",
    help="Logs out of gcloud — [supports skip mode]",
    epilog="usage: set_env Logout",
)
@cli_metadata(flags={"skip"})
def gcloud_logout() -> None:
    """
    Logs out of gcloud
    """
    os.system("gcloud auth revoke 2>/dev/null")
    ws_success("gcloud account is now logged out.")
    os.system("gcloud auth application-default revoke 2>/dev/null")
    ws_success("gcloud application-default credentials are now revoked.")

@cli.command(
    name="setJavaVersion",
    short_help="Sets the default Java version on the workspace",
    help="Sets the default Java version on the workspace",
    epilog="""usage: set_env setJavaVersion [OPTIONS]\n
    OPTIONS:\n
        -o | --override: Optional[bool] - Override the current Java version\n
    """
)
@click.option("--override", "-o", is_flag=True, help="Override the current Java version")
def set_java_version(override: bool) -> None:
    """
    Calls the set_java function from the config_environment module

    Args:
        override: bool
    """
    java(override)

@cli.command(
    name="setGradleVersion",
    short_help="Sets the default Gradle version on the workspace",
    help="Sets the default Gradle version on the workspace",
    epilog="""usage: set_env setGradleVersion [OPTIONS]\n
    OPTIONS:\n
        -o | --override: Optional[bool] - Override the current Gradle version\n
    """
)
@click.option("--override", "-o", is_flag=True, help="Override the current Gradle version")
def set_gradle_version(override: bool) -> None:
    """
    Calls the set_gradle function from the config_environment module

    Args:
        override: bool
    """
    gradle(override)

if __name__ == "__main__":
    try:
        cli.main(prog_name="set_env")
    except Exception as e:
        raise WorkspaceError("Error during cli execution", e) from e
