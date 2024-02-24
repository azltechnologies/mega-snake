untrackProperties(){
    local PROP_FILE='gradle.properties'
    if [ -f "$PROP_FILE" ]; then
        local UNTRACKED_FILE=$(git ls-files -v | grep -Ec "H\s+$PROP_FILE")
        if [ "$UNTRACKED_FILE" -eq 1 ]; then
            echo "untracking $PROP_FILE"
            git update-index --assume-unchanged $PROP_FILE
        fi
    fi
    if [ ! -d "$WS_TEMP" ]; then
        mkdir -p "$WS_TEMP"
    fi
    local EXCLUDE=".git/info/exclude"
    local UNTRACKED_FOLDER=$(cat "$EXCLUDE" | grep -Ec '^$WS_TEMP' || true)
    if [ "$UNTRACKED_FOLDER" -lt 1 ]; then
        local FOLDER=${WS_TEMP#./}
        echo "untracking $FOLDER"
        echo "\n$FOLDER/"  >> "$EXCLUDE"
    fi
}