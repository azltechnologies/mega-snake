untrackProperties() {
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
        echo "\n$FOLDER/" >>"$EXCLUDE"
    fi
    local UNTRACKED_WKSPC=$(cat "$EXCLUDE" | grep -Ec "^.+\.code-workspace" || true)
    if [ "$UNTRACKED_WKSPC" -lt 1 ]; then
        ws_info "untracking $FOLDER"
        echo "\n*.code-workspace"  >> "$EXCLUDE"
    fi
    # Search for the first file with extension .code-workspace in the current folder
    local REPO_NAME=$(basename -s .git $(git remote get-url origin))
    if [ ! -z "$REPO_NAME" ]; then
        ws_info "origin name: $REPO_NAME"
        local WORKSPACE=$(find . -maxdepth 1 -type f -name "*.code-workspace" | head -n 1)
        if [ ! -f "$WORKSPACE" ]; then
            local WORKSPACE="$REPO_NAME.code-workspace"
            ws_warning "creating $WORKSPACE"
            echo "{\"folders\": [ { \"path\": \".\", \"name\": \"main\" } ], \"settings\":{}}" >"$WORKSPACE"
        fi
        local VERIFY_BLAME=$(jq 'has("settings") and (.settings | has("git-blame.gitWebUrl"))' "$WORKSPACE")
        if [ $? -ne 0 ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        if [[ $VERIFY_BLAME != "true" ]]; then
            local NEW_VALUE="https://github.com/one-thd/$REPO_NAME/tree/\$ID"
            # Update the setting
            local JSON_OBJ=$(jq --arg value "$NEW_VALUE" '.settings."git-blame.gitWebUrl" = "\($value)"' "$WORKSPACE")
            if [ $? -ne 0 ]; then
                ws_error "\njq parsing error\n"
                return 1
            fi
            if [ ! -z "$JSON_OBJ" ]; then
                ws_info "updating .settings.\"git-blame.gitWebUrl\" in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi
    fi
}
