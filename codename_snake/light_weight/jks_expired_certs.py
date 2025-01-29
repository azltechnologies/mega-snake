"""Check for expired certificates in a Java KeyStore (JKS) file."""

from typing import Optional
from datetime import datetime
import shutil
import click
from codename_snake.util.formatting import ws_advice, ws_info, Color, ws_warning, ws_tip
from codename_snake.util.util import run_operation, get_command_return_code


@click.command(
    name="expiredCertsJks",
    short_help="Check for expired certificates in a JKS file",
    help="Analyze certificates in a Java KeyStore (JKS) file and report their validity status",
    epilog="""
    Usage: snake expiredCertsJks JKS_PATH [--password PASSWORD]

    Examples:
      snake expiredCertsJks /path/to/keystore.jks
      snake expiredCertsJks /path/to/keystore.jks --password mypassword
    Options:
        --password, -p: Custom password for the JKS file (default: changeit)
    """,
)
@click.argument("jks_path", type=click.Path(exists=True))
@click.option("--password", "-p", help="Custom password for the JKS file", required=True, default="changeit")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def expired_certs(jks_path: str, password: str, verbose: bool) -> None:
    """Check for expired certificates in a Java KeyStore (JKS) file."""

    # Verify keytool is available
    if not shutil.which("keytool"):
        raise RuntimeError("keytool could not be found. Please ensure Java is installed and keytool is in your PATH.")

    # Use default password if none provided
    ws_advice(f"JKS_PATH: {jks_path}")
    ws_advice(f"JKS_PASS: {password}")

    # Validate keytool parameters
    list_cmd: str = f"keytool -v -list -keystore '{jks_path}' -storepass '{password}'"
    if get_command_return_code(list_cmd) != 0:
        raise RuntimeError("keytool command failed on implementing parameters.")
    ws_info("Validation of parameters in keytool command succeeded.")

    # Get all aliases
    try:
        result = run_operation(list_cmd, "Checking certificates in JKS file").stdout.strip()

        # Parse aliases from output
        aliases = []
        for line in result.split("\n"):
            if "Alias name:" in line:
                aliases.append(line.split("Alias name:")[1].strip())

        for alias in aliases:
            ws_advice(f"Checking alias: {alias}")

            # Get certificate details
            cert_details = run_operation(
                f"keytool -list -v -keystore '{jks_path}' -storepass '{password}' -alias '{alias}'", f"Checking certificate details for alias {alias}"
            ).stdout.strip()

            # Parse dates
            valid_from: Optional[datetime] = None
            valid_until: Optional[datetime] = None
            for line in cert_details.split("\n"):
                if "Valid from:" in line:
                    date_str = line.split("until:")
                    valid_from = datetime.strptime(date_str[0].replace("Valid from:", "").strip(), "%a %b %d %H:%M:%S %Z %Y")
                    valid_until = datetime.strptime(date_str[1].strip(), "%a %b %d %H:%M:%S %Z %Y")

            color_dict: dict[Color, str]
            if not valid_from or not valid_until:
                ws_warning(f"Certificate with alias {alias} has no valid date information.")
                continue
            if valid_from <= datetime.now() <= valid_until:
                color_dict = {
                    Color.GREEN: f"Certificate with alias {Color.RED.value}{alias}{Color.GREEN.value} is valid until: ",
                    Color.YELLOW: str(valid_until),
                }
                ws_tip(color_dict)
            else:
                ws_warning(f"Certificate with alias {Color.BLUE.value}{alias}{Color.YELLOW.value} is expired since {Color.RED.value}{valid_until}")
                certificate_info = run_operation(f"{list_cmd} -alias {alias}", "Getting certificate info").stdout.strip()
                if verbose:
                    color_dict = {Color.RED: certificate_info}
                    ws_tip(color_dict)
                ws_advice("delete current certificate and add a new one. Please run the following commands:")
                ws_advice(f"   keytool -delete -alias {alias} -keystore {jks_path} -storepass {password}")
                ws_advice(f"   keytool -import -alias {alias} -file <CERTIFICATE_FILE> -keystore {jks_path} -storepass {password}")

    except Exception as e:
        ws_warning(f"Error processing certificates: {str(e)}")
        raise RuntimeError("Failed to process certificates") from e
