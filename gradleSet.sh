set_gradle(){
    local PARAM_GRADLE=$1
    echo "desired gradle version $PARAM_GRADLE"
        local TEMP=$(gradle -v 2>/dev/null | grep Gradle | grep -oE ' [0-9\.]+' | grep -oE '[0-9\.]+' || true)
    if [ ! -z "$TEMP" ]; then
        until [ ! -z "$GRADLE_VERSION" ]; do
            for FORMULA in $(brew list | grep gradle ); do
                if [ "$FORMULA" = "gradle" ]; then
                    local VER_FORMULA=8
                else
                    local VER_FORMULA=$(echo $FORMULA | grep -oE "@[0-9\.]+"| grep -oE "[0-9]+(\.[0-9]+)?")
                fi
                IS_GRADLE_VER=$(echo $TEMP | grep -cE "^$VER_FORMULA$" || true)
                if [ "$IS_GRADLE_VER" -gt 0 ]; then
                    local GRADLE_VERSION=$TEMP
                    break;
                fi
            done
            local TEMP=${TEMP%?}
        done
    fi
    echo "current gradle version: $GRADLE_VERSION"

     if [ -z "$PARAM_GRADLE" ]; then
        echo "gradle version not set"
        return 1
    fi
    local IS_GRADLE_SET=$(echo $GRADLE_VERSION | grep -cE "^$PARAM_GRADLE$" || true)

    if [ "$IS_GRADLE_SET" -gt 0 ]; then
        echo "gradle version already set"
    else

        declare -A GRADLE_MAP

        GRADLE_MAP["$(brew info gradle | grep -oE 'stable [0-9]*\.' | grep -oE ' [0-9]*\.' | grep -oE '[0-9]*')"]="gradle"
        for FORMULA in $(brew list | grep gradle@ ); do
            GRADLE_MAP["$(echo $FORMULA | grep -oE "@[0-9\.]+"| grep -oE "[0-9]+(\.[0-9]+)?")"]=$FORMULA
        done

        #for key in "${(@k)GRADLE_MAP}"; do
        #   echo "$key:${GRADLE_MAP[$key]}"
        #done
        if [ ! -z "$GRADLE_VERSION" ]; then
            echo "removing current gradle version ${GRADLE_MAP["$GRADLE_VERSION"]}"
            brew unlink ${GRADLE_MAP["$GRADLE_VERSION"]}
        fi

        brew link ${GRADLE_MAP["$PARAM_GRADLE"]}
        local GRADLE_VERSION=$(gradle -v 2>/dev/null | grep Gradle | grep -oE ' [0-9\.]+' | grep -oE '[0-9\.]+' || true)
        echo "Now using gradle version: $GRADLE_VERSION"
    fi
}