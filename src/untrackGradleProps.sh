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
        echo "\n*.code-workspace" >>"$EXCLUDE"
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
        # check if settings.jarFilePath exists
        local VERIFY_JAR=$(echo "$CONTENT" | jq 'has("settings") and (.settings | has("jarFilePath"))')
        if [ $? -ne 0 ] | [ -z "$VERIFY_JAR" ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        # If settings.jarFilePath does not exist, add it
        if [[ $VERIFY_JAR != "true" ]]; then
            local NEW_VALUE="build/libs/*.jar"
            # Update the setting
            local JSON_OBJ=$(jq --arg value "$NEW_VALUE" '.settings."jarFilePath" = "\($value)"' "$WORKSPACE")
            if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                ws_error "\njq parsing error\n"
                return 1
            else
                ws_info "updating .settings.\"jarFilePath\" in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi
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

        local CONFIG_NAME="Debug Java App (Attach)"
        # check if x.launch.configurations[] array is not empty and if `x.launch.configurations[X].name: "$CONFIG_NAME"` exists
        local VERIFY_LAUNCH=$(echo "$CONTENT" | jq '(.launch.configurations | length > 0) and (.launch.configurations[] | has("name") and .name == $CONFIG_NAME)' --arg CONFIG_NAME "$CONFIG_NAME")
        if [ $? -ne 0 ] | [ -z "$VERIFY_LAUNCH" ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        # If `x.launch.configurations[X].name: "$CONFIG_NAME"` does not exist, add it
        if [[ $VERIFY_LAUNCH != "true" ]]; then
            local NEW_VALUE="{\"type\":\"java\",\"name\":\"$CONFIG_NAME\",\"request\":\"attach\",\"hostName\":\"localhost\",\"port\":5005}"
            # Update the setting
            local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" '.launch.configurations += [$value]' "$WORKSPACE")
            if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                ws_error "\njq parsing error\n"
                return 1
            else
                ws_info "updating .launch.configurations[] in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi

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

        local TASK_BUILD="Gradle Clean Build"
        # check if x.tasks.tasks[] array is not empty and if `x.tasks.tasks[X].label: "$TASK_BUILD"` exists
        local VERIFY_TASK=$(echo "$CONTENT" | jq '(.tasks.tasks | length > 0) and (.tasks.tasks[] | has("label") and .label == $TASK_BUILD)' --arg TASK_BUILD "$TASK_BUILD")
        if [ $? -ne 0 ] | [ -z "$VERIFY_TASK" ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        # If `x.tasks.tasks[X].label: "$TASK_BUILD"` does not exist, add it
        if [[ $VERIFY_TASK != "true" ]]; then
            local NEW_VALUE="{\"label\":\"$TASK_BUILD\",\"type\":\"shell\",\"command\":\"./gradlew\",\"args\":[\"clean\",\"build\",\"-x\",\"test\"],\"group\":\"build\",\"problemMatcher\":[],\"detail\":\"Runs the gradle clean build task\"}"
            # Update the setting
            local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" '.tasks.tasks += [$value]' "$WORKSPACE")
            if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                ws_error "\njq parsing error\n"
                return 1
            else
                ws_info "updating .tasks.tasks[] in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi

        local TASK_TEST="Run Java App with Debugger"
        # check if x.tasks.tasks[] array is not empty and if `x.tasks.tasks[X].label: "$TASK_TEST"` exists
        local VERIFY_TASK=$(echo "$CONTENT" | jq '(.tasks.tasks | length > 0) and (.tasks.tasks[] | has("label") and .label == $TASK_TEST)' --arg TASK_TEST "$TASK_TEST")
        if [ $? -ne 0 ] | [ -z "$VERIFY_TASK" ]; then
            ws_error "\njq parsing error\n"
            return 1
        fi
        # If `x.tasks.tasks[X].label: "$TASK_TEST"` does not exist, add it
        if [[ $VERIFY_TASK != "true" ]]; then
            local NEW_VALUE="{\"label\":\"$TASK_TEST\",\"type\":\"shell\",\"command\":\"java\",\"args\":[\"-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005\",\"-Dspring.profiles.active=stage\",\"-Dspring.config.additional-location=workspace_temp/secrets/stage/applicationSecrets.yml\",\"-jar\",\"\${config:jarFilePath}\"],\"problemMatcher\":[],\"isBackground\":false,\"group\":{\"kind\":\"build\",\"isDefault\":true}}"
            # Update the setting
            local JSON_OBJ=$(jq --argjson value "$NEW_VALUE" '.tasks.tasks += [$value]' "$WORKSPACE")
            if [ $? -ne 0 ] | [ -z "$JSON_OBJ" ]; then
                ws_error "\njq parsing error\n"
                return 1
            else
                ws_info "updating .tasks.tasks[] in $WORKSPACE"
                echo "$JSON_OBJ" >"$WORKSPACE"
            fi
        fi
    fi
}
