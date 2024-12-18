""" This module contains the parse_json_logs function that parses logs from a JSON file and writes them to .log files """

import json
from pathlib import Path
from py.util.props import AppProperties
from py.util.formatting import ws_advice, ws_warning, ws_success


def parse_json_logs() -> None:
    """
    Parse logs from a JSON file and write them to .log files in the logs/parsed directory
    """

    log_path = Path(f"{AppProperties.get_instance().retrieve_property("working_path")}/logs/parsed")

    # Delete all .log files in log_path
    if log_path.exists():
        for log_file in log_path.glob("*.log"):
            log_file.unlink()
       
    for json_file in log_path.glob("*.json"):
        if not log_path.exists():
            ws_warning(f"directory {log_path} not found")
            log_path.mkdir(parents=True, exist_ok=True)
            ws_advice(f"The directory {log_path} has been created")

        if not json_file.exists():
            ws_warning(f"file {json_file} not found")
            raise FileNotFoundError("The input JSON file does not exist")

        with open(json_file, "r", encoding="utf-8") as f:
            records = json.load(f)

        sorted_records = sorted(records, key=lambda x: x["timestamp"])

        for record in sorted_records:
            log_name = record["logName"].split("/")[-1]
            log_file_path = log_path / f"{log_name}.log"
            text_payload = record["textPayload"]

            with open(log_file_path, "a", encoding="utf-8") as l_file:
                l_file.write(text_payload + "\n")

    ws_success("Logs have been parsed successfully")
