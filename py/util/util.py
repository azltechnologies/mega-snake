"""
This module contains utility functions for common operations.
"""

import subprocess
import time
from py.util.formatting import ws_info, ws_success, ws_advice, ws_warning, ws_error

def run_operation(cwd: str, description: str) -> subprocess.CompletedProcess[str]:
    """
    Runs the given command and retries on failure up to 3 times.

    Args:
        cwd: str
        description: str
    
    Returns:
        subprocess.CompletedProcess[str]
    """
    num_retries = 3
    for attempt in range(1, num_retries + 1):
        try:
            ws_info(f"Running: {cwd}")
            result = subprocess.run(cwd, shell=True, check=True, capture_output=True, text=True)
            ws_success(f"{description} successfully on attempt {attempt}!")
            ws_advice(f"stdout: {result.stdout}")
            break  # Exit the loop on successful push
        except subprocess.CalledProcessError as error:
            ws_warning(f"{description} failed on attempt {attempt}. Error: {error.stdout}")
            ws_warning(f"Error details: {error.stderr}")
            if attempt == num_retries:
                ws_error(
                    f"{description} failed after {num_retries} attempts. Giving up.",
                    error
                )
            else:
                ws_warning(f'Retrying {description} in 2 seconds...')
                time.sleep(2)  # Wait 2 seconds before retrying
        except Exception as e:
            ws_error(
                "Error creating diff tree",
                e
            )
    return result
