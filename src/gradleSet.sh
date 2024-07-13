versions_gradle(){
    local RESULT=""
    local FIRSTCYCLE="N"
    for EDITION in ${(f)"$(brew ls --versions | grep 'gradle')"}; do
        local version=$(echo $EDITION | grep -oE '^\S+')
        local key=$(echo $EDITION | grep -oE '\S+$')            
        local delimiter=" | "
        local text=$(printf "%-13s${delimiter}%-7s\n" "$version" "$key")
        if [ "$FIRSTCYCLE" = "N" ]; then
            RESULT="$text"
            FIRSTCYCLE="Y"
        else
            RESULT="$(echo "$RESULT\n$text")"
        fi
    done
    ws_info "$RESULT"
}
ws_advice "use versions_gradle to check all the gradle versions available"
set_gradle(){
    {
        function versionError(){
            ws_error $1
            ws_warning "available versions:"
            # Removing ANSI escape codes with sed
            VERS=$(versions_gradle | sed 's/\x1b\[[0-9;]*m//g')
            ws_warning $VERS
            return 1
        }
        function removingGradle(){   
            local VER=$1
            local NAME=$2
            if [ ! -z "$VER" ]; then
                ws_info "removing current gradle version $NAME"
                brew unlink $NAME
                if [ $? -ne 0 ]; then
                    versionError "Failure at removing current gradle version: $VER." || return 1
                    return 1
                fi
            fi
        }
        local PARAM_GRADLE=$1
        if [ -z "$PARAM_GRADLE" ]; then
            ws_error "desired gradle version not specified"
            return 1
        fi
        ws_info "desired gradle version $PARAM_GRADLE"
        local GRADLE_VERSION=$(gradle -v 2>/dev/null | grep Gradle | grep -oE ' [0-9\.]+' | grep -oE '[0-9\.]+' || true)
        ws_info "current gradle version: $GRADLE_VERSION"
        declare -A GRADLE_MAP
        local GRADLE_KEYS=()
        local GRADLE_VALUES=()

        for EDITION in ${(f)"$(brew ls --versions | grep 'gradle')"}; do
            local version=$(echo $EDITION | grep -oE '^\S+')
            local key=$(echo $EDITION | grep -oE '\S+$')
            GRADLE_MAP[$key]=$version
            GRADLE_KEYS+=("$key")
            GRADLE_VALUES+=("$key $version")
        done
            #for key in "${(@k)GRADLE_MAP}"; do
            #   echo "$key:${GRADLE_MAP[$key]}"
            #done
        GRADLE_VERSION_NAME=${GRADLE_MAP[$GRADLE_VERSION]}
        local IS_GRADLE_SET=$(echo $GRADLE_VERSION_NAME | grep -cE "^$PARAM_GRADLE$" || true)

        if [ "$IS_GRADLE_SET" -gt 0 ]; then
            ws_success "gradle version already set"
        else
            GRADLE_VALUES="${(j:\n:)GRADLE_VALUES}"
            local GRADLE_MATCHES=$(echo "$GRADLE_VALUES" | grep -cE "^$PARAM_GRADLE" || true)
            if [ "$GRADLE_MATCHES" -eq 1 ]; then
                local GRADLE_NEW=$(echo "$GRADLE_VALUES" | grep -E "^$PARAM_GRADLE" | grep -oE '\S+$' || true)
                if [ "$GRADLE_NEW" = "$GRADLE_VERSION_NAME" ]; then
                    ws_success "gradle version already set"
                    return 0
                fi
                removingGradle $GRADLE_VERSION $GRADLE_VERSION_NAME || return 1
                brew link $GRADLE_NEW
            elif [ "$GRADLE_MATCHES" -gt 1 ]; then
                local GRADLE_MATCHES=$(echo "$GRADLE_VALUES" | grep -oE "^\S" | grep -cE "^$PARAM_GRADLE$" || true)
                if [ "$GRADLE_MATCHES" -ne 1 ]; then
                    versionError "multiple available versions match with $PARAM_GRADLE, please be more specific" || return 1
                    return 1
                fi
                local GRADLE_NEW=$(echo "$GRADLE_VALUES" | grep -E "^\S" | grep -E "^$PARAM_GRADLE$"  | grep -oE "\S+$" || true)
                if [ "$GRADLE_NEW" = "$GRADLE_VERSION_NAME" ]; then
                    ws_success "gradle version already set"
                    return 0
                fi
                removingGradle $GRADLE_VERSION $GRADLE_VERSION_NAME || return 1
                brew link $GRADLE_NEW
            elif [ "$GRADLE_MATCHES" -lt 1 ]; then
                versionError "no gradle version found that matches with $PARAM_GRADLE, please verify the desired gradle version" || return 1
                return 1
            fi
            local GRADLE_VERSION=$(gradle -v 2>/dev/null | grep Gradle | grep -oE ' [0-9\.]+' | grep -oE '[0-9\.]+' || true)
            ws_success "Now using gradle version: $GRADLE_VERSION"
        fi
    } always {
        unfunction -m "removingGradle"
    }
}

