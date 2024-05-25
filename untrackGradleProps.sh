untrackProperties(){
    local PROP_FILE='gradle.properties'
    if [ -f "$PROP_FILE" ]; then
        local UNTRACKED_FILE=$(git ls-files -v | grep -Ec "H\s+$PROP_FILE")
        if [ "$UNTRACKED_FILE" -eq 1 ]; then
            ws_info "untracking $PROP_FILE"
            git update-index --assume-unchanged $PROP_FILE
        fi
    fi
    local EXCLUDE=".git/info/exclude"
    local FOLDER=${WS_TEMP#./}
    local UNTRACKED_FOLDER=$(cat "$EXCLUDE" | grep -Ec "^$FOLDER" || true)
    if [ "$UNTRACKED_FOLDER" -lt 1 ]; then
        ws_info "untracking $FOLDER"
        echo "\n$FOLDER/"  >> "$EXCLUDE"
    fi
}