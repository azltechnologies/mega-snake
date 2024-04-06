set_java(){
    local PARAM_JAVA=$1
        #local PARAM_JAVA=11.0.22
        #export JAVA_HOME="/Library/Java/JavaVirtualMachines/jdk-11.0.2.jdk/Contents/Home"
    echo "desired java version $PARAM_JAVA"

    # Creating JavaMap
    text=$(/usr/libexec/java_home -V 2>&1)
    VERSIONS_JAVA=$(echo "$text" | /Users/carlosmorales/IdeaProjects/stuff/parse_java_versions.py)
    local VERSIONS_JAVA=("${(f)VERSIONS_JAVA}")
    declare -A JAVA_MAP
    local JAVA_KEYS=()
    for version in "${VERSIONS_JAVA[@]}"; do
        local key=$(echo $version | grep -oE '[0-9\._]+\:' | grep -oE '[0-9\._]+' || true)
        local value=$(echo $version | grep -oE ':.+$' | grep -oE '[^:].+$' || true)
        JAVA_MAP[$key]="$value"
        JAVA_KEYS+=("$key")
    done
    #            for key in "${(@k)JAVA_MAP}"; do
    #                echo "$key:${JAVA_MAP[$key]}"
    #            done

    local JAVA_VERSION=$(java -version  2>&1 | grep -oE '"[0-9\.\_]+\"' | grep -oE '[0-9\.\_]+' )
    echo "current java version: $JAVA_VERSION"

    JAVA_KEYS="${(j:\n:)JAVA_KEYS}"
    local JAVA_MATCHES=$(echo "$JAVA_KEYS" | grep -cE "^$PARAM_JAVA" || true)
    if [ "$JAVA_MATCHES" -eq 1 ]; then
        local JAVA_NEW=$(echo "$JAVA_KEYS" | grep -E "^$PARAM_JAVA" || true)
        if [ "$JAVA_NEW" = "$JAVA_VERSION" ]; then
            echo "java version already set"
            return 0
        fi
        export JAVA_HOME=`/usr/libexec/java_home -v $JAVA_NEW`
    elif [ "$JAVA_MATCHES" -gt 1 ]; then
        local JAVA_MATCHES=$(echo "$JAVA_KEYS" | grep -cE "^$PARAM_JAVA$" || true)
        if [ "$JAVA_MATCHES" -ne 1 ]; then
            echo "multiple available versions match with $PARAM_JAVA, please be more specific"
            echo "available versions:"
            /usr/libexec/java_home -V 2>&1
            return 1
        fi
        local JAVA_MATCH=$(echo "$JAVA_KEYS" | grep -E "^$PARAM_JAVA$" || true)
        if [ "$JAVA_MATCH" = "$JAVA_VERSION" ]; then
            echo "java version already set"
            return 0
        fi
        local JAVA_NEW=$JAVA_MAP[$PARAM_JAVA]

        export JAVA_HOME="$JAVA_NEW"
    elif [ "$JAVA_MATCHES" -lt 1 ]; then
        echo "no java version found that matches with $PARAM_JAVA, please verify the desired java version"
        echo "available versions:"
        /usr/libexec/java_home -V 2>&1
        return 1
    else
        echo "unexpected error"
        return 1
    fi
    local JAVA_VERSION=$(java -version  2>&1 | grep -oE '"[0-9\.\_]+\"' | grep -oE '[0-9\.\_]+' )
    echo "Now using java version: $JAVA_VERSION"
}
versions_java(){
    /usr/libexec/java_home -V 2>&1
}