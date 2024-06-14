#!/bin/bash

WS_TEMP="$1"
LOG_PATH="$WS_TEMP/logs/parsed"
mkdir -p "$LOG_PATH"

# copilot, delete all .log files in $LOG_PATH please
find "$LOG_PATH" -type f -name "*.log" -delete

# Input JSON file
JSON_FILE="$LOG_PATH/input.json"

if [[ ! -f "$JSON_FILE" ]]; then
    ws_warning "file $JSON_FILE not found"
    ws_error "The input JSON file does not exist"
    return 1
fi

# Parse and sort the JSON array by timestamp
sorted_json=$(jq -c 'sort_by(.timestamp)[]' "$JSON_FILE")

# Loop through each record in the sorted JSON array
echo "$sorted_json" | while read -r record; do
    # Extract logName and textPayload from the current record
    logName=$(echo "$record" | jq -r '.logName' | grep -Eo '[^/]+$')
    if [[ $? -ne 0 ]]; then
        echo "Failed to parse JSON file with jq"
        echo "$record"
    fi
    logName="$LOG_PATH/$logName.log"
    textPayload=$(echo "$record" | jq -r '.textPayload')
    if [[ $? -ne 0 ]]; then
        echo "Failed to parse JSON file with jq"
        echo "$record"
    fi
    # Check if the log file exists, if not, create it
    if [[ ! -f "$logName" ]]; then
        touch "$logName"
    fi

    # Print textPayload to the log file
    echo "$textPayload" >> "$logName"
done
