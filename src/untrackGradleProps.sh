untrackProperties() {
    local PROP_FILE='gradle.properties'
    if [ -f "$PROP_FILE" ]; then
        local UNTRACKED_FILE=$(git ls-files -v | grep -Ec "H\s+$PROP_FILE")
        if [ "$UNTRACKED_FILE" -eq 1 ]; then
            ws_info "untracking $PROP_FILE"
            git update-index --assume-unchanged $PROP_FILE
        fi
    fi
    local JAVA_FORMATTER_FILE='./.vscode/java-formatter.xml'
    if [ ! -f "$JAVA_FORMATTER_FILE" ]; then
        ws_warning "creating $JAVA_FORMATTER_FILE"
        cp "$WS_CONFIG_HOME/src/resources/java-formatter.xml" "$JAVA_FORMATTER_FILE"
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
        ws_info "untracking code-workspace file"
        echo "\n*.code-workspace" >>"$EXCLUDE"
    fi
    local UNTRACKED_WKSPC=$(cat "$EXCLUDE" | grep -Ec "^\.vscode" || true)
    if [ "$UNTRACKED_WKSPC" -lt 1 ]; then
        ws_info "untracking .vscode folder"
        echo "\n.vscode/" >>"$EXCLUDE"
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
        # Remove trailing commas to sanitize the JSON
        local CONTENT=$(cat "$WORKSPACE" | perl -0777 -pe 's/,(\s*[\}\]\\])/$1/mg')
        echo "$CONTENT" >"$WORKSPACE"
        # check if git-blame.gitWebUrl exists
        local VERIFY_BLAME=$(echo "$CONTENT" | jq 'has("settings") and (.settings | has("git-blame.gitWebUrl"))')
        if [ $? -ne 0 ] | [ -z "$VERIFY_BLAME" ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        # If git-blame.gitWebUrl does not exist, add it
        if [[ $VERIFY_BLAME != "true" ]]; then
            local NEW_VALUE="https://github.com/one-thd/$REPO_NAME/tree/\$ID"
            # Update the setting
            local JSON_OBJ=$(jq --arg value "$NEW_VALUE" '.settings."git-blame.gitWebUrl" = "\($value)"' "$WORKSPACE")
            if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                ws_error "\njq parsing error\n"
                return 1
            else
                ws_info "updating .settings.\"git-blame.gitWebUrl\" in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi

        local PROPS=$(cat "$WS_CONFIG_HOME/src/resources/props.json" | sed "s|\$PWD|$PWD|g")
        while read -r PROP; do
            # check if settings.$PROP: [] exists
            local VERIFY_PROP=$(echo "$CONTENT" | jq 'has("settings") and (.settings | has($PROP) and (.settings[$PROP] | length == 0))' --arg PROP "$PROP")
            if [ $? -ne 0 ] | [ -z "$VERIFY_PROP" ]; then
                ws_error "\njq parsing error\n"
                return 1
            fi
            # If settings.$PROP: [] does not exist, add it
            if [[ $VERIFY_PROP != "true" ]]; then
                local NEW_VALUE=$(echo "$PROPS" | jq -r '.[$PROP]' --arg PROP "$PROP")
                # Update the setting
                if [[ "$NEW_VALUE" =~ ^([0-9]+(\.[0-9]+)?$|\{|\\[) ]]; then
                    local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" --arg PROP "$PROP" '.settings[$PROP] += $value' "$WORKSPACE")
                else
                    local JSON_OBJ=$(jq --arg value "$NEW_VALUE" --arg PROP "$PROP" '.settings[$PROP] = $value' "$WORKSPACE")
                fi
                if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                    ws_error "\njq parsing error\n"
                    return 1
                else
                    ws_info "updating .settings[\"$PROP\"] in $WORKSPACE"
                    echo "$JSON_OBJ" >"$WORKSPACE"
                fi
            fi
        done < <(echo "$PROPS" | jq -r 'keys[]')

        # check if settings.logViewer.watch: [] exists
        local VERIFY_WATCH=$(echo "$CONTENT" | jq 'has("settings") and (.settings | has("logViewer.watch") and (.settings."logViewer.watch" | length == 0))')
        if [ $? -ne 0 ] | [ -z "$VERIFY_WATCH" ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        # If settings.logViewer.watch: [] does not exist, add it
        if [[ $VERIFY_WATCH != "true" ]]; then
            local NEW_VALUE="[]"
            # Update the setting
            local JSON_OBJ=$(jq --arg value "$NEW_VALUE" '.settings."logViewer.watch" = []' "$WORKSPACE")
            if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                ws_error "\njq parsing error\n"
                return 1
            else
                ws_info "updating .settings.\"logViewer.watch\" in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi

        local WATCHERS=$(cat "$WS_CONFIG_HOME/src/resources/logWatchers.json" | sed "s|\$PWD|$PWD|g")
        while read -r TITLE; do
            local VERIFY_WATCH=$(echo "$CONTENT" | jq '(.settings."logViewer.watch" | length > 0) and any(.settings."logViewer.watch"[]; .title == $TITLE)' --arg TITLE "$TITLE")
            if [ $? -ne 0 ] | [ -z "$VERIFY_WATCH" ]; then
                ws_error "\njq parsing error\n"
                return 1
            fi
            # If `settings.logViewer.watch[X].title: "$TITLE"` does not exist, add it
            if [[ $VERIFY_WATCH != "true" ]]; then
                local NEW_VALUE=$(echo "$WATCHERS" | jq -c '."logViewer.watch"[] | select(.title == $TITLE)' --arg TITLE "$TITLE")
                # Update the setting
                local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" '.settings."logViewer.watch" += [$value]' "$WORKSPACE")
                if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                    ws_error "\njq parsing error\n"
                    return 1
                else
                    ws_info "updating .settings.\"logViewer.watch[]\" for '$TITLE' in $WORKSPACE"
                    echo "$JSON_OBJ" >"$WORKSPACE"
                fi
            fi
        done < <(echo "$WATCHERS" | jq -r '."logViewer.watch"[].title')

        # check if launch exists
        local VERIFY_LAUNCH=$(echo "$CONTENT" | jq 'has("launch")')
        if [ $? -ne 0 ] | [ -z "$VERIFY_LAUNCH" ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        # If launch does not exist, add it
        if [[ $VERIFY_LAUNCH != "true" ]]; then
            local NEW_VALUE='{"version":"0.2.0","configurations":[]}'
            # Update the setting
            local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" '.launch = $value' "$WORKSPACE")
            if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                ws_error "\njq parsing error\n"
                return 1
            else
                ws_info "updating .launch in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi

        local LAUNCH_CONFIGS=$(cat "$WS_CONFIG_HOME/src/resources/launch.json")
        while read -r NAME; do
            local VERIFY_LAUNCH=$(echo "$CONTENT" | jq '(.launch.configurations | length > 0) and any(.launch.configurations[]; .name == $NAME)' --arg NAME "$NAME")
            if [ $? -ne 0 ] | [ -z "$VERIFY_LAUNCH" ]; then
                ws_error "\njq parsing error\n"
                return 1
            fi
            # If `x.launch.configurations[X].name: "$NAME"` does not exist, add it
            if [[ $VERIFY_LAUNCH != "true" ]]; then
                local NEW_VALUE=$(echo "$LAUNCH_CONFIGS" | jq -c '.launch.configurations[] | select(.name == $NAME)' --arg NAME "$NAME")
                # Update the setting
                local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" '.launch.configurations += [$value]' "$WORKSPACE")
                if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                    ws_error "\njq parsing error\n"
                    return 1
                else
                    ws_info "updating .launch.configurations[] for config '$NAME' in $WORKSPACE"
                    echo "$JSON_OBJ" >"$WORKSPACE"
                fi
            fi
        done < <(echo "$LAUNCH_CONFIGS" | jq -r '.launch.configurations[].name')

        # check if tasks exists
        local VERIFY_TASKS=$(echo "$CONTENT" | jq 'has("tasks")')
        if [ $? -ne 0 ] | [ -z "$VERIFY_TASKS" ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        # If tasks does not exist, add it
        if [[ $VERIFY_TASKS != "true" ]]; then
            local NEW_VALUE='{"version":"2.0.0","tasks":[]}'
            # Update the setting
            local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" '.tasks = $value' "$WORKSPACE")
            if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                ws_error "\njq parsing error\n"
                return 1
            else
                ws_info "updating .tasks in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi

        local TASKS=$(cat "$WS_CONFIG_HOME/src/resources/tasks.json")
        while read -r LABEL; do
            local VERIFY_TASK=$(echo "$CONTENT" | jq '(.tasks.tasks | length > 0) and any(.tasks.tasks[]; .label == $LABEL)' --arg LABEL "$LABEL")
            if [ $? -ne 0 ] | [ -z "$VERIFY_TASK" ]; then
                ws_error "\njq parsing error\n"
                return 1
            fi
            # If `x.tasks.tasks[X].label: "$TASK_BUILD"` does not exist, add it
            if [[ $VERIFY_TASK != "true" ]]; then
                local NEW_VALUE=$(echo "$TASKS" | jq -c '.tasks.tasks[] | select(.label == $LABEL)' --arg LABEL "$LABEL")
                # Update the setting
                local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" '.tasks.tasks += [$value]' "$WORKSPACE")
                if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                    ws_error "\njq parsing error\n"
                    return 1
                else
                    ws_info "updating .tasks.tasks[] for '$LABEL' in $WORKSPACE"
                    echo "$JSON_OBJ" >"$WORKSPACE"
                fi
            fi
        done < <(echo "$TASKS" | jq -r '.tasks.tasks[].label')
    fi
}
